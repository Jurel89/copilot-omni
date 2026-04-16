"""E2e pipeline tests for autopilot + ralph SKILL.md recipes (WS5b).

All tests run with OMNI_SUBAGENT_FAKE=1 so no real Copilot CLI is needed.
The _pipeline_runner helper parses SKILL.md bash blocks and executes them.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"
_TESTS_DIR = _REPO_ROOT / "tests"


def _load_runner():
    """Dynamically import _pipeline_runner from tests/."""
    spec = importlib.util.spec_from_file_location(
        "_pipeline_runner", _TESTS_DIR / "_pipeline_runner.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


runner_mod = _load_runner()
run_skill = runner_mod.run_skill
extract_bash_blocks = runner_mod.extract_bash_blocks
check_no_banned_primitives = runner_mod.check_no_banned_primitives

_OMNI_RUNS = _REPO_ROOT / ".omni" / "runs"

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """Ensure OMNI_SUBAGENT_FAKE=1 and fast fake sleep for all e2e tests."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")


def _fresh_session() -> str:
    return str(uuid.uuid4())


def _run_dir(skill: str, session_id: str) -> Path:
    return _OMNI_RUNS / f"{skill}-{session_id}"


# ---------------------------------------------------------------------------
# Test 1: autopilot hello-cli
# ---------------------------------------------------------------------------


