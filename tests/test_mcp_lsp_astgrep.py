"""Phase-C C18: LSP + ast-grep MCP tool smokes."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


def _load():
    spec = importlib.util.spec_from_file_location("mcp_lsp", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(tool, args, env_home):
    env = {**os.environ, "OMNI_HOME": env_home}
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env,
    )
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    })
    out, _ = proc.communicate(payload + "\n", timeout=15)
    resp = json.loads(out.strip().splitlines()[0])
    body = resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    return json.loads(body)


class TestTrustBinariesAbsent(unittest.TestCase):
    """On a GitHub Linux runner neither pylsp nor ast-grep is installed.
    The handlers must return status='skipped' rather than crashing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_lsp_hover_skipped_when_binary_missing(self):
        body = _call("lsp_hover", {"path": "foo.py", "line": 1,
                                   "character": 0,
                                   "ls_binary": "nonexistent-lsp-xyz"},
                     self.home)
        self.assertEqual(body["status"], "skipped")
        self.assertIn("nonexistent-lsp-xyz", body["reason"])

    def test_lsp_goto_definition_skipped(self):
        body = _call("lsp_goto_definition",
                     {"path": "foo.py",
                      "ls_binary": "nonexistent-lsp-xyz"},
                     self.home)
        self.assertEqual(body["status"], "skipped")

    def test_lsp_find_references_skipped(self):
        body = _call("lsp_find_references",
                     {"path": "foo.py",
                      "ls_binary": "nonexistent-lsp-xyz"},
                     self.home)
        self.assertEqual(body["status"], "skipped")

    def test_ast_grep_search_skipped_without_binary(self):
        # We can't easily force the binary to be absent when running the
        # real server process (it would need an env-path override), so
        # instead we unit-test the underlying handler directly.
        mod = _load()
        with mock.patch.object(mod, "_which", return_value=None):
            body = json.loads(
                mod._tool_ast_grep_search({"pattern": "foo()"})
                ["content"][0]["text"]
            )
        self.assertEqual(body["status"], "skipped")

    def test_ast_grep_replace_skipped_without_binary(self):
        mod = _load()
        with mock.patch.object(mod, "_which", return_value=None):
            body = json.loads(
                mod._tool_ast_grep_replace({
                    "pattern": "foo()", "replacement": "bar()"
                })["content"][0]["text"]
            )
        self.assertEqual(body["status"], "skipped")

    def test_ast_grep_search_requires_pattern(self):
        """Empty pattern must be rejected by schema validation (required)."""
        env = {**os.environ, "OMNI_HOME": self.home}
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "ast_grep_search", "arguments": {}},
        })
        out, _ = proc.communicate(payload + "\n", timeout=15)
        resp = json.loads(out.strip().splitlines()[0])
        self.assertIn("error", resp,
                      f"expected schema rejection; resp={resp!r}")


class TestRegistryPresent(unittest.TestCase):

    def test_all_five_tools_registered(self):
        mod = _load()
        for name in ("lsp_hover", "lsp_goto_definition", "lsp_find_references",
                     "ast_grep_search", "ast_grep_replace"):
            self.assertIn(name, mod.TOOLS,
                          f"{name} must be registered in TOOLS")


class TestFlagInjectionGuard(unittest.TestCase):
    """Phase-C C34 Codex + security review finding: user-supplied positional
    args that start with '-' are interpreted as flags by ast-grep. Guard
    with both a value check and a '--' separator in the argv."""

    def test_guard_rejects_leading_dash_value(self):
        mod = _load()
        with self.assertRaises(ValueError) as ctx:
            mod._assert_no_flag_injection("--config=/tmp/evil")
        self.assertIn("-", str(ctx.exception))

    def test_guard_accepts_regular_values(self):
        mod = _load()
        # Should not raise.
        mod._assert_no_flag_injection("foo()", "src/", "python")

    def test_ast_grep_search_rejects_flag_path(self):
        mod = _load()
        with self.assertRaises(ValueError):
            mod._tool_ast_grep_search({
                "pattern": "print($X)", "path": "--config=/tmp/evil.yml",
            })

    def test_ast_grep_replace_rejects_flag_replacement(self):
        mod = _load()
        with self.assertRaises(ValueError):
            mod._tool_ast_grep_replace({
                "pattern": "print($X)", "replacement": "--update-all",
                "path": "src/",
            })


if __name__ == "__main__":
    unittest.main()
