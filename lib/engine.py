"""
测试执行引擎：读取 YAML 用例 → 发 HTTP → 断言 → 报告
"""

import time
import json
import re
import os
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from .assertion import AssertionEngine


@dataclass
class CaseResult:
    case_id: str
    name: str
    dimension: str
    priority: str
    status: str          # pass, fail, skip, error
    duration_ms: int = 0
    request_summary: str = ""
    response_status: int = 0
    response_body: Any = None
    failures: list = field(default_factory=list)
    error_message: str = ""
    source: str = ""


@dataclass
class SuiteResult:
    api: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errored: int = 0
    duration_ms: int = 0
    cases: list = field(default_factory=list)
    dimensions_covered: list = field(default_factory=list)


class TestEngine:
    def __init__(self, env: dict = None):
        self.env = env or {}
        self.variables = {}   # 存储 setup 和运行时提取的变量
        self.session = requests.Session()

    def run_suite(self, suite: dict) -> SuiteResult:
        result = SuiteResult(api=suite.get("metadata", {}).get("api", "unknown"))
        result.dimensions_covered = suite.get("metadata", {}).get("dimensions_covered", [])

        # 解析环境变量
        env_config = suite.get("env", {})
        for key, val in env_config.items():
            self.env[key] = self._resolve_variable(val)

        # 执行 setup
        setup_steps = suite.get("setup", [])
        for step in setup_steps:
            if not self._run_setup(step):
                result.errored = result.total = len(suite.get("cases", []))
                return result

        # 执行 cases
        start = time.time()
        cases = suite.get("cases", [])
        result.total = len(cases)

        for case in cases:
            case_result = self._run_case(case)
            result.cases.append(case_result)
            if case_result.status == "pass":
                result.passed += 1
            elif case_result.status == "fail":
                result.failed += 1
            elif case_result.status == "skip":
                result.skipped += 1
            else:
                result.errored += 1

        result.duration_ms = int((time.time() - start) * 1000)
        return result

    def _run_setup(self, step: dict) -> bool:
        step_id = step.get("id", "setup")
        action = step.get("action", "http")

        if action == "http":
            req = step.get("request", {})
            try:
                resp = self._send_request(req)
                if resp.status_code >= 400:
                    print(f"  ❌ Setup [{step_id}] failed: HTTP {resp.status_code}")
                    return False

                # 提取变量
                extracts = step.get("extract", {})
                body = self._parse_body(resp)
                for var_name, json_path in extracts.items():
                    value = self._extract_jsonpath(body, json_path)
                    self.variables[f"setup.{step_id}.{var_name}"] = value
                    self.variables[var_name] = value

                print(f"  ✅ Setup [{step_id}] OK")
                return True
            except Exception as e:
                print(f"  ❌ Setup [{step_id}] error: {e}")
                return False

        elif action == "skill":
            # 预留：联动造数 Skill
            print(f"  ⏭️ Setup [{step_id}] skill action (not implemented)")
            return True

        return True

    def _run_case(self, case: dict) -> CaseResult:
        case_id = case.get("id", "unknown")
        name = case.get("name", "")
        dimension = case.get("dimension", "")
        priority = case.get("priority", "P2")
        source = case.get("source", "")

        result = CaseResult(
            case_id=case_id, name=name, dimension=dimension,
            priority=priority, source=source
        )

        # 处理 repeat（幂等性测试）
        repeat = case.get("repeat", 1)
        # 处理 concurrent（并发测试）
        concurrent = case.get("concurrent", 0)

        if concurrent > 0:
            result.status = "skip"
            result.error_message = "并发测试需要专用执行器（待实现）"
            return result

        req = case.get("request", {})
        expects = case.get("expect", {})

        try:
            start = time.time()
            responses = []

            for i in range(repeat):
                resp = self._send_request(req)
                responses.append(resp)

            result.duration_ms = int((time.time() - start) * 1000)
            result.response_status = responses[-1].status_code
            result.response_body = self._parse_body(responses[-1])
            result.request_summary = f"{req.get('method', 'GET')} {req.get('url', '')}"

            # 幂等性检查
            if repeat > 1 and expects.get("all_responses_identical"):
                bodies = [self._parse_body(r) for r in responses]
                if not all(json.dumps(b, sort_keys=True) == json.dumps(bodies[0], sort_keys=True) for b in bodies):
                    result.status = "fail"
                    result.failures.append("幂等性失败：多次请求返回不同结果")
                    return result

            # 断言
            asserter = AssertionEngine()
            all_pass = True

            # status 断言
            expected_status = expects.get("status")
            if expected_status:
                if isinstance(expected_status, str) and expected_status.startswith("@"):
                    all_pass &= asserter._check_assertion("status", expected_status, responses[-1].status_code)
                else:
                    all_pass &= asserter.assert_status(responses[-1].status_code, expected_status)

            # body 断言
            body_expects = expects.get("body")
            if body_expects and isinstance(body_expects, dict):
                all_pass &= asserter.assert_body(result.response_body, body_expects)

            # headers 断言
            header_expects = expects.get("headers")
            if header_expects and isinstance(header_expects, dict):
                all_pass &= asserter.assert_headers(dict(responses[-1].headers), header_expects)

            if all_pass and not asserter.results:
                result.status = "pass"
            else:
                result.status = "fail"
                result.failures = [str(e) for e in asserter.results]

            # 执行 teardown
            teardown = case.get("teardown", [])
            for td in teardown:
                try:
                    td_req = td.get("request", {})
                    self._send_request(td_req)
                except Exception:
                    pass

        except requests.Timeout:
            result.status = "error"
            result.error_message = "请求超时"
        except requests.ConnectionError:
            result.status = "error"
            result.error_message = "连接失败"
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    def _send_request(self, req: dict) -> requests.Response:
        method = req.get("method", "GET").upper()
        url = self._resolve_variable(req.get("url", ""))
        headers = {}
        for k, v in req.get("headers", {}).items():
            headers[k] = self._resolve_variable(v)

        body = req.get("body")
        if isinstance(body, dict):
            body = self._resolve_dict(body)

        timeout = req.get("timeout", 30)

        if method == "GET":
            return self.session.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            return self.session.post(url, json=body, headers=headers, timeout=timeout)
        elif method == "PUT":
            return self.session.put(url, json=body, headers=headers, timeout=timeout)
        elif method == "DELETE":
            return self.session.delete(url, headers=headers, timeout=timeout)
        elif method == "PATCH":
            return self.session.patch(url, json=body, headers=headers, timeout=timeout)
        else:
            return self.session.request(method, url, json=body, headers=headers, timeout=timeout)

    def _resolve_variable(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        def replacer(match):
            var_path = match.group(1)
            # 先查 ENV
            if var_path.startswith("ENV."):
                env_key = var_path[4:]
                return os.environ.get(env_key, self.env.get(env_key, match.group(0)))
            # 查 env 配置
            if var_path.startswith("env."):
                env_key = var_path[4:]
                return str(self.env.get(env_key, match.group(0)))
            # 查运行时变量
            return str(self.variables.get(var_path, match.group(0)))

        return re.sub(r'\{\{(.+?)\}\}', replacer, value)

    def _resolve_dict(self, d: dict) -> dict:
        result = {}
        for k, v in d.items():
            if isinstance(v, str):
                result[k] = self._resolve_variable(v)
            elif isinstance(v, dict):
                result[k] = self._resolve_dict(v)
            elif isinstance(v, list):
                result[k] = [self._resolve_dict(item) if isinstance(item, dict) else self._resolve_variable(item) if isinstance(item, str) else item for item in v]
            else:
                result[k] = v
        return result

    def _parse_body(self, resp: requests.Response) -> Any:
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return resp.text

    def _extract_jsonpath(self, data: Any, path: str) -> Any:
        if not path.startswith("$."):
            return data
        parts = path[2:].split(".")
        current = data
        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
