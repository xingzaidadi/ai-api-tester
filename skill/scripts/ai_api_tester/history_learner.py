"""Learn from historical test reports to create risk profiles."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DimensionStats:
    dimension: str
    total: int = 0
    failed: int = 0
    failure_rate: float = 0.0


@dataclass
class ModuleStats:
    module: str  # file path or module name
    total_cases: int = 0
    total_bugs: int = 0
    bug_density: float = 0.0  # bugs per case


@dataclass
class RiskProfile:
    """Aggregated risk profile from historical test runs."""

    report_count: int = 0
    total_cases: int = 0
    total_failures: int = 0
    overall_failure_rate: float = 0.0
    dimension_stats: list[DimensionStats] = field(default_factory=list)
    hot_modules: list[ModuleStats] = field(default_factory=list)
    high_risk_dimensions: list[str] = field(default_factory=list)  # dims with failure_rate > 30%
    recommendations: list[str] = field(default_factory=list)


def profile_to_dict(profile: RiskProfile) -> dict:
    """Serialize *RiskProfile* to a JSON-serializable dict."""
    return {
        "report_count": profile.report_count,
        "total_cases": profile.total_cases,
        "total_failures": profile.total_failures,
        "overall_failure_rate": round(profile.overall_failure_rate, 4),
        "dimension_stats": [
            {
                "dimension": ds.dimension,
                "total": ds.total,
                "failed": ds.failed,
                "failure_rate": round(ds.failure_rate, 4),
            }
            for ds in profile.dimension_stats
        ],
        "hot_modules": [
            {
                "module": ms.module,
                "total_cases": ms.total_cases,
                "total_bugs": ms.total_bugs,
                "bug_density": round(ms.bug_density, 4),
            }
            for ms in profile.hot_modules
        ],
        "high_risk_dimensions": profile.high_risk_dimensions,
        "recommendations": profile.recommendations,
    }


class HistoryLearner:
    """Scan historical test output and build a :class:`RiskProfile`."""

    def __init__(self, output_dir: str):
        """
        Args:
            output_dir: path to ``test-output/`` directory containing historical results.
        """
        self.output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def learn(self) -> RiskProfile:
        """Analyse all historical reports and return an aggregated risk profile."""

        dim_totals: dict[str, int] = defaultdict(int)
        dim_failures: dict[str, int] = defaultdict(int)
        module_cases: dict[str, int] = defaultdict(int)
        module_bugs: dict[str, int] = defaultdict(int)
        report_count = 0
        total_cases = 0
        total_failures = 0

        # --- 1. Scan report.json files -----------------------------------
        for report_path in self.output_dir.rglob("report.json"):
            report = self._load_json(report_path)
            if report is None:
                continue
            report_count += 1

            for case in report.get("cases", []) or []:
                dimension = case.get("dimension", "unknown")
                status = case.get("status", "")
                source = case.get("source", "") or ""

                total_cases += 1
                dim_totals[dimension] += 1

                if status in ("fail", "error"):
                    total_failures += 1
                    dim_failures[dimension] += 1

                # Track module participation
                module = self._extract_module(source)
                if module:
                    module_cases[module] += 1

        # --- 2. Scan analysis.json files ---------------------------------
        for analysis_path in self.output_dir.rglob("analysis.json"):
            analysis = self._load_json(analysis_path)
            if analysis is None:
                continue
            for finding in analysis.get("findings", []) or []:
                if finding.get("classification") != "probable_bug":
                    continue
                source = finding.get("source", "") or ""
                module = self._extract_module(source)
                if module:
                    module_bugs[module] += 1
                    # Ensure the module appears in module_cases even if we
                    # only saw it via analysis (defensive).
                    if module not in module_cases:
                        module_cases[module] += 1

        # --- 3. Compute dimension stats ----------------------------------
        dimension_stats: list[DimensionStats] = []
        for dim in sorted(dim_totals, key=lambda d: dim_totals[d], reverse=True):
            t = dim_totals[dim]
            f = dim_failures.get(dim, 0)
            rate = f / t if t else 0.0
            dimension_stats.append(DimensionStats(dimension=dim, total=t, failed=f, failure_rate=rate))

        # Sort by failure_rate descending
        dimension_stats.sort(key=lambda ds: ds.failure_rate, reverse=True)

        # --- 4. Compute hot modules (top 10 by bug density) --------------
        hot_modules: list[ModuleStats] = []
        for mod in module_cases:
            cases = module_cases[mod]
            bugs = module_bugs.get(mod, 0)
            density = bugs / cases if cases else 0.0
            if bugs > 0:
                hot_modules.append(ModuleStats(module=mod, total_cases=cases, total_bugs=bugs, bug_density=density))

        hot_modules.sort(key=lambda ms: ms.bug_density, reverse=True)
        hot_modules = hot_modules[:10]

        # --- 5. High risk dimensions (failure_rate > 30%) ----------------
        high_risk_dimensions = [ds.dimension for ds in dimension_stats if ds.failure_rate > 0.30]

        # --- 6. Overall rate ---------------------------------------------
        overall_failure_rate = total_failures / total_cases if total_cases else 0.0

        # --- 7. Generate recommendations ---------------------------------
        recommendations = self._generate_recommendations(
            dimension_stats, hot_modules, overall_failure_rate,
        )

        return RiskProfile(
            report_count=report_count,
            total_cases=total_cases,
            total_failures=total_failures,
            overall_failure_rate=overall_failure_rate,
            dimension_stats=dimension_stats,
            hot_modules=hot_modules,
            high_risk_dimensions=high_risk_dimensions,
            recommendations=recommendations,
        )

    def save(self, profile: RiskProfile, output_path: str) -> None:
        """Write *risk_profile.json* to disk."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _extract_module(source: str) -> str:
        """Return a short module identifier from a ``source`` string.

        The *source* field in reports typically looks like
        ``com/example/OrderService.java:42`` or ``src/services/payment.py:10``.
        We strip the line number and return the path.
        """
        if not source:
            return ""
        # Drop everything after an arrow (setup→target patterns)
        source = source.split("\u2192")[0].split("->")[0].strip()
        # Strip line number suffix
        colon_idx = source.rfind(":")
        if colon_idx != -1:
            after = source[colon_idx + 1:]
            if after.isdigit():
                source = source[:colon_idx]
        return source.strip()

    @staticmethod
    def _generate_recommendations(
        dimension_stats: list[DimensionStats],
        hot_modules: list[ModuleStats],
        overall_failure_rate: float,
    ) -> list[str]:
        recs: list[str] = []

        # Dimension-level recommendations
        for ds in dimension_stats:
            if ds.failure_rate > 0.30:
                pct = int(round(ds.failure_rate * 100))
                recs.append(
                    f"{ds.dimension} has {pct}% failure rate "
                    f"-- generate extra P0 cases for {ds.dimension.replace('_', '-')}-related APIs"
                )
            if len(recs) >= 3:
                break

        # Module-level recommendations
        for ms in hot_modules[:2]:
            recs.append(
                f"{ms.module} has {ms.total_bugs} bugs across {ms.total_cases} cases "
                f"-- prioritize testing this module"
            )

        # Overall health
        if overall_failure_rate > 0.25:
            pct = int(round(overall_failure_rate * 100))
            recs.append(
                f"Overall failure rate is {pct}% "
                f"-- consider adding more constraint validation tests and reviewing test environment stability"
            )

        return recs[:5]
