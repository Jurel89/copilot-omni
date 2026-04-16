#!/usr/bin/env python3
"""omni_worktree.py — thin wrapper around git worktree for WS6 team orchestration.

Manages isolated git worktrees per team worker so each worker operates on its
own branch without conflicting with other workers or the main checkout.

Layout:
    .omni/runs/team-<id>/workers/<slug>/worktree/   (worktree root)
    branch: team-<id>/<slug>

Stdlib only. No third-party deps.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    """Return the repo root (uses git rev-parse for robustness)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return _REPO_ROOT


def _run_git(args: list[str], *, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command, returning CompletedProcess. Raises on non-zero if check=True."""
    root = cwd or _repo_root()
    cmd = ["git"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use as a branch component (no spaces, slashes, etc.)."""
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")


def add(
    run_id: str,
    slug: str,
    base_branch: str = "main",
    *,
    repo_root: Optional[Path] = None,
) -> dict:
    """Create a worktree for a worker.

    Creates:
      .omni/runs/<run_id>/workers/<slug>/worktree   (worktree path)
      branch: team-<run_id>/<slug>

    Returns dict with:
      worktree_path, branch, run_id, slug
    """
    root = repo_root or _repo_root()
    safe_run = _sanitize_name(run_id)
    safe_slug = _sanitize_name(slug)
    branch = f"team-{safe_run}/{safe_slug}"

    worktree_path = root / ".omni" / "runs" / run_id / "workers" / slug / "worktree"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Verify base branch exists; fall back to HEAD if not
    check_base = _run_git(
        ["rev-parse", "--verify", base_branch],
        cwd=root,
        check=False,
    )
    if check_base.returncode != 0:
        # Try HEAD instead
        head = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        base_branch = head.stdout.strip() or "HEAD"

    # Create worktree with a new branch
    _run_git(
        ["worktree", "add", "-b", branch, str(worktree_path), base_branch],
        cwd=root,
    )

    return {
        "run_id": run_id,
        "slug": slug,
        "branch": branch,
        "worktree_path": str(worktree_path),
        "base_branch": base_branch,
    }


def remove(
    run_id: str,
    slug: str,
    *,
    force: bool = False,
    repo_root: Optional[Path] = None,
) -> dict:
    """Remove a worker's worktree and delete its branch.

    Robust to the worktree dir already being manually deleted —
    prunes stale entries with `git worktree prune` before attempting remove.

    Returns dict with: run_id, slug, removed (bool), message
    """
    root = repo_root or _repo_root()
    safe_run = _sanitize_name(run_id)
    safe_slug = _sanitize_name(slug)
    branch = f"team-{safe_run}/{safe_slug}"
    worktree_path = root / ".omni" / "runs" / run_id / "workers" / slug / "worktree"

    # Prune stale entries first
    _run_git(["worktree", "prune"], cwd=root, check=False)

    removed = False
    message = ""

    # Try to remove the worktree
    remove_args = ["worktree", "remove"]
    if force:
        remove_args.append("--force")
    remove_args.append(str(worktree_path))

    result = _run_git(remove_args, cwd=root, check=False)
    if result.returncode == 0:
        removed = True
        message = f"worktree removed: {worktree_path}"
    else:
        # If the worktree dir doesn't exist, prune already handled it
        if not worktree_path.exists():
            removed = True
            message = f"worktree dir already gone, pruned: {worktree_path}"
        else:
            message = f"worktree remove failed: {result.stderr.strip()}"

    # Delete the branch
    branch_result = _run_git(
        ["branch", "-D", branch],
        cwd=root,
        check=False,
    )
    branch_removed = branch_result.returncode == 0

    return {
        "run_id": run_id,
        "slug": slug,
        "branch": branch,
        "worktree_path": str(worktree_path),
        "removed": removed,
        "branch_removed": branch_removed,
        "message": message,
    }


def list_for_team(run_id: str, *, repo_root: Optional[Path] = None) -> list[dict]:
    """Enumerate worktrees under .omni/runs/<run_id>/workers/.

    Parses `git worktree list --porcelain` and filters to those under the
    team's run directory. Also prunes stale entries first.

    Returns list of dicts: {slug, branch, worktree_path, prunable}
    """
    root = repo_root or _repo_root()

    # Prune stale first
    _run_git(["worktree", "prune"], cwd=root, check=False)

    result = _run_git(
        ["worktree", "list", "--porcelain"],
        cwd=root,
        check=False,
    )

    team_run_dir = root / ".omni" / "runs" / run_id / "workers"
    worktrees: list[dict] = []

    if result.returncode != 0:
        return worktrees

    # Parse porcelain output
    current: dict = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[len("worktree "):]}
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line.startswith("HEAD "):
            current["HEAD"] = line[len("HEAD "):]
        elif line == "":
            if current:
                worktrees.append(current)
                current = {}
    if current:
        worktrees.append(current)

    # Filter to team run directory
    team_worktrees: list[dict] = []
    for wt in worktrees:
        wt_path = Path(wt.get("path", ""))
        try:
            # Check if this worktree path is under team's workers dir
            wt_path.relative_to(team_run_dir)
        except ValueError:
            continue

        # Extract slug from path: .omni/runs/<run_id>/workers/<slug>/worktree
        try:
            parts = wt_path.relative_to(team_run_dir).parts
            slug = parts[0] if parts else "unknown"
        except Exception:
            slug = "unknown"

        branch = wt.get("branch", "")
        # Normalize refs/heads/ prefix
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/"):]

        team_worktrees.append({
            "slug": slug,
            "branch": branch,
            "worktree_path": str(wt_path),
            "exists": wt_path.exists(),
            "HEAD": wt.get("HEAD", ""),
        })

    return team_worktrees


def prune(*, repo_root: Optional[Path] = None) -> dict:
    """Run git worktree prune and return info about what was pruned."""
    root = repo_root or _repo_root()
    result = _run_git(["worktree", "prune", "--verbose"], cwd=root, check=False)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="omni_worktree — git worktree manager for WS6 team orchestration"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = sub.add_parser("add", help="Create a worktree for a team worker")
    add_p.add_argument("run_id", help="Team run ID (e.g. team-abc123)")
    add_p.add_argument("slug", help="Worker slug")
    add_p.add_argument("--base-branch", default="main", help="Base branch (default: main)")

    # remove
    rm_p = sub.add_parser("remove", help="Remove a worker worktree")
    rm_p.add_argument("run_id", help="Team run ID")
    rm_p.add_argument("slug", help="Worker slug")
    rm_p.add_argument("--force", action="store_true", help="Force remove even if dirty")

    # list
    ls_p = sub.add_parser("list", help="List worktrees for a team run")
    ls_p.add_argument("run_id", help="Team run ID")

    # prune
    sub.add_parser("prune", help="Prune stale worktree entries")

    args = parser.parse_args(argv)

    if args.command == "add":
        result = add(args.run_id, args.slug, args.base_branch)
        print(json.dumps(result, indent=2))
    elif args.command == "remove":
        result = remove(args.run_id, args.slug, force=args.force)
        print(json.dumps(result, indent=2))
    elif args.command == "list":
        result = list_for_team(args.run_id)
        print(json.dumps(result, indent=2))
    elif args.command == "prune":
        result = prune()
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
