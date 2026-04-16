"""Tests for T4 — production guard on OMNI_SUBAGENT_FAKE.

Verifies:
- FAKE=1 + pytest context (PYTEST_CURRENT_TEST set) → fake honored
- FAKE=1 + OMNI_TEST_MODE=1 → fake honored
- FAKE=1 alone (no test context) → REFUSED with WARNING on stderr
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBAGENT_PY = ROOT / "scripts" / "subagent.py"


def _load_subagent_with_env(extra_env: dict) -> object:
    """Load subagent module with specific env vars set."""
    backup = os.environ.copy()
    os.environ.update(extra_env)
    # Remove vars not in extra_env that should be absent
    for key in ["OMNI_SUBAGENT_FAKE", "PYTEST_CURRENT_TEST", "OMNI_TEST_MODE"]:
        if key not in extra_env:
            os.environ.pop(key, None)
    try:
        spec = importlib.util.spec_from_file_location("subagent_guarded", SUBAGENT_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    finally:
        os.environ.clear()
        os.environ.update(backup)


class TestFakeGuard(unittest.TestCase):
    """_FAKE is only True when FAKE=1 AND in a recognized test context."""

    def setUp(self):
        self.env_backup = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)

    def test_fake_plus_pytest_env_honored(self):
        """FAKE=1 + PYTEST_CURRENT_TEST → _FAKE is True."""
        mod = _load_subagent_with_env({
            "OMNI_SUBAGENT_FAKE": "1",
            "PYTEST_CURRENT_TEST": "tests/test_foo.py::test_bar",
        })
        self.assertTrue(mod._FAKE)

    def test_fake_plus_test_mode_honored(self):
        """FAKE=1 + OMNI_TEST_MODE=1 → _FAKE is True."""
        mod = _load_subagent_with_env({
            "OMNI_SUBAGENT_FAKE": "1",
            "OMNI_TEST_MODE": "1",
        })
        self.assertTrue(mod._FAKE)

    def test_fake_alone_refused(self):
        """FAKE=1 without test context → _FAKE is False and warning emitted."""
        import io
        from contextlib import redirect_stderr

        backup = os.environ.copy()
        os.environ["OMNI_SUBAGENT_FAKE"] = "1"
        os.environ.pop("PYTEST_CURRENT_TEST", None)
        os.environ.pop("OMNI_TEST_MODE", None)
        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                spec = importlib.util.spec_from_file_location(
                    "subagent_refused", SUBAGENT_PY)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
            self.assertFalse(mod._FAKE, "_FAKE should be False when no test context")
            warning = buf.getvalue()
            self.assertIn("WARNING", warning)
            self.assertIn("REFUSED", warning)
        finally:
            os.environ.clear()
            os.environ.update(backup)

    def test_no_fake_env_is_false(self):
        """No OMNI_SUBAGENT_FAKE → _FAKE is False."""
        mod = _load_subagent_with_env({})
        self.assertFalse(mod._FAKE)


class TestFakeGuardCLI(unittest.TestCase):
    """CLI subprocess test: FAKE alone emits WARNING to stderr."""

    def test_fake_alone_warns_on_stderr(self):
        env = os.environ.copy()
        env["OMNI_SUBAGENT_FAKE"] = "1"
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("OMNI_TEST_MODE", None)
        # Import-only: python3 -c "import importlib.util; ..."
        proc = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util, sys; "
             "spec = importlib.util.spec_from_file_location('sa', 'scripts/subagent.py'); "
             "mod = importlib.util.module_from_spec(spec); "
             "spec.loader.exec_module(mod)"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
        )
        self.assertIn("WARNING", proc.stderr)
        self.assertIn("REFUSED", proc.stderr)


if __name__ == "__main__":
    unittest.main()
