"""Detect affected API routes from git diff."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .detector import ProjectDetector, ProjectInfo
from .route_extractor import RouteExtractor, Route
from .locator import CodeLocator


@dataclass
class AffectedRoute:
    method: str
    path: str
    handler: str
    changed_files: list[str] = field(default_factory=list)
    change_type: str = "direct"  # "direct" or "indirect"


class DiffDetector:
    """Detect which API routes are affected by git changes.

    Uses only code logic (no LLM calls). Compares changed files from
    ``git diff`` against extracted routes and their dependency graphs.
    """

    def __init__(
        self,
        project_path: str,
        project_info: ProjectInfo,
        base: str = "HEAD~1",
    ):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info
        self.base = base

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self) -> list[AffectedRoute]:
        """Return a sorted list of routes affected by the git diff."""
        changed_files = self.get_changed_files()
        if not changed_files:
            return []

        routes = RouteExtractor(
            str(self.project_path), self.project_info
        ).extract()
        if not routes:
            return []

        # Normalise changed file paths to absolute for reliable comparison.
        changed_abs = [
            str(self._resolve_changed_path(f)) for f in changed_files
        ]

        # Build a set of route file paths for quick lookup.
        route_file_set: set[str] = {
            str(Path(r.file).resolve()) for r in routes
        }

        # Collect affected routes keyed by (method, path) for dedup.
        affected: dict[tuple[str, str], AffectedRoute] = {}

        for cf in changed_abs:
            cf_resolved = str(Path(cf).resolve())

            # --- Direct match: the changed file IS a route file ----------
            if cf_resolved in route_file_set:
                for route in routes:
                    if str(Path(route.file).resolve()) == cf_resolved:
                        key = (route.method, route.path)
                        if key not in affected:
                            affected[key] = AffectedRoute(
                                method=route.method,
                                path=route.path,
                                handler=route.handler,
                                changed_files=[],
                                change_type="direct",
                            )
                        ar = affected[key]
                        if cf not in ar.changed_files:
                            ar.changed_files.append(cf)
                        # Keep the strongest change type.
                        ar.change_type = "direct"
                continue

            # --- Indirect match: check if any route depends on this file -
            self._check_indirect(cf, routes, affected)

        return sorted(affected.values(), key=lambda a: (a.method, a.path))

    def get_changed_files(self) -> list[str]:
        """Return the list of files changed in the git diff.

        Binary files are excluded. Returns an empty list when the git
        command fails (e.g. not a git repo or invalid ref).
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMRT",
                 f"{self.base}...HEAD"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(self.project_path),
            )
            if result.returncode != 0:
                # Fallback: try two-dot diff (works when base is not an
                # ancestor, e.g. ``HEAD~1`` on a fresh branch).
                result = subprocess.run(
                    ["git", "diff", "--name-only", "--diff-filter=ACMRT",
                     self.base, "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=str(self.project_path),
                )
                if result.returncode != 0:
                    return []

            files: list[str] = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # Skip binary files (git may list them, but they are
                # useless for route analysis).
                if self._is_binary_path(line):
                    continue
                files.append(line)
            return files

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_changed_path(self, rel_path: str) -> Path:
        """Resolve a git-relative path to an absolute path."""
        return (self.project_path / rel_path).resolve()

    def _check_indirect(
        self,
        changed_file: str,
        routes: list[Route],
        affected: dict[tuple[str, str], AffectedRoute],
    ) -> None:
        """Check whether *changed_file* is referenced by any route's
        dependency graph and, if so, register the route as indirectly
        affected.
        """
        locator = CodeLocator(str(self.project_path), self.project_info)
        changed_name = Path(changed_file).stem  # e.g. "OrderService"

        for route in routes:
            ctx = locator.locate(route.path, route.method)
            # Walk all files the locator found for this route.
            for code_file in ctx.files:
                dep_path = str(Path(code_file.path).resolve())
                if dep_path == str(Path(changed_file).resolve()):
                    key = (route.method, route.path)
                    if key not in affected:
                        affected[key] = AffectedRoute(
                            method=route.method,
                            path=route.path,
                            handler=route.handler,
                            changed_files=[],
                            change_type="indirect",
                        )
                    ar = affected[key]
                    if changed_file not in ar.changed_files:
                        ar.changed_files.append(changed_file)
                    # Only upgrade to "indirect" if not already "direct".
                    if ar.change_type != "direct":
                        ar.change_type = "indirect"
                    break  # no need to check remaining files for this route

    @staticmethod
    def _is_binary_path(path: str) -> bool:
        """Heuristic to skip binary files based on extension."""
        binary_exts = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
            ".woff", ".woff2", ".ttf", ".eot",
            ".zip", ".tar", ".gz", ".jar", ".war", ".class",
            ".so", ".dll", ".exe", ".pyc", ".pyo",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        }
        _, ext = os.path.splitext(path)
        return ext.lower() in binary_exts
