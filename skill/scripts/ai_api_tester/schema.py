"""YAML suite validation for AI API Tester."""

from __future__ import annotations

import re
from typing import Any


DIMENSIONS = {
    "functional_positive",
    "functional_negative",
    "boundary_value",
    "security_auth",
    "security_injection",
    "idempotency",
    "state_machine",
    "concurrency",
    "data_consistency",
    "compliance",
}

EXECUTABLE_DIMENSIONS = DIMENSIONS - {"concurrency"}
PRIORITIES = {"P0", "P1", "P2"}

TOP_LEVEL_FIELDS = {"metadata", "env", "setup", "cases"}
METADATA_FIELDS = {
    "api",
    "language",
    "framework",
    "generated_at",
    "risk_score",
    "dimensions_covered",
}
STEP_FIELDS = {"id", "action", "request", "expect", "extract"}
CASE_FIELDS = {
    "id",
    "name",
    "dimension",
    "priority",
    "source",
    "request",
    "expect",
    "extract",
    "teardown",
    "repeat",
}
REQUEST_FIELDS = {"method", "url", "headers", "params", "query", "body", "timeout"}
EXPECT_FIELDS = {
    "status",
    "body",
    "headers",
    "all_responses_identical",
    "response_time_ms_lt",
}
TEARDOWN_FIELDS = {"action", "request"}

HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
BODY_LEVEL_ASSERTIONS = {"@not_contains"}

ASSERTION_PATTERNS = [
    r"@notNull",
    r"@isNull",
    r"@gt\(.+\)",
    r"@gte\(.+\)",
    r"@lt\(.+\)",
    r"@lte\(.+\)",
    r"@in\(\[.*\]\)",
    r"@notEqual\(.+\)",
    r"@contains\(['\"].*['\"]\)",
    r"@not_contains\(['\"].*['\"]\)",
    r"@matches\(.+\)",
    r"@startsWith\(['\"].*['\"]\)",
    r"@endsWith\(['\"].*['\"]\)",
    r"@size\(\d+\)",
    r"@minSize\(\d+\)",
    r"@maxSize\(\d+\)",
    r"@isString",
    r"@isNumber",
    r"@isArray",
]


def validate_suite(suite: Any) -> list[str]:
    """Return validation errors. An empty list means the suite is executable."""
    errors: list[str] = []

    if not isinstance(suite, dict):
        return ["suite must be a YAML object"]

    _check_unknown_fields(suite, TOP_LEVEL_FIELDS, "$", errors)

    metadata = suite.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("$.metadata is required and must be an object")
    else:
        _validate_metadata(metadata, errors)

    env = suite.get("env", {})
    if env is not None and not isinstance(env, dict):
        errors.append("$.env must be an object when present")

    setup = suite.get("setup", [])
    if setup is not None:
        if not isinstance(setup, list):
            errors.append("$.setup must be a list when present")
        else:
            for idx, step in enumerate(setup):
                _validate_step(step, f"$.setup[{idx}]", errors)

    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("$.cases is required and must be a non-empty list")
    else:
        for idx, case in enumerate(cases):
            _validate_case(case, f"$.cases[{idx}]", errors)

    return errors


def _validate_metadata(metadata: dict[str, Any], errors: list[str]) -> None:
    _check_unknown_fields(metadata, METADATA_FIELDS, "$.metadata", errors)

    api = metadata.get("api")
    if not isinstance(api, str) or not api.strip():
        errors.append("$.metadata.api is required and must be a non-empty string")

    covered = metadata.get("dimensions_covered", [])
    if covered is not None:
        if not isinstance(covered, list):
            errors.append("$.metadata.dimensions_covered must be a list")
        else:
            for idx, dimension in enumerate(covered):
                _validate_dimension(dimension, f"$.metadata.dimensions_covered[{idx}]", errors)


