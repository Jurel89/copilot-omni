"""Phase-C C12: Windows tmux gate semantics + documentation."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "omni_team_c12", ROOT / "scripts" / "omni_team.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWindowsGate(unittest.TestCase):

    def test_is_windows_helper(self):
        mod = _load()
        # Matches sys.platform for the current runner.
        expected = sys.platform == "win32"
        self.assertEqual(mod._is_windows(), expected)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only enforcement path")
    def test_gate_enforced_without_env(self):
        mod = _load()
        saved = os.environ.pop("OMNI_EXPERIMENTAL_TEAM", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                mod._TmuxSession.create("c12-gate-test")
            msg = str(ctx.exception)
            self.assertIn("OMNI_EXPERIMENTAL_TEAM", msg)
            self.assertIn("TEAM-WINDOWS.md", msg)
        finally:
            if saved is not None:
                os.environ["OMNI_EXPERIMENTAL_TEAM"] = saved


class TestDocsAndMessage(unittest.TestCase):

    def test_team_windows_doc_exists(self):
        doc = ROOT / "docs" / "TEAM-WINDOWS.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        for token in ("OMNI_EXPERIMENTAL_TEAM", "wezterm", "Windows Terminal",
                      "_SubprocessWorkerHost"):
            self.assertIn(token, text)

    def test_error_message_references_doc(self):
        src = (ROOT / "scripts" / "omni_team.py").read_text(encoding="utf-8")
        self.assertIn("TEAM-WINDOWS.md", src)
        self.assertIn("use_tmux=False", src)
        self.assertIn("wezterm", src)


if __name__ == "__main__":
    unittest.main()
