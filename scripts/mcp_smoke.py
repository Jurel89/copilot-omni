#!/usr/bin/env python3
"""Smoke-test the MCP server end-to-end with JSON-RPC over stdio."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


def main() -> int:
    assert SERVER.exists(), f"MCP server missing: {SERVER}"

    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "smoke", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "health", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "memory_capture",
                    "arguments": {"scope": "smoke", "content": "hello from CI"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "memory_search",
                    "arguments": {"query": "hello"}}},
    ]
    try:
        out, err = proc.communicate(
            "\n".join(json.dumps(m) for m in msgs) + "\n",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        print("timeout", file=sys.stderr)
        return 1

    lines = [l for l in out.strip().splitlines() if l]
    responses = [json.loads(l) for l in lines]

    # initialize
    init = next(r for r in responses if r.get("id") == 1)
    assert init["result"]["serverInfo"]["name"] == "copilot-omni", init
    assert init["result"]["protocolVersion"] == "2024-11-05"

    # tools/list
    tools = next(r for r in responses if r.get("id") == 2)
    tool_names = {t["name"] for t in tools["result"]["tools"]}
    assert len(tool_names) >= 20, f"too few tools: {len(tool_names)}"
    for required in ("health", "memory_capture", "memory_search",
                     "policy_check", "wiki_write", "state_write"):
        assert required in tool_names, f"missing tool: {required}"

    # tools/call health
    health = next(r for r in responses if r.get("id") == 3)
    assert "content" in health["result"]

    # tools/call memory_capture + memory_search
    cap = next(r for r in responses if r.get("id") == 4)
    assert "content" in cap["result"]
    search = next(r for r in responses if r.get("id") == 5)
    body = json.loads(search["result"]["content"][0]["text"])
    assert body["results"], f"memory_search returned empty: {body}"

    print(f"PASS: {len(tool_names)} tools, {len(responses)} responses OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
