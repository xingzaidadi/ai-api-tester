"""Lightweight source-code analysis for API test generation context."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import ProjectConfig, load_config
from .detector import ProjectInfo
from .locator import CodeContext, CodeFile
from .route_extractor import RouteExtractor


SENSITIVE_NAMES = ("phone", "mobile", "email", "idcard", "id_card", "bankcard", "bank_card", "address", "token")
EXTERNAL_CALL_HINTS = ("FeignClient", "RestTemplate", "WebClient", "httpx.", "requests.", "aiohttp.", "fetch(", "axios.")
AUTH_HINTS = ("@PreAuthorize", "@Secured", "@RolesAllowed", "SecurityContext", "Jwt", "JWT", "Depends(", "current_user", "get_current_user")
STATE_HINTS = ("status", "state", "setStatus", "setState")


class SourceAnalyzer:
    def __init__(self, project_path: str, project_info: ProjectInfo, config: ProjectConfig | None = None):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info
        self.config = config or load_config(str(self.project_path))

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
        route = test_basis.get("route")
        request_models = self._java_request_models(ctx, route)
        for model_name, source in request_models.items():
            test_basis["request_models"].append({"name": model_name, "source": source})

        # Ensure model files are loaded even if locator missed them
        self._ensure_model_files_loaded(ctx, request_models)

        for code_file in ctx.files:
            lines = code_file.content.splitlines()
            self._collect_common_signals(code_file, lines, test_basis)

            if code_file.role == "model" or Path(code_file.path).stem in request_models:
                model_name = Path(code_file.path).stem
                test_basis["fields"].extend(_parse_java_fields(code_file.path, model_name, lines))

    def _ensure_model_files_loaded(self, ctx: CodeContext, request_models: dict[str, str]) -> None:
        """Find and load model class files that aren't already in ctx.files."""
        existing_stems = {Path(f.path).stem for f in ctx.files}
        for model_name in request_models:
            if model_name in existing_stems:
                continue
            target = f"{model_name}.java"
            for entry_dir in self.project_info.entry_dirs:
                entry_path = Path(entry_dir)
                if not entry_path.is_dir():
                    continue
                for found in entry_path.rglob(target):
                    if found.is_file():
                        try:
                            content = found.read_text(encoding="utf-8", errors="ignore")
                        except OSError:
                            continue
                        ctx.files.append(CodeFile(
                            path=str(found), content=content, role="model"
                        ))
                        existing_stems.add(model_name)
                        break
                if model_name in existing_stems:
                    break

    def _body_annotation_names(self) -> list[str]:
        return ["RequestBody", "X5RequestBody"] + self.config.custom_body_annotations

    def _java_request_models(self, ctx: CodeContext, route: dict[str, Any] | None = None) -> dict[str, str]:
        models: dict[str, str] = {}
        names = self._body_annotation_names()
        body_re = re.compile(r"@(?:" + "|".join(re.escape(n) for n in names) + r")\b")
        type_re = re.compile(r"(?:^|[\s(,])([A-Z]\w+)(?:<([A-Z]\w+)>)?\s+\w+")
        _SKIP_TYPES = {"Valid", "NotNull", "NotEmpty", "NotBlank",
                       "String", "List", "Map", "Set", "Integer", "Long",
                       "Boolean", "Double", "Float", "Object", "Optional",
                       "HttpServletRequest", "HttpServletResponse"}

        # If route is known, scope search to the matched method (± 15 lines from route line)
        route_file = route.get("file", "") if route else ""
        route_line = route.get("line", 0) if route else 0

        for code_file in ctx.files:
            lines = code_file.content.splitlines()
            # Determine search range
            if route_file and route_line and code_file.path == route_file:
                # Only scan the matched method's region
                start = max(0, route_line - 3)
                end = min(len(lines), route_line + 15)
            else:
                start = 0
                end = len(lines)

            for idx in range(start, end):
                line = lines[idx]
                if not body_re.search(line):
                    continue
                search_block = line
                for lookahead in range(1, 4):
                    if idx + lookahead < len(lines):
                        search_block += " " + lines[idx + lookahead].strip()
                    type_match = type_re.search(search_block[search_block.find("@"):] if "@" in search_block else search_block)
                    if type_match:
                        outer_name = type_match.group(1)
                        inner_name = type_match.group(2)
                        is_skip = outer_name in names or outer_name in _SKIP_TYPES
                        if inner_name and inner_name not in _SKIP_TYPES:
                            models[inner_name] = f"{code_file.path}:{idx + 1}"
                        if not is_skip:
                            models[outer_name] = f"{code_file.path}:{idx + 1}"
                        if inner_name or not is_skip:
                            break
                        continue
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
    result = {
        "method": route.method,
        "path": route.path,
        "normalized_path": route.normalized_path,
        "file": route.file,
        "line": route.line,
        "handler": route.handler,
        "framework": route.framework,
    }
    if getattr(route, "description", ""):
        result["description"] = route.description
    return result


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
