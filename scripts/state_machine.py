#!/usr/bin/env python3
"""Phase-C C19: four-gate state machine for copilot-omni runs.

Every long-running omni workflow passes through four gates:

    discuss ─▶ plan ─▶ execute ─▶ verify ─▶ done

Each transition is recorded under .omni/runs/<run-id>/state.json so the
workflow can resume, audit, or be gated externally (e.g. via hooks that
block `omni execute` when there is no plan artifact).

The state machine is intentionally minimal — it enforces the forward
order, allows a single rewind to the previous gate (for re-review), and
rejects every other transition. No timers, no branching, no retries;
those belong to downstream controllers (ralph, autopilot, team).

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

GATES: tuple[str, ...] = ("discuss", "plan", "execute", "verify", "done")
_GATE_INDEX = {g: i for i, g in enumerate(GATES)}


class StateMachineError(RuntimeError):
    """Raised on invalid transitions."""


def _state_path(run_dir: Path) -> Path:
    return run_dir / "state.json"


def read_state(run_dir: Path) -> dict:
    """Return the state dict for *run_dir*, or an initial dict when absent."""
    sp = _state_path(run_dir)
    if not sp.exists():
        return {"gate": "discuss", "history": []}
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return {"gate": "discuss", "history": []}


def _write_state(run_dir: Path, state: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    sp = _state_path(run_dir)
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(sp))


def advance(run_dir: Path, target: str, *, note: str = "") -> dict:
    """Advance to *target* gate. Allowed transitions:

    - Forward by exactly one step (discuss → plan → execute → verify → done).
    - A single rewind to the immediately-previous gate (to re-run discuss
      after a plan review, etc.). Further rewinds are rejected.

    Raises StateMachineError on invalid input.
    """
    if target not in _GATE_INDEX:
        raise StateMachineError(
            f"unknown gate {target!r}; valid: {', '.join(GATES)}"
        )
    state = read_state(run_dir)
    current = state.get("gate", "discuss")
    if current not in _GATE_INDEX:
        raise StateMachineError(f"corrupt state: unknown current gate {current!r}")
    delta = _GATE_INDEX[target] - _GATE_INDEX[current]
    if delta == 0:
        return state  # idempotent
    if delta == 1:
        pass  # forward step, allowed
    elif delta == -1:
        # Single rewind allowed only when the immediately-previous
        # transition wasn't itself a rewind — chained rewinds indicate
        # thrashing and should surface as a StateMachineError.
        last_delta = state.get("last_delta")
        if last_delta == -1:
            raise StateMachineError(
                f"cannot rewind twice in a row; current={current}, target={target}"
            )
    else:
        raise StateMachineError(
            f"invalid transition {current} → {target} (delta={delta})"
        )
    state.setdefault("history", []).append({
        "gate": current,
        "ended_at": time.time(),
        "note": note or "",
        "delta": delta,
    })
    state["gate"] = target
    state["last_delta"] = delta
    state["updated_at"] = time.time()
    _write_state(run_dir, state)
    return state


def require_gate(run_dir: Path, expected: str) -> None:
    """Raise StateMachineError if *run_dir* is not currently at *expected*.

    Used by CLI wrappers (e.g. `omni execute`) to refuse when the workflow
    hasn't reached the execute gate yet.
    """
    state = read_state(run_dir)
    if state.get("gate") != expected:
        raise StateMachineError(
            f"gate check failed: expected {expected!r}, got {state.get('gate')!r} "
            f"in {run_dir}"
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Four-gate state machine for .omni/runs/<run-id>/."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="Print current state as JSON")
    p_read.add_argument("run_dir", type=Path)

    p_advance = sub.add_parser("advance", help="Advance to the given gate")
    p_advance.add_argument("run_dir", type=Path)
    p_advance.add_argument("target", choices=GATES)
    p_advance.add_argument("--note", default="")

    p_require = sub.add_parser("require", help="Exit non-zero if not at gate")
    p_require.add_argument("run_dir", type=Path)
    p_require.add_argument("gate", choices=GATES)

    args = parser.parse_args(argv)

    try:
        if args.command == "read":
            print(json.dumps(read_state(args.run_dir), indent=2))
            return 0
        if args.command == "advance":
            state = advance(args.run_dir, args.target, note=args.note)
            print(json.dumps(state, indent=2))
            return 0
        if args.command == "require":
            require_gate(args.run_dir, args.gate)
            return 0
    except StateMachineError as exc:
        print(f"state_machine: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
