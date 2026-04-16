"""Tests for scripts/parse_critic_verdict.py (WS5d)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "parse_critic_verdict",
        _REPO_ROOT / "scripts" / "parse_critic_verdict.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


pcv = _load_module()
extract_verdict = pcv.extract_verdict


# ---------------------------------------------------------------------------
# extract_verdict unit tests
# ---------------------------------------------------------------------------


def test_approve_verdict():
    text = "Some review text.\nVERDICT: APPROVE\n"
    assert extract_verdict(text) == "APPROVE"


def test_revise_verdict():
    text = "The plan needs work.\nVERDICT: REVISE\n"
    assert extract_verdict(text) == "REVISE"


def test_reject_verdict():
    text = "This plan is fundamentally flawed.\nVERDICT: REJECT\n"
    assert extract_verdict(text) == "REJECT"


def test_missing_verdict_returns_none():
    text = "This review has no verdict line at all."
    assert extract_verdict(text) is None


def test_empty_string_returns_none():
    assert extract_verdict("") is None


def test_multiple_verdicts_last_wins():
    """When multiple VERDICT lines exist, the LAST one wins."""
    text = (
        "VERDICT: REVISE\n"
        "After reconsideration, updating verdict.\n"
        "VERDICT: APPROVE\n"
    )
    assert extract_verdict(text) == "APPROVE"


def test_multiple_verdicts_last_wins_revise():
    text = "VERDICT: APPROVE\nActually reconsidered.\nVERDICT: REVISE\n"
    assert extract_verdict(text) == "REVISE"


def test_case_sensitive_lowercase_ignored():
    """Lowercase 'verdict: approve' must NOT match (case-sensitive)."""
    text = "verdict: approve\nNo uppercase verdict here."
    assert extract_verdict(text) is None


def test_case_sensitive_mixed_ignored():
    text = "Verdict: APPROVE\n"
    assert extract_verdict(text) is None


def test_verdict_with_trailing_whitespace():
    """Trailing whitespace on the VERDICT line should still match."""
    text = "Review done.\nVERDICT: APPROVE   \n"
    assert extract_verdict(text) == "APPROVE"


def test_verdict_embedded_in_longer_line_ignored():
    """A VERDICT token embedded inside a longer line must NOT match."""
    text = "The VERDICT: APPROVE should only count on its own line\n"
    # The regex requires the line to start with VERDICT:
    # "The VERDICT: APPROVE..." does NOT start with VERDICT — no match
    assert extract_verdict(text) is None


def test_verdict_standalone_line_only():
    """Only a line that IS the verdict (^VERDICT: ...$) counts."""
    text = "  VERDICT: APPROVE\n"  # leading space — does NOT match ^
    assert extract_verdict(text) is None


def test_long_review_with_approve_at_end():
    review = "\n".join([
        "# Critic Review v2",
        "",
        "## Strengths",
        "- Clear acceptance criteria",
        "- Good separation of concerns",
        "",
        "## Concerns",
        "- Missing error handling in Step 3",
        "",
        "## Verdict",
        "All major concerns addressed.",
        "",
        "VERDICT: APPROVE",
    ])
    assert extract_verdict(review) == "APPROVE"


# ---------------------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------------------


def test_main_reads_file(tmp_path):
    review = tmp_path / "critic-review-v1.md"
    review.write_text("Analysis...\nVERDICT: REVISE\n")
    assert pcv.main([str(review)]) == 0


def test_main_missing_file_exits_1(tmp_path):
    assert pcv.main([str(tmp_path / "nonexistent.md")]) == 1


def test_main_no_verdict_exits_1(tmp_path):
    review = tmp_path / "review.md"
    review.write_text("No verdict here.\n")
    assert pcv.main([str(review)]) == 1


def test_main_approve_prints_and_exits_0(tmp_path, capsys):
    review = tmp_path / "review.md"
    review.write_text("Good plan.\nVERDICT: APPROVE\n")
    rc = pcv.main([str(review)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "APPROVE"


def test_main_reject_prints_and_exits_0(tmp_path, capsys):
    review = tmp_path / "review.md"
    review.write_text("Fundamental flaw.\nVERDICT: REJECT\n")
    rc = pcv.main([str(review)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "REJECT"


# ---------------------------------------------------------------------------
# T7: fence-stripping adversarial tests
# ---------------------------------------------------------------------------


def test_verdict_inside_fence_ignored():
    """T7: VERDICT line inside a fenced code block must NOT win."""
    text = (
        "The critic's outside verdict is APPROVE.\n"
        "VERDICT: APPROVE\n"
        "\n"
        "Here is what a REJECT looks like:\n"
        "```\n"
        "VERDICT: REJECT\n"
        "```\n"
    )
    # The outside APPROVE must win, not the fenced REJECT
    assert extract_verdict(text) == "APPROVE"


def test_verdict_inside_tilde_fence_ignored():
    """T7: tilde fences are also stripped."""
    text = (
        "VERDICT: REVISE\n"
        "~~~\n"
        "VERDICT: REJECT\n"
        "~~~\n"
    )
    assert extract_verdict(text) == "REVISE"


def test_only_fenced_verdict_returns_none():
    """T7: if the only VERDICT line is inside a fence, return None."""
    text = (
        "This is a review with no outside verdict.\n"
        "```markdown\n"
        "VERDICT: APPROVE\n"
        "```\n"
    )
    assert extract_verdict(text) is None


def test_fence_then_outside_verdict():
    """T7: a VERDICT after the closing fence is picked up correctly."""
    text = (
        "```\n"
        "VERDICT: REJECT\n"
        "```\n"
        "Actually the plan is fine.\n"
        "VERDICT: APPROVE\n"
    )
    assert extract_verdict(text) == "APPROVE"


def test_multiple_fences_last_outside_wins():
    """T7: last VERDICT outside any fence wins."""
    text = (
        "VERDICT: REVISE\n"
        "```\n"
        "VERDICT: REJECT\n"
        "```\n"
        "Further reflection:\n"
        "VERDICT: APPROVE\n"
        "```\n"
        "VERDICT: REJECT\n"
        "```\n"
    )
    assert extract_verdict(text) == "APPROVE"
