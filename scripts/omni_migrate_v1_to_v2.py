#!/usr/bin/env python3
"""
omni_migrate_v1_to_v2.py — safe, idempotent v1 → v2 state-directory migrator.

Renames:
  <repo>/.omc/   → <repo>/.omni/
  ~/.omc/        → ~/.omni/

Never modifies user dotfiles. Prints env-var guidance only.

Usage:
  python3 scripts/omni_migrate_v1_to_v2.py            # dry-run (default)
  python3 scripts/omni_migrate_v1_to_v2.py --dry-run  # explicit dry-run
  python3 scripts/omni_migrate_v1_to_v2.py --apply    # execute migration
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_git_repo(path: Path) -> bool:
    """Return True if *path* is inside a git work-tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _git_mv(src: Path, dst: Path) -> None:
    """Run ``git mv src dst`` and raise RuntimeError on failure."""
    result = subprocess.run(
        ["git", "mv", str(src), str(dst)],
        cwd=str(src.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git mv failed: {result.stderr.decode().strip()}"
        )


def _plain_mv(src: Path, dst: Path) -> None:
    """Move *src* to *dst* using shutil (non-git path)."""
    shutil.move(str(src), str(dst))


def _migrate_one(
    src: Path,
    dst: Path,
    *,
    dry_run: bool,
    use_git: bool,
) -> str:
    """
    Migrate a single directory from *src* to *dst*.

    Returns a one-line status string.
    """
    if not src.exists():
        return f"  SKIP  {src}  (not found)"

    if dst.exists():
        return f"  WARN  {src}  → {dst}  already exists — skipped"

    if dry_run:
        verb = "git mv" if use_git else "mv"
        return f"  DRY   {verb} {src} → {dst}"

    try:
        if use_git:
            _git_mv(src, dst)
        else:
            _plain_mv(src, dst)
        return f"  DONE  {src} → {dst}"
    except Exception as exc:  # noqa: BLE001
        return f"  ERR   {src} → {dst}  ({exc})"


def _print_guidance() -> None:
    """Print env-var update guidance (never modifies dotfiles)."""
    print()
    print("Next steps — update your shell profile manually:")
    print()
    print("  # Replace OMC_SKIP_HOOKS with OMNI_SKIP_HOOKS")
    print("  #   old: export OMC_SKIP_HOOKS=1")
    print("  #   new: export OMNI_SKIP_HOOKS=1")
    print()
    print("  # Replace DISABLE_OMC with DISABLE_OMNI")
    print("  #   old: export DISABLE_OMC=1")
    print("  #   new: export DISABLE_OMNI=1")
    print()
    print("  # Replace /oh-my-claudecode: slash-commands with /copilot-omni:")
    print("  #   old: /oh-my-claudecode:omc-doctor")
    print("  #   new: /copilot-omni:omni-doctor")
    print()
    print("  # See docs/MIGRATION.md for the full v1 → v2 guide.")
    print()


# ---------------------------------------------------------------------------
# Locations to migrate
# ---------------------------------------------------------------------------


def _locations(
    repo_root: Path, *, rollback: bool = False
) -> list[tuple[Path, Path, bool]]:
    """
    Return a list of (src, dst, use_git) tuples to process.

    use_git=True when the src is inside a git work-tree (prefer ``git mv``
    so git history is preserved).

    When *rollback* is True, src and dst are swapped so .omni/ reverts to
    .omc/ — this is the last-resort undo path documented in
    docs/MIGRATION-ROLLBACK.md.
    """
    home = Path.home()
    targets = [
        (repo_root / ".omc", repo_root / ".omni"),
        (home / ".omc", home / ".omni"),
    ]
    if rollback:
        targets = [(dst, src) for (src, dst) in targets]
    result = []
    for src, dst in targets:
        # Only use git mv inside the repo, not for the user home dir
        use_git = (src.parent == repo_root) and _is_git_repo(src.parent)
        result.append((src, dst, use_git))
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def migrate(
    repo_root: Path, *, dry_run: bool, rollback: bool = False
) -> int:
    """
    Run the migration. Returns 0 on clean success, 1 if any location errored.

    When *rollback* is True, reverse the v1→v2 move: .omni/ is renamed back
    to .omc/. Intended as a last-resort undo — see docs/MIGRATION-ROLLBACK.md.
    """
    mode_label = "DRY-RUN" if dry_run else "APPLY"
    direction = "ROLLBACK" if rollback else "MIGRATE"
    print(f"omni_migrate_v1_to_v2 — {direction} ({mode_label})")
    if rollback:
        print("WARNING: rollback renames .omni/ back to .omc/. This is a")
        print("         last-resort recovery path — new content written under")
        print("         .omni/ since the forward migration will move with it.")
        print("         See docs/MIGRATION-ROLLBACK.md before running --apply.")
    print()

    had_error = False
    had_work = False

    for src, dst, use_git in _locations(repo_root, rollback=rollback):
        line = _migrate_one(src, dst, dry_run=dry_run, use_git=use_git)
        print(line)
        if "ERR" in line:
            had_error = True
        if "DONE" in line or "DRY" in line:
            had_work = True

    if not had_work:
        print()
        label = ".omni/" if rollback else ".omc/"
        print(f"Nothing to {'roll back' if rollback else 'migrate'} — no {label} directories found.")

    if not rollback:
        _print_guidance()
    else:
        _print_rollback_guidance()

    if had_error:
        verb = "Rollback" if rollback else "Migration"
        print(f"{verb} completed with errors (see ERR lines above).")
        return 1

    if dry_run and had_work:
        print("Dry-run complete. Re-run with --apply to execute.")

    return 0


def _print_rollback_guidance() -> None:
    """Print env-var revert guidance for rollback."""
    print()
    print("Rollback next steps — revert your shell profile manually:")
    print()
    print("  # Revert OMNI_SKIP_HOOKS → OMC_SKIP_HOOKS")
    print("  # Revert DISABLE_OMNI → DISABLE_OMC")
    print("  # Revert /copilot-omni: slash-commands → /oh-my-claudecode:")
    print()
    print("  # See docs/MIGRATION-ROLLBACK.md for full rollback checklist.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate copilot-omni v1 state directories to v2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without executing them (default behaviour).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Execute the migration (moves directories).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Path to repo root (default: cwd).",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        default=False,
        help=(
            "LAST-RESORT recovery: reverse the migration by moving .omni/ "
            "back to .omc/. See docs/MIGRATION-ROLLBACK.md first."
        ),
    )
    args = parser.parse_args(argv)

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive.")

    dry_run = not args.apply  # default is dry-run

    repo_root = args.repo_root if args.repo_root else Path.cwd()

    return migrate(repo_root, dry_run=dry_run, rollback=args.rollback)


if __name__ == "__main__":
    sys.exit(main())
