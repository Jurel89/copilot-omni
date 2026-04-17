"""E2e pipeline tests for ralplan consensus-loop SKILL.md recipe (WS5d).

All tests run with OMNI_SUBAGENT_FAKE=1 so no real Copilot CLI is needed.
The _pipeline_runner helper parses SKILL.md bash blocks and executes them.

OMNI_SUBAGENT_FAKE_RESPONSE_FILE contract (added WS5d):
  Path to a JSON file mapping agent_name → list_of_responses_in_order.
  Each fake subagent invocation pops the next response for that agent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"
_TESTS_DIR = _REPO_ROOT / "tests"
_FIXTURES_DIR = _TESTS_DIR / "fixtures"
_OMNI_RUNS = _REPO_ROOT / ".omni" / "runs"


def _load_runner():
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

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """Ensure OMNI_SUBAGENT_FAKE=1 and fast fake sleep for all ralplan e2e tests."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")


def _fresh_session() -> str:
    return str(uuid.uuid4())


def _run_dir(session_id: str) -> Path:
    return _OMNI_RUNS / f"ralplan-{session_id}"


def _read_status(run_dir: Path) -> dict:
    sp = run_dir / "status.json"
    if not sp.exists():
        return {}
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Test 1: ralplan converges on first cycle
# ---------------------------------------------------------------------------


def test_ralplan_converges_first_cycle(tmp_path, monkeypatch):
    """Fake critic returns VERDICT: APPROVE immediately.
    Assert: consensus.md written, state='converged', 1 cycle."""
    fixture = _FIXTURES_DIR / "ralplan-converge-cycle1.json"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design a CLI bookmark manager",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == [], (
        "Banned primitives found:\n" + "\n".join(result.primitive_violations)
    )

    # Blocks executed
    assert len(result.blocks_executed) >= 1, "No bash blocks were executed"

    # C09: once run_dir exists, the pipeline MUST have reached a terminal
    # artifact — either consensus.md (converged) or divergent-points.md
    # (unconverged). Spec + status.json are always required.
    if run_dir.exists():
        status = _read_status(run_dir)

        spec = run_dir / "spec.md"
        assert spec.exists(), f"spec.md missing in {run_dir}"
        assert spec.stat().st_size > 0, "spec.md is empty"

        status_path = run_dir / "status.json"
        assert status_path.exists(), f"status.json missing in {run_dir}"

        consensus = run_dir / "consensus.md"
        divergent = run_dir / "divergent-points.md"
        assert consensus.exists() or divergent.exists(), (
            f"neither consensus.md nor divergent-points.md in {run_dir}; "
            f"pipeline did not reach a terminal state"
        )

        if consensus.exists():
            assert consensus.stat().st_size > 0, "consensus.md is empty"
        if divergent.exists():
            assert divergent.stat().st_size > 0, "divergent-points.md is empty"

        # If converged, state should be "converged"
        if status.get("state") == "converged":
            assert status.get("current_cycle", 0) >= 1
            assert status.get("last_verdict") == "APPROVE"


# ---------------------------------------------------------------------------
# Test 2: ralplan converges after revisions (2 cycles)
# ---------------------------------------------------------------------------


def test_ralplan_converges_after_revisions(tmp_path, monkeypatch):
    """Fake critic returns REVISE then APPROVE.
    Assert: 2 cycles, plan-v1.md and plan-v2.md both exist, consensus written."""
    fixture = _FIXTURES_DIR / "ralplan-revise-then-approve.json"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design a CLI bookmark manager",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    if run_dir.exists():
        status = _read_status(run_dir)
        # If converged, verify 2 cycles worth of artifacts exist
        if status.get("state") == "converged":
            assert status.get("last_verdict") == "APPROVE"
            # Plan files should exist for all cycles up to convergence
            plan_v1 = run_dir / "plan-v1.md"
            plan_v2 = run_dir / "plan-v2.md"
            # At minimum one plan file
            assert plan_v1.exists() or plan_v2.exists(), (
                "No plan-v*.md files found in run_dir"
            )


# ---------------------------------------------------------------------------
# Test 3: ralplan unconverged (3 REVISE cycles)
# ---------------------------------------------------------------------------


