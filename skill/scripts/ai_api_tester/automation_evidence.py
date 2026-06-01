"""Export AI API Tester reports as Agentic QA Gate automation evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
DEFAULT_TRIGGERED_BY = "agentic_qa_gate"
DEFAULT_SOURCE_TOOL = "ai-api-tester"

DIMENSION_RISK_TAG_MAP = {
    "functional_positive": "test_coverage_gap",
    "functional_negative": "business_logic_change",
    "boundary_value": "business_logic_change",
    "security_auth": "auth_related_change",
    "security_injection": "auth_related_change",
    "idempotency": "duplicate_side_effect_risk",
    "state_machine": "status_logic_change",
    "data_consistency": "local_external_consistency_risk",
    "compliance": "sensitive_export_risk",
}

DIMENSION_DOMAIN_MAP = {
    "functional_positive": ["test_coverage_risk"],
    "functional_negative": ["financial_risk"],
    "boundary_value": ["financial_risk"],
    "security_auth": ["auth_risk"],
    "security_injection": ["auth_risk"],
    "idempotency": ["idempotency_risk", "external_side_effect_risk"],
    "state_machine": ["workflow_state_risk"],
    "data_consistency": ["workflow_state_risk", "external_side_effect_risk", "auditability_risk"],
    "compliance": ["data_export_risk", "auditability_risk"],
}

DOMAIN_ORDER = [
    "auth_risk",
    "financial_risk",
    "data_export_risk",
    "workflow_state_risk",
    "external_side_effect_risk",
    "auditability_risk",
    "idempotency_risk",
    "test_coverage_risk",
    "documentation_risk",
]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_automation_evidence(
    report: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    *,
    run_id: str | None = None,
    triggered_by: str = DEFAULT_TRIGGERED_BY,
    source_tool: str = DEFAULT_SOURCE_TOOL,
    suite_name: str | None = None,
    risk_domains: list[str] | None = None,
    report_path: str | Path | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Build Agentic QA Gate ``automation_results.json`` from a test report."""

    analysis = analysis or {}
    suite = _build_suite(report, analysis, suite_name=suite_name, report_path=report_path)
    domains = _collect_risk_domains(report, suite, risk_domains or [])
    evidence_notes = list(notes or [])
    evidence_notes.append("Generated from ai-api-tester report.")

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or _default_run_id(report),
        "triggered_by": triggered_by,
        "source_tool": source_tool,
        "risk_domains": domains,
        "suites": [suite],
        "notes": _ordered_unique(evidence_notes),
    }