def _validate_step(step: Any, path: str, errors: list[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{path} must be an object")
        return

    _check_unknown_fields(step, STEP_FIELDS, path, errors)

    step_id = step.get("id")
    if not isinstance(step_id, str) or not step_id.strip():
        errors.append(f"{path}.id is required and must be a non-empty string")

    action = step.get("action", "http")
    if action != "http":
        errors.append(f"{path}.action only supports 'http'")

    _validate_request(step.get("request"), f"{path}.request", errors)

    expect = step.get("expect")
    if expect is not None:
        _validate_expect(expect, f"{path}.expect", errors, status_required=False)

    extract = step.get("extract", {})
    if extract is not None:
        _validate_extract(extract, f"{path}.extract", errors)


def _validate_case(case: Any, path: str, errors: list[str]) -> None:
    if not isinstance(case, dict):
        errors.append(f"{path} must be an object")
        return

    _check_unknown_fields(case, CASE_FIELDS, path, errors)

    for field in ("id", "name", "source"):
        value = case.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}.{field} is required and must be a non-empty string")

    dimension = case.get("dimension")
    _validate_dimension(dimension, f"{path}.dimension", errors)
    if dimension == "concurrency":
        errors.append(f"{path}.dimension 'concurrency' is not executable yet; mark it skipped in the coverage matrix instead of generating a case")

    priority = case.get("priority")
    if priority not in PRIORITIES:
        errors.append(f"{path}.priority must be one of {sorted(PRIORITIES)}")

    repeat = case.get("repeat", 1)
    if not isinstance(repeat, int) or repeat < 1:
        errors.append(f"{path}.repeat must be a positive integer when present")

    _validate_request(case.get("request"), f"{path}.request", errors)
    _validate_expect(case.get("expect"), f"{path}.expect", errors)

    extract = case.get("extract", {})
    if extract is not None:
        _validate_extract(extract, f"{path}.extract", errors)

    teardown = case.get("teardown", [])
    if teardown is not None:
        if not isinstance(teardown, list):
            errors.append(f"{path}.teardown must be a list when present")
        else:
            for idx, step in enumerate(teardown):
                _validate_teardown(step, f"{path}.teardown[{idx}]", errors)


def _validate_request(request: Any, path: str, errors: list[str]) -> None:
    if not isinstance(request, dict):
        errors.append(f"{path} is required and must be an object")
        return

    _check_unknown_fields(request, REQUEST_FIELDS, path, errors)

    method = request.get("method")
    if not isinstance(method, str) or method.upper() not in HTTP_METHODS:
        errors.append(f"{path}.method is required and must be one of {sorted(HTTP_METHODS)}")

    url = request.get("url")
    if not isinstance(url, str) or not url.strip():
        errors.append(f"{path}.url is required and must be a non-empty string")

    headers = request.get("headers", {})
    if headers is not None and not isinstance(headers, dict):
        errors.append(f"{path}.headers must be an object when present")

    if "params" in request and "query" in request:
        errors.append(f"{path} must not include both params and query; use one")

    params = request.get("params", request.get("query", {}))
    if params is not None and not isinstance(params, dict):
        errors.append(f"{path}.params/query must be an object when present")

    timeout = request.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        errors.append(f"{path}.timeout must be a positive number when present")


def _validate_expect(expect: Any, path: str, errors: list[str], status_required: bool = True) -> None:
    if not isinstance(expect, dict):
        errors.append(f"{path} is required and must be an object")
        return

    _check_unknown_fields(expect, EXPECT_FIELDS, path, errors)

    if status_required and "status" not in expect:
        errors.append(f"{path}.status is required")

    response_time = expect.get("response_time_ms_lt")
    if response_time is not None and (not isinstance(response_time, (int, float)) or response_time <= 0):
        errors.append(f"{path}.response_time_ms_lt must be a positive number when present")

    body = expect.get("body", {})
    if body is not None:
        if not isinstance(body, dict):
            errors.append(f"{path}.body must be an object when present")
        else:
            _validate_assertion_map(body, f"{path}.body", errors)

    headers = expect.get("headers", {})
    if headers is not None:
        if not isinstance(headers, dict):
            errors.append(f"{path}.headers must be an object when present")
        else:
            _validate_assertion_map(headers, f"{path}.headers", errors)


def _validate_teardown(step: Any, path: str, errors: list[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{path} must be an object")
        return

    _check_unknown_fields(step, TEARDOWN_FIELDS, path, errors)

    action = step.get("action", "http")
    if action != "http":
        errors.append(f"{path}.action only supports 'http'")

    _validate_request(step.get("request"), f"{path}.request", errors)


def _validate_extract(extract: Any, path: str, errors: list[str]) -> None:
    if not isinstance(extract, dict):
        errors.append(f"{path} must be an object mapping variable names to JSON paths")
        return

    for key, value in extract.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(f"{path} contains an empty variable name")
        if not isinstance(value, str) or not value.startswith("$."):
            errors.append(f"{path}.{key} must be a JSON path string starting with '$.'")


def _validate_assertion_map(values: dict[str, Any], path: str, errors: list[str]) -> None:
    for key, value in values.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(f"{path} contains an empty assertion key")
            continue
        if key.startswith("@") and key not in BODY_LEVEL_ASSERTIONS:
            errors.append(f"{path}.{key} is not a supported body-level assertion")
        _validate_assertion_value(value, f"{path}.{key}", errors)


def _validate_assertion_value(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str) and value.startswith("@"):
        if not any(re.fullmatch(pattern, value) for pattern in ASSERTION_PATTERNS):
            errors.append(f"{path} uses unsupported assertion {value!r}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _validate_assertion_value(item, f"{path}[{idx}]", errors)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_assertion_value(item, f"{path}.{key}", errors)


def _validate_dimension(value: Any, path: str, errors: list[str]) -> None:
    if value not in DIMENSIONS:
        errors.append(f"{path} must be one of {sorted(DIMENSIONS)}")


def _check_unknown_fields(obj: dict[str, Any], allowed: set[str], path: str, errors: list[str]) -> None:
    for key in obj:
        if key not in allowed:
            errors.append(f"{path}.{key} is not supported")
