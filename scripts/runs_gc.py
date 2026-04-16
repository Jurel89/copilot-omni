#!/usr/bin/env python3
"""Phase-C C32: garbage-collector for .omni/runs/<run-id>/.

Deletes run directories whose most-recently-modified file is older than the
configured TTL. TTL defaults to 14 days and is overridable via the
OMNI_RUNS_TTL_DAYS env var.

Usage
-----
    python3 scripts/runs_gc.py                 # dry-run (default)
    python3 scripts/runs_gc.py --apply         # actually delete
    python3 scripts/runs_gc.py --ttl-days 7    # override TTL

Also callable from `omni doctor --gc` as the preferred ops entry point.

The script is defensive: it never deletes the top-level .omni/runs/ itself,
only its direct children, and it never follows symlinks.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable, Tuple

DEFAULT_TTL_DAYS = 14


def _runs_root(repo_root: Path) -> Path:
    return repo_root / ".omni" / "runs"


def _newest_mtime(path: Path) -> float:
    """Return the most-recently-modified mtime within *path* (recursive).

    Falls back to path.stat().st_mtime if we cannot walk (e.g. permission).
    Symlinks are NOT followed.
    """
    try:
        newest = path.stat().st_mtime
    except OSError:
        return 0.0
    try:
        for dirpath, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    m = os.stat(os.path.join(dirpath, name)).st_mtime
                    if m > newest:
                        newest = m
                except OSError:
                    continue
    except OSError:
        pass
    return newest


def collect_stale(runs_root: Path, ttl_days: float, now: float | None = None
                   ) -> Iterable[Tuple[Path, float]]:
    """Yield (path, age_days) for each stale direct child of *runs_root*."""
    if not runs_root.is_dir():
        return
    cutoff = (now if now is not None else time.time()) - ttl_days * 86400
    for child in sorted(runs_root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        newest = _newest_mtime(child)
        if newest == 0.0:
            continue  # could not stat; leave alone
        if newest < cutoff:
            age_days = ((now if now is not None else time.time()) - newest) / 86400.0
            yield child, age_days


def run_gc(repo_root: Path, *, ttl_days: float, apply_: bool) -> Tuple[int, int]:
    """Run the GC. Returns (candidates_found, deleted).

    dry-run (apply_=False) never mutates the filesystem.
    """
    runs_root = _runs_root(repo_root)
    verb = "DELETE" if apply_ else "DRY"
    found = 0
    deleted = 0
    for path, age in collect_stale(runs_root, ttl_days):
        found += 1
        print(f"  {verb}  {path}  (age={age:.1f}d, ttl={ttl_days:.1f}d)")
        if apply_:
            try:
                shutil.rmtree(path)
                deleted += 1
            except OSError as exc:
                print(f"  ERR   could not remove {path}: {exc}", file=sys.stderr)
    if found == 0:
        print(f"  no stale runs older than {ttl_days:.1f}d in {runs_root}")
    return found, deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Garbage-collect .omni/runs/ directories older than TTL."
    )
    parser.add_argument(
        "--repo-root", type=Path, default=None,
        help="Project root containing .omni/runs/ (default: cwd).",
    )
    parser.add_argument(
        "--ttl-days", type=float, default=None,
        help=f"Age threshold in days (default: ${{OMNI_RUNS_TTL_DAYS}} or {DEFAULT_TTL_DAYS}).",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Execute deletions (default is dry-run).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path.cwd()

    ttl_days = args.ttl_days
    if ttl_days is None:
        env = os.environ.get("OMNI_RUNS_TTL_DAYS")
        if env:
            try:
                ttl_days = float(env)
            except ValueError:
                print(f"warn: OMNI_RUNS_TTL_DAYS={env!r} is not numeric; using default",
                      file=sys.stderr)
                ttl_days = DEFAULT_TTL_DAYS
        else:
            ttl_days = DEFAULT_TTL_DAYS
    if ttl_days <= 0:
        parser.error("--ttl-days must be > 0")

    print(f"runs_gc {'APPLY' if args.apply else 'DRY-RUN'} "
          f"repo={repo_root} ttl={ttl_days:.1f}d")
    found, deleted = run_gc(repo_root, ttl_days=ttl_days, apply_=args.apply)
    if args.apply:
        print(f"deleted {deleted}/{found} stale run(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
