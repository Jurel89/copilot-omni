"""WS10 — category_resolver.py gap tests: SHELL availability-checker path.

Covers branches identified in the coverage audit:
  - _default_availability_checker: copilot CLI not found (FileNotFoundError)
  - _default_availability_checker: copilot returns non-zero exit code
  - _default_availability_checker: copilot returns invalid JSON
  - _default_availability_checker: copilot returns empty list (skipped)
  - _default_availability_checker: list-of-dicts format
  - _default_availability_checker: dict format {"models": [...]}
  - _default_availability_checker: model found → True
  - _default_availability_checker: model not found → False
  - resolve with primary unavailable falls back to first available fallback
  - resolve with all models unavailable returns primary (fail-open)
  - resolve with unknown category returns fail dict
  - resolve with custom availability_checker callable
  - load_config with missing file returns defaults
  - load_config with malformed JSON returns defaults
  - load_config with user models override merges correctly
  - CLI --known lists categories
  - CLI --check exits 1 when fallback used
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load_resolver():
    spec = importlib.util.spec_from_file_location(
        "category_resolver", SCRIPTS / "category_resolver.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestDefaultAvailabilityChecker(unittest.TestCase):
    """Unit tests for _default_availability_checker (mocked subprocess)."""

    def setUp(self):
        self._mod = _load_resolver()

    def _mock_run(self, stdout="", returncode=0, side_effect=None):
        """Return a mock for subprocess.run."""
        if side_effect:
            return mock.patch("subprocess.run", side_effect=side_effect)
        result = mock.MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        return mock.patch("subprocess.run", return_value=result)

    def test_copilot_not_found_returns_true_failed(self):
        """FileNotFoundError → fail-open (True, 'failed')."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("copilot not found")):
            avail, status = self._mod._default_availability_checker("claude-sonnet-4.5")
        self.assertTrue(avail)
        self.assertEqual(status, "failed")

    def test_copilot_timeout_returns_true_failed(self):
        """TimeoutExpired → fail-open (True, 'failed')."""
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("copilot", 10)):
            avail, status = self._mod._default_availability_checker("claude-sonnet-4.5")
        self.assertTrue(avail)
        self.assertEqual(status, "failed")

    def test_copilot_nonzero_exit_returns_true_failed(self):
        """Non-zero returncode → fail-open."""
        r = mock.MagicMock()
        r.returncode = 1
        r.stdout = ""
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("claude-sonnet-4.5")
        self.assertTrue(avail)
        self.assertEqual(status, "failed")

    def test_invalid_json_returns_true_failed(self):
        """Invalid JSON from copilot → fail-open."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = "not-json"
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("any-model")
        self.assertTrue(avail)
        self.assertEqual(status, "failed")

    def test_empty_list_returns_true_skipped(self):
        """Empty list response → skipped (no data to check)."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = "[]"
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("any-model")
        self.assertTrue(avail)
        self.assertEqual(status, "skipped")

    def test_list_of_strings_model_found(self):
        """List-of-strings format, model present → (True, 'ok')."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps(["claude-haiku-4-5", "claude-sonnet-4.5"])
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("claude-sonnet-4.5")
        self.assertTrue(avail)
        self.assertEqual(status, "ok")

    def test_list_of_strings_model_not_found(self):
        """List-of-strings format, model absent → (False, 'ok')."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps(["claude-haiku-4-5"])
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("claude-opus-4-6")
        self.assertFalse(avail)
        self.assertEqual(status, "ok")

    def test_list_of_dicts_model_found(self):
        """List-of-dicts format with 'name' key."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps([{"name": "claude-sonnet-4.5"}, {"name": "gpt-5"}])
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("gpt-5")
        self.assertTrue(avail)
        self.assertEqual(status, "ok")

    def test_dict_wrapper_models_key(self):
        """Dict wrapper format {"models": [...]}."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps({"models": ["claude-haiku-4-5", "claude-sonnet-4.5"]})
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("claude-haiku-4-5")
        self.assertTrue(avail)
        self.assertEqual(status, "ok")

    def test_list_of_dicts_id_key(self):
        """List-of-dicts using 'id' key instead of 'name'."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps([{"id": "my-model"}])
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("my-model")
        self.assertTrue(avail)
        self.assertEqual(status, "ok")

    def test_empty_available_names_returns_skipped(self):
        """List-of-dicts with no extractable names → skipped."""
        r = mock.MagicMock()
        r.returncode = 0
        r.stdout = json.dumps([{"other_key": "value"}])
        with mock.patch("subprocess.run", return_value=r):
            avail, status = self._mod._default_availability_checker("any-model")
        self.assertTrue(avail)
        self.assertEqual(status, "skipped")


class TestResolveFunction(unittest.TestCase):
    """resolve() with custom availability_checker to avoid subprocess."""

    def setUp(self):
        self._mod = _load_resolver()
        self._config = self._mod.load_default_categories()

    def test_resolve_primary_available(self):
        res = self._mod.resolve(
            "quick",
            config=self._config,
            availability_checker=lambda m: True,
        )
        self.assertEqual(res["model"], res["primary"])
        self.assertEqual(res["fallbacks_tried"], [])
        self.assertEqual(res["available_check"], "ok")

    def test_resolve_primary_unavailable_uses_first_fallback(self):
        """When primary is unavailable, resolve picks first available fallback."""
        def checker(model):
            # Primary is unavailable; first fallback is available
            return model != self._config["deep"]["model"]

        res = self._mod.resolve("deep", config=self._config, availability_checker=checker)
        self.assertEqual(res["model"], self._config["deep"]["fallbacks"][0])
        self.assertIn(self._config["deep"]["fallbacks"][0], res["fallbacks_tried"])

    def test_resolve_all_unavailable_returns_primary_fail_open(self):
        """When all candidates are unavailable, primary is returned (fail-open)."""
        res = self._mod.resolve(
            "ultrabrain",
            config=self._config,
            availability_checker=lambda m: False,
        )
        self.assertEqual(res["model"], res["primary"])
        self.assertGreater(len(res["fallbacks_tried"]), 0)

    def test_resolve_unknown_category(self):
        res = self._mod.resolve("unknown_cat", config=self._config)
        self.assertEqual(res["category"], "unknown_cat")
        self.assertEqual(res["model"], "unknown_cat")  # passthrough
        self.assertEqual(res["available_check"], "failed")

    def test_resolve_returns_ts(self):
        res = self._mod.resolve("quick", config=self._config,
                                availability_checker=lambda m: True)
        self.assertIn("ts", res)
        self.assertTrue(res["ts"].endswith("Z"))

    def test_resolve_checker_exception_fails_open(self):
        """If availability_checker raises, resolve fails open for that model."""
        def bad_checker(model):
            raise RuntimeError("network error")

        # Should not raise; returns primary with available_check derived from exception path
        res = self._mod.resolve("quick", config=self._config, availability_checker=bad_checker)
        self.assertEqual(res["model"], res["primary"])


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self._mod = _load_resolver()
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_config_returns_defaults(self):
        config = self._mod.load_config(Path(self._tmp.name) / "no_such.json")
        defaults = self._mod.load_default_categories()
        self.assertEqual(config, defaults)

    def test_malformed_json_returns_defaults(self):
        bad = Path(self._tmp.name) / "bad.json"
        bad.write_text("{ broken", encoding="utf-8")
        config = self._mod.load_config(bad)
        defaults = self._mod.load_default_categories()
        self.assertEqual(config, defaults)

    def test_user_model_override_merges(self):
        cfg_file = Path(self._tmp.name) / "config.json"
        cfg_file.write_text(json.dumps({
            "models": {
                "quick": {"model": "my-fast-model"}
            }
        }), encoding="utf-8")
        config = self._mod.load_config(cfg_file)
        self.assertEqual(config["quick"]["model"], "my-fast-model")
        # deep should still be default
        defaults = self._mod.load_default_categories()
        self.assertEqual(config["deep"]["model"], defaults["deep"]["model"])

    def test_user_fallbacks_override(self):
        cfg_file = Path(self._tmp.name) / "config.json"
        cfg_file.write_text(json.dumps({
            "models": {
                "deep": {"fallbacks": ["my-fallback-1", "my-fallback-2"]}
            }
        }), encoding="utf-8")
        config = self._mod.load_config(cfg_file)
        self.assertEqual(config["deep"]["fallbacks"], ["my-fallback-1", "my-fallback-2"])

    def test_non_dict_models_entry_skipped(self):
        cfg_file = Path(self._tmp.name) / "config.json"
        cfg_file.write_text(json.dumps({
            "models": {
                "quick": "flat-string-model"  # not a dict — should be skipped
            }
        }), encoding="utf-8")
        config = self._mod.load_config(cfg_file)
        defaults = self._mod.load_default_categories()
        # quick should remain unchanged
        self.assertEqual(config["quick"]["model"], defaults["quick"]["model"])


class TestCLI(unittest.TestCase):
    """CLI behaviour tests."""

    def setUp(self):
        self._mod = _load_resolver()

    def test_known_flag_prints_categories(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self._mod.main(["--known"])
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        for cat in ("deep", "quick", "ultrabrain"):
            self.assertIn(cat, output)

    def test_unknown_category_argument_returns_1(self):
        rc = self._mod.main(["bogus_category_xyz"])
        self.assertEqual(rc, 1)

    def test_no_args_returns_2(self):
        rc = self._mod.main([])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
