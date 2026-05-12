#!/usr/bin/env python3
"""Detect project language and framework."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector


def main():
    if len(sys.argv) < 2:
        print("Usage: detect.py <project_path>")
        sys.exit(1)

    project_path = sys.argv[1]
    detector = ProjectDetector(project_path)
    info = detector.detect()

    print(f"language: {info.language}")
    print(f"framework: {info.framework}")
    print(f"entry_dirs: {info.entry_dirs}")
    print(f"file_ext: {info.file_ext}")


if __name__ == "__main__":
    main()
