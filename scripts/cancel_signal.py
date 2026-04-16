#!/usr/bin/env python3
"""Phase-C C33: structured cancel reasons + partial-cancel scopes.

Historical contract — every copilot-omni skill checked for a plain
``cancel.signal`` file under the run-dir and exited on any non-zero
byte. That contract is preserved: **any** cancel.signal file still
triggers a full cancel.

New contract — the file can optionally contain a JSON body:

    {
      "reason": "user requested stop",
      "ts": 1713312000.0,
      "scope": "branch:critic-v2"   (or omitted for full-run cancel)
    }

When ``scope`` is ``None`` the cancel applies to the whole run (the
legacy behaviour). When ``scope`` is ``"branch:<id>"`` it applies only
to the named branch of a team run; other branches keep running.

Helper API for writers / readers (stdlib only, drop-in for skills):

    scripts/cancel_signal.py write <run-dir> --reason "..." [--scope branch:X]
    scripts/cancel_signal.py read  <run-dir>
    scripts/cancel_signal.py should-cancel <run-dir> [--scope branch:X]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


SIGNAL_NAME = "cancel.signal"


def _signal_path(run_dir: Path) -> Path:
    return run_dir / SIGNAL_NAME


def write_cancel(
    run_dir: Path,
    *,
    reason: str = "",
    scope: Optional[str] = None,
) -> Path:
    """Create a structured cancel.signal. Overwrites an existing file."""
    run_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "reason": reason,
        "ts": time.time(),
    }
    if scope is not None:
        body["scope"] = scope
    path = _signal_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))
    return path


def read_cancel(run_dir: Path) -> Optional[dict]:
    """Return the cancel record or None when no cancel is pending.

    Legacy empty/plain-text files are accepted — they return a
    best-effort dict with reason='legacy cancel.signal' and no scope.
    """
    path = _signal_path(run_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return {"reason": "unreadable cancel.signal", "ts": 0.0}
    if not raw.strip():
        return {"reason": "legacy cancel.signal", "ts": 0.0}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("cancel.signal must be a JSON object")
        data.setdefault("reason", "")
        data.setdefault("ts", 0.0)
        return data
    except Exception:
        # Unrecognised content — still treat as cancel for safety (the file
        # existing is the cancellation intent regardless of contents).
        return {"reason": raw.strip()[:200], "ts": 0.0}


def should_cancel(
    run_dir: Path,
    *,
    scope: Optional[str] = None,
) -> bool:
    """Return True when the current context (identified by *scope*) must
    cancel.

    - full-run cancel  (file has no scope) → applies to every caller
    - scoped cancel    (file has scope=X)  → applies only when
                                              caller's scope == X
    - unscoped caller  (scope=None)        → a scoped cancel never
                                              forces a full-run exit
    """
    record = read_cancel(run_dir)
    if record is None:
        return False
    file_scope = record.get("scope")
    if file_scope is None:
        return True
    if scope is None:
        # Caller has no branch identity → a branch-scoped cancel does
        # NOT apply to them.
        return False
    return file_scope == scope


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Structured cancel.signal helper (Phase-C C33)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    w = sub.add_parser("write", help="Create a structured cancel.signal")
    w.add_argument("run_dir", type=Path)
    w.add_argument("--reason", default="")
    w.add_argument("--scope", default=None,
                   help="Optional scope, e.g. 'branch:<id>' for partial cancel")

    r = sub.add_parser("read", help="Print the cancel record as JSON")
    r.add_argument("run_dir", type=Path)

    s = sub.add_parser("should-cancel",
                       help="Exit 0 iff cancellation applies to the caller")
    s.add_argument("run_dir", type=Path)
    s.add_argument("--scope", default=None)

    args = parser.parse_args(argv)
    if args.command == "write":
        path = write_cancel(args.run_dir, reason=args.reason, scope=args.scope)
        print(str(path))
        return 0
    if args.command == "read":
        record = read_cancel(args.run_dir)
        if record is None:
            print("null")
            return 1
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "should-cancel":
        return 0 if should_cancel(args.run_dir, scope=args.scope) else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
