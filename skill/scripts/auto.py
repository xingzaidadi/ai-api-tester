#!/usr/bin/env python3
"""One-command pipeline: detect → extract routes → gen_context for all APIs."""

import sys
import json
import argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.locator import CodeLocator
from ai_api_tester.route_extractor import RouteExtractor
from ai_api_tester.analyzer import GitAnalyzer, SchemaAnalyzer
from ai_api_tester.source_analyzer import SourceAnalyzer


def _slug(url: str) -> str:
    """Turn a URL path into a filesystem-safe slug."""
    return url.strip("/").replace("/", "_").replace("{", "").replace("}", "") or "root"


def gen_context(project_path: str, info, url: str, method: str) -> dict | None:
    """Generate test context for a single API endpoint.

    Returns the context dict on success, or None if no files are found.
    """
    locator = CodeLocator(project_path, info)
    ctx = locator.locate(url, method)

    if not ctx.files:
        return None

    git_analyzer = GitAnalyzer(project_path)
    risk_info = git_analyzer.analyze_risk([f.path for f in ctx.files])

    schema_analyzer = SchemaAnalyzer(project_path, info.language)
    model_files = [f.path for f in ctx.files if f.role in ("model", "mapper")]
    constraints = schema_analyzer.analyze_entity(model_files)

    source_analyzer = SourceAnalyzer(project_path, info)
    test_basis = source_analyzer.analyze(ctx)

    return {
        "project": {"language": info.language, "framework": info.framework},
        "api": {"url": url, "method": method},
        "test_basis": test_basis,
        "code_files": [
            {"path": f.path, "role": f.role, "content": f.content[:5000]}
            for f in ctx.files
        ],
        "risk": {
            "score": risk_info.risk_score,
            "factors": risk_info.risk_factors,
            "recent_changes": risk_info.recent_changes,
            "fix_commits": risk_info.recent_fix_commits,
        },
        "schema_constraints": [
            {"table": c.table, "column": c.column, "type": c.constraint_type, "detail": c.detail}
            for c in constraints
        ],
    }


def run_single(project_path: str, url: str, method: str, output_dir: str) -> int:
    """Single-API mode: detect → locate → gen_context → output."""
    detector = ProjectDetector(project_path)
    info = detector.detect()
    print(f"Detected: {info.language} / {info.framework}")

    context = gen_context(project_path, info, url, method)
    if context is None:
        print(f"No files found for {method} {url}")
        return 0

    today = date.today().isoformat()
    slug = _slug(url)
    out_path = Path(output_dir) / f"{today}-{slug}" / "context.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(context, ensure_ascii=False, indent=2))
    print(f"Context saved: {out_path}")
    return 1


def run_batch(project_path: str, output_dir: str) -> tuple[int, int]:
    """Batch mode: detect → extract ALL routes → gen_context for each.

    Returns (routes_found, contexts_generated).
    """
    detector = ProjectDetector(project_path)
    info = detector.detect()
    print(f"Detected: {info.language} / {info.framework}")

    extractor = RouteExtractor(project_path, info)
    routes = extractor.extract()

    if not routes:
        print("No routes discovered.")
        return 0, 0

    print(f"Found {len(routes)} route(s). Generating contexts...")

    today = date.today().isoformat()
    generated = 0

    for route in routes:
        label = f"{route.method} {route.path}"
        context = gen_context(project_path, info, route.path, route.method)
        if context is None:
            print(f"  SKIP  {label} (no matching files)")
            continue

        slug = _slug(route.path)
        out_path = Path(output_dir) / f"{today}-{slug}" / "context.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(context, ensure_ascii=False, indent=2))
        print(f"  OK    {label} -> {out_path}")
        generated += 1

    return len(routes), generated