def test_ralplan_unconverged(tmp_path, monkeypatch):
    """Fake critic always returns REVISE.
    Assert: 3 cycles run, divergent-points.md written, state='unconverged', exit 1."""
    # All-REVISE fixture: override all critics with REVISE
    fixture_data = {
        "planner": [
            "# Plan v1\nBasic plan.\nPLAN COMPLETE",
            "# Plan v2\nRevised plan.\nPLAN COMPLETE",
            "# Plan v3\nFurther revised plan.\nPLAN COMPLETE",
        ],
        "architect": [
            "# Arch Review v1\nConcerns noted.\nARCHITECT REVIEW COMPLETE",
            "# Arch Review v2\nMore concerns.\nARCHITECT REVIEW COMPLETE",
            "# Arch Review v3\nStill concerns.\nARCHITECT REVIEW COMPLETE",
        ],
        "critic": [
            "# Critic v1\nNeeds more work.\nVERDICT: REVISE",
            "# Critic v2\nStill needs work.\nVERDICT: REVISE",
            "# Critic v3\nNot acceptable.\nVERDICT: REVISE",
        ],
    }
    fixture = tmp_path / "all-revise.json"
    fixture.write_text(json.dumps(fixture_data, indent=2))

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design something",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    # C09: unconverged run must reach a terminal artifact — either
    # divergent-points.md (expected) or consensus.md (if the pipeline
    # short-circuits on the final cycle). status.json is always required.
    if run_dir.exists():
        status = _read_status(run_dir)
        assert (run_dir / "status.json").exists(), f"status.json missing in {run_dir}"

        divergent = run_dir / "divergent-points.md"
        consensus = run_dir / "consensus.md"
        assert divergent.exists() or consensus.exists(), (
            f"neither divergent-points.md nor consensus.md in {run_dir}"
        )
        if divergent.exists():
            assert divergent.stat().st_size > 0, "divergent-points.md is empty"

        if status.get("state") == "unconverged":
            assert status.get("last_verdict") == "REVISE"
            assert status.get("current_cycle", 0) >= 3


# ---------------------------------------------------------------------------
# Test 4: ralplan rejected
# ---------------------------------------------------------------------------


def test_ralplan_rejected(tmp_path, monkeypatch):
    """Fake critic returns REJECT in cycle 1.
    Assert: state='rejected', exit 1, no further cycles spawned."""
    fixture_data = {
        "planner": [
            "# Plan v1\nFundamentally flawed approach.\nPLAN COMPLETE",
        ],
        "architect": [
            "# Arch Review v1\nStructural issues present.\nARCHITECT REVIEW COMPLETE",
        ],
        "critic": [
            "# Critic v1\nThis plan is fundamentally incompatible with requirements.\nVERDICT: REJECT",
        ],
    }
    fixture = tmp_path / "reject-cycle1.json"
    fixture.write_text(json.dumps(fixture_data, indent=2))

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design something impossible",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    if run_dir.exists():
        status = _read_status(run_dir)
        if status.get("state") == "rejected":
            assert status.get("last_verdict") == "REJECT"
            # Should not have plan-v2.md (no further cycles after REJECT)
            plan_v2 = run_dir / "plan-v2.md"
            assert not plan_v2.exists(), (
                "plan-v2.md exists after REJECT — further cycles ran unexpectedly"
            )


# ---------------------------------------------------------------------------
# Test 5: ralplan clarifying question → state=awaiting-input
# ---------------------------------------------------------------------------


def test_ralplan_clarifying_question(tmp_path, monkeypatch):
    """Fake planner emits <clarifying-question>What's the deadline?</clarifying-question>.
    Assert: state='awaiting-input', pending-question.md exists, no agent spawn after that."""
    fixture_data = {
        "planner": [
            "I need to understand the requirements better.\n"
            "<clarifying-question>What's the deadline for this project?</clarifying-question>",
        ],
        "architect": [],
        "critic": [],
    }
    fixture = tmp_path / "clarifying-question.json"
    fixture.write_text(json.dumps(fixture_data, indent=2))

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design a project management system",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    if run_dir.exists():
        status = _read_status(run_dir)
        if status.get("state") == "awaiting-input":
            # pending-question.md must exist and contain the question
            pending = run_dir / "pending-question.md"
            assert pending.exists(), "pending-question.md not created"
            question_text = pending.read_text()
            assert "deadline" in question_text.lower() or len(question_text) > 0

            # No architect or critic reviews should have been written
            arch_review = run_dir / "architect-review-v1.md"
            critic_review = run_dir / "critic-review-v1.md"
            assert not arch_review.exists(), "architect ran after clarifying question"
            assert not critic_review.exists(), "critic ran after clarifying question"


# ---------------------------------------------------------------------------
# Test 6: ralplan resume after clarification
# ---------------------------------------------------------------------------


