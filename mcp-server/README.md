# AI API Tester - MCP Server

MCP (Model Context Protocol) server that exposes AI API Tester functionality as tools. Any MCP-compatible IDE or client (Claude Desktop, VS Code, Cursor) can use these tools to analyze source code, generate API test cases, execute tests, and triage failures.

## Configuration

Add the following to your MCP client configuration:

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ai-api-tester": {
      "command": "python",
      "args": ["path/to/mcp-server/server.py"]
    }
  }
}
```

**VS Code / Cursor** (`.vscode/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "ai-api-tester": {
      "command": "python",
      "args": ["path/to/mcp-server/server.py"]
    }
  }
}
```

Replace `path/to/mcp-server/server.py` with the absolute path to `server.py` on your machine.

## Available Tools

| Tool | Description |
|------|-------------|
| `detect_project` | Detect project language and framework from source code |
| `locate_api` | Find source files that implement a given API URL |
| `gen_context` | Generate test context JSON with code analysis, git risk, and schema constraints |
| `validate_cases` | Validate YAML test cases without executing HTTP requests |
| `run_tests` | Execute YAML test suite and generate report |
| `analyze_failures` | Classify test failures as env_issue, test_issue, or probable_bug |
| `diff_detect` | Detect APIs affected by recent git changes |
| `heal_cases` | Detect stale, broken, or outdated test cases |
| `risk_analysis` | Analyze Git-based risk score for an API endpoint |
| `auto_pipeline` | One-command pipeline: detect routes and generate test contexts |

## Prerequisites

- Python 3.8+
- `requests`
- `pyyaml`

Install dependencies:

```bash
pip install requests pyyaml
```
