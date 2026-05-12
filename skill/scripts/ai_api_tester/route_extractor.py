"""Route extraction and matching for supported API frameworks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .detector import ProjectInfo


@dataclass
class Route:
    method: str
    path: str
    normalized_path: str
    file: str
    line: int
    handler: str
    framework: str


SPRING_METHODS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

# Custom Mapping annotations that behave like @RequestMapping (treat as POST by default)
CUSTOM_MAPPING_ANNOTATIONS = {
    "X5RequestMapping",
}

FASTAPI_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class RouteExtractor:
    def __init__(self, project_path: str, project_info: ProjectInfo):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info

    def extract(self) -> list[Route]:
        framework = self.project_info.framework
        language = self.project_info.language

        if framework == "spring-boot" or language == "java":
            return self._extract_spring_routes()
        if framework == "fastapi":
            return self._extract_fastapi_routes()
        return []

    def find_matches(self, url: str, method: str | None = None) -> list[Route]:
        routes = self.extract()
        method_upper = method.upper() if method else None
        matches = [route for route in routes if route_matches(route, url, method_upper)]
        return sorted(matches, key=lambda route: _route_specificity(route.normalized_path), reverse=True)

    def _iter_source_files(self, pattern: str) -> Iterable[Path]:
        seen: set[Path] = set()
        for entry_dir in self.project_info.entry_dirs:
            base = Path(entry_dir)
            if not base.exists():
                continue
            for path in base.rglob(pattern):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    yield path

    def _extract_spring_routes(self) -> list[Route]:
        routes: list[Route] = []
        for path in self._iter_source_files("*.java"):
            content = _read_text(path)
            if not content:
                continue

            lines = content.splitlines()
            class_line = _find_first_line(lines, r"\bclass\s+\w+")
            class_prefix = self._spring_class_prefix(lines, class_line)

            for annotation, line_no in _iter_java_mapping_annotations(lines):
                if class_line and line_no < class_line:
                    continue

                methods, route_path = _parse_spring_mapping(annotation)
                if not methods:
                    continue

                handler = _find_java_method_name(lines, line_no) or ""
                for method in methods:
                    full_path = join_paths(class_prefix, route_path)
                    routes.append(Route(
                        method=method,
                        path=full_path,
                        normalized_path=normalize_path(full_path),
                        file=str(path),
                        line=line_no,
                        handler=handler,
                        framework="spring-boot",
                    ))
        return routes

    def _spring_class_prefix(self, lines: list[str], class_line: int) -> str:
        if not class_line:
            return ""

        # Inspect annotations immediately above the class declaration.
        start = max(1, class_line - 12)
        block = "\n".join(lines[start - 1:class_line - 1])
        for annotation, _ in _iter_java_mapping_annotations(block.splitlines(), line_offset=start - 1):
            methods, path = _parse_spring_mapping(annotation)
            if "ANY" in methods:
                return path
        return ""

    def _extract_fastapi_routes(self) -> list[Route]:
        routes: list[Route] = []
        for path in self._iter_source_files("*.py"):
            content = _read_text(path)
            if not content:
                continue

            lines = content.splitlines()
            router_prefixes = _extract_fastapi_router_prefixes(content)

            for idx, line in enumerate(lines, start=1):
                match = re.search(r"@\s*(\w+)\.(get|post|put|delete|patch|head|options)\s*\((.*)", line)
                if not match:
                    continue

                receiver, method, rest = match.groups()
                annotation = rest
                if ")" not in rest:
                    for extra in lines[idx:idx + 6]:
                        annotation += "\n" + extra
                        if ")" in extra:
                            break

                route_path = _extract_first_string(annotation)
                if route_path is None:
                    route_path = ""

                prefix = router_prefixes.get(receiver, "")
                handler = _find_python_function_name(lines, idx) or ""
                full_path = join_paths(prefix, route_path)
                routes.append(Route(
                    method=method.upper(),
                    path=full_path,
                    normalized_path=normalize_path(full_path),
                    file=str(path),
                    line=idx,
                    handler=handler,
                    framework="fastapi",
                ))
        return routes


def route_matches(route: Route, url: str, method: str | None = None) -> bool:
    if method and route.method != "ANY" and route.method.upper() != method.upper():
        return False

    route_segments = normalize_path(route.path).strip("/").split("/")
    url_segments = normalize_path(url).strip("/").split("/")
    if route_segments == [""]:
        route_segments = []
    if url_segments == [""]:
        url_segments = []
    if len(route_segments) != len(url_segments):
        return False

    for route_segment, url_segment in zip(route_segments, url_segments):
        if route_segment == "{param}":
            continue
        if route_segment != url_segment:
            return False
    return True


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = path.strip()
    normalized = re.sub(r"//+", "/", normalized)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    normalized = re.sub(r"\{[^}/]+\}", "{param}", normalized)
    normalized = re.sub(r":([^/]+)", "{param}", normalized)
    normalized = re.sub(r"<[^>/]+>", "{param}", normalized)
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized


def join_paths(*parts: str) -> str:
    clean = []
    for part in parts:
        if part is None:
            continue
        value = str(part).strip().strip("/")
        if value:
            clean.append(value)
    return "/" + "/".join(clean) if clean else "/"


def _parse_spring_mapping(annotation: str) -> tuple[list[str], str]:
    name_match = re.search(r"@(\w+Mapping)\b", annotation)
    if not name_match:
        return [], ""

    name = name_match.group(1)
    if name in SPRING_METHODS:
        methods = [SPRING_METHODS[name]]
    elif name == "RequestMapping":
        methods = _extract_spring_request_methods(annotation)
    elif name in CUSTOM_MAPPING_ANNOTATIONS:
        # Custom mapping annotations (e.g. @X5RequestMapping) default to POST
        methods = ["POST"]
    else:
        methods = []

    path = _extract_spring_path(annotation)
    return methods, path


def _extract_spring_request_methods(annotation: str) -> list[str]:
    methods = re.findall(r"RequestMethod\.([A-Z]+)", annotation)
    return methods or ["ANY"]


def _extract_spring_path(annotation: str) -> str:
    # Supports @GetMapping("/x"), value="/x", path="/x", value={"/x"}.
    direct = re.search(r"@\w+Mapping\s*\(\s*\"([^\"]*)\"", annotation)
    if direct:
        return direct.group(1)

    named = re.search(r"(?:value|path)\s*=\s*(?:\{\s*)?\"([^\"]*)\"", annotation)
    if named:
        return named.group(1)

    return ""


def _iter_java_mapping_annotations(lines: list[str], line_offset: int = 0) -> Iterable[tuple[str, int]]:
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if re.search(r"@\w+Mapping\b", stripped):
            start_line = line_offset + idx + 1
            block = stripped
            paren_balance = stripped.count("(") - stripped.count(")")
            while paren_balance > 0 and idx + 1 < len(lines):
                idx += 1
                next_line = lines[idx].strip()
                block += "\n" + next_line
                paren_balance += next_line.count("(") - next_line.count(")")
            yield block, start_line
        idx += 1


def _find_first_line(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    for idx, line in enumerate(lines, start=1):
        if regex.search(line):
            return idx
    return 0


def _find_java_method_name(lines: list[str], annotation_line: int) -> str | None:
    for line in lines[annotation_line:annotation_line + 8]:
        match = re.search(r"\b(public|protected|private)\s+[\w<>\[\], ?]+\s+(\w+)\s*\(", line)
        if match:
            return match.group(2)
    return None


def _extract_fastapi_router_prefixes(content: str) -> dict[str, str]:
    prefixes: dict[str, str] = {}

    for match in re.finditer(r"(\w+)\s*=\s*APIRouter\s*\(([^)]*)\)", content, re.DOTALL):
        name, args = match.groups()
        prefix = _extract_named_string(args, "prefix") or ""
        prefixes[name] = prefix

    prefixes.setdefault("app", "")

    for match in re.finditer(r"(\w+)\.include_router\s*\(\s*(\w+)\s*,([^)]*)\)", content, re.DOTALL):
        _, router_name, args = match.groups()
        include_prefix = _extract_named_string(args, "prefix") or ""
        existing = prefixes.get(router_name, "")
        prefixes[router_name] = join_paths(include_prefix, existing)

    return prefixes


def _find_python_function_name(lines: list[str], decorator_line: int) -> str | None:
    for line in lines[decorator_line:decorator_line + 8]:
        match = re.search(r"\b(?:async\s+def|def)\s+(\w+)\s*\(", line)
        if match:
            return match.group(1)
    return None


def _extract_first_string(text: str) -> str | None:
    match = re.search(r"['\"]([^'\"]*)['\"]", text)
    return match.group(1) if match else None


def _extract_named_string(text: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*['\"]([^'\"]*)['\"]", text)
    return match.group(1) if match else None


def _route_specificity(path: str) -> int:
    return sum(2 if segment != "{param}" else 1 for segment in normalize_path(path).strip("/").split("/") if segment)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
