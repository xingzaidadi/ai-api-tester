#!/usr/bin/env python3
"""Detect stale test cases and suggest fixes."""

import sys
import io
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.case_healer import CaseHealer, to_dict


def main():
    parser = argparse.ArgumentParser(description="Detect stale/broken/outdated test cases")
    parser.add_argument("yaml_file", help="Path to YAML test cases")
    parser.add_argument("project", help="Project root path")
    parser.add_argument("--output", "-o", help="Optional JSON output path for heal report")
    args = parser.parse_args()

    # Load YAML
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"File not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        suite = yaml.safe_load(f)

    if not suite or "cases" not in suite:
        print("Invalid YAML: missing 'cases' key")
        sys.exit(1)

    # Detect project
    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        print(f"Project path not found: {project_path}")
        sys.exit(1)

    detector = ProjectDetector(str(project_path))
    project_info = detector.detect()

    # Heal
    healer = CaseHealer(str(project_path), project_info)
    report = healer.heal(suite)

    # Console summary
    print()
    print("Case Health Check:")
    if report.healthy:
        print(f"  \u2705 {report.healthy} healthy")
    if report.stale:
        print(f"  \u26a0\ufe0f  {report.stale} stale (field renamed or source changed)")
    if report.broken:
        print(f"  \u274c {report.broken} broken (route no longer exists)")
    if report.outdated:
        print(f"  \U0001f504 {report.outdated} outdated (constraint values changed)")

    if not report.issues:
        print("\n  All cases are healthy!")
    else:
        print()
        print("Issues:")
        for issue in report.issues:
            tag = issue.issue_type
            msg = f"  {issue.case_id}: [{tag}] {issue.field} - {issue.detail}"
            print(msg)

    # Optional JSON output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(to_dict(report), f, indent=2, ensure_ascii=False)
        print(f"\nReport written to {output_path}")

    # Exit code: non-zero if any broken cases
    if report.broken:
        sys.exit(2)
    if report.stale or report.outdated:
        sys.exit(1)


if __name__ == "__main__":
    main()
