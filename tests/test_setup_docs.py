"""Regression tests for setup-skill phase references."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_omni_setup_phase_references_exist():
    skill_path = ROOT / "skills" / "omni-setup" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    matches = re.findall(r"phases/([0-9]{2}-[^`]+?\.md)", text)
    assert matches, "Expected omni-setup to reference at least one phase file"
    for match in matches:
        phase_path = ROOT / "skills" / "omni-setup" / "phases" / match
        assert phase_path.exists(), f"Referenced phase file is missing: {phase_path}"
