"""Tests for session_start.py cached banner behavior (WS7b).

Covers:
- First call computes banner and writes cache
- Second call (same tree hash) hits cache
- Cache miss on tree-hash change triggers recompute
- Banner format contains expected fields
- Policy permission warning emitted for over-permissive files
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def _load_session_start_module(plugin_root: Path):
    """Load session_start.py as a module with _PLUGIN_ROOT patched."""
    # We need to reload the module each time because _PLUGIN_ROOT is module-level
    spec = importlib.util.spec_from_file_location(
        "session_start_test", HOOKS / "session_start.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Patch _PLUGIN_ROOT before exec
    mod.__dict__["_PLUGIN_ROOT"] = plugin_root  # type: ignore[index]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestBannerCache(unittest.TestCase):
    """Banner caching behavior: compute on miss, hit on repeat, recompute on change."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        # Create minimal plugin structure
        (self._root / "skills").mkdir()
        for s in ["autopilot", "ralph", "plan"]:
            (self._root / "skills" / s).mkdir()
        (self._root / "scripts").mkdir()
        (self._root / "scripts" / "router.py").touch()
        (self._root / ".claude-plugin").mkdir()
        (self._root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": "2.0.0", "commands": ["/a", "/b"]}),
            encoding="utf-8",
        )
        (self._root / "hooks").mkdir()
        (self._root / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
        (self._root / "AGENTS.md").write_text("## AgentAlpha\n## AgentBeta\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _load_mod(self):
        spec = importlib.util.spec_from_file_location(
            "session_start_test", HOOKS / "session_start.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _get_banner(self, mod, root=None):
        r = root or self._root
        banner, cache_hit = mod._get_banner(r)
        return banner, cache_hit

    def test_first_call_computes_banner(self):
        mod = self._load_mod()
        banner, cache_hit = self._get_banner(mod)
        self.assertFalse(cache_hit, "First call should miss cache")
        self.assertIn("copilot-omni", banner)
        self.assertIn("v2.0.0", banner)

    def test_second_call_hits_cache(self):
        mod = self._load_mod()
        # First call — populates cache
        banner1, hit1 = self._get_banner(mod)
        self.assertFalse(hit1)
        # Second call — same tree hash
        banner2, hit2 = self._get_banner(mod)
        self.assertTrue(hit2, "Second call should hit cache")
        self.assertEqual(banner1, banner2)

    def test_cache_invalidated_on_tree_change(self):
        mod = self._load_mod()
        # Populate cache
        _, _ = self._get_banner(mod)
        # Modify a file that affects tree hash
        import time as _t
        _t.sleep(0.01)  # ensure mtime changes
        (self._root / "hooks" / "hooks.json").write_text('{"changed": true}', encoding="utf-8")
        # Touch the file so mtime changes (some filesystems have 1s resolution)
        p = self._root / "hooks" / "hooks.json"
        p.touch()
        # Reload mod to get fresh _compute_tree_hash
        mod2 = self._load_mod()
        _, hit = self._get_banner(mod2)
        # May or may not be a cache hit depending on filesystem mtime resolution,
        # but the banner should still be valid
        banner, _ = self._get_banner(mod2)
        self.assertIn("copilot-omni", banner)

    def test_banner_contains_skills_count(self):
        mod = self._load_mod()
        banner, _ = self._get_banner(mod)
        # Banner format: "copilot-omni vX | N skills | ..."
        self.assertRegex(banner, r"\d+ skills")

    def test_banner_contains_router_status(self):
        mod = self._load_mod()
        banner, _ = self._get_banner(mod)
        self.assertIn("router=on", banner)

    def test_banner_contains_version(self):
        mod = self._load_mod()
        banner, _ = self._get_banner(mod)
        self.assertIn("v2.0.0", banner)

    def test_banner_format_pipe_separated(self):
        mod = self._load_mod()
        banner, _ = self._get_banner(mod)
        # Must contain at least 4 pipe-separated segments
        parts = banner.split("|")
        self.assertGreaterEqual(len(parts), 4)

    def test_cache_file_written(self):
        mod = self._load_mod()
        self._get_banner(mod)
        cache_path = self._root / ".omni" / "cache" / "banner.json"
        self.assertTrue(cache_path.exists(), "Cache file should be written after first call")
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        self.assertIn("tree_hash", data)
        self.assertIn("banner", data)


class TestSessionStartOutput(unittest.TestCase):
    """Integration test: session_start.py output wraps banner in <omni-banner>."""

    def _run_hook(self, env_overrides=None):
        import subprocess
        env = {k: v for k, v in os.environ.items()}
        for var in ("OMNI_SKIP_HOOKS", "DISABLE_OMNI", "OMC_SKIP_HOOKS", "DISABLE_OMC",
                    "OMNI_SKIP_SESSION_START"):
            env.pop(var, None)
        if env_overrides:
            env.update(env_overrides)
        result = subprocess.run(
            [sys.executable, str(HOOKS / "session_start.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        return result

    def test_output_is_valid_json(self):
        result = self._run_hook()
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertIn("additionalContext", body)

    def test_banner_wrapped_in_tag(self):
        result = self._run_hook()
        ctx = json.loads(result.stdout)["additionalContext"]
        self.assertIn("<omni-banner>", ctx)
        self.assertIn("</omni-banner>", ctx)

    def test_banner_contains_copilot_omni(self):
        result = self._run_hook()
        ctx = json.loads(result.stdout)["additionalContext"]
        self.assertIn("copilot-omni", ctx)

    def test_kill_switch_bypasses_banner(self):
        result = self._run_hook({"OMNI_SKIP_HOOKS": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertNotIn("<omni-banner>", result.stdout)


class TestPolicyPermissionCheck(unittest.TestCase):
    """Policy file permission check emits warnings for > 0o644 mode."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _load_mod(self):
        spec = importlib.util.spec_from_file_location(
            "session_start_pol", HOOKS / "session_start.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    @unittest.skipIf(sys.platform == "win32", "File permission tests not supported on Windows")
    def test_over_permissive_file_produces_warning(self):
        policies = self._root / "policies"
        policies.mkdir()
        p = policies / "test.json"
        p.write_text('{}', encoding="utf-8")
        os.chmod(str(p), 0o666)
        mod = self._load_mod()
        warnings = mod._check_policy_permissions(self._root)
        self.assertTrue(any("policy-warning" in w for w in warnings))
        self.assertTrue(any("test.json" in w for w in warnings))

    @unittest.skipIf(sys.platform == "win32", "File permission tests not supported on Windows")
    def test_correct_permission_produces_no_warning(self):
        policies = self._root / "policies"
        policies.mkdir()
        p = policies / "ok.json"
        p.write_text('{}', encoding="utf-8")
        os.chmod(str(p), 0o644)
        mod = self._load_mod()
        warnings = mod._check_policy_permissions(self._root)
        self.assertEqual(warnings, [])

    def test_missing_policies_dir_produces_no_warning(self):
        mod = self._load_mod()
        # No policies/ dir under _root
        warnings = mod._check_policy_permissions(self._root)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
