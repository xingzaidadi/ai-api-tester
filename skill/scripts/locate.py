#!/usr/bin/env python3
"""Locate source code files from API URL path."""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.locator import CodeLocator


def main():
    parser = argparse.ArgumentParser(description="URL → source code lookup")
    parser.add_argument("url", help="API URL path")
    parser.add_argument("project", help="Project root path")
    parser.add_argument("--method", "-m", default=None, help="HTTP method")
    args = parser.parse_args()

    detector = ProjectDetector(args.project)
    info = detector.detect()

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"No files found matching '{args.url}'")
        sys.exit(1)

    print(f"project: {info.language}/{info.framework}")
    print(f"files_found: {len(ctx.files)}")
    for f in ctx.files:
        line_info = f" (line {f.line_match})" if f.line_match else ""
        print(f"  [{f.role}] {f.path}{line_info}")

    if ctx.call_chain:
        print("call_chain:")
        for chain in ctx.call_chain:
            print(f"  {chain}")


if __name__ == "__main__":
    main()
