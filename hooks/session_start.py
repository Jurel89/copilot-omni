#!/usr/bin/env python3
"""Session start hook — emits a computed banner and checks policy file permissions.

Banner is cached in .omni/cache/banner.json keyed by project tree hash.
If the cache is stale (tree hash changed), the banner is recomputed.

Kill switches:
  OMNI_SKIP_HOOKS=1        — disable all hooks (canonical)
  DISABLE_OMNI=1           — disable all hooks (canonical alternate)
  OMC_SKIP_HOOKS=1         — legacy alias, deprecated, removed in v3.0.0
  DISABLE_OMC=1            — legacy alias, deprecated, removed in v3.0.0
  OMNI_SKIP_SESSION_START=1 — disable only this hook
"""
from __future__ import annotations

import sys
import os as _os

_HOOK_NAME = "session_start"


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
    if env.get("OMNI_SKIP_SESSION_START"):
        return True
    return False


if _quick_disabled():
    sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)

import hashlib
import json
import os
import stat
import time
from pathlib import Path

import importlib.util as _iu
_lib_path = os.path.join(os.path.dirname(__file__), "_hook_lib.py")
_spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_append_audit = _mod._append_audit
_write_metric = _mod._write_metric

# Plugin root: OMNI_PLUGIN_ROOT (primary) > CLAUDE_PLUGIN_ROOT (legacy fallback) > file-relative default.
# NOTE: Path("") == Path(".") which is truthy, so we must NOT use `or` with Path("").
_PLUGIN_ROOT = (
    Path(os.environ["OMNI_PLUGIN_ROOT"]) if os.environ.get("OMNI_PLUGIN_ROOT")
    else Path(os.environ["CLAUDE_PLUGIN_ROOT"]) if os.environ.get("CLAUDE_PLUGIN_ROOT")
    else Path(__file__).resolve().parent.parent
)


# ---------------------------------------------------------------------------
# Banner computation helpers
# ---------------------------------------------------------------------------

def _count_items(directory: Path, glob: str) -> int:
    """Count items matching *glob* under *directory* (non-recursive top level)."""
    try:
        return sum(1 for _ in directory.glob(glob))
    except Exception:
        return 0


def _count_recursive(directory: Path, filename: str) -> int:
    """Count files named *filename* recursively under *directory*."""
    try:
        return sum(1 for _ in directory.rglob(filename))
    except Exception:
        return 0


def _compute_tree_hash(root: Path) -> str:
    """Compute a lightweight hash of the plugin's manifest files.

    Uses plugin.json + AGENTS.md modification times and sizes for speed
    (< 5ms), avoiding a full directory walk.
    """
    h = hashlib.md5()  # noqa: S324 — not security-sensitive, just cache key
    for candidate in [
        root / ".claude-plugin" / "plugin.json",
        root / "AGENTS.md",
        root / "hooks" / "hooks.json",
    ]:
        try:
            s = candidate.stat()
            h.update(f"{candidate}:{s.st_mtime}:{s.st_size}".encode())
        except Exception:
            h.update(str(candidate).encode())
    return h.hexdigest()


def _read_version(root: Path) -> str:
    """Read version from plugin.json or fall back to 'unknown'."""
    for p in [
        root / ".claude-plugin" / "plugin.json",
        root / "plugin.json",
    ]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return str(data.get("version", "unknown"))
        except Exception:
            continue
    return "unknown"


def _router_status(root: Path) -> str:
    """Return 'on' if scripts/router.py exists, else 'off'."""
    return "on" if (root / "scripts" / "router.py").exists() else "off"


def _pool_cap(root: Path) -> str:
    """Read pool capacity from subagent_pool or fall back to '?'."""
    pool_path = root / "scripts" / "subagent_pool.py"
    if not pool_path.exists():
        return "?"
    try:
        text = pool_path.read_text(encoding="utf-8")
        # Look for MAX_WORKERS = N or DEFAULT_POOL_SIZE = N
        import re
        m = re.search(r'(?:MAX_WORKERS|DEFAULT_POOL_SIZE|_CAP)\s*=\s*(\d+)', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "?"


def _compute_banner(root: Path) -> str:
    """Compute the banner string from current plugin state."""
    version = _read_version(root)
    n_skills = _count_items(root / "skills", "*") if (root / "skills").is_dir() else 0
    n_agents = 0
    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        try:
            text = agents_path.read_text(encoding="utf-8")
            import re
            # Count lines matching "## <AgentName>" or agent definitions
            n_agents = len(re.findall(r'^##\s+\w', text, re.MULTILINE))
        except Exception:
            pass
    # Count slash commands from plugin.json
    n_commands = 0
    for p in [root / ".claude-plugin" / "plugin.json", root / "plugin.json"]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            commands = data.get("commands", [])
            n_commands = len(commands) if isinstance(commands, list) else 0
            break
        except Exception:
            continue

    router = _router_status(root)
    pool = _pool_cap(root)

    return (
        f"copilot-omni v{version} | "
        f"{n_skills} skills | "
        f"{n_agents} agents | "
        f"{n_commands} commands | "
        f"router={router} | "
        f"pool={pool}"
    )


def _get_banner(root: Path) -> tuple[str, bool]:
    """Return (banner_text, cache_hit).

    Checks .omni/cache/banner.json keyed by tree hash.
    Recomputes + writes cache if stale or missing.
    """
    cache_path = root / ".omni" / "cache" / "banner.json"
    tree_hash = _compute_tree_hash(root)

    # Try cache
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("tree_hash") == tree_hash:
            return cached["banner"], True
    except Exception:
        pass

    # Recompute
    banner = _compute_banner(root)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"tree_hash": tree_hash, "banner": banner}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass  # cache write failure is non-fatal

    return banner, False


# ---------------------------------------------------------------------------
# Policy permission check
# ---------------------------------------------------------------------------

def _check_policy_permissions(root: Path) -> list[str]:
    """Return list of warning messages for over-permissive policy files.

    Files with mode > 0o644 are flagged.
    """
    warnings: list[str] = []
    policies_dir = root / "policies"
    if not policies_dir.is_dir():
        return warnings
    try:
        for p in policies_dir.glob("*.json"):
            try:
                mode = p.stat().st_mode & 0o777
                if mode > 0o644:
                    warnings.append(
                        f"<policy-warning>policy file {p.name} has mode "
                        f"{oct(mode)} (expected <= 0o644)</policy-warning>"
                    )
            except Exception:
                continue
    except Exception:
        pass
    return warnings


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    t_start = time.monotonic()

    banner, cache_hit = _get_banner(_PLUGIN_ROOT)
    policy_warnings = _check_policy_permissions(_PLUGIN_ROOT)

    # Build additionalContext
    parts = [f"<omni-banner>{banner}</omni-banner>"]
    parts.extend(policy_warnings)
    context = "\n".join(parts)

    payload = {"additionalContext": context}
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()

    _append_audit({
        "hook": _HOOK_NAME,
        "event_name": "session_start",
        "tool_name": "",
        "prompt_excerpt": "",
        "action": "banner",
        "reason": f"cache_hit={cache_hit}",
    })
    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME})
    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                  {"hook": _HOOK_NAME})

    return 0


if __name__ == "__main__":
    sys.exit(main())
