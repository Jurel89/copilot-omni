#!/usr/bin/env python3
"""Post-tool-use hook — best-effort audit log. Never blocks.

Kill switches:
  OMNI_SKIP_HOOKS=1          — disable all hooks (canonical)
  DISABLE_OMNI=1             — disable all hooks (canonical alternate)
  OMC_SKIP_HOOKS=1           — legacy alias, deprecated, removed in v3.0.0
  DISABLE_OMC=1              — legacy alias, deprecated, removed in v3.0.0
  OMNI_SKIP_POST_TOOL_USE=1  — disable only this hook
"""
from __future__ import annotations

import sys
import os as _os

_HOOK_NAME = "post_tool_use"


def _quick_disabled() -> bool:
    env = _os.environ
    if env.get("DISABLE_OMNI") or env.get("OMNI_SKIP_HOOKS"):
        return True
    if env.get("DISABLE_OMC") or env.get("OMC_SKIP_HOOKS"):
        import importlib.util as _iu
        _lib_path = _os.path.join(_os.path.dirname(__file__), "_hook_lib.py")
        _spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
        if _spec and _spec.loader:
            _mod = _iu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _mod._deprecation_warn()
        return True
    if env.get("OMNI_SKIP_POST_TOOL_USE"):
        return True
    return False


if _quick_disabled():
    sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)

import json
import os
import time
from pathlib import Path

import importlib.util as _iu
_lib_path = os.path.join(os.path.dirname(__file__), "_hook_lib.py")
_spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_append_audit = _mod._append_audit
_write_metric = _mod._write_metric


def main() -> int:
    t_start = time.monotonic()
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        event = {}

    tool_name = event.get("tool_name") or event.get("toolName") or ""
    status = event.get("status", "completed")

    # Atomic audit record via file-locked append (audit finding 3.1)
    _append_audit({
        "hook": _HOOK_NAME,
        "event_name": "post_tool_use",
        "tool_name": tool_name,
        "prompt_excerpt": "",
        "action": "log",
        "reason": status,
    })

    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME})
    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                  {"hook": _HOOK_NAME})

    sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
