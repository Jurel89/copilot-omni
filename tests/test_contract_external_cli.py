#!/usr/bin/env python3
"""Tests for the --check-external-cli gate in scripts/verify_plugin_contract.py.

Enforces ADR-0000 decisions 1 (Copilot-CLI host only) and 7 (no external CLIs
invoked).  All tests use subprocess so they exercise the real CLI surface.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Absolute path to the validator script — never relies on cwd.
_VALIDATOR = Path(__file__).resolve().parent.parent / "scripts" / "verify_plugin_contract.py"
_REPO_ROOT = _VALIDATOR.parent.parent


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_VALIDATOR)] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _make_minimal_tree(tmp_path: Path) -> None:
    """Create the directory skeleton the validator expects."""
    for d in ("skills", "commands", "agents", "scripts", "hooks", "mcp", "tests", "docs/ADR"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Test 1: clean tree passes
# ---------------------------------------------------------------------------


def test_external_cli_check_passes_on_clean_tree():
    """The current repo (post-cleanup) must pass --check-external-cli."""
    result = _run(["--check-external-cli"], cwd=_REPO_ROOT)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"Expected exit 0 on clean tree; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # Validator prints "passed" or "clean" on success.
    assert any(word in combined.lower() for word in ("pass", "clean")), (
        f"Expected 'pass' or 'clean' in output; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# Test 2: HUD reintroduction is caught
# ---------------------------------------------------------------------------


def test_external_cli_check_catches_hud_reintroduction(tmp_path: Path):
    """A skill containing 'statusLine' must be flagged."""
    _make_minimal_tree(tmp_path)
    skill_dir = tmp_path / "skills" / "hud_test"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hud-test\n---\n\nThis skill uses statusLine to show status.\n",
        encoding="utf-8",
    )

    result = _run(["--check-external-cli"], cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"Expected non-zero exit when statusLine present; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "statusLine" in combined, (
        f"Expected 'statusLine' mentioned in output; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# Test 3: codex binary invocation is caught
# ---------------------------------------------------------------------------


def test_external_cli_check_catches_codex_invocation(tmp_path: Path):
    """A skill calling 'codex --help' must be flagged."""
    _make_minimal_tree(tmp_path)
    skill_dir = tmp_path / "skills" / "codex_test"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: codex-test\n---\n\nRun codex --help to see options.\n",
        encoding="utf-8",
    )

    result = _run(["--check-external-cli"], cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"Expected non-zero exit when 'codex --' present; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "codex" in combined.lower(), (
        f"Expected 'codex' mentioned in output; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# Test 4: excluded paths (CHANGELOG, ADR) are ignored
# ---------------------------------------------------------------------------


def test_external_cli_check_ignores_changelog_and_adr(tmp_path: Path):
    """Forbidden tokens in CHANGELOG.md and docs/ADR/ must NOT cause failures."""
    _make_minimal_tree(tmp_path)

    # Every forbidden token in CHANGELOG.md
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "Removed :hud, statusLine, omni-hud, /copilot-omni:hud, /copilot-omni:ask,\n"
        "/copilot-omni:omni-teams, ccg orchestration, @openai/codex, @google/gemini-cli,\n"
        "claude -- flag, codex -- flag, gemini -- flag, omc ask claude, omni-teams skill,\n"
        "parallel (claude|codex|gemini) router.\n",
        encoding="utf-8",
    )

    # Same tokens in an ADR file
    adr_file = tmp_path / "docs" / "ADR" / "ADR-0000-decisions.md"
    adr_file.write_text(
        "# ADR-0000\n\nDecision 1: no statusLine HUD (:hud / omni-hud).\n"
        "Decision 7: no codex -- or gemini -- invocations, no ccg, no omni-teams.\n",
        encoding="utf-8",
    )

    result = _run(["--check-external-cli"], cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"Expected exit 0 when tokens only in excluded paths; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 5: external-cli check is included in --all
# ---------------------------------------------------------------------------


def test_external_cli_check_included_in_all():
    """--all must execute the external-cli check (regression gate for wiring)."""
    result = _run(["--all"], cwd=_REPO_ROOT)
    combined = result.stdout + result.stderr
    assert "external-cli" in combined, (
        f"Expected 'external-cli' in --all output; got:\n{combined}"
    )
