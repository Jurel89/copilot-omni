"""Phase-C C22: migrator --rollback flag + docs.

Covers:
- `--rollback` dry-run does not mutate filesystem.
- `--rollback --apply` renames .omni/ back to .omc/.
- Refuses when destination (.omc/) already exists.
- Migration docs exist and reference --rollback.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "omni_migrate_v1_to_v2.py"


def _load():
    spec = importlib.util.spec_from_file_location("omni_migrate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestRollbackFlag(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        (self.repo / ".omni").mkdir()
        (self.repo / ".omni" / "marker").write_text("v2-state")

    def tearDown(self):
        self._tmp.cleanup()

    def test_rollback_dry_run_does_not_mutate(self):
        mod = _load()
        # Redirect home so the ~/.omc path is a no-op in the sandbox.
        rc = mod.migrate(self.repo, dry_run=True, rollback=True)
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / ".omni" / "marker").exists(),
                        ".omni/ must be untouched in dry-run")
        self.assertFalse((self.repo / ".omc").exists(),
                         ".omc/ must not be created in dry-run")

    def test_rollback_apply_renames_omni_to_omc(self):
        mod = _load()
        rc = mod.migrate(self.repo, dry_run=False, rollback=True)
        self.assertEqual(rc, 0)
        self.assertFalse((self.repo / ".omni").exists())
        self.assertTrue((self.repo / ".omc" / "marker").exists())

    def test_rollback_refuses_when_omc_already_present(self):
        (self.repo / ".omc").mkdir()
        mod = _load()
        rc = mod.migrate(self.repo, dry_run=False, rollback=True)
        # Still exits 0 (no error) but skips the location with WARN.
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / ".omni" / "marker").exists(),
                        ".omni/ must be preserved when .omc/ exists")

    def test_cli_rollback_flag_advertised(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--rollback", result.stdout)
        self.assertIn("LAST-RESORT", result.stdout)


class TestMigrationRollbackDocs(unittest.TestCase):

    def test_doc_exists_and_mentions_rollback(self):
        doc = ROOT / "docs" / "MIGRATION-ROLLBACK.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("--rollback", text)
        self.assertIn(".omni/", text)
        self.assertIn(".omc/", text)


if __name__ == "__main__":
    unittest.main()
