"""Phase-C C21: skill i18n loader."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "skill_i18n.py"


def _load():
    spec = importlib.util.spec_from_file_location("skill_i18n", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestResolve(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.pop("OMNI_SKILL_LANG", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["OMNI_SKILL_LANG"] = self._saved

    def test_english_default(self):
        mod = _load()
        data = mod.resolve("plan")
        self.assertEqual(data["lang"], "en")
        # English description mentions "Strategic planning".
        self.assertIn("Strategic", data["description"])

    def test_spanish_translation_loaded(self):
        mod = _load()
        data = mod.resolve("plan", lang="es")
        self.assertEqual(data["lang"], "es")
        self.assertIn("Planificación", data["description"])

    def test_missing_translation_falls_back(self):
        mod = _load()
        data = mod.resolve("plan", lang="xx-ZZ")
        self.assertEqual(data["lang"], "en")
        self.assertIn("Strategic", data["description"])

    def test_env_var_respected(self):
        mod = _load()
        os.environ["OMNI_SKILL_LANG"] = "es"
        try:
            data = mod.resolve("plan")
        finally:
            os.environ.pop("OMNI_SKILL_LANG", None)
        self.assertEqual(data["lang"], "es")

    def test_unknown_skill_raises(self):
        mod = _load()
        with self.assertRaises(FileNotFoundError):
            mod.resolve("nonexistent-skill-xyz")


class TestListTranslations(unittest.TestCase):

    def test_plan_lists_es(self):
        mod = _load()
        langs = mod.list_translations("plan")
        self.assertIn("es", langs)

    def test_unknown_skill_returns_empty(self):
        mod = _load()
        self.assertEqual(mod.list_translations("nonexistent"), [])


class TestCli(unittest.TestCase):

    def test_resolve_cli_returns_valid_json(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "resolve", "plan", "--lang", "es"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertEqual(body["lang"], "es")

    def test_list_translations_cli(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "list-translations", "plan"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("es", result.stdout)


class TestDocs(unittest.TestCase):

    def test_i18n_doc_exists(self):
        doc = ROOT / "docs" / "I18N.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("OMNI_SKILL_LANG", text)
        self.assertIn("translations/", text)


if __name__ == "__main__":
    unittest.main()
