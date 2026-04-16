"""Kill-switch coverage for all four lifecycle hooks.

Tests all five kill-switch env var combinations across all four hooks (20 cases):
  1. OMNI_SKIP_HOOKS=1         (canonical)
  2. DISABLE_OMNI=1            (canonical alternate)
  3. OMC_SKIP_HOOKS=1          (legacy alias — deprecated)
  4. DISABLE_OMC=1             (legacy alias — deprecated)
  5. OMNI_SKIP_<HOOK_UPPER>=1  (per-hook kill switch)

Expected behaviour for any active kill-switch:
  - Hook exits with code 0
  - stdout is "{}" (empty JSON object)
  - Legacy vars (OMC_SKIP_HOOKS, DISABLE_OMC) additionally emit a deprecation
    warning to stderr (de-dup'd by sentinel file, so we skip the sentinel before
    each legacy test).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
SENTINEL = ROOT / ".omni" / "cache" / "omc-deprecation-warned"  # omni-rename-allow: legacy sentinel name

HOOK_FILES = [
    "pre_tool_use.py",
    "post_tool_use.py",
    "session_start.py",
    "user_prompt_submit.py",
]

# Per-hook env var names (OMNI_SKIP_<HOOK_UPPER>)
_PER_HOOK_VARS = {
    "pre_tool_use.py": "OMNI_SKIP_PRE_TOOL_USE",
    "post_tool_use.py": "OMNI_SKIP_POST_TOOL_USE",
    "session_start.py": "OMNI_SKIP_SESSION_START",
    "user_prompt_submit.py": "OMNI_SKIP_USER_PROMPT_SUBMIT",
}

# Minimal valid payloads for each hook so they don't crash on malformed input
_PAYLOADS = {
    "pre_tool_use.py": {"tool_name": "shell", "tool_args": {"command": "ls"}},
    "post_tool_use.py": {"tool_name": "shell", "status": "completed"},
    "session_start.py": {},
    "user_prompt_submit.py": {"prompt": "fix the bug"},
}


def _run(hook: str, env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()}
    # Remove all kill-switch vars first so tests don't inherit from parent env
    for var in ("OMNI_SKIP_HOOKS", "DISABLE_OMNI", "OMC_SKIP_HOOKS", "DISABLE_OMC",
                "OMNI_SKIP_PRE_TOOL_USE", "OMNI_SKIP_POST_TOOL_USE",
                "OMNI_SKIP_SESSION_START", "OMNI_SKIP_USER_PROMPT_SUBMIT"):
        env.pop(var, None)
    env.update(env_overrides)
    payload = _PAYLOADS[hook]
    return subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def _remove_sentinel():
    """Remove de-dup sentinel so deprecation warnings can be tested."""
    try:
        SENTINEL.unlink()
    except FileNotFoundError:
        pass


class TestKillSwitchOmniSkipHooks(unittest.TestCase):
    """OMNI_SKIP_HOOKS=1 — all four hooks must exit 0 with empty JSON."""

    def _assert_bypassed(self, hook: str):
        result = _run(hook, {"OMNI_SKIP_HOOKS": "1"})
        self.assertEqual(result.returncode, 0, f"{hook}: non-zero exit")
        self.assertEqual(json.loads(result.stdout), {}, f"{hook}: stdout not empty JSON")

    def test_pre_tool_use(self):
        self._assert_bypassed("pre_tool_use.py")

    def test_post_tool_use(self):
        self._assert_bypassed("post_tool_use.py")

    def test_session_start(self):
        self._assert_bypassed("session_start.py")

    def test_user_prompt_submit(self):
        self._assert_bypassed("user_prompt_submit.py")


class TestKillSwitchDisableOmni(unittest.TestCase):
    """DISABLE_OMNI=1 — all four hooks must exit 0 with empty JSON."""

    def _assert_bypassed(self, hook: str):
        result = _run(hook, {"DISABLE_OMNI": "1"})
        self.assertEqual(result.returncode, 0, f"{hook}: non-zero exit")
        self.assertEqual(json.loads(result.stdout), {}, f"{hook}: stdout not empty JSON")

    def test_pre_tool_use(self):
        self._assert_bypassed("pre_tool_use.py")

    def test_post_tool_use(self):
        self._assert_bypassed("post_tool_use.py")

    def test_session_start(self):
        self._assert_bypassed("session_start.py")

    def test_user_prompt_submit(self):
        self._assert_bypassed("user_prompt_submit.py")


class TestKillSwitchOmcSkipHooksLegacy(unittest.TestCase):
    """OMC_SKIP_HOOKS=1 — legacy alias: bypass + deprecation warning on stderr."""

    def setUp(self):
        _remove_sentinel()

    def _assert_bypassed_with_warn(self, hook: str):
        result = _run(hook, {"OMC_SKIP_HOOKS": "1"})
        self.assertEqual(result.returncode, 0, f"{hook}: non-zero exit")
        self.assertEqual(json.loads(result.stdout), {}, f"{hook}: stdout not empty JSON")
        self.assertIn("deprecated", result.stderr.lower(), f"{hook}: no deprecation warning on stderr")

    def test_pre_tool_use(self):
        self._assert_bypassed_with_warn("pre_tool_use.py")

    def test_post_tool_use(self):
        # Sentinel may already be written from pre_tool_use; remove it first
        _remove_sentinel()
        self._assert_bypassed_with_warn("post_tool_use.py")

    def test_session_start(self):
        _remove_sentinel()
        self._assert_bypassed_with_warn("session_start.py")

    def test_user_prompt_submit(self):
        _remove_sentinel()
        self._assert_bypassed_with_warn("user_prompt_submit.py")


class TestKillSwitchDisableOmcLegacy(unittest.TestCase):
    """DISABLE_OMC=1 — legacy alias: bypass + deprecation warning on stderr."""

    def setUp(self):
        _remove_sentinel()

    def _assert_bypassed_with_warn(self, hook: str):
        result = _run(hook, {"DISABLE_OMC": "1"})
        self.assertEqual(result.returncode, 0, f"{hook}: non-zero exit")
        self.assertEqual(json.loads(result.stdout), {}, f"{hook}: stdout not empty JSON")
        self.assertIn("deprecated", result.stderr.lower(), f"{hook}: no deprecation warning on stderr")

    def test_pre_tool_use(self):
        self._assert_bypassed_with_warn("pre_tool_use.py")

    def test_post_tool_use(self):
        _remove_sentinel()
        self._assert_bypassed_with_warn("post_tool_use.py")

    def test_session_start(self):
        _remove_sentinel()
        self._assert_bypassed_with_warn("session_start.py")

    def test_user_prompt_submit(self):
        _remove_sentinel()
        self._assert_bypassed_with_warn("user_prompt_submit.py")


class TestKillSwitchPerHook(unittest.TestCase):
    """OMNI_SKIP_<HOOK>=1 — per-hook kill switch bypasses only that hook."""

    def test_pre_tool_use_per_hook(self):
        result = _run("pre_tool_use.py", {"OMNI_SKIP_PRE_TOOL_USE": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_post_tool_use_per_hook(self):
        result = _run("post_tool_use.py", {"OMNI_SKIP_POST_TOOL_USE": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_session_start_per_hook(self):
        result = _run("session_start.py", {"OMNI_SKIP_SESSION_START": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_user_prompt_submit_per_hook(self):
        result = _run("user_prompt_submit.py", {"OMNI_SKIP_USER_PROMPT_SUBMIT": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})


class TestKillSwitchNotActive(unittest.TestCase):
    """Verify hooks are NOT bypassed when kill-switch vars are absent."""

    def test_session_start_runs_normally(self):
        """Without kill-switch, session_start emits a banner."""
        result = _run("session_start.py", {})
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertIn("additionalContext", body)
        self.assertIn("<omni-banner>", body["additionalContext"])

    def test_pre_tool_use_runs_normally(self):
        """Without kill-switch, pre_tool_use returns a permissionDecision."""
        result = _run("pre_tool_use.py", {})
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertIn("permissionDecision", body)


if __name__ == "__main__":
    unittest.main()
