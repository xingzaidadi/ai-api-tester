"""Lightweight source-code analysis for API test generation context."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .detector import ProjectInfo
from .locator import CodeContext, CodeFile
from .route_extractor import RouteExtractor


SENSITIVE_NAMES = ("phone", "mobile", "email", "idcard", "id_card", "bankcard", "bank_card", "address", "token")
EXTERNAL_CALL_HINTS = ("FeignClient", "RestTemplate", "WebClient", "httpx.", "requests.", "aiohttp.", "fetch(", "axios.")
AUTH_HINTS = ("@PreAuthorize", "@Secured", "@RolesAllowed", "SecurityContext", "Jwt", "JWT", "Depends(", "current_user", "get_current_user")
STATE_HINTS = ("status", "state", "setStatus", "setState")


class SourceAnalyzer:
    def __init__(self, project_path: str, project_info: ProjectInfo):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info

    def analyze(self, ctx: CodeContext) -> dict[str, Any]:
        routes = RouteExtractor(str(self.project_path), self.project_info).find_matches(ctx.url, ctx.method)
        route = routes[0] if routes else None

        test_basis = {
            "route": _route_to_dict(route),
            "request_models": [],
            "fields": [],
            "auth": [],
            "branches": [],
            "state_changes": [],
            "external_calls": [],
            "sensitive_fields": [],
        }

        if self.project_info.language == "java":
            self._analyze_java(ctx, test_basis)
        elif self.project_info.language == "python":
            self._analyze_python(ctx, test_basis)

        test_basis["request_models"] = _dedupe_dicts(test_basis["request_models"], ("name", "source"))
        test_basis["fields"] = _dedupe_dicts(test_basis["fields"], ("model", "name", "source"))
        test_basis["auth"] = _dedupe_dicts(test_basis["auth"], ("source", "line"))
        test_basis["branches"] = _dedupe_dicts(test_basis["branches"], ("source", "line"))
        test_basis["state_changes"] = _dedupe_dicts(test_basis["state_changes"], ("source", "line"))
        test_basis["external_calls"] = _dedupe_dicts(test_basis["external_calls"], ("source", "line"))
        test_basis["sensitive_fields"] = _dedupe_dicts(test_basis["sensitive_fields"], ("name", "source", "line"))
        return test_basis

    def _analyze_java(self, ctx: CodeContext, test_basis: dict[str, Any]) -> None:
        request_models = self._java_request_models(ctx)
        for model_name, source in request_models.items():
            test_basis["request_models"].append({"name": model_name, "source": source})

        for code_file in ctx.files:
            lines = code_file.content.splitlines()
            self._collect_common_signals(code_file, lines, test_basis)

            if code_file.role == "model" or Path(code_file.path).stem in request_models:
                model_name = Path(code_file.path).stem
                test_basis["fields"].extend(_parse_java_fields(code_file.path, model_name, lines))

    def _java_request_models(self, ctx: CodeContext) -> dict[str, str]:
        models: dict[str, str] = {}
        for code_file in ctx.files:
            for idx, line in enumerate(code_file.content.splitlines(), start=1):
                for match in re.finditer(r"@RequestBody\s+(?:@\w+\s+)*(\w+)", line):
                    model_name = match.group(1)
                    models[model_name] = f"{code_file.path}:{idx}"
        return models

    def _analyze_python(self, ctx: CodeContext, test_basis: dict[str, Any]) -> None:
        request_models = self._python_request_models(ctx)
        for model_name, source in request_models.items():
            test_basis["request_models"].append({"name": model_name, "source": source})

        for code_file in ctx.files:
            lines = code_file.content.splitlines()
            self._collect_common_signals(code_file, lines, test_basis)
            test_basis["fields"].extend(_parse_pydantic_fields(code_file.path, lines, request_models))

    def _python_request_models(self, ctx: CodeContext) -> dict[str, str]:
        models: dict[str, str] = {}
        class_names = set()
        for code_file in ctx.files:
            for line in code_file.content.splitlines():
                match = re.search(r"class\s+(\w+)\s*\(\s*BaseModel\s*\)", line)
                if match:
                    class_names.add(match.group(1))

        if not class_names:
            return models

        for code_file in ctx.files:
            for idx, line in enumerate(code_file.content.splitlines(), start=1):
                for class_name in class_names:
                    if re.search(rf"\b\w+\s*:\s*{class_name}\b", line):
                        models[class_name] = f"{code_file.path}:{idx}"
        return models

    def _collect_common_signals(self, code_file: CodeFile, lines: list[str], test_basis: dict[str, Any]) -> None:
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            lower = stripped.lower()

            if any(hint in stripped for hint in AUTH_HINTS):
                test_basis["auth"].append({
                    "source": code_file.path,
                    "line": idx,
                    "evidence": stripped[:240],
                })

            if re.search(r"\bif\s*\(|\bswitch\s*\(|\bcase\b|\braise\s+HTTPException\b|throw\s+new\b", stripped):
                test_basis["branches"].append({
                    "source": code_file.path,
                    "line": idx,
                    "condition": stripped[:240],
                })

            if any(hint.lower() in lower for hint in STATE_HINTS) and ("=" in stripped or "(" in stripped):
                test_basis["state_changes"].append({
                    "source": code_file.path,
                    "line": idx,
                    "evidence": stripped[:240],
                })

            if any(hint in stripped for hint in EXTERNAL_CALL_HINTS):
                test_basis["external_calls"].append({
                    "source": code_file.path,
                    "line": idx,
                    "evidence": stripped[:240],
                })

            for name in SENSITIVE_NAMES:
                if name in lower:
                    test_basis["sensitive_fields"].append({
                        "name": name,
                        "source": code_file.path,
                        "line": idx,
                        "evidence": stripped[:240],
                    })


def _parse_java_fields(source: str, model_name: str, lines: list[str]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    pending_annotations: list[tuple[str, int]] = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("@"):
            pending_annotations.append((stripped, idx))
            continue

        match = re.search(r"(?:private|public|protected)\s+([\w<>?, ]+)\s+(\w+)\s*;", stripped)
        if not match:
            if stripped and not stripped.startswith("//"):
                pending_annotations = []
            continue

        field_type, field_name = match.groups()
        constraints = _java_constraints(pending_annotations)
        fields.append({
            "model": model_name,
            "name": field_name,
            "type": field_type.strip(),
            "required": any(item["type"] in ("not_null", "not_blank") for item in constraints),
            "constraints": constraints,
            "source": f"{source}:{idx}",
        })
        pending_annotations = []

    return fields


def _java_constraints(annotations: list[tuple[str, int]]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for annotation, line_no in annotations:
        if annotation.startswith("@NotNull"):
            constraints.append({"type": "not_null", "detail": annotation, "line": line_no})
        elif annotation.startswith("@NotBlank"):
            constraints.append({"type": "not_blank", "detail": annotation, "line": line_no})
        elif annotation.startswith("@Min"):
            value = _first_number(annotation)
            constraints.append({"type": "min", "value": value, "detail": annotation, "line": line_no})
        elif annotation.startswith("@Max"):
            value = _first_number(annotation)
            constraints.append({"type": "max", "value": value, "detail": annotation, "line": line_no})
        elif annotation.startswith("@Size"):
            constraints.append({"type": "size", **_named_numbers(annotation), "detail": annotation, "line": line_no})
        elif annotation.startswith("@Pattern"):
            pattern = _named_string(annotation, "regexp")
            constraints.append({"type": "pattern", "value": pattern, "detail": annotation, "line": line_no})
        elif annotation.startswith("@Column"):
            column = {"type": "column", "detail": annotation, "line": line_no}
            if "nullable = false" in annotation or "nullable=false" in annotation:
                column["nullable"] = False
            if "unique = true" in annotation or "unique=true" in annotation:
                column["unique"] = True
            length = _named_number(annotation, "length")
            if length is not None:
                column["length"] = length
            constraints.append(column)
        elif annotation.startswith("@Enumerated"):
            constraints.append({"type": "enum", "detail": annotation, "line": line_no})
    return constraints


def _parse_pydantic_fields(source: str, lines: list[str], request_models: dict[str, str]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    current_class = ""
    in_model = False

    for idx, line in enumerate(lines, start=1):
        class_match = re.search(r"class\s+(\w+)\s*\(\s*BaseModel\s*\)", line)
        if class_match:
            current_class = class_match.group(1)
            in_model = current_class in request_models or not request_models
            continue

        if in_model and line and not line.startswith((" ", "\t")) and not line.lstrip().startswith("#"):
            in_model = False
            current_class = ""

        if not in_model or not current_class:
            continue

        field_match = re.search(r"^\s*(\w+)\s*:\s*([\w\[\], .|]+)(?:\s*=\s*(.+))?", line)
        if not field_match:
            continue

        field_name, field_type, default_expr = field_match.groups()
        constraints = _pydantic_constraints(default_expr or "")
        required = _pydantic_required(default_expr)
        fields.append({
            "model": current_class,
            "name": field_name,
            "type": field_type.strip(),
            "required": required,
            "constraints": constraints,
            "source": f"{source}:{idx}",
        })

    return fields


def _pydantic_constraints(expr: str) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    if "Field(" not in expr:
        return constraints

    for key in ("ge", "gt", "le", "lt", "min_length", "max_length"):
        value = _named_number(expr, key)
        if value is not None:
            constraints.append({"type": key, "value": value, "detail": expr.strip()})

    pattern = _named_string(expr, "pattern") or _named_string(expr, "regex")
    if pattern is not None:
        constraints.append({"type": "pattern", "value": pattern, "detail": expr.strip()})

    return constraints


def _pydantic_required(default_expr: str | None) -> bool:
    if default_expr is None:
        return True

    expr = default_expr.strip()
    if expr == "...":
        return True
    if expr in ("None", "False", "True") or re.fullmatch(r"[-]?\d+(\.\d+)?", expr):
        return False
    if expr.startswith(("'", '"', "[", "{")):
        return False
    if expr.startswith("Field("):
        args = expr[len("Field("):].strip()
        if args.startswith("..."):
            return True
        if re.match(r"(default|default_factory)\s*=", args):
            return False
        # Field(ge=1) has no default value; Pydantic treats the field as required.
        if re.match(r"\w+\s*=", args):
            return True
        return False
    return False


def _route_to_dict(route: Any) -> dict[str, Any] | None:
    if route is None:
        return None
    return {
        "method": route.method,
        "path": route.path,
        "normalized_path": route.normalized_path,
        "file": route.file,
        "line": route.line,
        "handler": route.handler,
        "framework": route.framework,
    }


def _dedupe_dicts(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _first_number(text: str) -> int | None:
    match = re.search(r"-?\d+", text)
    return int(match.group(0)) if match else None


def _named_number(text: str, name: str) -> int | None:
    match = re.search(rf"\b{name}\s*=\s*(-?\d+)", text)
    return int(match.group(1)) if match else None


def _named_numbers(text: str) -> dict[str, int]:
    values = {}
    for name in ("min", "max"):
        value = _named_number(text, name)
        if value is not None:
            values[name] = value
    return values


def _named_string(text: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*\"([^\"]+)\"", text)
    return match.group(1) if match else None
