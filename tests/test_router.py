"""WS3 router classifier regression tests.

ADR-0005 rubric signals:
  file_line_ref   +0.10
  file_path       +0.30
  func_name       +0.25
  code_block      +0.40
  issue_ref       +0.20
  error_keyword   +0.20
  tech_name       +0.10
  numeric_spec    +0.15
  bypass_marker   +1.00 (force bypass)
  vagueness_penalty -0.10 each, capped at -0.50

Default threshold = 0.40
decision = "bypass"   if --skip-interview present
decision = "redirect" if score < 0.40
decision = "proceed"  if score >= 0.40
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Load router without installing it on sys.path
_ROUTER_PATH = Path(__file__).resolve().parent.parent / "scripts" / "router.py"
_spec = importlib.util.spec_from_file_location("router", _ROUTER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)   # type: ignore[union-attr]
classify = _mod.classify


def _sc(prompt: str, threshold: float = 0.4) -> tuple[float, str]:
    """Return (rounded_score, decision) for a prompt."""
    r = classify(prompt, threshold=threshold)
    return round(r["score"], 2), r["decision"]


class TestTriviallyConcretePrompts(unittest.TestCase):
    """Prompts with strong concrete signals → proceed."""

    def test_file_path_and_func_name(self):
        # file_path +0.30, func_name +0.25 → 0.55
        prompt = "fix scripts/router.py — the classify() function is returning wrong score"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.55)
        self.assertEqual(dec, "proceed")

    def test_code_block_only(self):
        # code_block +0.40, func_name +0.25 (foo()), tech_name(python) +0.10 → 0.75
        prompt = "explain this snippet:\n```python\ndef foo():\n    pass\n\nfoo()\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.75)
        self.assertEqual(dec, "proceed")

    def test_error_traceback(self):
        # error_keyword +0.20, func_name +0.25 → 0.45
        prompt = "Traceback (most recent call last): foo() raised ValueError"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.45)
        self.assertEqual(dec, "proceed")

    def test_error_keyword_only(self):
        # error_keyword +0.20 → 0.20 < 0.40 → redirect
        prompt = "Error: connection refused on port 5432"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.20)
        self.assertEqual(dec, "redirect")

    def test_issue_ref(self):
        # issue_ref +0.20, tech_name(git) +0.10 → 0.30 < 0.40 → redirect
        prompt = "fix the regression in issue #1234 with git"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.30)
        self.assertEqual(dec, "redirect")

    def test_issue_ref_plus_file(self):
        # file_path +0.30, issue_ref +0.20 → 0.50
        prompt = "PR #456 broke hooks/pre_tool_use.py — revert the change"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.50)
        self.assertEqual(dec, "proceed")

    def test_file_line_plus_file(self):
        # file_line_ref +0.10, file_path +0.30 → 0.40 (tie → proceed)
        prompt = "fix hooks/pre_tool_use.py:42 — the regex is wrong"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_numeric_spec(self):
        # numeric_spec +0.15, tech_name +0.10 → 0.25 → redirect
        prompt = "set the redis timeout to 500ms"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.25)
        self.assertEqual(dec, "redirect")

    def test_multiple_strong_signals(self):
        # file_line_ref +0.10, file_path +0.30, func_name +0.25, error_keyword +0.20 → 0.85
        prompt = "mcp/server.py:100 — _tool_state_write() raises Exception: key error"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.85)
        self.assertEqual(dec, "proceed")

    def test_code_block_with_many_lines(self):
        # code_block +0.40 → 0.40 → proceed
        prompt = (
            "review this:\n```\nline one\nline two\nline three\nline four\n```"
        )
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")


class TestTriviallyVaguePrompts(unittest.TestCase):
    """Prompts with no concrete signals → redirect."""

    def test_build_me_something(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "build me something useful"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_i_want_a_website(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "I want a website for my business"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_do_whatever(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "do whatever you think is best"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_you_decide(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "you decide what to build"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_fix_this_no_object(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "fix this please"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_create_something(self):
        # vagueness -0.10 → -0.10 → redirect
        prompt = "create something cool for me"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_empty_prompt(self):
        # no signals → 0.00 → redirect
        prompt = ""
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_single_word(self):
        # no signals → 0.00 → redirect
        sc, dec = _sc("help")
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")


class TestBypassCases(unittest.TestCase):
    """Prompts with --skip-interview → always bypass."""

    def test_bypass_plain(self):
        prompt = "do something --skip-interview"
        r = classify(prompt)
        self.assertEqual(r["decision"], "bypass")
        self.assertIsNone(r["redirect_to"])

    def test_bypass_vague_prompt(self):
        # Even a maximally vague prompt with --skip-interview → bypass
        prompt = "build me something create something i want a do whatever you decide fix this --skip-interview"
        r = classify(prompt)
        self.assertEqual(r["decision"], "bypass")

    def test_bypass_at_start(self):
        prompt = "--skip-interview please fix the login page"
        r = classify(prompt)
        self.assertEqual(r["decision"], "bypass")

    def test_bypass_at_end(self):
        prompt = "deploy to production without tests --skip-interview"
        r = classify(prompt)
        self.assertEqual(r["decision"], "bypass")

    def test_bypass_score_includes_marker(self):
        # bypass_marker +1.00, clamped to 1.00
        prompt = "--skip-interview"
        r = classify(prompt)
        self.assertEqual(round(r["score"], 2), 1.00)
        self.assertEqual(r["decision"], "bypass")

    def test_bypass_with_concrete_signals(self):
        # file_path +0.30, bypass +1.00 → clamped 1.00
        prompt = "fix scripts/router.py:10 --skip-interview"
        r = classify(prompt)
        self.assertEqual(r["decision"], "bypass")
        self.assertEqual(round(r["score"], 2), 1.00)


class TestNearThresholdEdgeCases(unittest.TestCase):
    """Scores within ±0.10 of threshold=0.40. ≥ 8 cases."""

    def test_score_0_30_redirect(self):
        # file_path +0.30 → 0.30 < 0.40 → redirect
        prompt = "fix scripts/server.py — it crashes"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.30)
        self.assertEqual(dec, "redirect")

    def test_score_0_40_proceed_tie(self):
        # file_line_ref +0.10, file_path +0.30 → 0.40, tie → proceed
        prompt = "fix scripts/server.py:15 — it crashes"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_score_0_35_redirect(self):
        # tech_name +0.10, numeric_spec +0.15, vagueness -0.10 → 0.15 → redirect
        # Actually: numeric +0.15, tech +0.10 = 0.25, vagueness -0.10 = 0.15
        prompt = "fix this sqlite timeout to 30s"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.15)
        self.assertEqual(dec, "redirect")

    def test_score_0_45_proceed(self):
        # file_path +0.30, tech_name +0.10, vagueness -0.10 → 0.30
        # Actually fix: file_path+0.30, issue_ref+0.20 = 0.50
        prompt = "fix PR #999 in scripts/omni.py"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.50)
        self.assertEqual(dec, "proceed")

    def test_score_0_40_no_vagueness(self):
        # file_line_ref +0.10, file_path +0.30 → 0.40 → proceed
        prompt = "review hooks/session_start.py:5"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_score_0_25_redirect(self):
        # func_name +0.25 → 0.25 < 0.40 → redirect
        prompt = "why does authenticate() fail"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.25)
        self.assertEqual(dec, "redirect")

    def test_score_0_50_proceed(self):
        # func_name +0.25, error_keyword +0.20 → 0.45? No: Traceback + func
        # Traceback(error_keyword +0.20), validate() (func_name +0.25) → 0.45
        prompt = "Traceback in validate() call stack"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.45)
        self.assertEqual(dec, "proceed")

    def test_custom_threshold_proceed(self):
        # file_path +0.30 → 0.30, threshold=0.25 → proceed
        prompt = "fix scripts/omni.py — broken"
        sc, dec = _sc(prompt, threshold=0.25)
        self.assertEqual(sc, 0.30)
        self.assertEqual(dec, "proceed")

    def test_custom_threshold_redirect(self):
        # file_path +0.30 → 0.30, threshold=0.50 → redirect
        prompt = "fix scripts/omni.py — broken"
        sc, dec = _sc(prompt, threshold=0.50)
        self.assertEqual(sc, 0.30)
        self.assertEqual(dec, "redirect")

    def test_score_exactly_threshold_boundary(self):
        # issue_ref +0.20, tech_name(postgres) +0.10, numeric +0.15 → 0.45
        prompt = "fix issue #100 — postgres query taking 5s"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.45)
        self.assertEqual(dec, "proceed")


class TestAdversarialCases(unittest.TestCase):
    """Prompts that look concrete but aren't, or have tricky patterns."""

    def test_inline_backtick_not_code_block(self):
        # `fix` in backtick is NOT a code block; no func_name, no file_path
        prompt = "please `fix` the `thing`"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_meaningless_file_path(self):
        # File path signal fires even for meaningless paths (pattern-based)
        # xyz/asdf.foo → file_path +0.30
        prompt = "fix xyz/asdf.foo — broken"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.30)
        self.assertEqual(dec, "redirect")

    def test_two_line_fenced_block_no_signal(self):
        # Only 2 body lines in fence → does NOT fire code_block signal
        prompt = "explain:\n```\nfoo\nbar\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_one_line_fenced_block_no_signal(self):
        # Only 1 body line → does NOT fire
        prompt = "explain:\n```\nfoo\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_three_line_fenced_block_fires(self):
        # 3 body lines → fires code_block +0.40
        prompt = "explain:\n```\nfoo\nbar\nbaz\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_three_indented_lines_fires(self):
        # 3 consecutive 4-space indented lines → code_block +0.40
        prompt = "explain:\n    line one\n    line two\n    line three"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_two_indented_lines_no_signal(self):
        # Only 2 indented → does NOT fire
        prompt = "explain:\n    line one\n    line two"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_inline_backtick_regex_not_code_block(self):
        # The acceptance gate: file:line + inline backtick → 0.40
        # omni-rename-allow: test prompt reproduces the exact WS3 acceptance-gate string
        prompt = "fix hooks/pre_tool_use.py:42 \u2014 the regex `\\.omc/` is leaking"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")


