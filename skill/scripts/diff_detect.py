#!/usr/bin/env python3
"""Detect APIs affected by recent git changes."""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.diff_detector import DiffDetector


def main():
    parser = argparse.ArgumentParser(
        description="Detect API routes affected by recent git changes"
    )
    parser.add_argument("project", help="Project root path")
    parser.add_argument(
        "--base", "-b", default="HEAD~1",
        help="Base git ref for diff (default: HEAD~1)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Optional path to write JSON output",
    )
    args = parser.parse_args()

    project_path = str(Path(args.project).resolve())

    # Detect project framework.
    detector = ProjectDetector(project_path)
    info = detector.detect()

    # Find affected routes.
    diff_detector = DiffDetector(project_path, info, base=args.base)
    affected = diff_detector.detect()

    # Build output payload.
    payload = {
        "base": args.base,
        "affected_routes": [
            {
                "method": ar.method,
                "path": ar.path,
                "handler": ar.handler,
                "changed_files": ar.changed_files,
                "change_type": ar.change_type,
            }
            for ar in affected
        ],
        "total": len(affected),
    }

    # Console summary.
    if affected:
        print(f"Affected APIs (base: {args.base}):")
        for ar in affected:
            tag = ar.change_type
            # Right-pad method for alignment.
            method = ar.method.ljust(6)
            # Show the shortest changed file name for readability.
            short_files = ", ".join(Path(f).name for f in ar.changed_files)
            handler_label = f" ({ar.handler})" if ar.handler else ""
            print(
                f"  [{tag:8s}] {method} {ar.path}{handler_label} "
                f"\u2190 {short_files}"
            )
        print(f"Total: {len(affected)} affected route(s)")
    else:
        print("No affected API routes detected.")

    # Write JSON output if requested.
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nJSON written to {output_path}")

    # Always print JSON to stdout as well for piping.
    if not sys.stdout.isatty():
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
