#!/usr/bin/env python3
"""Generate test context JSON from source code analysis."""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.locator import CodeLocator
from ai_api_tester.analyzer import GitAnalyzer, SchemaAnalyzer
from ai_api_tester.source_analyzer import SourceAnalyzer


def main():
    parser = argparse.ArgumentParser(description="Generate test context")
    parser.add_argument("url", help="API URL path")
    parser.add_argument("project", help="Project root path")
    parser.add_argument("--method", "-m", default="POST", help="HTTP method")
    parser.add_argument("--output", "-o", default=None, help="Output path")
    args = parser.parse_args()

    detector = ProjectDetector(args.project)
    info = detector.detect()

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"No files found matching '{args.url}'")
        sys.exit(1)

    git_analyzer = GitAnalyzer(args.project)
    risk_info = git_analyzer.analyze_risk([f.path for f in ctx.files])

    schema_analyzer = SchemaAnalyzer(args.project, info.language)
    model_files = [f.path for f in ctx.files if f.role in ("model", "mapper")]
    constraints = schema_analyzer.analyze_entity(model_files)
    source_analyzer = SourceAnalyzer(args.project, info)
    test_basis = source_analyzer.analyze(ctx)

    output = {
        "project": {"language": info.language, "framework": info.framework},
        "api": {"url": args.url, "method": args.method or "unknown"},
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

    # Merge risk_profile if available (from historical learning)
    risk_profile_path = Path(args.project) / "test-output" / "risk_profile.json"
    if risk_profile_path.exists():
        try:
            risk_profile = json.loads(risk_profile_path.read_text(encoding="utf-8"))
            output["risk_profile"] = risk_profile
        except (json.JSONDecodeError, OSError):
            pass

    output_path = args.output or f"tests/{args.url.strip('/').replace('/', '_')}_context.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )
    print(f"Context saved to: {output_path}")


if __name__ == "__main__":
    main()
