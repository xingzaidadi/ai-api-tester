#!/usr/bin/env python3
"""Initialize ai-api-tester for a project — zero-friction onboarding."""

import sys
import io
import os
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_api_tester.detector import ProjectDetector
from ai_api_tester.route_extractor import RouteExtractor


def _has_auth_routes(routes) -> bool:
    """Check if any route path or handler suggests authentication."""
    auth_keywords = ("auth", "login", "token", "oauth", "session", "jwt", "bearer")
    for route in routes:
        combined = f"{route.path} {route.handler}".lower()
        if any(kw in combined for kw in auth_keywords):
            return True
    return False


def _generate_env_yaml(framework: str, has_auth: bool) -> str:
    """Generate the env.yaml template content."""
    lines = [
        "# AI API Tester - Environment Configuration",
        f"# Generated for: {framework} project",
        "# Modify values below to match your test environment.",
        "",
        "# Base URL of the API server (required)",
        'base_url: "http://localhost:8080"',
    ]

    if has_auth:
        lines += [
            "",
            "# Authentication tokens (fill in your test tokens)",
            'auth_token: "your-test-token-here"',
            'admin_token: "your-admin-token-here"',
            'user_b_token: "your-user-b-token-here"',
        ]

    lines += [
        "",
        "# Request settings",
        "request_timeout: 30",
        "",
    ]

    return "\n".join(lines)


_GITIGNORE_CONTENT = """\
# AI API Tester outputs
*.json
*.html
!env.yaml
"""


def _print_onboarding(project_info, route_count: int, output_dir: Path, env_file: Path):
    """Print the onboarding guide with next steps."""
    rel_output = os.path.relpath(output_dir)
    rel_env = os.path.relpath(env_file)

    # Normalize to forward slashes for display
    rel_output = rel_output.replace("\\", "/")
    rel_env = rel_env.replace("\\", "/")

    # Ensure paths start with ./
    if not rel_output.startswith("."):
        rel_output = "./" + rel_output
    if not rel_env.startswith("."):
        rel_env = "./" + rel_env

    # Ensure output dir ends with /
    if not rel_output.endswith("/"):
        rel_output += "/"

    print(f"""
\u2705 AI API Tester initialized!

Project:     {project_info.language} / {project_info.framework}
APIs found:  {route_count} routes
Output dir:  {rel_output}
Env config:  {rel_env}

Next steps:
  1. Edit {rel_env} with your test environment values
  2. Generate & run tests:
     \u2022 All APIs:    "\u5e2e\u6211\u6d4b\u8fd9\u4e2a\u9879\u76ee\u7684\u6240\u6709\u63a5\u53e3"
     \u2022 Single API:  "\u5e2e\u6211\u6d4b POST /api/v1/orders"
     \u2022 Changes only: "\u5e2e\u6211\u6d4b\u8fd9\u6b21\u6539\u52a8\u6d89\u53ca\u7684\u63a5\u53e3"
  3. Or use CLI directly:
     python scripts/auto.py . --validate-only    # List routes
     python scripts/auto.py . --output-dir {rel_output}  # Gen contexts

Tips:
  \u2022 Run 'python scripts/diff_detect.py . --base main' to see affected APIs
  \u2022 Run 'python scripts/dashboard.py {rel_output}' to view test history
  \u2022 CI templates available in ci-templates/ directory
""")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize ai-api-tester for a project."
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=".",
        help="Project root path (default: current directory)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Where to put test outputs (default: {project}/test-output)",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Where to write env template (default: {output-dir}/env.yaml)",
    )
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    output_dir = Path(args.output_dir) if args.output_dir else project_path / "test-output"
    output_dir = output_dir.resolve()
    env_file = Path(args.env_file) if args.env_file else output_dir / "env.yaml"
    env_file = env_file.resolve()

    # ------------------------------------------------------------------
    # 1. Detect project
    # ------------------------------------------------------------------
    print(f"Detecting project at: {project_path}")
    detector = ProjectDetector(str(project_path))
    project_info = detector.detect()
    print(f"  Language:  {project_info.language}")
    print(f"  Framework: {project_info.framework}")

    # ------------------------------------------------------------------
    # 2. Extract routes
    # ------------------------------------------------------------------
    extractor = RouteExtractor(str(project_path), project_info)
    routes = extractor.extract()
    route_count = len(routes)
    print(f"  APIs found: {route_count} routes")

    already_initialized = env_file.exists()
    if already_initialized:
        print(f"\n\u26a0\ufe0f  env.yaml already exists at {env_file}, skipping generation.")

    # ------------------------------------------------------------------
    # 3. Create output directory
    # ------------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 4. Generate env.yaml (skip if exists)
    # ------------------------------------------------------------------
    if not already_initialized:
        has_auth = _has_auth_routes(routes)
        env_content = _generate_env_yaml(project_info.framework, has_auth)
        env_file.write_text(env_content, encoding="utf-8")
        print(f"  Created: {env_file}")

    # ------------------------------------------------------------------
    # 5. Generate .gitignore for test-output
    # ------------------------------------------------------------------
    gitignore_path = output_dir / ".gitignore"
    gitignore_path.write_text(_GITIGNORE_CONTENT, encoding="utf-8")

    # ------------------------------------------------------------------
    # 6. Print onboarding guide
    # ------------------------------------------------------------------
    _print_onboarding(project_info, route_count, output_dir, env_file)


if __name__ == "__main__":
    main()
