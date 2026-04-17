"""Phase-C C25: router-decision transport enforcement.

When .omni/cache/router-last.json records a 'redirect' decision and
OMNI_ROUTER_ENFORCE=1 is set, pre_tool_use.py must deny non-exempt tool
calls with a router-attributed reason.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def _run_pre(payload, env):
    result = subprocess.run(
        [sys.executable, str(HOOKS / "pre_tool_use.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=10, env=env,
    )
    return result.stdout, result.returncode


def _run_submit(payload, env):
    result = subprocess.run(
        [sys.executable, str(HOOKS / "user_prompt_submit.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=10, env=env,
    )
    return result.stdout, result.returncode


class TestRouterEnforcementGate(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".omni" / "cache").mkdir(parents=True)
        self.sentinel = self.cwd / ".omni" / "cache" / "router-last.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _env(self, **extra):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.cwd),          # isolate audit/metrics writes
            "OMNI_HOME": str(self.cwd / ".omni"),
        }
        env.update(extra)
        return env

    def _write_sentinel(self, decision: str):
        self.sentinel.write_text(json.dumps({
            "decision": decision,
            "redirect_to": "deep-interview" if decision == "redirect" else None,
            "score": 0.1,
            "ts": "2026-04-17T00:00:00Z",
            "prompt_excerpt": "build me something",
        }))

    def test_redirect_blocks_non_exempt_tool_when_enforcing(self):
        self._write_sentinel("redirect")
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        env["__cwd__"] = str(self.cwd)
        # pre_tool_use.py reads getcwd(); we set cwd via subprocess.
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("router", body["permissionDecisionReason"].lower())

    def test_redirect_without_enforce_flag_allows(self):
        self._write_sentinel("redirect")
        env = self._env()  # no OMNI_ROUTER_ENFORCE
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_exempt_tool_allowed_even_when_redirected(self):
        self._write_sentinel("redirect")
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "state_read",
                              "tool_args": {}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_proceed_decision_allows(self):
        self._write_sentinel("proceed")
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_missing_sentinel_allows(self):
        # No sentinel file at all — enforcement must not block.
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_stale_sentinel_past_ttl_allows(self):
        """Phase-C C34 Codex: stale sentinels must not brick unrelated work."""
        self._write_sentinel("redirect")
        # Backdate mtime to 2 hours ago; TTL defaults to 300s.
        past = time.time() - 2 * 3600
        os.utime(self.sentinel, (past, past))
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow",
                         "stale sentinel (past TTL) must not deny")

    def test_oversized_sentinel_is_ignored(self):
        """A multi-MB crafted sentinel must not OOM the hook nor enforce."""
        self.sentinel.write_bytes(b'{"decision":"redirect",' + b' ' * 20000 + b'}')
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        # Oversized payload is truncated → JSON parse fails → sentinel ignored.
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_non_dict_sentinel_is_ignored(self):
        """A JSON array (not an object) must not enforce."""
        self.sentinel.write_text('["not", "an", "object"]')
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({"tool_name": "write",
                              "tool_args": {"file_path": "README.md"}}),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow")

    def test_per_session_scope_mismatch_does_not_block(self):
        """Codex P1: a sentinel tagged with session A must NOT block a
        pre_tool_use call carrying session B."""
        self.sentinel.write_text(json.dumps({
            "decision": "redirect",
            "redirect_to": "deep-interview",
            "score": 0.1,
            "ts": "2026-04-17T00:00:00Z",
            "prompt_excerpt": "build me something",
            "session_id": "session-alpha",
        }))
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({
                "tool_name": "write",
                "tool_args": {"file_path": "README.md"},
                "session_id": "session-beta",
            }),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "allow",
                         "cross-session sentinel must not deny")

    def test_per_session_scope_match_still_blocks(self):
        """Session A sentinel + session A caller still denies."""
        self.sentinel.write_text(json.dumps({
            "decision": "redirect",
            "redirect_to": "deep-interview",
            "score": 0.1,
            "ts": "2026-04-17T00:00:00Z",
            "prompt_excerpt": "build me something",
            "session_id": "session-alpha",
        }))
        env = self._env(OMNI_ROUTER_ENFORCE="1")
        result = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool_use.py")],
            input=json.dumps({
                "tool_name": "write",
                "tool_args": {"file_path": "README.md"},
                "session_id": "session-alpha",
            }),
            capture_output=True, text=True, timeout=10,
            env=env, cwd=str(self.cwd),
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["permissionDecision"], "deny")


class TestUserPromptSubmitWritesSentinel(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_submit_writes_router_last_json(self):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.cwd),
            "OMNI_HOME": str(self.cwd / ".omni"),
            "OMNI_PLUGIN_ROOT": str(ROOT),  # so skill triggers map loads
        }
        result = subprocess.run(
            [sys.executable, str(HOOKS / "user_prompt_submit.py")],
            input=json.dumps({"prompt": "build me something"}),
            capture_output=True, text=True, timeout=20,
            env=env, cwd=str(self.cwd),
        )
        self.assertEqual(result.returncode, 0)
        sentinel = self.cwd / ".omni" / "cache" / "router-last.json"
        self.assertTrue(sentinel.exists(),
                        f"sentinel missing: stderr={result.stderr!r}")
        data = json.loads(sentinel.read_text())
        self.assertIn("decision", data)


if __name__ == "__main__":
    unittest.main()
