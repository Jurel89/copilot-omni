#!/usr/bin/env python3
"""Shared hook utilities — stdlib only.

Imported by all four lifecycle hooks.  Provides:
  - _hook_disabled(name)  — kill-switch check (canonical + legacy aliases)
  - _deprecation_warn()   — one-shot stderr warning for legacy env vars
  - _append_audit(record) — atomic file-locked audit append to .omni/audit/hooks.jsonl
  - _write_metric(name, value, labels) — append to .omni/audit/metrics.jsonl

Kill-switch semantics
---------------------
OMNI_SKIP_HOOKS=1    — disable all hooks (canonical)
DISABLE_OMNI=1       — disable all hooks (canonical alternate)
OMC_SKIP_HOOKS=1     — backward-compat alias; deprecated, removed in v3.0.0
DISABLE_OMC=1        — backward-compat alias; deprecated, removed in v3.0.0
OMNI_SKIP_<HOOK>=1   — per-hook kill-switch (e.g. OMNI_SKIP_PRE_TOOL_USE=1)

Audit log schema
----------------
Each line in hooks.jsonl is a JSON object:
  {ts, hook, event_name, tool_name, prompt_excerpt, action, reason}

Metrics log schema
------------------
Each line in metrics.jsonl is a JSON object:
  {ts, name, value, labels}
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Platform-specific file locking
# ---------------------------------------------------------------------------
_LOCK_EX = None
_LOCK_NB = None
_fcntl = None
_msvcrt = None

try:
    import fcntl as _fcntl_mod  # type: ignore[import]
    _fcntl = _fcntl_mod
    _LOCK_EX = _fcntl_mod.LOCK_EX  # type: ignore[attr-defined]
    _LOCK_NB = _fcntl_mod.LOCK_NB  # type: ignore[attr-defined]
except ImportError:
    pass

if _fcntl is None:
    try:
        import msvcrt as _msvcrt_mod  # type: ignore[import]
        _msvcrt = _msvcrt_mod
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Kill-switch helpers
# ---------------------------------------------------------------------------

_LEGACY_VARS: tuple[str, ...] = ("OMC_SKIP_HOOKS", "DISABLE_OMC")
_DEDUP_SENTINEL = Path(__file__).resolve().parent.parent / ".omni" / "cache" / "omc-deprecation-warned"  # omni-rename-allow: legacy sentinel name preserved for backward compat


def _hook_disabled(hook_name: str) -> bool:
    """Return True if any kill-switch is active for *hook_name*.

    Checks (in order):
    1. DISABLE_OMNI or DISABLE_OMC (legacy)
    2. OMNI_SKIP_HOOKS or OMC_SKIP_HOOKS (legacy)
    3. OMNI_SKIP_<HOOK_UPPER>=1  (per-hook; hook_name uppercased, spaces→_)

    Side-effect: emits a one-shot deprecation warning on stderr when a
    legacy env var (OMC_SKIP_HOOKS or DISABLE_OMC) triggers the kill-switch.
    """
    env = os.environ

    def _truthy(name: str) -> bool:
        """Kill-switch env vars are documented as ``=1``. Only treat
        recognizable truthy values (1, true, yes, on) as enabled so that
        ``DISABLE_OMNI=0`` or ``OMNI_SKIP_HOOKS=false`` do NOT silently
        disable hook enforcement."""
        val = env.get(name)
        if val is None:
            return False
        return val.strip().lower() in ("1", "true", "yes", "on")

    if _truthy("DISABLE_OMNI") or _truthy("OMNI_SKIP_HOOKS"):
        return True

    # Legacy aliases — check and warn
    if _truthy("DISABLE_OMC") or _truthy("OMC_SKIP_HOOKS"):
        _deprecation_warn()
        return True

    # Per-hook kill-switch: OMNI_SKIP_<HOOK_UPPER>
    per_hook_var = "OMNI_SKIP_" + hook_name.upper().replace(" ", "_").replace("-", "_")
    if _truthy(per_hook_var):
        return True

    return False


def _deprecation_warn() -> None:
    """Emit a one-time deprecation warning for legacy env vars.

    De-duplicated via .omni/cache/omc-deprecation-warned sentinel file.  # omni-rename-allow: legacy sentinel name in docstring
    """
    if _DEDUP_SENTINEL.exists():
        return
    msg = (
        "[copilot-omni WARN] OMC_SKIP_HOOKS / DISABLE_OMC are deprecated and "
        "will be removed in v3.0.0.  Switch to OMNI_SKIP_HOOKS=1 or DISABLE_OMNI=1.\n"
    )
    sys.stderr.write(msg)
    sys.stderr.flush()
    try:
        _DEDUP_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        _DEDUP_SENTINEL.touch()
    except Exception:
        pass  # sentinel write failure is non-fatal


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------

def _audit_log_path() -> Path:
    """Return canonical path to hooks.jsonl audit log."""
    return Path(os.getcwd()) / ".omni" / "audit" / "hooks.jsonl"


def _metrics_log_path() -> Path:
    """Return canonical path to metrics.jsonl."""
    return Path(os.getcwd()) / ".omni" / "audit" / "metrics.jsonl"


def _ensure_dir(p: Path) -> None:
    """Create parent directory tree if needed (best-effort)."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _atomic_append(path: Path, line: str, lock_budget_s: float = 1.0) -> None:
    """Append *line* to *path* with a file lock; drops write if lock takes > lock_budget_s.

    POSIX: uses fcntl.flock(LOCK_EX | LOCK_NB) with a spin-wait up to budget.
    Windows: uses msvcrt.locking on a lock-file sidecar.
    Neither: plain append (best-effort, no locking).

    Always opens in text mode so Python handles line-endings portably.
    """
    _ensure_dir(path)
    deadline = time.monotonic() + lock_budget_s

    if _fcntl is not None:
        # POSIX path
        try:
            with path.open("a", encoding="utf-8") as fh:
                # Try non-blocking lock first; fall back to spinning
                while True:
                    try:
                        _fcntl.flock(fh, _LOCK_EX | _LOCK_NB)  # type: ignore[attr-defined]
                        break
                    except (OSError, BlockingIOError):
                        if time.monotonic() >= deadline:
                            sys.stderr.write(
                                f"[copilot-omni] audit: lock timeout on {path}, dropping write\n"
                            )
                            return
                        time.sleep(0.05)
                try:
                    fh.write(line + "\n")
                finally:
                    _fcntl.flock(fh, _fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except Exception as exc:
            sys.stderr.write(f"[copilot-omni] audit: write error {exc}\n")
        return

    if _msvcrt is not None:
        # Windows path — use a sidecar lock file
        lock_path = path.with_suffix(path.suffix + ".lock")
        import ctypes  # noqa: PLC0415 — Windows only path
        while True:
            try:
                lock_fd = lock_path.open("a", encoding="utf-8")
                # Lock 1 byte at position 0
                import struct  # noqa: PLC0415
                lock_fd.flush()
                try:
                    _msvcrt.locking(lock_fd.fileno(), _msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                    break
                except OSError:
                    lock_fd.close()
                    if time.monotonic() >= deadline:
                        sys.stderr.write(
                            f"[copilot-omni] audit: lock timeout on {path}, dropping write\n"
                        )
                        return
                    time.sleep(0.05)
            except Exception:
                break  # Can't lock — fall through to plain write
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:
            sys.stderr.write(f"[copilot-omni] audit: write error {exc}\n")
        finally:
            try:
                _msvcrt.locking(lock_fd.fileno(), _msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                lock_fd.close()
            except Exception:
                pass
        return

    # Fallback: no locking available — plain append
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:
        sys.stderr.write(f"[copilot-omni] audit: write error {exc}\n")


def _append_audit(record: Dict[str, Any]) -> None:
    """Write one audit record to .omni/audit/hooks.jsonl.

    Record schema: {ts, hook, event_name, tool_name, prompt_excerpt, action, reason}
    Missing keys are filled with None / empty string.

    Normalised record always includes 'ts' even if caller omits it.
    """
    record.setdefault("ts", time.time())
    try:
        line = json.dumps(record, ensure_ascii=False)
    except Exception:
        line = json.dumps({"ts": time.time(), "hook": record.get("hook", ""), "error": "serialize_failed"})
    _atomic_append(_audit_log_path(), line)


def _write_metric(name: str, value: Any, labels: Optional[Dict[str, Any]] = None) -> None:
    """Append one metric record to .omni/audit/metrics.jsonl.

    Record schema: {ts, name, value, labels}
    """
    record = {
        "ts": time.time(),
        "name": name,
        "value": value,
        "labels": labels or {},
    }
    try:
        line = json.dumps(record, ensure_ascii=False)
    except Exception:
        return  # metrics are non-critical; never raise
    _atomic_append(_metrics_log_path(), line)
