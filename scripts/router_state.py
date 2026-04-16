#!/usr/bin/env python3
"""WS3 stub pipeline-state reader.

Public API
----------
    read_pipeline_state(session_id=None, mode="router") -> dict | None

For mode="router": attempts to read the most recent router decision from MCP
state (via state_read mode=router). Returns the stored body dict on success,
or None when MCP is unavailable.

For any OTHER pipeline mode (autopilot, ralph, ultrawork, …): returns the
explicit stub dict per F4 / ADR plan — WS5 has not shipped yet.

CLI
---
    python3 scripts/router_state.py --read [--mode router] [--session-id <id>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Modes that WS5b will eventually populate.  Until then, return the stub.
_PIPELINE_MODES_WS5: frozenset[str] = frozenset({
    "autopilot",
    "ralph",
    "ultrawork",
    "team",
})

_WS5_STUB: dict[str, str] = {
    "status": "unknown",
    "reason": "WS5 not yet shipped",
}


def read_pipeline_state(
    session_id: str | None = None,
    mode: str = "router",
) -> dict | None:
    """Read pipeline state for the given mode.

    - mode="router": reads the most recent WS3 router decision from MCP.
      Returns the body dict, or None if MCP is unavailable / no entry exists.
    - Any other pipeline mode: returns _WS5_STUB (explicit stub per F4).
    """
    if mode in _PIPELINE_MODES_WS5:
        return dict(_WS5_STUB)

    if mode == "router":
        return _read_router_state(session_id=session_id)

    # Unknown mode — also stub
    return dict(_WS5_STUB)


def _read_router_state(session_id: str | None = None) -> dict | None:
    """Attempt to read mode=router from MCP state. Returns None on failure."""
    try:
        return _read_via_mcp(mode="router", session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[router_state] warn: could not read MCP state: {exc}",
            file=sys.stderr,
        )
        return None


def _read_via_mcp(mode: str, session_id: str | None) -> dict | None:
    """Send a state_read JSON-RPC request to the MCP server subprocess."""
    import subprocess
    import uuid

    server_py = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    if not server_py.exists():
        raise FileNotFoundError(f"MCP server not found at {server_py}")

    args: dict[str, Any] = {"mode": mode}
    if session_id:
        args["session_id"] = session_id

    rpc_request = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": "state_read",
            "arguments": args,
        },
    })

    proc = subprocess.run(
        [sys.executable, str(server_py)],
        input=rpc_request,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"MCP server exited {proc.returncode}: {proc.stderr[:200]}"
        )

    # Parse the JSON-RPC response
    try:
        resp = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"Malformed MCP response: {exc}") from exc

    result = resp.get("result", {})
    # MCP state_read returns {"content": [{"type": "text", "text": "<json>"}]}
    content = result.get("content", [])
    if not content:
        return None
    text = content[0].get("text", "")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WS3 stub pipeline-state reader."
    )
    parser.add_argument(
        "--read", action="store_true", required=True,
        help="Read state for the given mode",
    )
    parser.add_argument(
        "--mode", default="router",
        help="State mode to read (default: router)",
    )
    parser.add_argument(
        "--session-id", default=None,
        help="Optional session ID to scope the read",
    )
    args = parser.parse_args(argv)

    result = read_pipeline_state(session_id=args.session_id, mode=args.mode)
    if result is None:
        print(json.dumps({"status": "none", "reason": "no state found"}))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
