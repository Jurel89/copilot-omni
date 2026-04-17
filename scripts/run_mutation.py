#!/usr/bin/env python3
"""Phase-C C29: mutation testing wrapper.

Runs mutmut against the high-value modules only (subagent_pool and
category_resolver) so wall time stays bounded on CI. mutmut is an
optional dev dependency; when it's not installed the script prints an
install hint and exits 0 so it never blocks the fast lane.

Usage:
    python3 scripts/run_mutation.py                # run the default set
    python3 scripts/run_mutation.py --module X     # run a single module
    python3 scripts/run_mutation.py --list         # print targeted paths
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_TARGETS = (
    "scripts/subagent_pool.py",
    "scripts/category_resolver.py",
)


def _mutmut_available() -> bool:
    if shutil.which("mutmut"):
        return True
    try:
        __import__("mutmut")
        return True
    except ImportError:
        return False


def _run_mutmut(paths: list[str]) -> int:
    """Invoke mutmut with the narrowest possible scope."""
    cmd = [sys.executable, "-m", "mutmut", "run", "--paths-to-mutate",
           ",".join(paths)]
    print("→", " ".join(cmd))
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scoped mutation-testing wrapper for copilot-omni.",
    )
    parser.add_argument("--module", action="append", default=None,
                        help="Restrict to a specific module (repeatable).")
    parser.add_argument("--list", action="store_true",
                        help="Print the default target list and exit.")
    args = parser.parse_args(argv)

    if args.list:
        for p in DEFAULT_TARGETS:
            print(p)
        return 0

    if not _mutmut_available():
        print("mutmut not installed — run `pip install mutmut` to enable.",
              file=sys.stderr)
        print("This wrapper is optional; exit 0.", file=sys.stderr)
        return 0

    targets = list(args.module) if args.module else list(DEFAULT_TARGETS)
    for t in targets:
        if not Path(t).exists():
            print(f"warn: target {t!r} not found — skipping", file=sys.stderr)
    targets = [t for t in targets if Path(t).exists()]
    if not targets:
        print("no valid targets — nothing to do", file=sys.stderr)
        return 0

    return _run_mutmut(targets)


if __name__ == "__main__":
    sys.exit(main())
