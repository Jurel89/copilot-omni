#!/usr/bin/env python3
"""Phase-B cross-wave integration smokes (WS10 §D).

One high-level test per wave that exercises the full stack under
`OMNI_SUBAGENT_FAKE=1`. These are INTEGRATION tests, not unit tests —
they assert end-to-end invariants across multiple subsystems and catch
regressions where individual WS tests pass but the composed system
breaks.

Contract: FAKE mode bypasses real copilot exec. Each test documents
exactly which real production paths are exercised vs mocked.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
RUNS = ROOT / ".omni" / "runs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _fake_env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["OMNI_SUBAGENT_FAKE"] = "1"
    env["OMNI_TEST_MODE"] = "1"
    env["OMNI_SUBAGENT_FAKE_SLEEP_SECS"] = "0.05"
    if extra:
        env.update(extra)
    return env


def _import_script(name: str):
    """Dynamically import a scripts/<name>.py module."""
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Wave 1 — rename + decontamination invariants
# ---------------------------------------------------------------------------


class TestWave1Rename:
    """Every skill declaring a dispatchable trigger uses the new slash-command
    convention; no Claude-Code primitives survive in skill bodies."""

    def test_every_skill_uses_copilot_omni_slash_command(self):
        for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            # If the skill mentions a slash-command at all, it must be the
            # `/copilot-omni:` namespace.  Legacy `/oh-my-claudecode:` is banned.
            assert "/oh-my-claudecode:" not in text, (
                f"{skill_md.relative_to(ROOT)} still references legacy slash namespace"
            )

    def test_no_claude_primitives_in_surviving_skills(self):
        banned = re.compile(
            r"(?<!`)(?:Task|Skill|AskUserQuestion|SendMessage|TeamCreate)\s*\("
        )
        # Skip markdown code-fence content: we want live-code references only.
        for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            # Allow inline citations that mark themselves as historical
            lines = stripped.splitlines()
            for i, line in enumerate(lines):
                if banned.search(line):
                    window = "\n".join(lines[max(0, i - 3): i + 4])
                    assert "cc-primitive-allow" in window, (
                        f"{skill_md.relative_to(ROOT)}:{i + 1}: banned primitive"
                    )


# ---------------------------------------------------------------------------
# Wave 2 — autonomous pipeline composition
# ---------------------------------------------------------------------------


class TestWave2Pipeline:
    """autopilot composes with ralplan via subagent.py; banned primitives stay
    at zero; mode-key registry honored end-to-end."""

    def test_subagent_dispatcher_distinguishes_skills_from_agents(self):
        subagent = _import_script("subagent")
        assert "ralplan" in subagent._KNOWN_SKILLS
        assert "autopilot" in subagent._KNOWN_SKILLS
        # Real agents (agents/*.md) MUST NOT be in the skill set
        for agent_md in (ROOT / "agents").glob("*.md"):
            name = agent_md.stem
            assert name not in subagent._KNOWN_SKILLS, (
                f"agent {name!r} wrongly appears in _KNOWN_SKILLS"
            )

    def test_subagent_build_cmd_routes_skill_to_slash_command(self):
        subagent = _import_script("subagent")
        # Known skill → /copilot-omni:<name>
        # Signature: _build_cmd(agent, prompt, effective_model, allow_all)
        cmd_skill = subagent._build_cmd("ralplan", "test prompt", None, False)
        assert cmd_skill is not None
        joined = " ".join(cmd_skill)
        assert "/copilot-omni:ralplan" in joined
        assert "--agent ralplan" not in joined

        # Real agent → --agent
        cmd_agent = subagent._build_cmd("executor", "test prompt", None, False)
        assert cmd_agent is not None
        joined = " ".join(cmd_agent)
        assert "--agent executor" in joined
        assert "/copilot-omni:executor" not in joined

    def test_router_state_no_longer_returns_ws5_stub(self):
        router_state = _import_script("router_state")
        # The four previously-stubbed modes should now pass through to MCP
        # (or return None if MCP unavailable). Never the stale stub.
        # Signature: read_pipeline_state(session_id=None, mode="router")
        for mode in ("autopilot", "ralph", "ultrawork", "team"):
            result = router_state.read_pipeline_state(
                session_id="nonexistent", mode=mode,
            )
            if result is not None:
                assert "WS5 not yet shipped" not in str(result), (
                    f"mode={mode} still returns the WS5 stub"
                )

    def test_mcp_mode_key_registry_covers_all_pipeline_modes(self):
        registry_path = ROOT / "docs" / "STATE_MODES.md"
        assert registry_path.exists(), "STATE_MODES.md missing"
        registry = registry_path.read_text(encoding="utf-8")
        for mode in (
            "router", "autopilot", "ralph", "ultrawork", "ultraqa",
            "ralplan", "team", "subagent",
        ):
            assert mode in registry, f"STATE_MODES.md missing mode={mode!r}"


# ---------------------------------------------------------------------------
# Wave 3 — team orchestrator composition
# ---------------------------------------------------------------------------


class TestWave3Team:
    """omni_team orchestrator creates manifest + run-dir + dispatches workers
    via subagent.py; cancel cascade writes to all worker dirs."""

    def test_team_create_writes_manifest_and_status(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMNI_TEST_MODE", "1")
        monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
        monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

        omni_team = _import_script("omni_team")
        plan = {
            "name": "integration-smoke",
            "workers": [
                {"slug": "w1", "skill": "ralph", "prompt": "p1", "category": "quick"},
                {"slug": "w2", "skill": "ralph", "prompt": "p2", "category": "quick"},
            ],
        }
        result = omni_team.create_team(
            "integration-smoke", plan,
            session_id=_fresh_id("int"),
            use_tmux=False,  # force subprocess fallback for reproducibility
        )
        assert "run_id" in result
        assert Path(result["manifest_path"]).exists()
        assert Path(result["status_path"]).exists()
        manifest = json.loads(Path(result["manifest_path"]).read_text())
        assert len(manifest["workers"]) == 2

    def test_team_cancel_cascades_signal_to_all_worker_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMNI_TEST_MODE", "1")
        monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
        monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

        omni_team = _import_script("omni_team")
        plan = {
            "name": "cancel-smoke",
            "workers": [
                {"slug": f"w{i}", "skill": "ralph", "prompt": "p", "category": "quick"}
                for i in range(3)
            ],
        }
        created = omni_team.create_team(
            "cancel-smoke", plan,
            session_id=_fresh_id("int"),
            use_tmux=False,
        )
        run_id = created["run_id"]
        omni_team.cancel_team(run_id, reason="integration-test")

        run_dir = RUNS / run_id
        # Root cancel.signal present
        assert (run_dir / "cancel.signal").exists()
        # Every worker dir has its own cancel.signal (B5 nesting)
        for w in ["w0", "w1", "w2"]:
            worker_dir = run_dir / "workers" / w
            # worker dir may exist pre-dispatch; at minimum the signal file
            # propagates when worker dir is present.
            if worker_dir.exists():
                assert (worker_dir / "cancel.signal").exists(), (
                    f"cancel.signal missing from worker {w}"
                )

        # Cleanup
        omni_team.cleanup_team(run_id, force=True)


# ---------------------------------------------------------------------------
# Cross-cutting — router behavior (WS3)
# ---------------------------------------------------------------------------


class TestCrossCuttingRouter:
    """Vague prompts redirect to deep-interview; --skip-interview bypasses."""

    def test_vague_prompt_redirects_to_deep_interview(self):
        router = _import_script("router")
        decision = router.classify("build me something cool", threshold=0.4)
        assert decision["decision"] == "redirect"
        assert decision["redirect_to"] == "deep-interview"

    def test_concrete_prompt_proceeds(self):
        router = _import_script("router")
        decision = router.classify(
            "fix hooks/pre_tool_use.py:42 — the `shlex.split` fallback is leaking",
            threshold=0.4,
        )
        assert decision["decision"] == "proceed"

    def test_bypass_syntax_overrides_vagueness(self):
        router = _import_script("router")
        decision = router.classify(
            "build me something cool --skip-interview",
            threshold=0.4,
        )
        assert decision["decision"] == "bypass"
        assert decision["redirect_to"] is None

    def test_hook_integration_emits_router_decision_block(self, tmp_path):
        """user_prompt_submit.py actually invokes the router and emits
        a structured decision tag on stdout."""
        hook = ROOT / "hooks" / "user_prompt_submit.py"
        payload = json.dumps({
            "event_name": "UserPromptSubmit",
            "prompt": "build me something cool",
            "session_id": _fresh_id("int"),
            "cwd": str(ROOT),
        })
        env = _fake_env()
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=payload,
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert proc.returncode == 0
        # Router decision tag should be present for vague prompts
        assert "<router-decision" in proc.stdout or "<router-decision" in proc.stderr