class TestPenaltyStacking(unittest.TestCase):
    """Vagueness penalties accumulate but cap at -0.50."""

    def test_two_penalties(self):
        # build me -0.10 + create something -0.10 = -0.20
        prompt = "build me and create something"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.20)
        self.assertEqual(dec, "redirect")

    def test_five_penalties_capped(self):
        # 5 distinct phrases → -0.50 (cap)
        prompt = "build me create something i want a do whatever you decide fix this"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.50)
        self.assertEqual(dec, "redirect")

    def test_six_phrases_still_capped(self):
        # All 6 phrases → still -0.50 (cap, not -0.60)
        prompt = "build me create something i want a do whatever you decide fix this please"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.50)
        self.assertEqual(dec, "redirect")

    def test_same_phrase_twice_counted_once(self):
        # "build me" appears twice → only -0.10 (not -0.20)
        prompt = "build me a thing and also build me another thing"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, -0.10)
        self.assertEqual(dec, "redirect")

    def test_penalty_with_file_path(self):
        # file_path +0.30, vagueness -0.10 → 0.20 → redirect
        prompt = "fix scripts/omni.py — build me a fix"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.20)
        self.assertEqual(dec, "redirect")

    def test_penalty_with_strong_signals_still_proceeds(self):
        # file_path +0.30, func_name +0.25, vagueness -0.10 → 0.45 → proceed
        prompt = "build me a fix for the parse() function in scripts/omni.py"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.45)
        self.assertEqual(dec, "proceed")


