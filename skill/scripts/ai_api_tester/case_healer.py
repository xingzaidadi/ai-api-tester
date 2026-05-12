"""Detect stale, broken, or outdated test cases by comparing against current source code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from .detector import ProjectDetector, ProjectInfo
from .route_extractor import RouteExtractor, route_matches, normalize_path
from .source_analyzer import SourceAnalyzer
from .locator import CodeLocator, CodeContext


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CaseIssue:
    case_id: str
    case_name: str
    issue_type: str  # "stale", "broken", "outdated"
    detail: str      # Human-readable description
    field: str       # Which field is affected (e.g. "request.body.productId", "request.url", "expect.status")
    old_value: Any = None
    suggested_value: Any = None


@dataclass
class HealReport:
    cases_checked: int = 0
    issues: list[CaseIssue] = field(default_factory=list)
    healthy: int = 0
    stale: int = 0
    broken: int = 0
    outdated: int = 0


# ---------------------------------------------------------------------------
# Main healer
# ---------------------------------------------------------------------------

class CaseHealer:
    """Compare YAML test cases against current source code and detect drift."""

    def __init__(self, project_path: str, project_info: ProjectInfo):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info
        self.route_extractor = RouteExtractor(str(self.project_path), project_info)
        self.routes = self.route_extractor.extract()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(self, suite: dict) -> HealReport:
        """Scan every case in *suite* and return a :class:`HealReport`."""
        report = HealReport()
        cases = suite.get("cases", [])

        for case in cases:
            report.cases_checked += 1
            case_id = case.get("id", "")
            case_name = case.get("name", "")
            issues_before = len(report.issues)

            # 1. Check route existence (broken detection)
            request = case.get("request", {})
            raw_url = request.get("url", "")
            method = request.get("method", "GET").upper()
            api_path = self._extract_api_path(raw_url)

            if api_path and api_path != "/":
                matched = [r for r in self.routes if route_matches(r, api_path, method)]
                if not matched:
                    report.issues.append(CaseIssue(
                        case_id=case_id,
                        case_name=case_name,
                        issue_type="broken",
                        detail="Route no longer exists or path changed",
                        field="request.url",
                        old_value=raw_url,
                    ))

            # 2. Check source line (stale detection)
            source_issue = self._check_source_line(case.get("source", ""), case_id, case_name)
            if source_issue:
                report.issues.append(source_issue)

            # 3. Check request body fields (stale detection)
            body = request.get("body", {})
            if body and api_path and api_path != "/":
                current_fields = self._get_current_fields(method, api_path)
                current_field_names = [f["name"] for f in current_fields]

                if current_field_names:
                    for body_field in body:
                        if body_field not in current_field_names:
                            close = get_close_matches(body_field, current_field_names, n=1, cutoff=0.5)
                            suggestion = close[0] if close else None
                            detail = f"field not found in current source"
                            if suggestion:
                                detail += f", did you mean '{suggestion}'?"
                            report.issues.append(CaseIssue(
                                case_id=case_id,
                                case_name=case_name,
                                issue_type="stale",
                                detail=detail,
                                field=f"request.body.{body_field}",
                                old_value=body_field,
                                suggested_value=suggestion,
                            ))

            # 4. Check constraints (outdated detection)
            self._check_constraints(case, current_fields if body else [], report)

            # Tally
            case_issues = report.issues[issues_before:]
            if not case_issues:
                report.healthy += 1
            else:
                types_seen = {i.issue_type for i in case_issues}
                if "broken" in types_seen:
                    report.broken += 1
                elif "stale" in types_seen:
                    report.stale += 1
                elif "outdated" in types_seen:
                    report.outdated += 1

        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_api_path(self, url: str) -> str:
        """Strip common template prefixes and return the bare API path."""
        cleaned = url.strip()
        # Remove template variable prefixes like {{env.base_url}}, {{ENV.API_BASE}}, etc.
        cleaned = re.sub(r"\{\{[^}]*\}\}", "", cleaned)
        # Remove protocol + host if present (e.g. http://localhost:8080)
        cleaned = re.sub(r"^https?://[^/]*", "", cleaned)
        # Strip query string
        cleaned = cleaned.split("?")[0]
        cleaned = cleaned.strip()
        if not cleaned:
            return "/"
        return normalize_path(cleaned)

    def _find_file(self, filename: str) -> Path | None:
        """Recursively find a file by name in the project."""
        for entry_dir in self.project_info.entry_dirs:
            base = Path(entry_dir)
            if not base.exists():
                continue
            for path in base.rglob(filename):
                if path.is_file():
                    return path
        # Fallback: search project root
        for path in self.project_path.rglob(filename):
            if path.is_file():
                return path
        return None

    def _check_source_line(self, source: str, case_id: str, case_name: str) -> CaseIssue | None:
        """Parse the source field (e.g. 'File.java:42 -> code') and verify it."""
        if not source:
            return None

        # Parse "FileName.java:42" or "FileName.java:42 -> someHint"
        match = re.match(r"^(.+?):(\d+)(?:\s*(?:->|→)\s*(.+))?$", source.strip())
        if not match:
            return None

        filename = match.group(1).strip()
        line_no = int(match.group(2))
        hint = (match.group(3) or "").strip()

        # Find the file
        found = self._find_file(Path(filename).name)
        if not found:
            return CaseIssue(
                case_id=case_id,
                case_name=case_name,
                issue_type="stale",
                detail=f"Source file not found: {filename}",
                field="source",
                old_value=source,
            )

        # Read the line and check if hint still matches
        if hint:
            try:
                lines = found.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line_no <= len(lines):
                    actual_line = lines[line_no - 1].strip()
                    # Check if the hint keywords are still present
                    hint_keywords = [w for w in re.split(r"\W+", hint) if len(w) > 2]
                    if hint_keywords:
                        matches = sum(1 for kw in hint_keywords if kw in actual_line)
                        if matches < len(hint_keywords) * 0.4:
                            return CaseIssue(
                                case_id=case_id,
                                case_name=case_name,
                                issue_type="stale",
                                detail=f"Source code at {found.name}:{line_no} has changed",
                                field="source",
                                old_value=source,
                                suggested_value=f"{found.name}:{line_no} → {actual_line[:120]}",
                            )
                else:
                    return CaseIssue(
                        case_id=case_id,
                        case_name=case_name,
                        issue_type="stale",
                        detail=f"Source code at {found.name}:{line_no} has changed (file only has {len(lines)} lines)",
                        field="source",
                        old_value=source,
                    )
            except OSError:
                pass

        return None

    def _get_current_fields(self, method: str, path: str) -> list[dict]:
        """Use CodeLocator + SourceAnalyzer to get current fields for a route."""
        try:
            locator = CodeLocator(str(self.project_path), self.project_info)
            ctx = locator.locate(path, method)
            if not ctx.files:
                return []
            analyzer = SourceAnalyzer(str(self.project_path), self.project_info)
            test_basis = analyzer.analyze(ctx)
            return test_basis.get("fields", [])
        except Exception:
            return []

    def _check_constraints(
        self,
        case: dict,
        current_fields: list[dict],
        report: HealReport,
    ) -> None:
        """Detect outdated constraint values (e.g. boundary tests against changed @Min/@Max)."""
        if not current_fields:
            return

        case_id = case.get("id", "")
        case_name = case.get("name", "")
        dimensions = case.get("dimensions", [])

        # Only check boundary_value dimension cases
        is_boundary = "boundary_value" in dimensions or "boundary" in case_name.lower()
        if not is_boundary:
            return

        body = case.get("request", {}).get("body", {})
        if not body:
            return

        # Build a map of field -> constraints from current source
        constraint_map: dict[str, list[dict]] = {}
        for f in current_fields:
            constraint_map[f["name"]] = f.get("constraints", [])

        for field_name, test_value in body.items():
            constraints = constraint_map.get(field_name, [])
            for c in constraints:
                ctype = c.get("type", "")
                cvalue = c.get("value")
                if cvalue is None:
                    continue

                # Check if the test's boundary value no longer aligns
                if ctype in ("min", "ge", "gt") and isinstance(test_value, (int, float)):
                    # If test value == old_boundary - 1 but current boundary is different
                    if test_value == cvalue - 1:
                        # Boundary still consistent: test is exactly below min
                        pass
                    elif test_value < cvalue - 1 or test_value >= cvalue:
                        # Might be testing an old boundary
                        expected = case.get("expect", {})
                        if expected.get("status") in (400, 422):
                            # Test expects failure — check if value is still invalid
                            if test_value >= cvalue:
                                report.issues.append(CaseIssue(
                                    case_id=case_id,
                                    case_name=case_name,
                                    issue_type="outdated",
                                    detail=f"@{ctype.title()} changed: test value {test_value} is now valid (constraint is {cvalue})",
                                    field=f"request.body.{field_name}",
                                    old_value=test_value,
                                    suggested_value=cvalue - 1 if ctype in ("min", "ge") else cvalue,
                                ))

                if ctype in ("max", "le", "lt") and isinstance(test_value, (int, float)):
                    expected = case.get("expect", {})
                    if expected.get("status") in (400, 422):
                        if test_value <= cvalue:
                            report.issues.append(CaseIssue(
                                case_id=case_id,
                                case_name=case_name,
                                issue_type="outdated",
                                detail=f"@{ctype.title()} changed: test value {test_value} is now valid (constraint is {cvalue})",
                                field=f"request.body.{field_name}",
                                old_value=test_value,
                                suggested_value=cvalue + 1 if ctype in ("max", "le") else cvalue,
                            ))


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def to_dict(report: HealReport) -> dict:
    """Convert a :class:`HealReport` to a JSON-serializable dict."""
    return {
        "cases_checked": report.cases_checked,
        "healthy": report.healthy,
        "stale": report.stale,
        "broken": report.broken,
        "outdated": report.outdated,
        "issues": [
            {
                "case_id": issue.case_id,
                "case_name": issue.case_name,
                "issue_type": issue.issue_type,
                "detail": issue.detail,
                "field": issue.field,
                "old_value": issue.old_value,
                "suggested_value": issue.suggested_value,
            }
            for issue in report.issues
        ],
    }
