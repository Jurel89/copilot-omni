"""Phase-C C03: falling exemption-cap schedule (25 → 22 → 18 → 12)."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts" / "verify_plugin_contract.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_pc", VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFallingScheduleBoundaries(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("OMNI_EXEMPTION_CAP_OVERRIDE",
                                 "OMNI_EXEMPTION_CAP_DATE")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_before_phase_c(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2025-12-31"), 25)

    def test_on_phase_c_start(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-04-17"), 22)

    def test_mid_phase_c(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-05-15"), 22)

    def test_step_2(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-08-01"), 18)

    def test_step_3(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-11-01"), 12)

    def test_after_steady_state(self):
        v = _load()
        self.assertEqual(v._current_exemption_cap("2030-01-01"), 12)


class TestEnvOverrides(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("OMNI_EXEMPTION_CAP_OVERRIDE",
                                 "OMNI_EXEMPTION_CAP_DATE")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_env_date_overrides_argument(self):
        os.environ["OMNI_EXEMPTION_CAP_DATE"] = "2026-11-01"
        v = _load()
        # argument should be ignored because the env var wins.
        self.assertEqual(v._current_exemption_cap("2025-01-01"), 12)

    def test_env_override_wins_absolute(self):
        os.environ["OMNI_EXEMPTION_CAP_OVERRIDE"] = "99"
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-11-01"), 99)

    def test_bad_override_falls_back_to_schedule(self):
        os.environ["OMNI_EXEMPTION_CAP_OVERRIDE"] = "not-a-number"
        v = _load()
        self.assertEqual(v._current_exemption_cap("2026-04-17"), 22)


class TestBudgetCheckUsesSchedule(unittest.TestCase):

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("OMNI_EXEMPTION_CAP_OVERRIDE",
                                 "OMNI_EXEMPTION_CAP_DATE")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_messages_report_current_cap_not_legacy_25(self):
        os.environ["OMNI_EXEMPTION_CAP_DATE"] = "2026-11-01"  # step-3 → cap=12
        v = _load()
        ok, msgs = v.check_exemption_budget()
        # We don't know if the repo happens to pass/fail at 12 in aggregate,
        # but the reported cap must be 12, not the legacy constant 25.
        joined = "\n".join(msgs)
        self.assertIn("/12", joined)
        self.assertNotIn("/25", joined)


if __name__ == "__main__":
    unittest.main()
