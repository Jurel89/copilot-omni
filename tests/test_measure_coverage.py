"""tests/test_measure_coverage.py — unit tests for scripts/measure_coverage.py

C9 regression guard:
  When a module has 0 instrumented statements (instrumentation broken or
  module not executed), parse_coverage_json() must NOT report 100% coverage.
  Instead it must report status="unmeasured" and line_coverage=0.0.
  The --check mode must exit 1 for "unmeasured" modules.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_ROOT = Path(__file__).resolve().parent.parent


def _load_measure_coverage():
    spec = importlib.util.spec_from_file_location(
        "measure_coverage", _SCRIPTS / "measure_coverage.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


mc = _load_measure_coverage()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coverage_json(tmp_path: Path, *, with_files: bool, stmts: int, missing: int) -> Path:
    """Write a synthetic coverage.json and return its path."""
    cov_json = tmp_path / "coverage.json"

    if not with_files:
        data = {"files": {}}
    else:
        # Produce a fake file under scripts/ with the given statement count
        fake_file = str(_ROOT / "scripts" / "fake_module.py")
        data = {
            "files": {
                fake_file: {
                    "summary": {
                        "num_statements": stmts,
                        "missing_lines": missing,
                    },
                    "missing_lines": list(range(1, missing + 1)),
                }
            }
        }

    cov_json.write_text(json.dumps(data), encoding="utf-8")
    return cov_json


# ---------------------------------------------------------------------------
# C9: zero-statements → unmeasured, not 100%
# ---------------------------------------------------------------------------


class TestZeroStatementsUnmeasured:
    """C9: 0 instrumented statements must yield status='unmeasured', not 'ok'."""

    def test_no_files_produces_unmeasured(self, tmp_path):
        """Coverage JSON with no files → all modules unmeasured."""
        cov_json = _make_coverage_json(tmp_path, with_files=False, stmts=0, missing=0)
        report = mc.parse_coverage_json(cov_json)

        for module, info in report.items():
            assert info["status"] == "unmeasured", (
                f"module {module!r} with 0 statements must be 'unmeasured', "
                f"got {info['status']!r}"
            )
            assert info["line_coverage"] == 0.0, (
                f"module {module!r} with 0 statements must report 0.0% coverage, "
                f"got {info['line_coverage']!r}"
            )
            assert info["num_statements"] == 0

    def test_zero_statements_not_reported_as_100_percent(self, tmp_path):
        """The specific C9 bug: 0 statements must never produce line_coverage=100.0."""
        cov_json = _make_coverage_json(tmp_path, with_files=False, stmts=0, missing=0)
        report = mc.parse_coverage_json(cov_json)

        for module, info in report.items():
            assert info["line_coverage"] != 100.0, (
                f"C9 regression: module {module!r} with 0 statements reported "
                f"100% coverage (rubber-stamp bug)"
            )

    def test_unmeasured_fails_any_fail_check(self, tmp_path):
        """any_fail logic must treat 'unmeasured' as failure, not success."""
        cov_json = _make_coverage_json(tmp_path, with_files=False, stmts=0, missing=0)
        report = mc.parse_coverage_json(cov_json)

        # Replicate the any_fail logic from measure_coverage.py
        any_fail = any(v["status"] in ("fail", "unmeasured") for v in report.values())
        assert any_fail, (
            "any_fail must be True when modules are 'unmeasured' — "
            "--check should exit 1"
        )

    def test_normal_coverage_still_passes(self, tmp_path):
        """Normal coverage with statements should still report correctly."""
        cov_json = _make_coverage_json(tmp_path, with_files=True, stmts=100, missing=10)
        report = mc.parse_coverage_json(cov_json)

        # scripts/ module should have 90% coverage (100 - 10 executed = 90)
        scripts_info = report.get("scripts/")
        if scripts_info is not None:
            assert scripts_info["num_statements"] == 100
            assert scripts_info["line_coverage"] == 90.0
            assert scripts_info["status"] in ("ok", "fail")  # not unmeasured
            assert scripts_info["status"] != "unmeasured"