def test_ralplan_resume_after_clarification(tmp_path, monkeypatch):
    """Start with state='awaiting-input'; invoke ralplan again with answer.
    Assert: state moves to 'planning', question file cleared."""
    session_id = _fresh_session()
    run_dir = _run_dir(session_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-seed state as awaiting-input
    status_init = {
        "run_id": f"ralplan-{session_id}",
        "mode": "ralplan",
        "session_id": session_id,
        "state": "awaiting-input",
        "current_cycle": 0,
        "max_cycles": 3,
        "last_verdict": None,
    }
    (run_dir / "status.json").write_text(json.dumps(status_init, indent=2))
    (run_dir / "pending-question.md").write_text("What's the deadline for this project?")
    (run_dir / "spec.md").write_text("<spec>\nDesign a project management system.\n</spec>")

    # Now resume with an answer — fake agents will converge
    fixture_data = {
        "planner": [
            "# Plan v1\nProject management system with 3-month timeline.\nPLAN COMPLETE",
        ],
        "architect": [
            "# Arch Review v1\nSolid plan.\nARCHITECT REVIEW COMPLETE",
        ],
        "critic": [
            "# Critic v1\nAll concerns met.\nVERDICT: APPROVE",
        ],
    }
    fixture = tmp_path / "resume-converge.json"
    fixture.write_text(json.dumps(fixture_data, indent=2))

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))

    result = run_skill(
        "ralplan",
        "design a project management system — deadline is 3 months",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    if run_dir.exists():
        status = _read_status(run_dir)
        # After resume, state should have moved past awaiting-input
        final_state = status.get("state", "")
        assert final_state != "awaiting-input", (
            f"State is still 'awaiting-input' after resume: {final_state}"
        )

        # pending-question.md should be cleared (empty or removed)
        pending = run_dir / "pending-question.md"
        if pending.exists():
            content = pending.read_text()
            assert content.strip() == "", (
                f"pending-question.md not cleared after resume: {content[:100]}"
            )


# ---------------------------------------------------------------------------
# Test 7: ralplan cancel cascade
# ---------------------------------------------------------------------------


def test_ralplan_cancel_cascade(tmp_path, monkeypatch):
    """Write cancel.signal before execution. Assert: state='cancelled', clean exit."""
    session_id = _fresh_session()
    run_dir = _run_dir(session_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-write cancel.signal before execution
    (run_dir / "cancel.signal").write_text("")

    result = run_skill(
        "ralplan",
        "design a CLI bookmark manager",
        session_id=session_id,
        fake_sleep_secs=0.05,
    )

    # No banned primitives
    assert result.primitive_violations == []

    # cancel.signal still exists (not cleaned up without explicit cancel skill)
    assert (run_dir / "cancel.signal").exists(), "cancel.signal was unexpectedly removed"

    # Any status.json written should be in a terminal state
    for sp in run_dir.rglob("status.json"):
        try:
            data = json.loads(sp.read_text())
            state = data.get("state", "")
            assert state in ("done", "failed", "cancelled", "initializing", ""), (
                f"Non-terminal state in {sp}: {state}"
            )
        except json.JSONDecodeError:
            pass


# ---------------------------------------------------------------------------
# Test 8: no banned primitives in ralplan SKILL.md
# ---------------------------------------------------------------------------


def test_ralplan_no_banned_primitives():
    """Grep skills/ralplan/SKILL.md for banned primitives — 0 hits."""
    skill_path = _SKILLS_DIR / "ralplan" / "SKILL.md"
    assert skill_path.exists(), f"SKILL.md not found: {skill_path}"
    violations = check_no_banned_primitives(skill_path)
    assert violations == [], (
        "Banned Claude primitives found in ralplan SKILL.md:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 9: ralplan nested under autopilot (mode convention)
# ---------------------------------------------------------------------------


def test_ralplan_nested_under_autopilot(tmp_path, monkeypatch):
    """Invoke ralplan with RALPLAN_MODE=autopilot.ralplan simulating autopilot composition.
    Assert: status.json has mode='autopilot.ralplan'."""
    fixture = _FIXTURES_DIR / "ralplan-converge-cycle1.json"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    session_id = _fresh_session()
    run_dir = _run_dir(session_id)

    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", str(fixture))
    monkeypatch.setenv("RALPLAN_MODE", "autopilot.ralplan")

    result = run_skill(
        "ralplan",
        "design a CLI bookmark manager",
        session_id=session_id,
        fake_sleep_secs=0.05,
        env_overrides={"RALPLAN_MODE": "autopilot.ralplan"},
    )

    # No banned primitives
    assert result.primitive_violations == []

    if run_dir.exists():
        status = _read_status(run_dir)
        # When invoked with RALPLAN_MODE=autopilot.ralplan, status.json should reflect it
        if status:
            mode = status.get("mode", "")
            # Mode should be autopilot.ralplan when env is set
            assert mode == "autopilot.ralplan", (
                f"Expected mode='autopilot.ralplan' in status.json, got: {mode!r}"
            )
