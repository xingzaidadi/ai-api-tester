#!/usr/bin/env python3
"""Analyze API risk from Git history."""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.locator import CodeLocator
from ai_api_tester.analyzer import GitAnalyzer


def main():
    parser = argparse.ArgumentParser(description="API risk analysis")
    parser.add_argument("url", help="API URL path")
    parser.add_argument("project", help="Project root path")
    parser.add_argument("--method", "-m", default=None, help="HTTP method")
    args = parser.parse_args()

    detector = ProjectDetector(args.project)
    info = detector.detect()

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"No code found for '{args.url}'")
        sys.exit(1)

    git_analyzer = GitAnalyzer(args.project)
    risk_info = git_analyzer.analyze_risk([f.path for f in ctx.files])

    print(f"url: {args.url}")
    print(f"risk_score: {risk_info.risk_score:.1f}/10")
    print(f"recent_changes_30d: {risk_info.recent_changes}")
    print(f"last_modified: {risk_info.last_modified}")

    if risk_info.recent_fix_commits:
        print("fix_commits:")
        for c in risk_info.recent_fix_commits:
            print(f"  - {c}")

    if risk_info.hot_files:
        print("hot_files:")
        for f in risk_info.hot_files:
            print(f"  - {f}")

    if risk_info.risk_factors:
        print("risk_factors:")
        for f in risk_info.risk_factors:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
