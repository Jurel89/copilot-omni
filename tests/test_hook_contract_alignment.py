"""Hook contract alignment regression test.

Fails if hooks/hooks.json disagrees with docs/HOOK_CONTRACT.md about which
lifecycle events ship as LIVE hooks. Also asserts the sessionStart banner
template in the doc matches the shape produced by session_start.py.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS_JSON = REPO / "hooks" / "hooks.json"
HOOK_DOC = REPO / "docs" / "HOOK_CONTRACT.md"
SESSION_START = REPO / "hooks" / "session_start.py"


def _shipped_events() -> set[str]:
    """Events registered in the shipped hooks.json config."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    return set((data.get("hooks") or {}).keys())


def _documented_live_events() -> set[str]:
    """Events documented as LIVE in HOOK_CONTRACT.md section 2.X."""
    text = HOOK_DOC.read_text(encoding="utf-8")
    # Match headers like "### 2.1 `sessionStart` — `...` (LIVE)"
    pattern = re.compile(
        r"^###\s+\d+\.\d+\s+`([A-Za-z]+)`\s+—\s+`[^`]+`\s+\(LIVE\)\s*$",
        re.MULTILINE,
    )
    return set(pattern.findall(text))


def test_hooks_json_matches_doc_live_set():
    shipped = _shipped_events()
    documented = _documented_live_events()
    missing_from_doc = shipped - documented
    extra_in_doc = documented - shipped
    assert not missing_from_doc, (
        f"hooks.json registers {missing_from_doc!r} but HOOK_CONTRACT.md "
        "does not document them as LIVE."
    )
    assert not extra_in_doc, (
        f"HOOK_CONTRACT.md documents {extra_in_doc!r} as LIVE but "
        "hooks.json does not register them."
    )


def test_session_start_banner_shape_matches_doc():
    """The banner template emitted by _compute_banner must share the same
    four-segment shape (separated by `|`) as the one shown in the doc.
    """
    spec = importlib.util.spec_from_file_location(
        "_hook_session_start_alignment", SESSION_START
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    banner = mod._compute_banner(REPO)
    # Strip `copilot-omni v...` segment back to the four-pipe shape.
    segments = [s.strip() for s in banner.split("|")]
    assert len(segments) == 4, (
        f"Expected 4 pipe-separated banner segments, got {segments!r}"
    )

    doc_text = HOOK_DOC.read_text(encoding="utf-8")
    doc_template = (
        "copilot-omni vX.Y.Z | N skills | N agents | pool=N"
    )
    assert doc_template in doc_text, (
        "HOOK_CONTRACT.md must contain the canonical banner template "
        f"{doc_template!r}. Update the doc if the hook changed shape."
    )


def test_all_shipped_scripts_exist():
    """Every hook referenced by hooks.json must exist on disk."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for event_name, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            cmd = entry.get("bash", "")
            # Extract the hook script path
            m = re.search(r"hooks/([A-Za-z_]+\.py)", cmd)
            assert m is not None, (
                f"Could not locate a hooks/<script>.py reference in "
                f"{event_name} bash command: {cmd!r}"
            )
            script_path = REPO / "hooks" / m.group(1)
            assert script_path.exists(), (
                f"{event_name} references {script_path} which does not exist."
            )
