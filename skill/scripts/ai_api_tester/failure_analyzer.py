"""Classify test failures from AI API Tester JSON reports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


CLASS_ENV = "env_issue"
CLASS_TEST = "test_issue"
CLASS_BUG = "probable_bug"

CLASS_LABELS = {
    CLASS_ENV: "环境问题",
    CLASS_TEST: "用例问题",
    CLASS_BUG: "疑似代码缺陷",
}

REASON_ZH = {
    "setup request contains unresolved variables": "Setup 请求中存在未解析变量",
    "setup request could not reach the target service": "Setup 请求无法连接目标服务",
    "setup data creation or setup assertion failed": "Setup 造数或断言失败",
    "request contains unresolved variables": "请求中存在未解析变量",
    "request could not reach the target service": "请求无法连接目标服务",
    "test runner raised an execution error": "测试执行器发生运行错误",
    "assertion likely references a missing or wrong response path": "断言可能引用了缺失或错误的响应路径",
    "security/compliance assertion failed": "安全或合规断言失败",
    "business rule or validation assertion failed": "业务规则或参数校验断言失败",
    "assertion failed but no strong bug signal was found": "断言失败，但缺少明确代码缺陷信号",
    "teardown failed after the case completed": "用例完成后清理步骤失败",
}


def analyze_report(report: dict[str, Any], context: dict[str, Any] | None = None, source_window: int = 5) -> dict[str, Any]:
    context = context or {}
    findings = []

    for setup_error in report.get("setup_errors", []) or []:
        findings.append(_enrich_finding(_analyze_setup_error(setup_error), context, source_window))

    for case in report.get("cases", []) or []:
        if case.get("status") in ("fail", "error"):
            findings.append(_enrich_finding(_analyze_case(case), context, source_window))
        elif case.get("teardown_errors"):
            findings.append(_enrich_finding(_finding(
                item_id=case.get("id", "unknown"),
                name=case.get("name", ""),
                classification=CLASS_TEST,
                severity="P2",
                reason="teardown failed after the case completed",
                evidence=case.get("teardown_errors", []),
                suggestion="Check cleanup endpoint, extracted variables, and test data ownership.",
                source=case.get("source", ""),
            ), context, source_window))

    summary = {CLASS_ENV: 0, CLASS_TEST: 0, CLASS_BUG: 0}
    for finding in findings:
        summary[finding["classification"]] = summary.get(finding["classification"], 0) + 1

    return {
        "api": report.get("api", "unknown"),
        "summary": summary,
        "summary_zh": {CLASS_LABELS.get(key, key): value for key, value in summary.items()},
        "findings": findings,
    }


def _analyze_setup_error(setup_error: dict[str, Any]) -> dict[str, Any]:
    request = setup_error.get("request", {})
    failures = setup_error.get("failures", [])
    body = setup_error.get("response_body")
    status = setup_error.get("response_status", 0)
    error = setup_error.get("error", "")

    if _has_unresolved_variables(request):
        return _finding(
            item_id=f"setup:{setup_error.get('id', 'unknown')}",
            name="setup failed",
            classification=CLASS_ENV,
            severity="P0",
            reason="setup request contains unresolved variables",
            evidence=_evidence(request, failures, error, body),
            suggestion="Provide the missing env/config value or fix the variable name before running tests.",
        )

    if error and _is_connection_error(error):
        return _finding(
            item_id=f"setup:{setup_error.get('id', 'unknown')}",
            name="setup failed",
            classification=CLASS_ENV,
            severity="P0",
            reason="setup request could not reach the target service",
            evidence=_evidence(request, failures, error, body),
            suggestion="Check base_url, network access, service startup, and timeout settings.",
        )

    if status in (401, 403):
        return _finding(
            item_id=f"setup:{setup_error.get('id', 'unknown')}",
            name="setup failed",
            classification=CLASS_ENV,
            severity="P0",
            reason=f"setup was rejected with HTTP {status}",
            evidence=_evidence(request, failures, error, body),
            suggestion="Check auth token, role, and test environment credentials.",
        )

    return _finding(
        item_id=f"setup:{setup_error.get('id', 'unknown')}",
        name="setup failed",
        classification=CLASS_TEST,
        severity="P1",
        reason="setup data creation or setup assertion failed",
        evidence=_evidence(request, failures, error, body),
        suggestion="Verify setup endpoint, required request fields, expected status, and extracted JSON paths.",
    )


def _analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    request = case.get("request", {})
    failures = case.get("failures", []) or []
    error = case.get("error", "")
    status = case.get("response_status", 0)
    body = case.get("response_body")
    dimension = case.get("dimension", "")

    if _has_unresolved_variables(request):
        return _case_finding(case, CLASS_ENV, "P0", "request contains unresolved variables", "Provide missing env/setup/case extracted variables or fix variable references.")

    if case.get("status") == "error":
        if _is_connection_error(error):
            return _case_finding(case, CLASS_ENV, "P0", "request could not reach the target service", "Check base_url, network access, service startup, DNS, and timeout settings.")
        return _case_finding(case, CLASS_ENV, "P1", "test runner raised an execution error", "Inspect the error message and request configuration.")

    if status in (401, 403) and dimension != "security_auth":
        return _case_finding(case, CLASS_ENV, "P0", f"request was rejected with HTTP {status}", "Check auth token, role, account state, and environment credentials.")

    if _extract_issue(failures, body):
        return _case_finding(case, CLASS_TEST, "P1", "assertion likely references a missing or wrong response path", "Check the expected JSON path against the actual response body.")

    if status >= 500:
        return _case_finding(case, CLASS_BUG, _severity(case), f"server returned HTTP {status}", "Inspect the source location and server logs; this likely indicates an unhandled exception or backend defect.")

    if dimension in ("security_auth", "security_injection", "compliance"):
        return _case_finding(case, CLASS_BUG, _severity(case), "security/compliance assertion failed", "Inspect the source location for missing authorization, sanitization, masking, or error handling.")

    if dimension in ("boundary_value", "functional_negative", "state_machine", "idempotency", "data_consistency"):
        return _case_finding(case, CLASS_BUG, _severity(case), "business rule or validation assertion failed", "Compare the source rule with the actual response; fix validation, state handling, or persistence logic if the test expectation matches the source intent.")

    return _case_finding(case, CLASS_TEST, _severity(case), "assertion failed but no strong bug signal was found", "Verify the test data and expected response contract before treating this as a product bug.")


def _case_finding(case: dict[str, Any], classification: str, severity: str, reason: str, suggestion: str) -> dict[str, Any]:
    return _finding(
        item_id=case.get("id", "unknown"),
        name=case.get("name", ""),
        classification=classification,
        severity=severity,
        reason=reason,
        evidence=_evidence(case.get("request", {}), case.get("failures", []), case.get("error", ""), case.get("response_body")),
        suggestion=suggestion,
        source=case.get("source", ""),
        response_status=case.get("response_status", 0),
        dimension=case.get("dimension", ""),
    )


def _finding(
    item_id: str,
    name: str,
    classification: str,
    severity: str,
    reason: str,
    evidence: Any,
    suggestion: str,
    source: str = "",
    response_status: int = 0,
    dimension: str = "",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "classification": classification,
        "classification_zh": CLASS_LABELS.get(classification, classification),
        "severity": severity,
        "reason": reason,
        "reason_zh": _reason_zh(reason),
        "source": source,
        "dimension": dimension,
        "response_status": response_status,
        "evidence": evidence,
        "suggestion": suggestion,
        "suggestion_zh": _suggestion_zh(classification, reason, dimension, response_status),
    }


def _enrich_finding(finding: dict[str, Any], context: dict[str, Any], source_window: int) -> dict[str, Any]:
    finding["source_context"] = _source_context(finding.get("source", ""), source_window, context)
    finding["context_evidence"] = _context_evidence(finding, context)

    refined = _context_aware_suggestion(finding, context)
    if refined:
        finding["suggestion"] = refined["suggestion"]
        finding["suggestion_zh"] = refined["suggestion_zh"]

    return finding


def _source_context(source: str, window: int, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    parsed = _parse_source(source, context or {})
    if not parsed:
        return None

    path, line_no = parsed
    if not path.exists() or not path.is_file():
        return None

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    start = max(1, line_no - window)
    end = min(len(lines), line_no + window)
    return {
        "file": str(path),
        "line": line_no,
        "start_line": start,
        "end_line": end,
        "snippet": [
            {"line": idx, "text": lines[idx - 1]}
            for idx in range(start, end + 1)
        ],
    }


def _parse_source(source: str, context: dict[str, Any]) -> tuple[Path, int] | None:
    if not source:
        return None

    # Accept "file:line -> annotation" and similar suffixes.
    source = source.split("→", 1)[0].split("->", 1)[0].strip()
    match = re.match(r"(.+?):(\d+)", source)
    if not match:
        return None

    raw_path = match.group(1).strip()
    line_no = int(match.group(2))
    path = Path(raw_path)
    if path.exists():
        return path, line_no

    resolved = _resolve_source_from_context(raw_path, context)
    if resolved:
        return resolved, line_no

    return path, line_no


def _resolve_source_from_context(raw_path: str, context: dict[str, Any]) -> Path | None:
    candidates = []

    for code_file in context.get("code_files", []) or []:
        path = code_file.get("path")
        if path:
            candidates.append(Path(path))

    route = (context.get("test_basis", {}) or {}).get("route", {})
    if route.get("file"):
        candidates.append(Path(route["file"]))

    raw_normalized = raw_path.replace("\\", "/")
    raw_name = Path(raw_normalized).name

    for candidate in candidates:
        candidate_text = str(candidate).replace("\\", "/")
        if candidate_text == raw_normalized or candidate_text.endswith("/" + raw_normalized):
            return candidate
        if raw_name and candidate.name == raw_name:
            return candidate

    return None


def _context_evidence(finding: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    test_basis = context.get("test_basis", {}) if isinstance(context, dict) else {}
    dimension = finding.get("dimension", "")
    evidence: dict[str, Any] = {}

    if test_basis.get("route"):
        evidence["route"] = test_basis["route"]

    if dimension in ("functional_negative", "boundary_value"):
        evidence["fields"] = test_basis.get("fields", [])
        evidence["branches"] = test_basis.get("branches", [])
    elif dimension == "security_auth":
        evidence["auth"] = test_basis.get("auth", [])
    elif dimension == "state_machine":
        evidence["state_changes"] = test_basis.get("state_changes", [])
    elif dimension == "compliance":
        evidence["sensitive_fields"] = test_basis.get("sensitive_fields", [])
    elif dimension == "data_consistency":
        evidence["external_calls"] = test_basis.get("external_calls", [])
        evidence["branches"] = test_basis.get("branches", [])

    return evidence


def _context_aware_suggestion(finding: dict[str, Any], context: dict[str, Any]) -> dict[str, str] | None:
    if finding.get("classification") != CLASS_BUG:
        return None

    dimension = finding.get("dimension", "")
    evidence = finding.get("context_evidence", {})

    if dimension == "security_auth" and evidence.get("auth"):
        return {
            "suggestion": "Review the authorization evidence in test_basis.auth and the source snippet; add role/ownership checks at the controller/service boundary if missing.",
            "suggestion_zh": "结合 test_basis.auth 和源码片段检查鉴权链路；如果缺少角色或资源归属校验，应在 Controller/Service 边界补充校验。",
        }
    if dimension in ("functional_negative", "boundary_value") and evidence.get("fields"):
        return {
            "suggestion": "Compare the failed assertion with test_basis.fields constraints; add or fix validation annotations/schema checks and ensure invalid input returns the expected 4xx response.",
            "suggestion_zh": "对照 test_basis.fields 中的字段约束检查失败断言；补充或修正参数校验，并确保非法输入返回预期的 4xx 响应。",
        }
    if dimension == "state_machine" and evidence.get("state_changes"):
        return {
            "suggestion": "Review state transition evidence and reject illegal transitions before persistence.",
            "suggestion_zh": "检查状态流转证据，在落库前拒绝非法状态迁移。",
        }
    if dimension == "compliance" and evidence.get("sensitive_fields"):
        return {
            "suggestion": "Review sensitive field evidence and apply masking or error sanitization before returning the response.",
            "suggestion_zh": "检查敏感字段证据，在响应返回前补充脱敏或异常信息清洗。",
        }
    if finding.get("response_status", 0) >= 500:
        return {
            "suggestion": "Use the source snippet and server logs to find the unhandled exception path; add validation/error handling and return a controlled 4xx/5xx contract.",
            "suggestion_zh": "结合源码片段和服务日志定位未处理异常路径；补充校验或异常处理，并返回受控的 4xx/5xx 契约响应。",
        }
    return None


def _reason_zh(reason: str) -> str:
    if reason.startswith("setup was rejected with HTTP"):
        return reason.replace("setup was rejected with HTTP", "Setup 被拒绝，HTTP")
    if reason.startswith("request was rejected with HTTP"):
        return reason.replace("request was rejected with HTTP", "请求被拒绝，HTTP")
    if reason.startswith("server returned HTTP"):
        return reason.replace("server returned HTTP", "服务端返回 HTTP")
    return REASON_ZH.get(reason, reason)


def _suggestion_zh(classification: str, reason: str, dimension: str, response_status: int) -> str:
    if classification == CLASS_ENV:
        if "unresolved variables" in reason:
            return "补齐缺失的环境变量、env 配置或 setup/case 提取变量，并检查变量名是否一致。"
        if response_status in (401, 403) or "401" in reason or "403" in reason:
            return "检查认证 Token、角色权限、账号状态和测试环境凭据。"
        return "检查 base_url、网络连通性、服务启动状态、DNS 和超时配置。"
    if classification == CLASS_TEST:
        if "response path" in reason:
            return "对照实际响应体修正 YAML 中的 JSON path 或测试数据。"
        return "检查测试数据、setup 步骤、提取变量和预期契约是否正确。"
    if dimension in ("security_auth", "security_injection", "compliance"):
        return "检查源码中的鉴权、输入清洗、脱敏和异常处理逻辑。"
    if response_status >= 500:
        return "结合源码和服务日志定位未处理异常，补充参数校验或异常处理。"
    return "对照 source 位置和 test_basis 证据检查业务规则实现，并修复缺失的校验或状态处理。"


def _has_unresolved_variables(value: Any) -> bool:
    if isinstance(value, str):
        return bool(re.search(r"\{\{.+?\}\}", value))
    if isinstance(value, dict):
        return any(_has_unresolved_variables(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_unresolved_variables(item) for item in value)
    return False


def _is_connection_error(error: str) -> bool:
    error_lower = str(error).lower()
    return any(token in error_lower for token in ("连接失败", "timeout", "timed out", "connection", "dns", "name or service", "refused"))


def _extract_issue(failures: list[Any], body: Any) -> bool:
    joined = " ".join(str(item) for item in failures).lower()
    if "got none" in joined or "expected not null, got none" in joined:
        return True
    if body in (None, "", []):
        return True
    return False


def _severity(case: dict[str, Any]) -> str:
    priority = case.get("priority")
    return priority if priority in ("P0", "P1", "P2") else "P1"


def _evidence(request: Any, failures: Any, error: str, body: Any) -> dict[str, Any]:
    return {
        "request": request,
        "failures": failures,
        "error": error,
        "response_body": body,
    }
