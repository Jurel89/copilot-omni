"""Tests for scripts/router_state.py — WS3 stub pipeline-state reader."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_STATE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "router_state.py"
_spec = importlib.util.spec_from_file_location("router_state", _STATE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)   # type: ignore[union-attr]
read_pipeline_state = _mod.read_pipeline_state
_WS5_STUB = _mod._WS5_STUB
_PIPELINE_MODES_WS5 = _mod._PIPELINE_MODES_WS5


class TestStubReturnsForUnknownModes(unittest.TestCase):
    """Non-router modes return the WS5 stub per F4."""

    def test_autopilot_returns_stub(self):
        result = read_pipeline_state(mode="autopilot")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("WS5", result["reason"])

    def test_ralph_returns_stub(self):
        result = read_pipeline_state(mode="ralph")
        self.assertEqual(result["status"], "unknown")

    def test_ultrawork_returns_stub(self):
        result = read_pipeline_state(mode="ultrawork")
        self.assertEqual(result["status"], "unknown")

    def test_team_returns_stub(self):
        result = read_pipeline_state(mode="team")
        self.assertEqual(result["status"], "unknown")

    def test_arbitrary_unknown_mode_returns_stub(self):
        result = read_pipeline_state(mode="totally-unknown-mode")
        self.assertEqual(result["status"], "unknown")

    def test_stub_is_copy_not_reference(self):
        # Modifying the returned dict must not affect the module-level constant
        result = read_pipeline_state(mode="autopilot")
        result["status"] = "mutated"
        fresh = read_pipeline_state(mode="autopilot")
        self.assertEqual(fresh["status"], "unknown")

    def test_all_ws5_modes_return_stub(self):
        for mode in _PIPELINE_MODES_WS5:
            result = read_pipeline_state(mode=mode)
            self.assertEqual(
                result["status"], "unknown",
                msg=f"mode={mode!r} should return stub"
            )


class TestRouterModeRead(unittest.TestCase):
    """mode='router' attempts MCP read; returns None when MCP unavailable."""

    def test_router_mode_returns_none_or_dict_when_mcp_unavailable(self):
        # In CI / unit tests the MCP server is not running; the function
        # should return None (not raise) when MCP is unavailable.
        result = read_pipeline_state(mode="router")
        # Either None (MCP down) or a dict (MCP running with prior state)
        self.assertTrue(result is None or isinstance(result, dict))

    def test_router_mode_with_session_id_returns_none_or_dict(self):
        result = read_pipeline_state(session_id="test-session-123", mode="router")
        self.assertTrue(result is None or isinstance(result, dict))

    def test_router_mode_does_not_raise(self):
        # Must never propagate exceptions to caller
        try:
            read_pipeline_state(mode="router")
        except Exception as exc:
            self.fail(f"read_pipeline_state raised unexpectedly: {exc}")

    def test_router_mode_default_arg(self):
        # Default mode is "router"
        result = read_pipeline_state()
        self.assertTrue(result is None or isinstance(result, dict))


class TestCLI(unittest.TestCase):
    """CLI smoke test."""

    def test_cli_autopilot_stub(self):
        import json
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, str(_STATE_PATH), "--read", "--mode", "autopilot"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "unknown")

    def test_cli_router_mode_no_crash(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, str(_STATE_PATH), "--read", "--mode", "router"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
