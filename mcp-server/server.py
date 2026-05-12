#!/usr/bin/env python3
"""MCP Server for AI API Tester - exposes testing tools via Model Context Protocol."""

import sys
import json
import subprocess
from pathlib import Path
from typing import Any

# The scripts directory relative to this server
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skill" / "scripts"

TOOLS = [
    {
        "name": "detect_project",
        "description": "Detect project language and framework from source code",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to project root"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "locate_api",
        "description": "Find source code files that implement a given API URL",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API URL path (e.g. /api/v1/orders)"},
                "project_path": {"type": "string", "description": "Path to project root"},
                "method": {"type": "string", "description": "HTTP method", "default": "POST"}
            },
            "required": ["url", "project_path"]
        }
    },
    {
        "name": "gen_context",
        "description": "Generate test context JSON with code analysis, git risk, and schema constraints",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API URL path"},
                "project_path": {"type": "string", "description": "Path to project root"},
                "method": {"type": "string", "description": "HTTP method", "default": "POST"},
                "output": {"type": "string", "description": "Output file path"}
            },
            "required": ["url", "project_path"]
        }
    },
    {
        "name": "validate_cases",
        "description": "Validate YAML test cases without executing HTTP requests",
        "inputSchema": {
            "type": "object",
            "properties": {
                "yaml_file": {"type": "string", "description": "Path to YAML test case file"}
            },
            "required": ["yaml_file"]
        }
    },
    {
        "name": "run_tests",
        "description": "Execute YAML test suite and generate report",
        "inputSchema": {
            "type": "object",
            "properties": {
                "yaml_file": {"type": "string", "description": "Path to YAML test case file"},
                "env_file": {"type": "string", "description": "Environment config file path"},
                "report": {"type": "string", "description": "Report output path"}
            },
            "required": ["yaml_file"]
        }
    },
    {
        "name": "analyze_failures",
        "description": "Classify test failures from report JSON (env_issue, test_issue, probable_bug)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_file": {"type": "string", "description": "Path to report.json"},
                "context_file": {"type": "string", "description": "Optional context.json for richer analysis"},
                "output": {"type": "string", "description": "Output path for analysis JSON"}
            },
            "required": ["report_file"]
        }
    },
    {
        "name": "diff_detect",
        "description": "Detect APIs affected by recent git changes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to project root"},
                "base": {"type": "string", "description": "Base git ref for diff", "default": "HEAD~1"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "heal_cases",
        "description": "Detect stale, broken, or outdated test cases",
        "inputSchema": {
            "type": "object",
            "properties": {
                "yaml_file": {"type": "string", "description": "Path to YAML test cases"},
                "project_path": {"type": "string", "description": "Path to project root"},
                "output": {"type": "string", "description": "Output path for heal report"}
            },
            "required": ["yaml_file", "project_path"]
        }
    },
    {
        "name": "risk_analysis",
        "description": "Analyze Git-based risk score for an API endpoint",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API URL path"},
                "project_path": {"type": "string", "description": "Path to project root"},
                "method": {"type": "string", "description": "HTTP method", "default": "POST"}
            },
            "required": ["url", "project_path"]
        }
    },
    {
        "name": "auto_pipeline",
        "description": "One-command pipeline: detect all routes and generate test contexts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to project root"},
                "url": {"type": "string", "description": "Single API URL (omit for batch mode)"},
                "method": {"type": "string", "description": "HTTP method", "default": "POST"},
                "output_dir": {"type": "string", "description": "Output directory", "default": "./test-output"}
            },
            "required": ["project_path"]
        }
    }
]

TOOL_SCRIPTS = {
    "detect_project": ("detect.py", lambda args: [args["project_path"]]),
    "locate_api": ("locate.py", lambda args: [args["url"], args["project_path"]] + (["--method", args["method"]] if args.get("method") else [])),
    "gen_context": ("gen_context.py", lambda args: [args["url"], args["project_path"]] + (["--method", args["method"]] if args.get("method") else []) + (["--output", args["output"]] if args.get("output") else [])),
    "validate_cases": ("validate_cases.py", lambda args: [args["yaml_file"]]),
    "run_tests": ("run_tests.py", lambda args: [args["yaml_file"]] + (["--env-file", args["env_file"]] if args.get("env_file") else []) + (["--report", args["report"]] if args.get("report") else [])),
    "analyze_failures": ("analyze_failures.py", lambda args: [args["report_file"]] + (["--context-json", args["context_file"]] if args.get("context_file") else []) + (["--output", args["output"]] if args.get("output") else [])),
    "diff_detect": ("diff_detect.py", lambda args: [args["project_path"]] + (["--base", args["base"]] if args.get("base") else [])),
    "heal_cases": ("heal.py", lambda args: [args["yaml_file"], args["project_path"]] + (["--output", args["output"]] if args.get("output") else [])),
    "risk_analysis": ("risk.py", lambda args: [args["url"], args["project_path"]] + (["--method", args["method"]] if args.get("method") else [])),
    "auto_pipeline": ("auto.py", lambda args: [args["project_path"]] + (["--url", args["url"]] if args.get("url") else []) + (["--method", args["method"]] if args.get("method") else []) + (["--output-dir", args["output_dir"]] if args.get("output_dir") else [])),
}


def make_response(request_id: Any, result: dict) -> dict:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id: Any, code: int, message: str) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_initialize(request_id: Any, _params: dict) -> dict:
    """Handle the initialize handshake."""
    return make_response(request_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "ai-api-tester", "version": "0.1.0"}
    })


def handle_tools_list(request_id: Any, _params: dict) -> dict:
    """Return the list of available tools."""
    return make_response(request_id, {"tools": TOOLS})


def handle_tools_call(request_id: Any, params: dict) -> dict:
    """Dispatch a tool call to the corresponding script."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in TOOL_SCRIPTS:
        return make_error(request_id, -32602, f"Unknown tool: {tool_name}")

    script_file, build_args = TOOL_SCRIPTS[tool_name]
    script_path = SCRIPTS_DIR / script_file

    if not script_path.exists():
        return make_error(request_id, -32603, f"Script not found: {script_path}")

    try:
        cmd_args = build_args(arguments)
    except KeyError as exc:
        return make_error(request_id, -32602, f"Missing required argument: {exc}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + cmd_args,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return make_response(request_id, {
            "content": [{"type": "text", "text": "Error: script timed out after 300 seconds"}],
            "isError": True,
        })
    except Exception as exc:
        return make_response(request_id, {
            "content": [{"type": "text", "text": f"Error launching script: {exc}"}],
            "isError": True,
        })

    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip() or f"Script exited with code {result.returncode}"
        return make_response(request_id, {
            "content": [{"type": "text", "text": error_text}],
            "isError": True,
        })

    return make_response(request_id, {
        "content": [{"type": "text", "text": result.stdout}],
    })


def handle_request(request: dict) -> dict | None:
    """Route a JSON-RPC request to the appropriate handler."""
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params", {})

    # Notifications (no id) don't require a response
    if request_id is None:
        return None

    handlers = {
        "initialize": handle_initialize,
        "tools/list": handle_tools_list,
        "tools/call": handle_tools_call,
    }

    handler = handlers.get(method)
    if handler is None:
        return make_error(request_id, -32601, f"Method not found: {method}")

    return handler(request_id, params)


def main():
    """MCP Server main loop - reads JSON-RPC from stdin, writes to stdout."""
    # Ensure stderr is used for any debug/log output so stdout stays clean
    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            error_resp = make_error(None, -32700, f"Parse error: {exc}")
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