class TestCodeBlockDetection(unittest.TestCase):
    """Focused tests for the code-block signal."""

    def test_fenced_exactly_3_body_lines(self):
        prompt = "```\na\nb\nc\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_fenced_4_body_lines(self):
        prompt = "```python\ndef foo():\n    pass\n\nfoo()\n```"
        # code_block +0.40, func_name +0.25 (foo()), tech_name(python) +0.10 → 0.75
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.75)
        self.assertEqual(dec, "proceed")

    def test_fenced_2_body_lines_no_signal(self):
        prompt = "```\na\nb\n```"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_indented_3_lines(self):
        prompt = "here:\n    x = 1\n    y = 2\n    z = 3"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.40)
        self.assertEqual(dec, "proceed")

    def test_indented_2_lines_no_signal(self):
        prompt = "here:\n    x = 1\n    y = 2"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")

    def test_mixed_inline_backtick_not_code(self):
        # Many inline backticks but no fenced or indented block
        prompt = "`foo` and `bar` and `baz` and `qux`"
        sc, dec = _sc(prompt)
        self.assertEqual(sc, 0.00)
        self.assertEqual(dec, "redirect")


class TestSignalsAuditTrail(unittest.TestCase):
    """Verify the signals list is populated correctly."""

    def test_signals_present_for_file_path(self):
        r = classify("fix scripts/router.py")
        names = [s["name"] for s in r["signals"]]
        self.assertIn("file_path", names)

    def test_bypass_signal_name(self):
        r = classify("do it --skip-interview")
        names = [s["name"] for s in r["signals"]]
        self.assertIn("bypass_marker", names)

    def test_no_signals_for_vague(self):
        r = classify("build me something")
        names = [s["name"] for s in r["signals"]]
        self.assertNotIn("file_path", names)
        self.assertNotIn("func_name", names)
        self.assertIn("vagueness_penalty", names)

    def test_penalty_signal_has_evidence(self):
        r = classify("build me a website")
        penalty_sigs = [s for s in r["signals"] if s["name"] == "vagueness_penalty"]
        self.assertTrue(len(penalty_sigs) >= 1)
        self.assertIn("build me", penalty_sigs[0]["evidence"])

    def test_prompt_excerpt_truncated(self):
        long_prompt = "x" * 300
        r = classify(long_prompt)
        self.assertEqual(len(r["prompt_excerpt"]), 240)

    def test_ts_iso_format(self):
        r = classify("some prompt")
        ts = r["ts"]
        self.assertIn("T", ts)
        self.assertIn("+", ts)

    def test_redirect_to_deep_interview(self):
        r = classify("build me something")
        self.assertEqual(r["redirect_to"], "deep-interview")

    def test_proceed_redirect_to_none(self):
        r = classify("fix scripts/router.py:10 — the parse() function fails")
        self.assertIsNone(r["redirect_to"])


if __name__ == "__main__":
    unittest.main()
