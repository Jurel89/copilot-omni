#!/usr/bin/env python3
"""Pre-tool-use policy enforcement. stdlib only.

Reads JSON from stdin (Copilot CLI event payload). Returns JSON with
permissionDecision = allow|deny|ask and an optional reason. Fails open
(allow) on any error so we never brick the user.

Policy file lookup order:
  1. $OMNI_POLICY_FILE
  2. <cwd>/.omni/policy-<profile>.json
  3. <plugin_root>/policies/<profile>.json (default: standard)

Kill switches (checked first, before any imports):
  OMNI_SKIP_HOOKS=1         — disable all hooks (canonical)
  DISABLE_OMNI=1            — disable all hooks (canonical alternate)
  OMC_SKIP_HOOKS=1          — legacy alias, deprecated, removed in v3.0.0
  DISABLE_OMC=1             — legacy alias, deprecated, removed in v3.0.0
  OMNI_SKIP_PRE_TOOL_USE=1  — disable only this hook

shlex tokenisation note:
  The hook always uses shlex.split(raw, posix=True).  On ValueError (e.g.
  unclosed quotes), the raw input is treated as a single opaque token rather
  than falling back to str.split().  This prevents quote-injection bypasses
  where a malicious command like "rm'-rf /" would not match the "rm" deny
  pattern under naive split().
"""
from __future__ import annotations

import sys
import os as _os

# ---------------------------------------------------------------------------
# Kill-switch: evaluated before any expensive imports.
# _hook_lib is imported inline so the fast path (kill-switch active) incurs
# minimal overhead.
# ---------------------------------------------------------------------------
_HOOK_NAME = "pre_tool_use"

# Fast path using raw env lookup (avoids importing _hook_lib on the hot path)
def _quick_disabled() -> bool:
    env = _os.environ
    if env.get("DISABLE_OMNI") or env.get("OMNI_SKIP_HOOKS"):
        return True
    if env.get("DISABLE_OMC") or env.get("OMC_SKIP_HOOKS"):
        # Lazy import to emit deprecation warning
        import importlib.util as _iu
        _lib_path = _os.path.join(_os.path.dirname(__file__), "_hook_lib.py")
        _spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
        if _spec and _spec.loader:
            _mod = _iu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _mod._deprecation_warn()
        return True
    if env.get("OMNI_SKIP_PRE_TOOL_USE"):
        return True
    return False

if _quick_disabled():
    sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)

import json
import os
import shlex
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List


def _nfc(s: str) -> str:
    """Return *s* in Unicode NFC form.

    Guard against macOS/Windows filesystem normalisation mismatches: a path can
    be received in NFD (decomposed) form while the policy entries are written
    in NFC (composed). Without normalisation the substring match below misses
    and a protected path is allowed through.
    """
    try:
        return unicodedata.normalize("NFC", s)
    except Exception:
        return s

