"""End-to-end check: launch src/server.py over stdio and drive it as a real
MCP client would. Verifies the handshake, the tool list, and one tool call of
each kind -- including that a destructive query is refused.

    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "src", "server.py")


def text_of(result) -> str:
    return "\n".join(
        c.text for c in result.content if getattr(c, "type", None) == "text"
    )


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[SERVER])
    failures: list[str] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            # mcp 2.x uses snake_case on result models (was serverInfo in 1.x).
            info = init.server_info
            print(f"handshake  : {info.name} v{info.version}")

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools      : {names}")
            for expected in ("describe_schema", "find_team", "query"):
                if expected not in names:
                    failures.append(f"missing tool {expected}")

            schema = text_of(await session.call_tool("describe_schema", {}))
            print(f"schema     : {len(schema)} chars, "
                  f"mentions team_match_form={'team_match_form' in schema}")
            if "team_match_form" not in schema:
                failures.append("schema does not document team_match_form")

            resolved = text_of(await session.call_tool(
                "find_team", {"name": "Manchester United"}))
            print(f"find_team  : {'Man United' in resolved}")
            if "Man United" not in resolved:
                failures.append("find_team failed to resolve Manchester United")

            q = text_of(await session.call_tool("query", {
                "sql": "SELECT team, sum(corners) c FROM team_match_form "
                       "GROUP BY team ORDER BY c DESC",
                "max_rows": 3,
            }))
            print("query      :", q.replace("\n", " ")[:80])
            if "Arsenal" not in q:
                failures.append("query returned unexpected result")

            refused = text_of(await session.call_tool("query", {
                "sql": "DROP TABLE raw_matches"}))
            print(f"guard      : refused={refused.startswith('Query rejected')}")
            if not refused.startswith("Query rejected"):
                failures.append("destructive query was NOT refused")

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
