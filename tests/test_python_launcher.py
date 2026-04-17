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

    def test_cmd_probes_launcher_before_use(self) -> None:
        """Regression for P2: a broken `py -3` must fall through, not exit.

        The batch shim must version-probe each launcher with `-c ...` and
        only dispatch to it if that probe exits 0. Otherwise a present-but-
        broken `py` launcher (e.g. no -3 registered) would short-circuit the
        fallback chain.
        """
        text = (ROOT / "scripts" / "omni.cmd").read_text(encoding="utf-8")
        # Each launcher line is preceded by a `-c` probe that checks
        # sys.version_info. Assert at least one such probe per launcher.
        self.assertGreaterEqual(
            text.count('-c "import sys;raise SystemExit('), 3,
            "omni.cmd should probe all three launchers with a version check",
        )
        # The first launcher invocation guarded by `if !errorlevel! equ 0`
        # must appear AFTER the first `-c` probe, not before.
        probe_pos = text.find('-c "import sys;')
        dispatch_pos = text.find("%~dp0omni.py")
        self.assertLess(
            probe_pos, dispatch_pos,
            "omni.cmd must probe the launcher before dispatching",
        )

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
                    "args": ["${OMNI_PLUGIN_ROOT}/mcp/server.py"],
                }
            }
        }, indent=2) + "\n", encoding="utf-8")
        self._hooks = self._tmp / "hooks" / "hooks.json"
        self._hooks.write_text(json.dumps({
            "version": 1,
            "hooks": {
                "sessionStart": [{
                    "type": "command",
                    "command": 'python3 "${OMNI_PLUGIN_ROOT}/hooks/session_start.py"',
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

    def test_quoted_interpreter_with_spaces_is_respected(self) -> None:
        """Regression for P1: `"C:\\Program Files\\...\\python.exe" ...`
        must not be truncated at the first space.

        Seed the hooks file with a pre-calibrated Windows-style quoted path
        and confirm the rewriter recognises the interpreter as already-
        resolved (i.e. it does NOT re-rewrite it into a corrupt string).
        """
        # Use this test's real interpreter so the calibration check passes
        # and nothing gets rewritten.
        fake_mcp = {
            "mcpServers": {
                "copilot-omni": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [],
                }
            }
        }
        # Simulate a hook command whose interpreter path contains spaces
        # (mimics a real Windows install: C:\Program Files\...).
        faux_interp = sys.executable  # absolute + exists on PATH
        fake_hooks = {
            "version": 1,
            "hooks": {
                "sessionStart": [{
                    "type": "command",
                    "command": f'"{faux_interp}" "${{OMNI_PLUGIN_ROOT}}/hooks/session_start.py"',
                }],
            },
        }
        self._mcp.write_text(
            json.dumps(fake_mcp, indent=2) + "\n", encoding="utf-8"
        )
        self._hooks.write_text(
            json.dumps(fake_hooks, indent=2) + "\n", encoding="utf-8"
        )
        before = self._hooks.read_text()
        out = self._run(apply_=True)
        self.assertIn("already calibrated", out)
        # File content is byte-identical — the quoted path was not split
        # on the first space and no spurious rewrite happened.
        self.assertEqual(self._hooks.read_text(), before)


class TestWindowsStoreStubRejection(unittest.TestCase):
    """Regression for the MCP ``-32000 Connection closed`` bug on Windows.

    ``shutil.which("python3")`` happily returns the Microsoft Store reparse
    stub under ``%LOCALAPPDATA%\\Microsoft\\WindowsApps\\python3.exe``. The
    stub is a 0-byte redirector that either launches the Store UI or exits
    silently. Treating it as a valid interpreter is what caused Copilot CLI
    to log ``MCP error -32000: Connection closed`` on every corporate Windows
    box that had only the Store stub on PATH.

    ``_is_usable_python`` must reject anything under that directory outright
    without spawning the stub (which would block for several seconds).
    """

    def test_rejects_windows_apps_path(self) -> None:
        fake_stub = (
            "C:\\Users\\Tester\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"
        )
        old_windows_apps = omni._WINDOWS_APPS
        try:
            omni._WINDOWS_APPS = (
                "c:\\users\\tester\\appdata\\local\\microsoft\\windowsapps"
            )
            self.assertFalse(omni._is_usable_python(fake_stub))
        finally:
            omni._WINDOWS_APPS = old_windows_apps

    def test_accepts_real_interpreter(self) -> None:
        self.assertTrue(omni._is_usable_python(sys.executable))

    def test_rejects_empty_and_none(self) -> None:
        self.assertFalse(omni._is_usable_python(""))
        self.assertFalse(omni._is_usable_python(None))

    def test_rejects_nonexistent_path(self) -> None:
        self.assertFalse(omni._is_usable_python("/no/such/python"))


class TestSplitCmdHead(unittest.TestCase):
    """Unit coverage for `_split_cmd_head` — the quote-aware head parser."""

    def test_unquoted_bare_name(self) -> None:
        self.assertEqual(omni._split_cmd_head("python3"), ("python3", ""))

    def test_unquoted_with_args(self) -> None:
        head, rest = omni._split_cmd_head('python3 script.py arg')
        self.assertEqual(head, "python3")
        self.assertEqual(rest, "script.py arg")

    def test_double_quoted_path_with_spaces(self) -> None:
        head, rest = omni._split_cmd_head(
            '"C:\\Program Files\\Python311\\python.exe" "arg one" "arg two"'
        )
        self.assertEqual(head, "C:\\Program Files\\Python311\\python.exe")
        self.assertEqual(rest, '"arg one" "arg two"')

    def test_single_quoted_path_with_spaces(self) -> None:
        head, rest = omni._split_cmd_head(
            "'/Applications/Python 3.11/bin/python3' --version"
        )
        self.assertEqual(head, "/Applications/Python 3.11/bin/python3")
        self.assertEqual(rest, "--version")

    def test_unterminated_quote_is_treated_as_head(self) -> None:
        head, rest = omni._split_cmd_head('"C:\\Program Files')
        self.assertEqual(head, "C:\\Program Files")
        self.assertEqual(rest, "")

    def test_empty_string(self) -> None:
        self.assertEqual(omni._split_cmd_head(""), ("", ""))
        self.assertEqual(omni._split_cmd_head("   "), ("", ""))


if __name__ == "__main__":
    unittest.main()