# Import shared hook library
import importlib.util as _iu
_lib_path = os.path.join(os.path.dirname(__file__), "_hook_lib.py")
_spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_append_audit = _mod._append_audit
_write_metric = _mod._write_metric


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
    # OMNI_PLUGIN_ROOT (primary) > CLAUDE_PLUGIN_ROOT (legacy fallback)
    plugin_root = os.environ.get("OMNI_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
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


# ---------------------------------------------------------------------------
# Phase-C C25: router-decision enforcement (advisory → enforced).
# ---------------------------------------------------------------------------

# Tools that are exempt from enforcement: these are the ways the user
# *takes* the redirect or manages the session around it. Without the
# allowlist a redirect would pin every subsequent action.
_ROUTER_EXEMPT_TOOLS = frozenset({
    "",                        # unknown / non-routed tool
    "deep_interview",
    "deep-interview",
    "ask",                     # interview UX uses read-only tools
    "state_read",
    "state_write",
    "state_clear",
    "health",
    "doctor",
    "memory_search",
    "memory_capture",
    "notepad_read",
    "notepad_write",
    "router",
})


def _router_enforce_deny() -> Dict[str, Any] | None:
    """Return a deny-decision if the last router verdict was 'redirect'
    and OMNI_ROUTER_ENFORCE=1 and the current tool isn't exempt.

    Returns None when enforcement does not apply.
    """
    if os.environ.get("OMNI_ROUTER_ENFORCE", "").strip().lower() not in ("1", "true", "yes"):
        return None
    sentinel = Path(os.getcwd()) / ".omni" / "cache" / "router-last.json"
    if not sentinel.exists():
        return None
    try:
        data = json.loads(sentinel.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("decision") != "redirect":
        return None
    return {
        "reason": (
            "copilot-omni router (OMNI_ROUTER_ENFORCE=1): last prompt was "
            f"classified vague (score={data.get('score', 0.0)}). Take the "
            f"{data.get('redirect_to') or 'deep-interview'} redirect or add "
            "--skip-interview to the prompt."
        ),
    }


def main() -> int:
    t_start = time.monotonic()
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    policy = _load_policy()
    tool_name = (event.get("tool_name") or event.get("toolName")
                 or os.environ.get("COPILOT_TOOL_NAME") or "").lower()
    tool_args = event.get("tool_args") or event.get("toolArgs") or {}

    action = "allow"
    reason = ""

    # Phase-C C25: router enforcement gate. Runs before policy checks so the
    # operator gets one unambiguous reason back (router, not policy).
    if tool_name not in _ROUTER_EXEMPT_TOOLS:
        router_block = _router_enforce_deny()
        if router_block is not None:
            result = _decision("deny", router_block["reason"])
            sys.stdout.write(json.dumps(result))
            _append_audit({
                "hook": _HOOK_NAME,
                "event_name": "pre_tool_use",
                "tool_name": tool_name,
                "prompt_excerpt": "",
                "action": "deny",
                "reason": router_block["reason"],
            })
            _write_metric("hook_exit_code", 0,
                          {"hook": _HOOK_NAME, "action": "deny",
                           "cause": "router_enforce"})
            _write_metric("hook_latency_ms",
                          round((time.monotonic() - t_start) * 1000, 2),
                          {"hook": _HOOK_NAME})
            return 0

    if tool_name in ("shell", "bash"):
        cmd = str(tool_args.get("command", ""))
        # Always use shlex.split with posix=True.
        # On ValueError (e.g. unclosed quote), treat entire input as a single
        # opaque token — this is the safe default that prevents quote-injection
        # bypasses (audit finding 2.1).
        try:
            tokens: List[str] = shlex.split(cmd, posix=True)
        except ValueError:
            # Malformed shell input (e.g. unclosed quote): DENY immediately.
            # Plan §2.WS7 contract: ValueError → DENY.
            # Falling through to allow would violate the security contract because
            # a crafted malformed command could bypass deny-pattern matching.
            reason = "copilot-omni policy: malformed-shell-command (unclosed quote or invalid syntax)"
            result = _decision("deny", reason)
            sys.stdout.write(json.dumps(result))
            _append_audit({
                "hook": _HOOK_NAME,
                "event_name": "pre_tool_use",
                "tool_name": tool_name,
                "prompt_excerpt": cmd[:120],
                "action": "deny",
                "reason": reason,
            })
            _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "action": "deny"})
            _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                          {"hook": _HOOK_NAME})
            return 0
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
                    action = "deny"
                    reason = f"copilot-omni policy: blocked dangerous pattern '{pattern}'"
                    result = _decision("deny", reason)
                    sys.stdout.write(json.dumps(result))
                    _append_audit({
                        "hook": _HOOK_NAME,
                        "event_name": "pre_tool_use",
                        "tool_name": tool_name,
                        "prompt_excerpt": cmd[:120],
                        "action": "deny",
                        "reason": reason,
                    })
                    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "action": "deny"})
                    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                                  {"hook": _HOOK_NAME})
                    return 0
            else:
                # Single-token pattern: match against basename or whole token
                if plower in token_set or plower in token_basenames:
                    action = "deny"
                    reason = f"copilot-omni policy: blocked command '{pattern}'"
                    result = _decision("deny", reason)
                    sys.stdout.write(json.dumps(result))
                    _append_audit({
                        "hook": _HOOK_NAME,
                        "event_name": "pre_tool_use",
                        "tool_name": tool_name,
                        "prompt_excerpt": cmd[:120],
                        "action": "deny",
                        "reason": reason,
                    })
                    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "action": "deny"})
                    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                                  {"hook": _HOOK_NAME})
                    return 0

    if tool_name in ("edit", "write", "edit_file", "multi_edit",
                     "multiedit", "patch", "apply_patch",
                     "str_replace_editor", "create_file"):
        path_raw = str(tool_args.get("file_path") or tool_args.get("path") or "")
        # Normalize path separators and resolve `..` where possible.
        # Apply Unicode NFC normalisation so a decomposed (NFD) path can't
        # bypass a composed (NFC) protected-path entry.
        try:
            norm = os.path.normpath(path_raw).replace("\\", "/")
        except Exception:
            norm = path_raw.replace("\\", "/")
        lower_norm = _nfc(norm).lower()
        for protected in policy.get("protected_paths", []):
            if not protected:
                continue
            prot_norm = _nfc(protected.replace("\\", "/")).lower()
            if prot_norm in lower_norm:
                action = "deny"
                reason = f"copilot-omni policy: protected path '{protected}' — edit via `omni init` instead"
                result = _decision("deny", reason)
                sys.stdout.write(json.dumps(result))
                _append_audit({
                    "hook": _HOOK_NAME,
                    "event_name": "pre_tool_use",
                    "tool_name": tool_name,
                    "prompt_excerpt": path_raw[:120],
                    "action": "deny",
                    "reason": reason,
                })
                _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "action": "deny"})
                _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                              {"hook": _HOOK_NAME})
                return 0

    sys.stdout.write(json.dumps(_decision("allow")))
    _append_audit({
        "hook": _HOOK_NAME,
        "event_name": "pre_tool_use",
        "tool_name": tool_name,
        "prompt_excerpt": "",
        "action": "allow",
        "reason": "",
    })
    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "action": "allow"})
    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                  {"hook": _HOOK_NAME})
    return 0


if __name__ == "__main__":
    sys.exit(main())
