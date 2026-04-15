#!/usr/bin/env python3
"""Pre-tool-use policy enforcement. stdlib only.

Reads JSON from stdin (Copilot CLI event payload). Returns JSON with
permissionDecision = allow|deny|ask and an optional reason. Fails open
(allow) on any error so we never brick the user.

Policy file lookup order:
  1. $OMNI_POLICY_FILE
  2. <cwd>/.omni/policy-<profile>.json
  3. <plugin_root>/policies/<profile>.json (default: standard)
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_policy() -> Dict[str, Any]:
    policy_default: Dict[str, Any] = {
        "deny_commands": [
            "sudo ",
            "rm -rf /",
            "mkfs",
            "dd if=/dev/zero",
            ":(){ :|:& };:",
        ],
        "protected_paths": [
            ".omni/config.json",
            ".github/copilot-instructions.md",
            ".claude-plugin/plugin.json",
            "AGENTS.md",
        ],
    }
    override = os.environ.get("OMNI_POLICY_FILE")
    candidates = []
    if override:
        candidates.append(Path(override))
    profile = os.environ.get("OMNI_POLICY_PROFILE", "standard")
    cwd = Path(os.getcwd())
    candidates.append(cwd / ".omni" / f"policy-{profile}.json")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        candidates.append(Path(plugin_root) / "policies" / f"{profile}.json")
    for p in candidates:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return policy_default


def _decision(decision: str, reason: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"permissionDecision": decision}
    if reason:
        out["permissionDecisionReason"] = reason
    return out


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    policy = _load_policy()
    tool_name = (event.get("tool_name") or event.get("toolName")
                 or os.environ.get("COPILOT_TOOL_NAME") or "").lower()
    tool_args = event.get("tool_args") or event.get("toolArgs") or {}

    if tool_name in ("shell", "bash"):
        cmd = str(tool_args.get("command", ""))
        try:
            tokens: List[str] = shlex.split(cmd, posix=True)
        except ValueError:
            tokens = cmd.split()
        lower_cmd = cmd.lower()
        token_set = {t.lower() for t in tokens}
        token_basenames = {os.path.basename(t).lower() for t in tokens}
        for pattern in policy.get("deny_commands", []):
            plower = pattern.lower().strip()
            if not plower:
                continue
            if " " in plower:
                # Multi-token pattern: substring match against joined lowercase cmd
                if plower in lower_cmd:
                    sys.stdout.write(json.dumps(_decision(
                        "deny",
                        f"copilot-omni policy: blocked dangerous pattern '{pattern}'",
                    )))
                    return 0
            else:
                # Single-token pattern: match against basename or whole token
                if plower in token_set or plower in token_basenames:
                    sys.stdout.write(json.dumps(_decision(
                        "deny",
                        f"copilot-omni policy: blocked command '{pattern}'",
                    )))
                    return 0

    if tool_name in ("edit", "write", "edit_file"):
        path_raw = str(tool_args.get("file_path") or tool_args.get("path") or "")
        # Normalize path separators and resolve `..` where possible
        try:
            norm = os.path.normpath(path_raw).replace("\\", "/")
        except Exception:
            norm = path_raw.replace("\\", "/")
        lower_norm = norm.lower()
        for protected in policy.get("protected_paths", []):
            if not protected:
                continue
            prot_norm = protected.replace("\\", "/").lower()
            if prot_norm in lower_norm:
                sys.stdout.write(json.dumps(_decision(
                    "deny",
                    f"copilot-omni policy: protected path '{protected}' — edit via `omni init` instead",
                )))
                return 0

    sys.stdout.write(json.dumps(_decision("allow")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
