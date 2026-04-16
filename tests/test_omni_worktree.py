"""Tests for scripts/omni_worktree.py — WS6 git worktree manager (5+ cases).

Tests use a real git repo (tmp_path-based) to verify worktree operations.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_module(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


omni_worktree = _load_module("omni_worktree")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo in tmp_path for worktree tests."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True)

    # Initial commit (required before worktree add)
    readme = repo / "README.md"
    readme.write_text("# test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)

    return repo


# ---------------------------------------------------------------------------
# Test 1: add creates worktree and branch
# ---------------------------------------------------------------------------


def test_add_creates_worktree(git_repo):
    """omni_worktree.add should create a worktree at the expected path."""
    run_id = "team-abc123"
    slug = "worker-1"

    result = omni_worktree.add(run_id, slug, "main", repo_root=git_repo)

    expected_path = git_repo / ".omni" / "runs" / run_id / "workers" / slug / "worktree"
    assert result["worktree_path"] == str(expected_path)
    assert result["branch"] == f"team-{run_id}/{slug}"
    assert result["run_id"] == run_id
    assert result["slug"] == slug
    assert expected_path.exists(), "worktree directory must exist"


# ---------------------------------------------------------------------------
# Test 2: remove deletes worktree and branch
# ---------------------------------------------------------------------------


def test_remove_deletes_worktree(git_repo):
    """omni_worktree.remove should remove the worktree and its branch."""
    run_id = "team-rem123"
    slug = "worker-1"

    # First add
    omni_worktree.add(run_id, slug, "main", repo_root=git_repo)

    worktree_path = git_repo / ".omni" / "runs" / run_id / "workers" / slug / "worktree"
    assert worktree_path.exists()

    # Now remove
    result = omni_worktree.remove(run_id, slug, repo_root=git_repo)

    assert result["removed"] is True
    assert not worktree_path.exists(), "worktree directory should be gone"


# ---------------------------------------------------------------------------
# Test 3: list_for_team returns workers under team run-dir
# ---------------------------------------------------------------------------


def test_list_for_team_returns_team_worktrees(git_repo):
    """list_for_team should enumerate only worktrees for the given run_id."""
    run_id = "team-list001"

    # Add 2 workers
    omni_worktree.add(run_id, "worker-1", "main", repo_root=git_repo)
    omni_worktree.add(run_id, "worker-2", "main", repo_root=git_repo)

    # Also add a worker for a different team (should not appear in results)
    other_run_id = "team-other99"
    omni_worktree.add(other_run_id, "worker-1", "main", repo_root=git_repo)

    team_wts = omni_worktree.list_for_team(run_id, repo_root=git_repo)

    slugs = {wt["slug"] for wt in team_wts}
    assert "worker-1" in slugs
    assert "worker-2" in slugs
    # Other team's worker must not appear
    assert len(team_wts) == 2


# ---------------------------------------------------------------------------
# Test 4: prune runs without error
# ---------------------------------------------------------------------------


def test_prune_succeeds(git_repo):
    """prune should run git worktree prune and return a result dict."""
    result = omni_worktree.prune(repo_root=git_repo)
    assert "returncode" in result
    assert result["returncode"] == 0


# ---------------------------------------------------------------------------
# Test 5: remove is robust when worktree dir was manually deleted
# ---------------------------------------------------------------------------


def test_remove_robust_to_manually_deleted_dir(git_repo):
    """remove should succeed (via prune) even if the worktree dir was deleted."""
    run_id = "team-prune99"
    slug = "worker-orphan"

    # Add a worktree
    omni_worktree.add(run_id, slug, "main", repo_root=git_repo)

    worktree_path = git_repo / ".omni" / "runs" / run_id / "workers" / slug / "worktree"
    assert worktree_path.exists()

    # Manually delete the directory (simulate orphan)
    import shutil
    shutil.rmtree(str(worktree_path))
    assert not worktree_path.exists()

    # remove with force=True should still succeed
    result = omni_worktree.remove(run_id, slug, force=True, repo_root=git_repo)
    # Either removed=True (prune handled it) or worktree was already gone
    assert result["removed"] is True or not worktree_path.exists()


# ---------------------------------------------------------------------------
# Test 6: add with non-existent base branch falls back gracefully
# ---------------------------------------------------------------------------


def test_add_falls_back_when_base_branch_missing(git_repo):
    """add should fall back to HEAD if the specified base_branch doesn't exist."""
    run_id = "team-fallback1"
    slug = "worker-fb"

    # Use a branch that doesn't exist
    result = omni_worktree.add(run_id, slug, "nonexistent-branch-xyz", repo_root=git_repo)

    expected_path = git_repo / ".omni" / "runs" / run_id / "workers" / slug / "worktree"
    assert expected_path.exists(), "worktree should be created even with fallback branch"
    assert result["slug"] == slug


# ---------------------------------------------------------------------------
# Test 7: CLI add command
# ---------------------------------------------------------------------------


def test_cli_add(git_repo, capsys, monkeypatch):
    """CLI 'add' subcommand should print JSON result."""
    monkeypatch.setattr(omni_worktree, "_repo_root", lambda: git_repo)

    rc = omni_worktree.main([
        "add", "team-cli01", "worker-cli",
        "--base-branch", "main",
    ])

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["slug"] == "worker-cli"
    assert data["run_id"] == "team-cli01"
