"""Coverage for the cross-OS Python-launcher dispatch.

Two surfaces under test:

1. `scripts/omni.cmd` + `scripts/omni` must probe PATH in the correct order
   and fail loudly when no Python is found. These are shell/batch scripts, so
   we assert their *source* contains the required probes and the failure
   branch — running them in-process is neither cross-OS portable nor useful
   in a Linux CI lane.

2. `scripts/omni.py doctor --fix-python(-apply)` — the in-place config
   rewriter. We test it end-to-end against scratch copies of `.mcp.json`
   and `hooks/hooks.json` to confirm:
   - dry-run is a no-op on disk
   - apply rewrites bare `python3` / `python` to the running interpreter
     *only when* the configured command does not resolve on PATH
   - running it again is idempotent (already-calibrated → no change)
   - malformed JSON is reported, not silently corrupted
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_omni():
    path = ROOT / "scripts" / "omni.py"
    spec = importlib.util.spec_from_file_location("omni_module_under_test", path)
    assert spec is not None and spec.loader is not None, "cannot load scripts/omni.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


omni = _load_omni()


class TestShimSource(unittest.TestCase):
    """Source-level assertions on the omni launchers."""

    def test_cmd_probes_in_order(self) -> None:
        text = (ROOT / "scripts" / "omni.cmd").read_text(encoding="utf-8")
        # All three launcher names appear and in priority order.
        for token in ("py ", "python ", "python3 "):
            self.assertIn(token, text, f"omni.cmd missing launcher probe: {token!r}")
        self.assertLess(text.find("py "), text.find("python "),
                        "omni.cmd should prefer `py -3` over `python`")
        self.assertLess(text.find("python "), text.find("python3 "),
                        "omni.cmd should fall through to `python3` last")
        self.assertIn("exit /b 127", text,
                      "omni.cmd should exit non-zero when no Python is found")

    def test_bash_shim_probes_in_order(self) -> None:
        text = (ROOT / "scripts" / "omni").read_text(encoding="utf-8")
        self.assertIn("python3", text)
        self.assertIn("python", text)
        self.assertIn("command -v python3", text,
                      "bash shim should probe python3 via `command -v`")
        self.assertIn("exit 127", text,
                      "bash shim should exit 127 when no Python found")


class TestFixPythonRewrite(unittest.TestCase):
    """End-to-end tests for `doctor --fix-python(-apply)`."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="omni-fixpy-"))
        (self._tmp / "hooks").mkdir()

        # Mini mirrors of the real configs.
        self._mcp = self._tmp / ".mcp.json"
        self._mcp.write_text(json.dumps({
            "mcpServers": {
                "copilot-omni": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/server.py"],
                }
            }
        }, indent=2) + "\n", encoding="utf-8")
        self._hooks = self._tmp / "hooks" / "hooks.json"
        self._hooks.write_text(json.dumps({
            "version": 1,
            "hooks": {
                "sessionStart": [{
                    "type": "command",
                    "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"',
                }],
                "preToolUse": [{
                    "type": "command",
                    "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py"',
                }],
            }
        }, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self, *, path_overrides: dict[str, str] | None = None,
             apply_: bool = False) -> str:
        """Drive `_doctor_fix_python` against the scratch directory."""
        # Force `which` to miss `python3` so the rewriter kicks in.
        env_path = ""
        if path_overrides is not None:
            env_path = path_overrides.get("PATH", "")
        old_path = os.environ.get("PATH", "")
        try:
            if path_overrides is not None:
                os.environ["PATH"] = env_path
            buf = io.StringIO()
            with redirect_stdout(buf):
                omni._doctor_fix_python(self._tmp, apply_=apply_)
            return buf.getvalue()
        finally:
            os.environ["PATH"] = old_path

    def test_dry_run_does_not_touch_files(self) -> None:
        # Strip python3 from PATH so the rewriter detects a mismatch.
        empty = str(self._tmp / "_empty_path")
        os.makedirs(empty, exist_ok=True)
        mcp_before = self._mcp.read_text()
        hooks_before = self._hooks.read_text()
        out = self._run(path_overrides={"PATH": empty}, apply_=False)
        self.assertIn("DRY-RUN", out)
        self.assertEqual(self._mcp.read_text(), mcp_before)
        self.assertEqual(self._hooks.read_text(), hooks_before)

    def test_apply_rewrites_to_sys_executable(self) -> None:
        empty = str(self._tmp / "_empty_path")
        os.makedirs(empty, exist_ok=True)
        out = self._run(path_overrides={"PATH": empty}, apply_=True)
        self.assertIn("APPLY", out)
        self.assertIn("WRITTEN", out)
        mcp = json.loads(self._mcp.read_text())
        self.assertEqual(
            mcp["mcpServers"]["copilot-omni"]["command"],
            sys.executable,
            "MCP command should be the absolute interpreter path",
        )
        hooks = json.loads(self._hooks.read_text())
        for event, entries in hooks["hooks"].items():
            for entry in entries:
                self.assertTrue(
                    entry["command"].startswith(f'"{sys.executable}"'),
                    f"hook {event} should start with the interpreter path: "
                    f"got {entry['command']!r}",
                )

    def test_apply_is_idempotent(self) -> None:
        empty = str(self._tmp / "_empty_path")
        os.makedirs(empty, exist_ok=True)
        self._run(path_overrides={"PATH": empty}, apply_=True)
        # Second run should find nothing to change — the command is now
        # an absolute path that exists.
        out = self._run(path_overrides={"PATH": empty}, apply_=True)
        self.assertIn("already calibrated", out)

    def test_skip_when_command_already_on_path(self) -> None:
        # With an unrestricted PATH, `python3` resolves and nothing should
        # be rewritten.
        mcp_before = self._mcp.read_text()
        hooks_before = self._hooks.read_text()
        out = self._run(apply_=True)
        self.assertIn("already calibrated", out)
        self.assertEqual(self._mcp.read_text(), mcp_before)
        self.assertEqual(self._hooks.read_text(), hooks_before)

    def test_malformed_json_is_reported_not_corrupted(self) -> None:
        self._mcp.write_text("{not json", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = omni._doctor_fix_python(self._tmp, apply_=True)
        out = buf.getvalue()
        self.assertFalse(ok)
        self.assertIn("FAIL to read/parse", out)
        # Content preserved verbatim.
        self.assertEqual(self._mcp.read_text(), "{not json")


if __name__ == "__main__":
    unittest.main()
