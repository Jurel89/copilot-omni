"""Unit tests for the omni CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMNI = ROOT / "scripts" / "omni.py"


def run(args, cwd=None):
    proc = subprocess.run(
        [sys.executable, str(OMNI), *args],
        capture_output=True, text=True, cwd=cwd, timeout=15,
    )
    return proc.stdout, proc.stderr, proc.returncode


class TestCli(unittest.TestCase):

    def test_version(self):
        out, _, rc = run(["version"])
        self.assertEqual(rc, 0)
        self.assertIn("1.0.0", out)

    def test_init_creates_config(self):
        with tempfile.TemporaryDirectory() as td:
            out, _, rc = run(["init", "--path", td])
            self.assertEqual(rc, 0, out)
            cfg = Path(td) / ".omni" / "config.json"
            self.assertTrue(cfg.exists())
            data = json.loads(cfg.read_text())
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["profile"], "standard")

    def test_list_all(self):
        out, _, rc = run(["list", "all"])
        self.assertEqual(rc, 0)
        self.assertIn("# Skills", out)
        self.assertIn("# Agents", out)

    def test_doctor_returns_ok_in_repo(self):
        out, _, rc = run(["doctor"])
        self.assertIn("python:", out)
        self.assertIn("plugin.json:", out)


if __name__ == "__main__":
    unittest.main()