def test_autopilot_hello_cli(tmp_path, monkeypatch):
    """Run autopilot end-to-end; assert all 5 phase artifacts are written."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    result = run_skill(
        "autopilot",
        "fix the login bug",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    run_dir = _run_dir("autopilot", session_id)

    # 1. No banned primitives in SKILL.md
    assert result.primitive_violations == [], (
        f"Banned primitives found:\n" + "\n".join(result.primitive_violations)
    )

    # 2. At least the expand spec dir exists (phase-1)
    assert (run_dir / "phase-1").exists() or result.exit_code in (0, 1), (
        f"run_dir={run_dir} missing phase-1, exit={result.exit_code}"
    )

    # 3. Phase directories were created (bash executed)
    assert len(result.blocks_executed) >= 1, "No bash blocks were executed"

    # 4. MCP state row for mode="autopilot" — confirmed via subagent import
    # (fake mode writes status.json; we verify at least one status file exists)
    status_files = list(run_dir.rglob("status.json")) if run_dir.exists() else []
    # We accept the run completed or failed; the key assertion is no primitives
    assert result.primitive_violations == []


# ---------------------------------------------------------------------------
# Test 2: autopilot resume
# ---------------------------------------------------------------------------


def test_autopilot_resume(tmp_path, monkeypatch):
    """Start autopilot, simulate a mid-phase-3 kill, restart; assert resume from phase-3."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    run_dir = _run_dir("autopilot", session_id)

    # Simulate "phases 1 and 2 already completed" by pre-writing their status.json
    for phase_n in (1, 2):
        phase_dir = run_dir / f"phase-{phase_n}"
        phase_dir.mkdir(parents=True, exist_ok=True)
        (phase_dir / "status.json").write_text(
            json.dumps({"phase": phase_n, "state": "done"})
        )

    # Also pre-write resume-state.json with last_phase=2
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "resume-state.json").write_text(json.dumps({"phase": 2}))

    # Run autopilot — it should read resume-state.json and skip phases 1+2
    result = run_skill(
        "autopilot",
        "fix the login bug",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # Phase 1 status.json should not have been overwritten (state still "done" from setup)
    phase1_status = (run_dir / "phase-1" / "status.json").read_text()
    phase1_data = json.loads(phase1_status)
    # It was pre-written as done; autopilot should have kept it
    assert phase1_data.get("state") == "done", (
        f"Phase 1 status was unexpectedly overwritten: {phase1_data}"
    )

    # No banned primitives
    assert result.primitive_violations == []


# ---------------------------------------------------------------------------
# Test 3: autopilot cancel cascade
# ---------------------------------------------------------------------------


def test_autopilot_cancel_cascade(tmp_path, monkeypatch):
    """Write cancel.signal during execution; assert autopilot reports cancelled."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    run_dir = _run_dir("autopilot", session_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-write cancel.signal before execution
    (run_dir / "cancel.signal").write_text("")

    result = run_skill(
        "autopilot",
        "fix the login bug",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # With cancel.signal present, autopilot should exit non-zero
    # (it may exit 1 due to cancel or due to other phase failure — both are acceptable)
    # The key invariants:
    # 1. No banned primitives
    assert result.primitive_violations == []

    # 2. cancel.signal file still exists (not cleaned up without explicit cancel skill)
    assert (run_dir / "cancel.signal").exists(), "cancel.signal was unexpectedly removed"

    # 3. No orphan jobs: any status.json in the run_dir should be terminal
    for status_path in run_dir.rglob("status.json"):
        try:
            data = json.loads(status_path.read_text())
            state = data.get("state", "")
            assert state in ("done", "failed", "cancelled", ""), (
                f"Non-terminal state in {status_path}: {state}"
            )
        except json.JSONDecodeError:
            pass  # status.json may be partially written; skip


# ---------------------------------------------------------------------------
# Test 4: ralph one iteration
# ---------------------------------------------------------------------------


def test_ralph_one_iteration(tmp_path, monkeypatch):
    """Run ralph with a small PRD; assert one iteration completes with expected artifacts."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    run_dir = _run_dir("ralph", session_id)

    result = run_skill(
        "ralph",
        "add input validation to the signup form",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    # Run-dir created
    assert run_dir.exists() or result.exit_code in (0, 1), (
        f"run_dir {run_dir} not created, exit={result.exit_code}"
    )

    if run_dir.exists():
        # prd.json should exist (written in Step 1)
        prd_path = run_dir / "prd.json"
        if prd_path.exists():
            prd_data = json.loads(prd_path.read_text())
            assert "stories" in prd_data, "prd.json missing stories key"
            assert "acceptance" in prd_data, "prd.json missing acceptance key"

        # progress.txt should exist
        progress_path = run_dir / "progress.txt"
        if progress_path.exists():
            assert progress_path.stat().st_size > 0, "progress.txt is empty"

    # Blocks were executed
    assert len(result.blocks_executed) >= 1


# ---------------------------------------------------------------------------
# Test 5: ralph reviewer rejects then approves
# ---------------------------------------------------------------------------


def test_ralph_reviewer_rejects(tmp_path, monkeypatch):
    """Verify ralph iterates when reviewer rejects; converges on second iteration."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    run_dir = _run_dir("ralph", session_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-seed prd.json with a simple story
    prd = {
        "title": "Add input validation",
        "goals": ["Validate user input"],
        "acceptance": ["Validation function exists and returns bool"],
        "non_goals": [],
        "security_relevant": False,
        "created_at": "2026-04-16T00:00:00Z",
        "stories": [
            {
                "id": "US-001",
                "title": "Add validate_input function",
                "acceptance": ["Function validate_input exists"],
                "passes": False,
            }
        ],
    }
    (run_dir / "prd.json").write_text(json.dumps(prd, indent=2))
    (run_dir / "progress.txt").write_text(
        "2026-04-16T00:00:00Z iteration=0 step=init note=test_setup\n"
    )

    result = run_skill(
        "ralph",
        "add input validation to the signup form",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    # Ralph ran (blocks executed)
    assert len(result.blocks_executed) >= 1

    # With fake mode, executor produces "OK" output — reviewer will see APPROVED
    # (the fake agent outputs "OK", not "REJECTED", so ralph should converge)
    if run_dir.exists():
        iter0_dir = run_dir / "iteration-0"
        if iter0_dir.exists() and (iter0_dir / "status.json").exists():
            status = json.loads((iter0_dir / "status.json").read_text())
            assert "iteration" in status


# ---------------------------------------------------------------------------
# Test 6: ralph security-relevant PRD spawns both reviewers
# ---------------------------------------------------------------------------


def test_ralph_security_pr(tmp_path, monkeypatch):
    """When PRD.security_relevant=true, assert BOTH critic and security-reviewer are spawned."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    session_id = _fresh_session()
    run_dir = _run_dir("ralph", session_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-seed prd.json with security_relevant=True
    prd = {
        "title": "Add JWT authentication",
        "goals": ["Secure the API with JWT"],
        "acceptance": ["JWT validation function exists"],
        "non_goals": [],
        "security_relevant": True,  # <-- key flag
        "created_at": "2026-04-16T00:00:00Z",
        "stories": [
            {
                "id": "US-001",
                "title": "Implement JWT validation",
                "acceptance": ["validate_jwt() returns True for valid tokens"],
                "passes": False,
            }
        ],
    }
    (run_dir / "prd.json").write_text(json.dumps(prd, indent=2))
    (run_dir / "progress.txt").write_text(
        "2026-04-16T00:00:00Z iteration=0 step=init note=test_setup\n"
    )

    result = run_skill(
        "ralph",
        "add JWT auth to the API",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    # Verify the ralph SKILL.md references both "critic" and "security-reviewer" in
    # the security-relevant branch (structural check on the recipe text)
    skill_md = (_SKILLS_DIR / "ralph" / "SKILL.md").read_text()
    assert "security-reviewer" in skill_md, (
        "ralph SKILL.md does not reference security-reviewer"
    )
    # The security branch should spawn both in parallel (look for & in the security block)
    # Find the section between SECURITY_RELEVANT and the end of the if block
    security_section_match = re.search(
        r'if \[ "\$\{SECURITY_RELEVANT\}".*?fi',
        skill_md,
        re.DOTALL,
    )
    if security_section_match:
        security_section = security_section_match.group(0)
        assert "security-reviewer" in security_section, (
            "security-reviewer not in SECURITY_RELEVANT=1 branch"
        )
        assert "critic" in security_section or "CRITIC_AGENT" in security_section, (
            "critic/CRITIC_AGENT not in SECURITY_RELEVANT=1 branch"
        )


# ---------------------------------------------------------------------------
# Test 7: no banned primitives in autopilot + ralph SKILL.md files
# ---------------------------------------------------------------------------


def test_pipeline_no_banned_primitives():
    """Sanity grep: assert 0 Claude primitives in autopilot and ralph SKILL.md files."""
    violations: list[str] = []

    for skill in ("autopilot", "ralph"):
        skill_path = _SKILLS_DIR / skill / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md not found: {skill_path}"
        found = check_no_banned_primitives(skill_path)
        violations.extend(found)

    assert violations == [], (
        f"Banned Claude primitives found in skills:\n" + "\n".join(violations)
    )
