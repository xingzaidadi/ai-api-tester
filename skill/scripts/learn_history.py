#!/usr/bin/env python3
"""Learn from historical test results and generate risk profile."""

import sys
import io
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.history_learner import HistoryLearner, profile_to_dict


def _rate_icon(rate: float) -> str:
    if rate > 0.30:
        return "\u274c"   # red cross
    if rate > 0.15:
        return "\u26a0\ufe0f"   # warning
    return "\u2705"       # green check


def main():
    parser = argparse.ArgumentParser(description="Learn from historical test results and generate risk profile")
    parser.add_argument("output_dir", help="Path to test-output/ directory containing historical results")
    parser.add_argument("--save", "-s", default=None, help="Path to write risk_profile.json (default: {output_dir}/risk_profile.json)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        print(f"Directory not found: {output_dir}")
        sys.exit(1)

    learner = HistoryLearner(str(output_dir))
    profile = learner.learn()

    if profile.report_count == 0:
        print("No report.json files found in the specified directory.")
        sys.exit(1)

    # --- Console output --------------------------------------------------
    print(f"\nHistorical Analysis ({profile.report_count} reports, {profile.total_cases} cases):\n")

    # Dimension risk
    print("Dimension Risk:")
    for ds in profile.dimension_stats:
        icon = _rate_icon(ds.failure_rate)
        pct = int(round(ds.failure_rate * 100))
        print(f"  {icon} {ds.dimension + ':':.<28s} {pct:>3d}% failure rate ({ds.failed}/{ds.total})")
    print()

    # Hot modules
    if profile.hot_modules:
        print("Hot Modules (bug density):")
        for i, ms in enumerate(profile.hot_modules, 1):
            print(f"  {i}. {ms.module:<32s} -- {ms.total_bugs} bugs / {ms.total_cases} cases ({ms.bug_density:.2f})")
        print()

    # Recommendations
    if profile.recommendations:
        print("Recommendations:")
        for rec in profile.recommendations:
            print(f"  \u2022 {rec}")
        print()

    # --- Save ------------------------------------------------------------
    save_path = args.save or str(output_dir / "risk_profile.json")
    learner.save(profile, save_path)
    print(f"Risk profile saved to: {save_path}")


if __name__ == "__main__":
    main()
