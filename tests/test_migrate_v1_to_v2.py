"""
tests/test_migrate_v1_to_v2.py — unit tests for scripts/omni_migrate_v1_to_v2.py

Three required cases:
  1. No v1 dir present  → noop (SKIP lines, exit 0)
  2. v1 dir present     → renamed to v2 (DONE line, exit 0)
  3. Both v1 and v2     → abort / warn (WARN line, no overwrite, exit 0)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from omni_migrate_v1_to_v2 import migrate  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_migrate(tmp_path: Path, *, dry_run: bool, capsys) -> tuple[int, str]:
    rc = migrate(tmp_path, dry_run=dry_run)
    captured = capsys.readouterr()
    return rc, captured.out


# ---------------------------------------------------------------------------
# Case 1: no v1 dir → noop
# ---------------------------------------------------------------------------


class TestNoV1Dir:
    """When .omc/ is absent, migrate() should be a complete noop."""

    def test_exit_zero(self, tmp_path, capsys):
        rc, _ = _capture_migrate(tmp_path, dry_run=False, capsys=capsys)
        assert rc == 0

    def test_skip_line_emitted(self, tmp_path, capsys):
        _, out = _capture_migrate(tmp_path, dry_run=False, capsys=capsys)
        assert "SKIP" in out

    def test_no_omni_dir_created(self, tmp_path, capsys):
        _capture_migrate(tmp_path, dry_run=False, capsys=capsys)
        assert not (tmp_path / ".omni").exists()

    def test_dry_run_also_noop(self, tmp_path, capsys):
        rc, out = _capture_migrate(tmp_path, dry_run=True, capsys=capsys)
        assert rc == 0
        assert "SKIP" in out
        assert not (tmp_path / ".omni").exists()


# ---------------------------------------------------------------------------
# Case 2: v1 dir present → renamed
# ---------------------------------------------------------------------------


class TestV1Present:
    """When .omc/ exists and .omni/ does not, migration should rename."""

    @pytest.fixture()
    def repo_with_omc(self, tmp_path):
        omc = tmp_path / ".omc"
        omc.mkdir()
        (omc / "config.json").write_text('{"schema_version": 1}')
        return tmp_path

    def test_dry_run_does_not_rename(self, repo_with_omc, capsys):
        rc, out = _capture_migrate(repo_with_omc, dry_run=True, capsys=capsys)
        assert rc == 0
        assert "DRY" in out
        assert (repo_with_omc / ".omc").exists()
        assert not (repo_with_omc / ".omni").exists()

    def test_apply_renames_directory(self, repo_with_omc, capsys):
        rc, out = _capture_migrate(repo_with_omc, dry_run=False, capsys=capsys)
        assert rc == 0
        assert "DONE" in out
        assert not (repo_with_omc / ".omc").exists()
        assert (repo_with_omc / ".omni").exists()

    def test_contents_preserved_after_rename(self, repo_with_omc, capsys):
        _capture_migrate(repo_with_omc, dry_run=False, capsys=capsys)
        cfg = repo_with_omc / ".omni" / "config.json"
        assert cfg.exists()
        assert "schema_version" in cfg.read_text()

    def test_apply_is_idempotent(self, repo_with_omc, capsys):
        """Running apply twice should not error on second run (WARN, not ERR)."""
        _capture_migrate(repo_with_omc, dry_run=False, capsys=capsys)
        # Second run: .omc is gone, .omni exists — should be SKIP/noop
        rc2, out2 = _capture_migrate(repo_with_omc, dry_run=False, capsys=capsys)
        assert rc2 == 0
        assert "ERR" not in out2


# ---------------------------------------------------------------------------
# Case 3: both v1 and v2 present → abort / warn, no overwrite
# ---------------------------------------------------------------------------


class TestBothPresent:
    """When both .omc/ and .omni/ exist, migration must warn and not overwrite."""

    @pytest.fixture()
    def repo_with_both(self, tmp_path):
        omc = tmp_path / ".omc"
        omc.mkdir()
        (omc / "old.txt").write_text("old state")

        omni = tmp_path / ".omni"
        omni.mkdir()
        (omni / "new.txt").write_text("new state")
        return tmp_path

    def test_exit_zero(self, repo_with_both, capsys):
        rc, _ = _capture_migrate(repo_with_both, dry_run=False, capsys=capsys)
        assert rc == 0

    def test_warn_line_emitted(self, repo_with_both, capsys):
        _, out = _capture_migrate(repo_with_both, dry_run=False, capsys=capsys)
        assert "WARN" in out

    def test_omni_not_overwritten(self, repo_with_both, capsys):
        _capture_migrate(repo_with_both, dry_run=False, capsys=capsys)
        # .omni/new.txt must still exist (not replaced by .omc contents)
        assert (repo_with_both / ".omni" / "new.txt").exists()
        assert not (repo_with_both / ".omni" / "old.txt").exists()

    def test_omc_still_present(self, repo_with_both, capsys):
        """Source dir must NOT be deleted when destination already exists."""
        _capture_migrate(repo_with_both, dry_run=False, capsys=capsys)
        assert (repo_with_both / ".omc").exists()

    def test_dry_run_also_warns(self, repo_with_both, capsys):
        rc, out = _capture_migrate(repo_with_both, dry_run=True, capsys=capsys)
        assert rc == 0
        assert "WARN" in out


# ---------------------------------------------------------------------------
# Guidance output
# ---------------------------------------------------------------------------


class TestGuidanceOutput:
    """migrate() always prints env-var guidance regardless of outcome."""

    def test_guidance_mentions_omni_skip_hooks(self, tmp_path, capsys):
        _, out = _capture_migrate(tmp_path, dry_run=True, capsys=capsys)
        assert "OMNI_SKIP_HOOKS" in out

    def test_guidance_mentions_migration_doc(self, tmp_path, capsys):
        _, out = _capture_migrate(tmp_path, dry_run=True, capsys=capsys)
        assert "MIGRATION.md" in out


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLI:
    """Smoke tests for the argparse layer via main()."""

    def test_main_dry_run_default(self, tmp_path, capsys):
        from omni_migrate_v1_to_v2 import main

        rc = main(["--repo-root", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out

    def test_main_explicit_dry_run(self, tmp_path, capsys):
        from omni_migrate_v1_to_v2 import main

        rc = main(["--dry-run", "--repo-root", str(tmp_path)])
        assert rc == 0

    def test_main_apply(self, tmp_path, capsys):
        from omni_migrate_v1_to_v2 import main

        rc = main(["--apply", "--repo-root", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "APPLY" in out
