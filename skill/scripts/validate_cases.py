#!/usr/bin/env python3
"""Validate an AI API Tester YAML suite without executing HTTP requests."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from ai_api_tester.schema import validate_suite


def main():
    parser = argparse.ArgumentParser(description="Validate YAML test case suite")
    parser.add_argument("yaml_file", help="YAML test case file")
    args = parser.parse_args()

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

    print("YAML validation passed.")


if __name__ == "__main__":
    main()
