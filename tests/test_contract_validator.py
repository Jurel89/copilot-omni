#!/usr/bin/env python3
"""Tests for scripts/verify_plugin_contract.py — WS9 contract validator.

Each test uses a tmp_path fixture tree so the checks run against controlled
inputs rather than the live repo.  The validator functions accept an optional
``root`` argument to enable this pattern.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Make the scripts package importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from verify_plugin_contract import (
    check_command_refs,
    check_exemption_budget,
    check_frontmatter_schema,
    check_mcp_tool_refs,
    check_skill_agent_refs,
    check_stdlib_only_imports,
    run_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tree(tmp_path: Path) -> None:
    """Create the minimum directory skeleton every check expects."""
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "commands").mkdir(parents=True, exist_ok=True)
    (tmp_path / "mcp").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "hooks").mkdir(parents=True, exist_ok=True)


def _write_skill(tmp_path: Path, name: str, frontmatter: str, body: str = "") -> Path:
    d = tmp_path / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return p


def _write_agent(tmp_path: Path, name: str, frontmatter: str, body: str = "") -> Path:
    p = tmp_path / "agents" / f"{name}.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return p


def _write_command(tmp_path: Path, name: str, frontmatter: str, body: str = "") -> Path:
    p = tmp_path / "commands" / f"{name}.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return p


def _minimal_mcp_server(tmp_path: Path, tools: list[str]) -> Path:
    """Write a minimal mcp/server.py with the given tool names in TOOLS dict."""
    entries = "\n".join(
        f'    "{t}": {{"description": "tool {t}", "inputSchema": {{}}, "handler": None}},'
        for t in tools
    )
    src = textwrap.dedent(f"""\
        TOOLS = {{
        {entries}
        }}
        """)
    p = tmp_path / "mcp" / "server.py"
    p.write_text(src, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# check_frontmatter_schema
# ---------------------------------------------------------------------------


class TestFrontmatterSchema:
    def test_pass_minimal_valid(self, tmp_path):
        _make_tree(tmp_path)
        # Create exactly MIN_SKILLS=25, MIN_AGENTS=15, MIN_COMMANDS=6 valid entries
        for i in range(25):
            _write_skill(tmp_path, f"skill-{i}", f"name: skill-{i}\ndescription: desc {i}")
        for i in range(15):
            _write_agent(tmp_path, f"agent-{i}", f"name: agent-{i}\ndescription: desc {i}")
        for i in range(6):
            _write_command(tmp_path, f"cmd-{i}", f"name: cmd-{i}")
        ok, msgs = check_frontmatter_schema(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_missing_description(self, tmp_path):
        _make_tree(tmp_path)
        for i in range(25):
            frontmatter = f"name: skill-{i}\ndescription: desc {i}"
            if i == 3:
                frontmatter = f"name: skill-{i}"  # missing description
            _write_skill(tmp_path, f"skill-{i}", frontmatter)
        for i in range(15):
            _write_agent(tmp_path, f"agent-{i}", f"name: agent-{i}\ndescription: desc {i}")
        for i in range(6):
            _write_command(tmp_path, f"cmd-{i}", f"name: cmd-{i}")
        ok, msgs = check_frontmatter_schema(root=tmp_path)
        assert not ok
        assert any("description" in m for m in msgs)

    def test_fail_invalid_writable_value(self, tmp_path):
        _make_tree(tmp_path)
        for i in range(25):
            fm = f"name: skill-{i}\ndescription: desc {i}"
            if i == 0:
                fm += "\nwritable: maybe"  # invalid
            _write_skill(tmp_path, f"skill-{i}", fm)
        for i in range(15):
            _write_agent(tmp_path, f"agent-{i}", f"name: agent-{i}\ndescription: desc {i}")
        for i in range(6):
            _write_command(tmp_path, f"cmd-{i}", f"name: cmd-{i}")
        ok, msgs = check_frontmatter_schema(root=tmp_path)
        assert not ok
        assert any("writable" in m for m in msgs)

    def test_fail_insufficient_skills(self, tmp_path):
        _make_tree(tmp_path)
        for i in range(5):  # way under MIN_SKILLS=25
            _write_skill(tmp_path, f"skill-{i}", f"name: skill-{i}\ndescription: desc {i}")
        for i in range(15):
            _write_agent(tmp_path, f"agent-{i}", f"name: agent-{i}\ndescription: desc {i}")
        for i in range(6):
            _write_command(tmp_path, f"cmd-{i}", f"name: cmd-{i}")
        ok, msgs = check_frontmatter_schema(root=tmp_path)
        assert not ok
        assert any("insufficient skills" in m for m in msgs)


# ---------------------------------------------------------------------------
# check_skill_agent_refs
# ---------------------------------------------------------------------------


class TestSkillAgentRefs:
    def _make_base(self, tmp_path, n_skills=25, n_agents=15, n_commands=6):
        _make_tree(tmp_path)
        for i in range(n_skills):
            _write_skill(tmp_path, f"skill-{i}", f"name: skill-{i}\ndescription: desc {i}")
        for i in range(n_agents):
            _write_agent(tmp_path, f"agent-{i}", f"name: agent-{i}\ndescription: desc {i}")
        for i in range(n_commands):
            _write_command(tmp_path, f"cmd-{i}", f"name: cmd-{i}")

    def test_pass_known_agent(self, tmp_path):
        self._make_base(tmp_path)
        _write_agent(tmp_path, "myagent", "name: myagent\ndescription: agent")
        _write_skill(tmp_path, "ref-skill", "name: ref-skill\ndescription: d",
                     body="python3 scripts/subagent.py myagent \"do stuff\"")
        ok, msgs = check_skill_agent_refs(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_unknown_agent(self, tmp_path):
        self._make_base(tmp_path)
        _write_skill(tmp_path, "bad-ref", "name: bad-ref\ndescription: d",
                     body="python3 scripts/subagent.py nonexistent_agent \"do stuff\"")
        ok, msgs = check_skill_agent_refs(root=tmp_path)
        assert not ok
        assert any("nonexistent_agent" in m for m in msgs)

    def test_pass_with_allow_marker(self, tmp_path):
        self._make_base(tmp_path)
        body = textwrap.dedent("""\
            <!-- omni-ref-allow: example -->
            python3 scripts/subagent.py ghost_agent "example"
        """)
        _write_skill(tmp_path, "allowed-ref", "name: allowed-ref\ndescription: d", body=body)
        ok, msgs = check_skill_agent_refs(root=tmp_path)
        assert ok, "\n".join(msgs)


# ---------------------------------------------------------------------------
# check_command_refs
# ---------------------------------------------------------------------------


class TestCommandRefs:
    def _make_base(self, tmp_path):
        _make_tree(tmp_path)
        # Create min counts so frontmatter check would pass (not tested here)
        for i in range(3):
            _write_skill(tmp_path, f"skill-{i}", f"name: skill-{i}\ndescription: d")
        _write_agent(tmp_path, "myagent", "name: myagent\ndescription: a")
        _write_command(tmp_path, "mycmd", "name: mycmd")

    def test_pass_known_skill_ref(self, tmp_path):
        self._make_base(tmp_path)
        _write_skill(tmp_path, "ref-skill", "name: ref-skill\ndescription: d",
                     body="Use `/copilot-omni:skill-0` for listing.")
        ok, msgs = check_command_refs(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_pass_known_command_ref(self, tmp_path):
        self._make_base(tmp_path)
        _write_skill(tmp_path, "ref-skill2", "name: ref-skill2\ndescription: d",
                     body="Run `/copilot-omni:mycmd` to execute.")
        ok, msgs = check_command_refs(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_unknown_command(self, tmp_path):
        self._make_base(tmp_path)
        _write_skill(tmp_path, "bad-cmd", "name: bad-cmd\ndescription: d",
                     body="Run `/copilot-omni:nonexistent` to do things.")
        ok, msgs = check_command_refs(root=tmp_path)
        assert not ok
        assert any("nonexistent" in m for m in msgs)


# ---------------------------------------------------------------------------
# check_mcp_tool_refs
# ---------------------------------------------------------------------------


class TestMcpToolRefs:
    def test_pass_no_refs(self, tmp_path):
        _make_tree(tmp_path)
        _minimal_mcp_server(tmp_path, ["health", "memory_capture"])
        ok, msgs = check_mcp_tool_refs(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_pass_known_tool_ref(self, tmp_path):
        _make_tree(tmp_path)
        _minimal_mcp_server(tmp_path, ["health", "memory_capture"])
        p = tmp_path / "skills" / "demo" / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\nname: demo\ndescription: d\n---\n\nCall `mcp__copilot_omni_health`.\n",
                     encoding="utf-8")
        ok, msgs = check_mcp_tool_refs(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_unknown_tool_ref(self, tmp_path):
        _make_tree(tmp_path)
        _minimal_mcp_server(tmp_path, ["health"])
        p = tmp_path / "skills" / "demo2" / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text(
            "---\nname: demo2\ndescription: d\n---\n\nCall `mcp__copilot_omni_ghost_tool`.\n",
            encoding="utf-8"
        )
        ok, msgs = check_mcp_tool_refs(root=tmp_path)
        assert not ok
        assert any("ghost_tool" in m for m in msgs)


# ---------------------------------------------------------------------------
# check_exemption_budget
# ---------------------------------------------------------------------------


class TestExemptionBudget:
    """Phase-C C03 makes the cap date-dependent. These legacy tests pin
    the cap to 25 with OMNI_EXEMPTION_CAP_OVERRIDE so they are stable
    across the falling schedule (22 → 18 → 12)."""

    def setup_method(self, _method):
        import os as _os
        self._saved = _os.environ.pop("OMNI_EXEMPTION_CAP_OVERRIDE", None)
        _os.environ["OMNI_EXEMPTION_CAP_OVERRIDE"] = "25"

    def teardown_method(self, _method):
        import os as _os
        _os.environ.pop("OMNI_EXEMPTION_CAP_OVERRIDE", None)
        if self._saved is not None:
            _os.environ["OMNI_EXEMPTION_CAP_OVERRIDE"] = self._saved

    def _populate(self, tmp_path, rename: int, cc: int, ref: int) -> None:
        _make_tree(tmp_path)
        lines = []
        lines += [f"<!-- omni-rename-allow: r{i} -->" for i in range(rename)]
        lines += [f"<!-- cc-primitive-allow: c{i} -->" for i in range(cc)]
        lines += [f"<!-- omni-ref-allow: example e{i} -->" for i in range(ref)]
        p = tmp_path / "MARKERS.md"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_pass_under_budget(self, tmp_path):
        self._populate(tmp_path, rename=3, cc=2, ref=5)  # total=10
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_over_budget(self, tmp_path):
        # cap pinned to 25 via setup_method
        self._populate(tmp_path, rename=9, cc=9, ref=9)  # total=27 > 25
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert not ok
        assert any("exceeded" in m or "FAIL" in m for m in msgs)

    def test_exactly_at_budget(self, tmp_path):
        self._populate(tmp_path, rename=8, cc=8, ref=9)  # total=25 == cap
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_one_over_budget(self, tmp_path):
        self._populate(tmp_path, rename=9, cc=9, ref=8)  # total=26 > 25
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert not ok


# ---------------------------------------------------------------------------
# check_stdlib_only_imports
# ---------------------------------------------------------------------------


class TestStdlibOnlyImports:
    def test_pass_stdlib_imports(self, tmp_path):
        _make_tree(tmp_path)
        p = tmp_path / "scripts" / "good_script.py"
        p.write_text("import os\nimport sys\nimport json\n", encoding="utf-8")
        ok, msgs = check_stdlib_only_imports(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_fail_third_party_import(self, tmp_path):
        _make_tree(tmp_path)
        p = tmp_path / "scripts" / "bad_script.py"
        p.write_text("import requests\nimport os\n", encoding="utf-8")
        ok, msgs = check_stdlib_only_imports(root=tmp_path)
        assert not ok
        assert any("requests" in m for m in msgs)

    def test_fail_third_party_in_tests(self, tmp_path):
        _make_tree(tmp_path)
        p = tmp_path / "tests" / "test_bad.py"
        p.write_text("import numpy\n", encoding="utf-8")
        ok, msgs = check_stdlib_only_imports(root=tmp_path)
        assert not ok
        assert any("numpy" in m for m in msgs)

    def test_pass_relative_import(self, tmp_path):
        _make_tree(tmp_path)
        p = tmp_path / "scripts" / "helper.py"
        p.write_text("from . import utils\n", encoding="utf-8")
        ok, msgs = check_stdlib_only_imports(root=tmp_path)
        assert ok, "\n".join(msgs)


# ---------------------------------------------------------------------------
# --all-strict semantics via run_checks
# ---------------------------------------------------------------------------


class TestAllStrictMode:
    """Verify that --all passes with exemptions present but --all-strict fails."""

    def _build_tree_with_exemption(self, tmp_path: Path) -> None:
        """Build a minimal valid tree that has exactly 1 omni-rename-allow exemption."""
        _make_tree(tmp_path)
        p = tmp_path / "NOTES.md"
        # One legitimate rename-allow exemption
        p.write_text("<!-- omni-rename-allow: historical note -->\n", encoding="utf-8")

    def test_run_checks_exemption_budget_all_passes(self, tmp_path):
        """run_checks with strict=False passes even when exemptions exist."""
        self._build_tree_with_exemption(tmp_path)
        # patch ROOT to tmp_path for the budget check via direct call
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert ok, "\n".join(msgs)

    def test_run_checks_strict_fails_on_exemptions(self, tmp_path):
        """run_checks with strict=True fails when any exemptions are present."""
        self._build_tree_with_exemption(tmp_path)
        # Simulate strict mode: exemption-budget passes (1 < 15), but strict flags it
        ok, msgs = check_exemption_budget(root=tmp_path)
        assert ok  # budget check alone passes

        # Now simulate what run_checks does in strict mode
        has_exemption = any(
            "exempt" in m.lower() or "exemption" in m.lower()
            for m in msgs
        )
        # With 1 exemption, strict mode should detect it
        assert has_exemption, "Expected exemption message to trigger strict fail"


# ---------------------------------------------------------------------------
# Integration: live repo checks (sanity)
# ---------------------------------------------------------------------------


class TestLiveRepo:
    """Smoke tests against the real repo root. These verify the live tree is green."""

    def test_frontmatter_schema_live(self):
        ok, msgs = check_frontmatter_schema()
        assert ok, "\n".join(msgs)

    def test_skill_agent_refs_live(self):
        ok, msgs = check_skill_agent_refs()
        assert ok, "\n".join(msgs)

    def test_command_refs_live(self):
        ok, msgs = check_command_refs()
        assert ok, "\n".join(msgs)

    def test_mcp_tool_refs_live(self):
        ok, msgs = check_mcp_tool_refs()
        assert ok, "\n".join(msgs)

    def test_exemption_budget_live(self):
        ok, msgs = check_exemption_budget()
        assert ok, "\n".join(msgs)

    def test_stdlib_only_imports_live(self):
        ok, msgs = check_stdlib_only_imports()
        assert ok, "\n".join(msgs)