def run_tests(output_dir: str, env_file: str | None = None) -> int:
    """Run mode: find cases.yaml files, validate, execute, report, analyze.

    Returns exit code: 0 if all pass, 1 if any failures/errors.
    """
    import yaml
    from ai_api_tester.schema import validate_suite
    from ai_api_tester.engine import TestEngine
    from ai_api_tester.report import ReportGenerator
    from ai_api_tester.failure_analyzer import analyze_report

    env = {}
    if env_file:
        env_path = Path(env_file)
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    out = Path(output_dir)
    suite_dirs = sorted(
        p.parent for p in out.rglob("cases.yaml")
    )

    if not suite_dirs:
        print(f"No cases.yaml files found in: {output_dir}")
        return 0

    print(f"Running test suites from: {output_dir}\n")

    total_pass = 0
    total_fail = 0
    total_error = 0
    total_suites = len(suite_dirs)

    for idx, suite_dir in enumerate(suite_dirs, 1):
        cases_file = suite_dir / "cases.yaml"
        rel_path = cases_file.relative_to(Path.cwd()) if cases_file.is_relative_to(Path.cwd()) else cases_file
        print(f"  [{idx}/{total_suites}] {rel_path}")

        with open(cases_file, "r", encoding="utf-8") as f:
            suite_data = yaml.safe_load(f)

        errors = validate_suite(suite_data)
        if errors:
            print(f"        ⚠️ Validation failed: {errors}")
            total_error += 1
            continue

        engine = TestEngine(suite_data, env=env)
        results = engine.run()

        generator = ReportGenerator()
        report = generator.generate(results)

        report_path = suite_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

        context_path = suite_dir / "context.json"
        if context_path.exists():
            with open(context_path, "r", encoding="utf-8") as f:
                context = json.load(f)
            analysis = analyze_report(report, context)
            analysis_path = suite_dir / "analysis.json"
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2))

        passed = report.get("passed", 0)
        failed = report.get("failed", 0)
        errors = report.get("errors", 0)
        total_pass += passed
        total_fail += failed
        total_error += errors

        rel_report = report_path.relative_to(Path.cwd()) if report_path.is_relative_to(Path.cwd()) else report_path
        print(f"        ✅ {passed} passed, ❌ {failed} failed, ⚠️ {errors} errors")
        print(f"        Report: {rel_report}\n")

    print(f"Summary: {total_pass} passed, {total_fail} failed, {total_error} errors across {total_suites} suites.")

    return 1 if (total_fail > 0 or total_error > 0) else 0


def run_validate(project_path: str) -> None:
    """Validate-only mode: detect + route extraction, no context generation."""
    detector = ProjectDetector(project_path)
    info = detector.detect()
    print(f"Detected: {info.language} / {info.framework}")
    print(f"  entry_dirs: {info.entry_dirs}")
    print(f"  file_ext:   {info.file_ext}")
    print()

    extractor = RouteExtractor(project_path, info)
    routes = extractor.extract()

    if not routes:
        print("No routes discovered.")
        return

    print(f"Discovered {len(routes)} route(s):")
    for r in routes:
        handler_info = f"  [{r.handler}]" if r.handler else ""
        print(f"  {r.method:7s} {r.path}{handler_info}")


def main():
    parser = argparse.ArgumentParser(
        description="One-command pipeline: detect, extract routes, generate contexts."
    )
    parser.add_argument("project_path", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--url", default=None, help="Single API URL path (skip batch extraction)")
    parser.add_argument("--method", default="POST", help="HTTP method (default: POST)")
    parser.add_argument("--env-file", default=None, help="Environment file for test execution")
    parser.add_argument("--output-dir", default="./test-output", help="Output directory (default: ./test-output)")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only detect and list routes without generating contexts",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run existing cases.yaml test suites instead of generating contexts",
    )
    args = parser.parse_args()

    if args.run:
        exit_code = run_tests(args.output_dir, env_file=args.env_file)
        sys.exit(exit_code)

    project_path = str(Path(args.project_path).resolve())

    if args.validate_only:
        run_validate(project_path)
        return

    if args.url:
        count = run_single(project_path, args.url, args.method, args.output_dir)
        print(f"\nSummary: 1 API requested, {count} context(s) generated.")
    else:
        found, generated = run_batch(project_path, args.output_dir)
        print(f"\nSummary: {found} API(s) found, {generated} context(s) generated.")


if __name__ == "__main__":
    main()