def _build_suite(
    report: dict[str, Any],
    analysis: dict[str, Any],
    *,
    suite_name: str | None,
    report_path: str | Path | None,
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    cases = list(report.get("cases") or [])
    setup_errors = list(report.get("setup_errors") or [])
    findings_by_id = _findings_by_id(analysis)

    passed_cases = []
    failed_cases = []
    skipped_cases = []

    for index, case in enumerate(cases, start=1):
        status = _normalize_case_status(case.get("status"))
        if status == "passed":
            passed_cases.append(_normalize_case(case, index, report_path=report_path))
        elif status == "skipped":
            skipped_cases.append(_normalize_case(case, index, report_path=report_path))
        else:
            failed_cases.append(
                _normalize_failed_case(
                    case,
                    index,
                    findings_by_id,
                    report_path=report_path,
                )
            )

    for index, setup_error in enumerate(setup_errors, start=1):
        failed_cases.append(
            _normalize_setup_error(
                setup_error,
                index,
                findings_by_id,
                report_path=report_path,
            )
        )

    cases_total = _int_value(summary.get("total"), len(cases) + len(setup_errors))
    cases_failed = _int_value(
        summary.get("failed"),
        len([case for case in cases if _normalize_case_status(case.get("status")) == "failed"]),
    )
    cases_failed += _int_value(summary.get("errored"), len(setup_errors))
    cases_failed = max(cases_failed, len(failed_cases))
    cases_skipped = _int_value(summary.get("skipped"), len(skipped_cases))

    status = "failed" if failed_cases else "passed"
    if not failed_cases and cases_total and cases_skipped == cases_total:
        status = "skipped"

    return {
        "name": suite_name or _safe_suite_name(report.get("api", "api_validation")),
        "status": status,
        "cases_total": cases_total,
        "cases_failed": cases_failed,
        "cases_skipped": cases_skipped,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "skipped_cases": skipped_cases,
    }


def _normalize_case(case: dict[str, Any], index: int, *, report_path: str | Path | None) -> dict[str, Any]:
    case_id = _case_id(case, index)
    normalized = {
        "case_id": case_id,
        "title": case.get("name") or case_id,
    }

    risk_tag = _risk_tag(case)
    if risk_tag:
        normalized["risk_tag"] = risk_tag

    evidence = _evidence_ref(report_path, case_id)
    if evidence:
        normalized["evidence"] = evidence

    return normalized


def _normalize_failed_case(
    case: dict[str, Any],
    index: int,
    findings_by_id: dict[str, dict[str, Any]],
    *,
    report_path: str | Path | None,
) -> dict[str, Any]:
    normalized = _normalize_case(case, index, report_path=report_path)
    finding = findings_by_id.get(normalized["case_id"])
    normalized["classification"] = _classification(case, finding)

    reason = _failure_reason(case, finding)
    if reason:
        normalized["reason"] = reason

    return normalized


def _normalize_setup_error(
    setup_error: dict[str, Any],
    index: int,
    findings_by_id: dict[str, dict[str, Any]],
    *,
    report_path: str | Path | None,
) -> dict[str, Any]:
    case_id = f"setup:{setup_error.get('id') or index}"
    finding = findings_by_id.get(case_id)
    normalized = {
        "case_id": case_id,
        "title": f"setup failed: {setup_error.get('id') or index}",
        "classification": finding.get("classification") if finding else "env_issue",
    }
    reason = finding.get("reason") if finding else setup_error.get("error") or "; ".join(setup_error.get("failures") or [])
    if reason:
        normalized["reason"] = reason

    evidence = _evidence_ref(report_path, case_id)
    if evidence:
        normalized["evidence"] = evidence

    return normalized


def _findings_by_id(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for finding in analysis.get("findings", []) or []:
        finding_id = finding.get("id") or finding.get("case_id")
        if finding_id:
            result[str(finding_id)] = finding
    return result


def _classification(case: dict[str, Any], finding: dict[str, Any] | None) -> str:
    if finding and finding.get("classification"):
        return finding["classification"]

    status = _normalize_case_status(case.get("status"))
    if status == "failed" and str(case.get("status", "")).lower() == "error":
        error = str(case.get("error") or "").lower()
        if any(token in error for token in ("timeout", "connection", "dns", "refused", "连接", "超时")):
            return "env_issue"
        return "test_issue"

    dimension = case.get("dimension")
    if dimension in {"security_auth", "security_injection", "idempotency", "state_machine", "data_consistency", "compliance"}:
        return "probable_bug"
    if case.get("failures"):
        return "probable_bug"
    return "test_issue"


def _failure_reason(case: dict[str, Any], finding: dict[str, Any] | None) -> str:
    if finding and finding.get("reason"):
        return str(finding["reason"])
    if case.get("error"):
        return str(case["error"])
    failures = case.get("failures") or []
    return "; ".join(str(item) for item in failures)


def _normalize_case_status(status: Any) -> str:
    value = str(status or "").lower()
    if value in {"pass", "passed", "success", "ok"}:
        return "passed"
    if value in {"skip", "skipped", "ignored"}:
        return "skipped"
    return "failed"


def _risk_tag(case: dict[str, Any]) -> str:
    return case.get("risk_tag") or DIMENSION_RISK_TAG_MAP.get(case.get("dimension"), "")


def _collect_risk_domains(report: dict[str, Any], suite: dict[str, Any], explicit_domains: list[str]) -> list[str]:
    domains = list(explicit_domains)
    for dimension in report.get("dimensions_covered") or []:
        domains.extend(DIMENSION_DOMAIN_MAP.get(dimension, []))
    for key in ("passed_cases", "failed_cases", "skipped_cases"):
        for case in suite.get(key, []) or []:
            risk_tag = case.get("risk_tag")
            domains.extend(_domains_from_risk_tag(risk_tag))
    return _sort_domains(domains)


def _domains_from_risk_tag(risk_tag: str | None) -> list[str]:
    if not risk_tag:
        return []
    for dimension, mapped_tag in DIMENSION_RISK_TAG_MAP.items():
        if risk_tag == mapped_tag:
            return DIMENSION_DOMAIN_MAP.get(dimension, [])
    return []


def _case_id(case: dict[str, Any], index: int) -> str:
    return str(case.get("id") or case.get("case_id") or f"case_{index:03d}")


def _evidence_ref(report_path: str | Path | None, case_id: str) -> str:
    if not report_path:
        return ""
    return f"{Path(report_path).as_posix()}#cases/{case_id}"


def _safe_suite_name(api: str) -> str:
    lowered = str(api or "api_validation").strip().lower()
    safe = "".join(char if char.isalnum() else "_" for char in lowered)
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "api_validation"


def _default_run_id(report: dict[str, Any]) -> str:
    prefix = _safe_suite_name(report.get("api", "api_validation"))
    date = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    return f"{prefix}_{date}"


def _int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _ordered_unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _sort_domains(domains: list[str]) -> list[str]:
    order = {domain: index for index, domain in enumerate(DOMAIN_ORDER)}
    return sorted(_ordered_unique(domains), key=lambda domain: order.get(domain, len(order)))
