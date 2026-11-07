"""CLI script to inspect and list all registered MCP tools in the Tinkercad server."""

from __future__ import annotations

import sys
from ..server import server


def main() -> None:
    # Ensure stdout handles unicode without crashing on Windows cmd/powershell
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tools = server._tool_manager.list_tools()
    print("=" * 65)
    print(f"  Tinkercad Circuits MCP Server - Registered Tools ({len(tools)})")
    print("=" * 65)
    for idx, t in enumerate(tools, 1):
        doc = (t.description or "").strip().split("\n")[0]
        print(f"{idx:2d}. {t.name:<32} : {doc}")
    print("=" * 65)


if __name__ == "__main__":
    main()

