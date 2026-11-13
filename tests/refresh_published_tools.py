"""Refresh tests/published_tools.json from the published servers.

Run in an environment where the five Python packages are installed (pip install k11-release-gate-mcp
k11-selenium-qa-mcp k11-api-contract-qa-mcp k11-api-functional-qa-mcp k11-llm-assure-mcp) and Node is on PATH:

    python tests/refresh_published_tools.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent
BIN = Path(sys.executable).parent


def exe(name: str) -> str:
    found = shutil.which(name, path=str(BIN)) or shutil.which(name)
    if not found:
        sys.exit(f"{name} not found; install the published packages first")
    return found


SERVERS = {
    "release-gate": ("k11-release-gate-mcp", []),
    "selenium-qa": ("k11-selenium-qa-mcp", []),
    "api-contract-qa": ("k11-api-contract-qa-mcp", []),
    "api-functional-qa": ("k11-api-functional-qa-mcp", []),
    "llm-assure": ("k11-llm-assure-mcp", []),
    "playwright-qa": ("npx", ["-y", "k11-playwright-qa-mcp"]),
}


async def tools(cmd: str, args: list[str]):
    params = StdioServerParameters(command=exe(cmd), args=args, env={**os.environ, "QA_MCP_ROOT": str(HERE)})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            info = await s.initialize()
            return info.serverInfo.version, sorted(t.name for t in (await s.list_tools()).tools)


async def main():
    out = {}
    for name, (cmd, args) in SERVERS.items():
        version, names = await tools(cmd, args)
        out[name] = {"version": version, "tools": names}
        print(f"{name:18} {version:8} {len(names)} tools")
    (HERE / "published_tools.json").write_text(json.dumps(out, indent=2) + "\n")


anyio.run(main)
