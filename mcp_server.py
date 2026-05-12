"""Entry point for `ai-tester-mcp` console script."""

import runpy
import sys
from pathlib import Path

def main():
    """Run the MCP server."""
    server_path = Path(__file__).resolve().parent / "mcp-server" / "server.py"
    sys.argv = [str(server_path)]
    runpy.run_path(str(server_path), run_name="__main__")


if __name__ == "__main__":
    main()
