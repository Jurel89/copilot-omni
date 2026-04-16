#!/usr/bin/env python3
"""Phase-B plugin-contract verifier.

Grows with each Phase-B workstream. At Wave 0 only `--check-rename-stub`
and `--list-checks` exist; later waves append checks by adding functions
to CHECKS and wiring them into main().

Every check returns (ok: bool, messages: list[str]). Exit code is 0 on
all-green, 1 on any failure.

Contract: stdlib only. No third-party deps. Idempotent.

Usage:
    python3 scripts/verify_plugin_contract.py --all
    python3 scripts/verify_plugin_contract.py --check-rename-stub
    python3 scripts/verify_plugin_contract.py --list-checks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Tuple

ROOT = Path(__file__).resolve().parent.parent


CheckResult = Tuple[bool, list]


def check_rename_stub() -> CheckResult:
    """Wave-0 stub. Verifies only that the check harness itself is alive.

    WS1 replaces this with the real whole-tree grep for `.omc/` /
    `oh-my-claudecode` with an explicit allowlist.
    """
    return True, ["rename stub: harness alive; WS1 will implement the real check"]


CHECKS: dict = {
    "rename-stub": check_rename_stub,
}


def run_checks(names: list) -> int:
    overall_ok = True
    for name in names:
        if name not in CHECKS:
            print(f"[error] unknown check: {name}", file=sys.stderr)
            overall_ok = False
            continue
        ok, messages = CHECKS[name]()
        status = "ok" if ok else "FAIL"
        print(f"[{status}] {name}")
        for m in messages:
            print(f"       {m}")
        overall_ok = overall_ok and ok
    return 0 if overall_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-B plugin-contract verifier")
    parser.add_argument("--all", action="store_true", help="Run every registered check")
    parser.add_argument("--list-checks", action="store_true", help="Print the registered checks and exit")
    for name in CHECKS:
        parser.add_argument(f"--check-{name}", action="append_const",
                            dest="requested", const=name,
                            help=f"Run only the {name} check")
    parser.set_defaults(requested=[])
    args = parser.parse_args()

    if args.list_checks:
        for name in CHECKS:
            print(name)
        return 0

    if args.all:
        names = list(CHECKS.keys())
    elif args.requested:
        names = args.requested
    else:
        parser.print_help()
        return 2

    return run_checks(names)


if __name__ == "__main__":
    sys.exit(main())
