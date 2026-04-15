#!/usr/bin/env python3
"""Subagent helper — invoke a specialized agent via `copilot -p ... --agent <name>`.

This is the Copilot-CLI equivalent of Claude Code's `Task(subagent_type=...)`.
Ported skills call this module to spawn an agent and capture its output.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def run_agent(name: str, prompt: str,
              allow_all: Optional[bool] = None,
              model: Optional[str] = None,
              timeout: int = 1800) -> int:
    copilot = shutil.which("copilot")
    if not copilot:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2
    if allow_all is None:
        # Default OFF unless OMNI_SUBAGENT_ALLOW_ALL=1 — corporate-safe default
        allow_all = _env_bool("OMNI_SUBAGENT_ALLOW_ALL", False)
    cmd = [copilot, "-p", prompt, "--agent", name]
    if allow_all:
        cmd.append("--allow-all")
    if model:
        cmd.extend(["--model", model])
    try:
        result = subprocess.run(cmd, timeout=timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"error: agent {name!r} timed out after {timeout}s", file=sys.stderr)
        return 124


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Copilot Omni subagent")
    parser.add_argument("name", help="Agent name (matches agents/<name>.md)")
    parser.add_argument("prompt", help="Task prompt to send the agent")
    parser.add_argument("--model", default=None)
    parser.add_argument("--allow-all", dest="allow_all", action="store_true",
                        help="Pass --allow-all to the spawned copilot session")
    parser.add_argument("--no-allow-all", dest="allow_all", action="store_false",
                        help="Require the spawned session to ask for permissions (default)")
    parser.set_defaults(allow_all=None)
    args = parser.parse_args()
    return run_agent(args.name, args.prompt,
                     allow_all=args.allow_all,
                     model=args.model)


if __name__ == "__main__":
    sys.exit(main())
