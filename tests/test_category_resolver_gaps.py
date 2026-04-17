"""Passthrough contract tests for the simplified category_resolver.

v2.1.0 removed the ``copilot models --json`` subprocess probe (the subcommand
does not exist in GitHub Copilot CLI) and the fallback chain. ``resolve()`` is
now a pure mapping from a logical category to the configured model string;
these tests pin that contract.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load_resolver():
    spec = importlib.util.spec_from_file_location(
        "category_resolver", SCRIPTS / "category_resolver.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestResolveContract(unittest.TestCase):
    def setUp(self):
        self._mod = _load_resolver()

    def test_known_categories(self):
        self.assertEqual(
            self._mod.known_categories(),
            frozenset({"quick", "deep", "ultrabrain"}),
        )

    def test_resolve_returns_expected_keys(self):
        res = self._mod.resolve("deep")
        self.assertEqual(
            set(res.keys()),
            {"category", "model", "primary", "fallbacks_tried", "available_check"},
        )

    def test_resolve_primary_equals_model(self):
        # With the probe removed, primary and model are always the same.
        for cat in ("quick", "deep", "ultrabrain"):
            res = self._mod.resolve(cat)
            self.assertEqual(res["model"], res["primary"], cat)

    def test_resolve_no_fallbacks_tried(self):
        res = self._mod.resolve("quick")
        self.assertEqual(res["fallbacks_tried"], [])
        self.assertEqual(res["available_check"], "skipped")

    def test_resolve_unknown_category_returns_none(self):
        res = self._mod.resolve("no-such-category")
        self.assertIsNone(res["model"])
        self.assertIsNone(res["primary"])

    def test_resolve_does_not_shell_out(self):
        # Regression: confirm resolve() never invokes subprocess. We patch
        # subprocess.run on the module under test; any call would fail the
        # test because the mock raises.
        from unittest import mock
        with mock.patch.object(
            self._mod,
            "subprocess",
            create=True,
            new=mock.MagicMock(
                run=mock.MagicMock(side_effect=AssertionError(
                    "resolve() must not call subprocess"
                ))
            ),
        ):
            self._mod.resolve("deep")


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self._mod = _load_resolver()

    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = self._mod.load_config(Path(td) / "no-such.json")
        self.assertIn("quick", cfg)
        self.assertIn("deep", cfg)
        self.assertIn("ultrabrain", cfg)

    def test_malformed_json_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text("{not-json", encoding="utf-8")
            cfg = self._mod.load_config(p)
        self.assertIn("deep", cfg)

    def test_user_model_override_merges(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text(
                json.dumps({"categories": {"deep": {"model": "gpt-5"}}}),
                encoding="utf-8",
            )
            cfg = self._mod.load_config(p)
        self.assertEqual(cfg["deep"]["model"], "gpt-5")
        # Untouched categories keep their defaults.
        self.assertEqual(cfg["quick"]["model"], "claude-haiku-4-5")


if __name__ == "__main__":
    unittest.main()
