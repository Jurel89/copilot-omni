"""Phase-C C15: configure-notifications + scripts/notify.py tests."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
NOTIFY = ROOT / "scripts" / "notify.py"
SKILL = ROOT / "skills" / "configure-notifications" / "SKILL.md"


def _load():
    spec = importlib.util.spec_from_file_location("notify", NOTIFY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestConfigure(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_configure_telegram(self):
        mod = _load()
        entry = mod.configure(self.repo, "telegram", bot_token="abc:123",
                              chat_id="-1001", webhook=None,
                              events=["done", "error"])
        self.assertEqual(entry["target"], "telegram")
        cfg = json.loads((self.repo / ".omni" / "config.json").read_text())
        self.assertEqual(len(cfg["notifications"]), 1)

    def test_configure_slack_requires_webhook(self):
        mod = _load()
        with self.assertRaises(ValueError):
            mod.configure(self.repo, "slack", bot_token=None,
                          chat_id=None, webhook=None, events=[])

    def test_configure_replaces_existing(self):
        mod = _load()
        mod.configure(self.repo, "slack", bot_token=None, chat_id=None,
                      webhook="https://hooks.slack.com/s/AAA", events=["done"])
        mod.configure(self.repo, "slack", bot_token=None, chat_id=None,
                      webhook="https://hooks.slack.com/s/AAA", events=["error"])
        cfg = json.loads((self.repo / ".omni" / "config.json").read_text())
        self.assertEqual(len(cfg["notifications"]), 1,
                         "same-webhook configure must replace, not duplicate")
        self.assertEqual(cfg["notifications"][0]["events"], ["error"])

    def test_list_masks_credentials(self):
        mod = _load()
        mod.configure(self.repo, "telegram",
                      bot_token="123456:REAL_SECRET_STRING",
                      chat_id="-111", webhook=None, events=[])
        entries = mod.list_targets(self.repo)
        self.assertEqual(len(entries), 1)
        masked = entries[0]["bot_token"]
        self.assertIn("…", masked)
        self.assertNotIn("REAL_SECRET_STRING", masked)


class TestEmit(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.mod = _load()
        # Configure a slack target by default.
        self.mod.configure(
            self.repo, "slack", bot_token=None, chat_id=None,
            webhook="https://hooks.slack.com/services/AAA/BBB/CCC",
            events=["done", "error"],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_emit_matches_event(self):
        """emit invokes _post exactly once for a matching event."""
        with mock.patch.object(self.mod, "_post",
                               return_value=(200, "ok")) as m:
            delivered = self.mod.emit(self.repo, "done", "hello")
        self.assertEqual(delivered, 1)
        m.assert_called_once()

    def test_emit_skips_unmatched_event(self):
        with mock.patch.object(self.mod, "_post",
                               return_value=(200, "ok")) as m:
            delivered = self.mod.emit(self.repo, "progress", "chug")
        self.assertEqual(delivered, 0)
        m.assert_not_called()

    def test_network_failure_is_nonfatal(self):
        """HTTP 500 or network errors must not crash emit; returns 0 delivered."""
        with mock.patch.object(self.mod, "_post",
                               return_value=(500, "server down")):
            delivered = self.mod.emit(self.repo, "done", "hi")
        self.assertEqual(delivered, 0)


class TestCli(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_configure_and_list(self):
        configure = subprocess.run(
            [sys.executable, str(NOTIFY), "--repo-root", str(self.repo),
             "configure", "discord",
             "--webhook", "https://discord.com/api/webhooks/XYZ",
             "--events", "error"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(configure.returncode, 0,
                         f"stderr={configure.stderr!r}")

        listing = subprocess.run(
            [sys.executable, str(NOTIFY), "--repo-root", str(self.repo), "list"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(listing.returncode, 0)
        body = json.loads(listing.stdout)
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["target"], "discord")
        self.assertIn("discord.com/…", body[0]["webhook"])


class TestSkillShape(unittest.TestCase):

    def test_skill_md_exists_and_declares_triggers(self):
        self.assertTrue(SKILL.exists())
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("triggers:", text)
        self.assertIn("configure notifications", text)


if __name__ == "__main__":
    unittest.main()
