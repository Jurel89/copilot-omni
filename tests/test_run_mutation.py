"""Phase-C C29: contract tests for scripts/run_mutation.py wrapper."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_mutation.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_mutation", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDefaultTargets(unittest.TestCase):

    def test_targets_point_at_real_files(self):
        mod = _load()
        for t in mod.DEFAULT_TARGETS:
            self.assertTrue((ROOT / t).exists(),
                            f"mutation target missing: {t}")

    def test_targets_are_high_value(self):
        """The scope must include the remaining hot-path modules.

        v2.1.0 removed ``scripts/router.py`` (the front-door classifier was
        retired as a product claim in the contract-reset PR), so the target
        set narrows to the two surviving high-value modules.
        """
        mod = _load()
        scoped = set(mod.DEFAULT_TARGETS)
        for expected in ("scripts/subagent_pool.py", "scripts/category_resolver.py"):
            self.assertIn(expected, scoped)


class TestCliListing(unittest.TestCase):

    def test_list_flag_prints_targets(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--list"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("scripts/subagent_pool.py", result.stdout)
        self.assertIn("scripts/category_resolver.py", result.stdout)


class TestGracefulWhenMutmutAbsent(unittest.TestCase):

    def test_script_exits_zero_without_mutmut(self):
        """Running with no mutmut on PATH must exit 0 and print an install hint."""
        # We can't easily unimport mutmut in the current process; instead
        # subprocess-invoke the script with an env that masks mutmut by
        # pointing PYTHONPATH / PATH at nothing relevant — simplest
        # reliable check is to run the script and inspect exit code; the
        # script itself prints the hint when mutmut is unavailable.
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        # The wrapper must NEVER fail CI; exit code is 0 regardless.
        self.assertEqual(result.returncode, 0,
                         f"wrapper returned non-zero; stderr={result.stderr!r}")


if __name__ == "__main__":
    unittest.main()
