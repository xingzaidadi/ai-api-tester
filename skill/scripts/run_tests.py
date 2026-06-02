#!/usr/bin/env python3
"""Execute YAML test suite and generate report."""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _configure_output_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main():
    _configure_output_encoding()

    parser = argparse.ArgumentParser(description="Run test suite")
    parser.add_argument("yaml_file", help="YAML test case file")
    parser.add_argument("--env-file", "-e", default=None, help="Environment config file")
    parser.add_argument("--report", "-r", default=None, help="Report output path")
    parser.add_argument("--automation-results", default=None, help="Agentic QA Gate automation_results.json output path")
    parser.add_argument("--dashboard", "-d", default=None, help="Path to test-output/ dir for dashboard regeneration")
    parser.add_argument("--ci", action="store_true", default=False, help="Output JUnit XML next to the report")
    args = parser.parse_args()

    import yaml
    from ai_api_tester.engine import TestEngine
    from ai_api_tester.report import ReportGenerator
    from ai_api_tester.schema import validate_suite
    from ai_api_tester.automation_evidence import build_automation_evidence, write_json

    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"File not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        suite = yaml.safe_load(f)

    errors = validate_suite(suite)
    if errors:
        print("YAML validation failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(2)

    env = {}
    if args.env_file:
        env_path = Path(args.env_file)
        if env_path.exists():
            with open(env_path, "r") as f:
                env = yaml.safe_load(f) or {}

    engine = TestEngine(env=env)
    result = engine.run_suite(suite)

    reporter = ReportGenerator()
    print(reporter.console_report(result))
    report_payload = None

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_text = reporter.json_report(result)
        report_path.write_text(report_text, encoding="utf-8")
        import json
        report_payload = json.loads(report_text)
        print(f"Report saved: {report_path}")

    if args.automation_results:
        import json
        if report_payload is None:
            report_payload = json.loads(reporter.json_report(result))
        automation_path = Path(args.automation_results)
        evidence = build_automation_evidence(
            report_payload,
            report_path=Path(args.report) if args.report else None,
        )
        write_json(automation_path, evidence)
        print(f"Automation evidence saved: {automation_path}")

    if args.dashboard and args.report:
        try:
            import subprocess
            dashboard_dir = Path(args.dashboard)
            if dashboard_dir.is_dir():
                subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "dashboard.py"), str(dashboard_dir)],
                    check=False
                )
        except Exception:
            pass  # Dashboard update is best-effort

    if args.ci and args.report:
        try:
            import subprocess
            junit_path = Path(args.report).with_suffix('.xml')
            subprocess.run(
                [sys.executable, str(Path(__file__).parent / "ci_reporter.py"),
                 args.report, "-f", "junit", "-o", str(junit_path)],
                check=False
            )
            print(f"JUnit XML: {junit_path}")
        except Exception:
            pass

    sys.exit(0 if result.failed == 0 and result.errored == 0 else 1)


if __name__ == "__main__":
    main()
