"""
测试执行引擎：读取 YAML 用例 → 发 HTTP → 断言 → 报告
"""

from __future__ import annotations

import time
import json
import re
import os
import warnings
from dataclasses import dataclass, field
from typing import Any
from .assertion import AssertionEngine


@dataclass
class CaseResult:
    case_id: str
    name: str
    dimension: str
    priority: str
    status: str = "error"          # pass, fail, skip, error
    duration_ms: int = 0
    request_summary: str = ""
    response_status: int = 0
    response_body: Any = None
    response_headers: dict = field(default_factory=dict)
    request: dict = field(default_factory=dict)
    extracted_variables: dict = field(default_factory=dict)
    teardown_errors: list = field(default_factory=list)
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
    setup_errors: list = field(default_factory=list)


class TestEngine:
    def __init__(self, env: dict = None):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")
            import requests

        self.env = env or {}
        self.variables = {}   # 存储 setup 和运行时提取的变量
        self.requests = requests
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
            ok, setup_error = self._run_setup(step)
            if not ok:
                if setup_error:
                    result.setup_errors.append(setup_error)
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

    def _run_setup(self, step: dict) -> tuple[bool, dict]:
        step_id = step.get("id", "setup")
        action = step.get("action", "http")

        if action == "http":
            req = step.get("request", {})
            try:
                start = time.time()
                resp = self._send_request(req)
                duration_ms = int((time.time() - start) * 1000)
                body = self._parse_body(resp)

                expects = step.get("expect")
                if expects:
                    ok, failures = self._assert_response(
                        resp.status_code,
                        body,
                        dict(resp.headers),
                        duration_ms,
                        expects,
                        status_required=False,
                    )
                    if not ok:
                        print(f"  ❌ Setup [{step_id}] assertion failed: {'; '.join(failures)}")
                        return False, {
                            "id": step_id,
                            "type": "assertion_failed",
                            "request": self._prepare_request(req),
                            "response_status": resp.status_code,
                            "response_headers": dict(resp.headers),
                            "response_body": body,
                            "failures": failures,
                        }
                elif resp.status_code >= 400:
                    print(f"  ❌ Setup [{step_id}] failed: HTTP {resp.status_code}")
                    return False, {
                        "id": step_id,
                        "type": "http_error",
                        "request": self._prepare_request(req),
                        "response_status": resp.status_code,
                        "response_headers": dict(resp.headers),
                        "response_body": body,
                        "failures": [f"HTTP {resp.status_code}"],
                    }

                # 提取变量
                extracts = step.get("extract", {})
                for var_name, json_path in extracts.items():
                    value = self._extract_jsonpath(body, json_path)
                    self.variables[f"setup.{step_id}.{var_name}"] = value
                    self.variables[var_name] = value

                print(f"  ✅ Setup [{step_id}] OK")
                return True, {}
            except Exception as e:
                print(f"  ❌ Setup [{step_id}] error: {e}")
                return False, {
                    "id": step_id,
                    "type": "exception",
                    "request": self._prepare_request(req),
                    "error": str(e),
                }

        elif action == "skill":
            # 预留：联动造数 Skill
            print(f"  ⏭️ Setup [{step_id}] skill action (not implemented)")
            return True, {}

        return True, {}

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
            result.response_headers = dict(responses[-1].headers)
            result.request = self._prepare_request(req)
            result.request_summary = f"{result.request.get('method', 'GET')} {result.request.get('url', '')}"
            self._store_response_paths(result.response_body)

            # 提取当前 case 变量，供后续 case 或 teardown 使用
            extracts = case.get("extract", {})
            for var_name, json_path in extracts.items():
                value = self._extract_jsonpath(result.response_body, json_path)
                self.variables[f"case.{case_id}.{var_name}"] = value
                self.variables[var_name] = value
                result.extracted_variables[var_name] = value

            # 幂等性检查
            if repeat > 1 and expects.get("all_responses_identical"):
                bodies = [self._parse_body(r) for r in responses]
                if not all(json.dumps(b, sort_keys=True) == json.dumps(bodies[0], sort_keys=True) for b in bodies):
                    result.status = "fail"
                    result.failures.append("幂等性失败：多次请求返回不同结果")
                    return result

            all_pass, failures = self._assert_response(
                responses[-1].status_code,
                result.response_body,
                result.response_headers,
                result.duration_ms,
                expects,
            )

            if all_pass:
                result.status = "pass"
            else:
                result.status = "fail"
                result.failures = failures

            # 执行 teardown
            teardown = case.get("teardown", [])
            for td in teardown:
                try:
                    td_req = td.get("request", {})
                    self._send_request(td_req)
                except Exception as e:
                    result.teardown_errors.append(str(e))

        except Exception as e:
            if self._is_timeout(e):
                result.status = "error"
                result.error_message = "请求超时"
            elif self._is_connection_error(e):
                result.status = "error"
                result.error_message = "连接失败"
            else:
                result.status = "error"
                result.error_message = str(e)

        return result

    def _is_timeout(self, error: Exception) -> bool:
        return isinstance(error, getattr(self.requests, "Timeout", ())) or error.__class__.__name__ == "Timeout"

    def _is_connection_error(self, error: Exception) -> bool:
        return isinstance(error, getattr(self.requests, "ConnectionError", ())) or error.__class__.__name__ == "ConnectionError"

    def _send_request(self, req: dict) -> requests.Response:
        prepared = self._prepare_request(req)
        method = prepared["method"]
        url = prepared["url"]
        headers = prepared.get("headers", {})
        params = prepared.get("params", {})
        body = prepared.get("body")
        timeout = prepared.get("timeout", 30)

        if method == "GET":
            return self.session.get(url, params=params, headers=headers, timeout=timeout)
        elif method == "POST":
            return self.session.post(url, params=params, json=body, headers=headers, timeout=timeout)
        elif method == "PUT":
            return self.session.put(url, params=params, json=body, headers=headers, timeout=timeout)
        elif method == "DELETE":
            return self.session.delete(url, params=params, headers=headers, timeout=timeout)
        elif method == "PATCH":
            return self.session.patch(url, params=params, json=body, headers=headers, timeout=timeout)
        else:
            return self.session.request(method, url, params=params, json=body, headers=headers, timeout=timeout)

    def _prepare_request(self, req: dict) -> dict:
        prepared = {
            "method": req.get("method", "GET").upper(),
            "url": self._resolve_variable(req.get("url", "")),
            "headers": self._resolve_dict(req.get("headers", {})),
            "params": self._resolve_dict(req.get("params", req.get("query", {}))),
            "timeout": req.get("timeout", 30),
        }

        body = req.get("body")
        if isinstance(body, dict):
            prepared["body"] = self._resolve_dict(body)
        elif isinstance(body, str):
            prepared["body"] = self._resolve_variable(body)
        elif body is not None:
            prepared["body"] = body

        return prepared

    def _assert_response(
        self,
        status_code: int,
        body: Any,
        headers: dict,
        duration_ms: int,
        expects: dict,
        status_required: bool = True,
    ) -> tuple[bool, list]:
        asserter = AssertionEngine()
        all_pass = True

        if "status" in expects:
            expected_status = expects.get("status")
            if isinstance(expected_status, str) and expected_status.startswith("@"):
                all_pass &= asserter._check_assertion("status", expected_status, status_code)
            else:
                all_pass &= asserter.assert_status(status_code, expected_status)
        elif status_required:
            asserter.results.append("missing status assertion")
            all_pass = False

        body_expects = expects.get("body")
        if body_expects and isinstance(body_expects, dict):
            all_pass &= asserter.assert_body(body, body_expects)

        header_expects = expects.get("headers")
        if header_expects and isinstance(header_expects, dict):
            all_pass &= asserter.assert_headers(headers, header_expects)

        response_time_limit = expects.get("response_time_ms_lt")
        if response_time_limit is not None:
            all_pass &= asserter.assert_response_time(duration_ms, response_time_limit)

        failures = [str(e) for e in asserter.results]
        return all_pass and not failures, failures

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

    def _store_response_paths(self, data: Any, prefix: str = "") -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                self.variables[path] = value
                self._store_response_paths(value, path)
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                path = f"{prefix}.{idx}" if prefix else str(idx)
                self.variables[path] = value
                self._store_response_paths(value, path)
