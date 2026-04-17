"""Phase-C C27: skill-trigger priority / disambiguation on multi-match."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "user_prompt_submit.py"


def _write_skill(root: Path, name: str, triggers: list[str], priority: int | None = None):
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}"]
    lines.append(f'triggers: {json.dumps(triggers)}')
    if priority is not None:
        lines.append(f"priority: {priority}")
    lines.extend(["---", "", f"# {name}", ""])
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


class TestTriggerPriority(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plug_root = Path(self.tmp.name)
        (self.plug_root / "skills").mkdir()
        # Hook also needs a scripts/router.py — reuse the real one via sys.path
        # by setting OMNI_PLUGIN_ROOT to the real plugin root for the router,
        # but _build_trigger_map walks OMNI_PLUGIN_ROOT/skills, so we need it
        # pointed at our sandbox. To bridge: copy scripts/ into our sandbox
        # so the hook finds a working router there.
        scripts_src = ROOT / "scripts"
        scripts_dst = self.plug_root / "scripts"
        scripts_dst.mkdir()
        import shutil
        shutil.copy(scripts_src / "router.py", scripts_dst / "router.py")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, prompt: str) -> str:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.plug_root),
            "OMNI_HOME": str(self.plug_root / ".omni"),
            "OMNI_PLUGIN_ROOT": str(self.plug_root),
        }
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True, text=True, timeout=15,
            env=env, cwd=str(self.plug_root),
        )
        self.assertEqual(result.returncode, 0,
                         f"hook failed: stderr={result.stderr!r}")
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        return out.get("additionalContext", "")

    def test_single_match_no_primary_attr(self):
        _write_skill(self.plug_root, "only", ["alpha"])
        ctx = self._run("the alpha keyword fires")
        self.assertIn('skill="only"', ctx)
        self.assertNotIn('primary="true"', ctx)

    def test_multi_match_lowest_priority_becomes_primary(self):
        _write_skill(self.plug_root, "high", ["foo"], priority=10)
        _write_skill(self.plug_root, "low", ["foo"], priority=50)
        ctx = self._run("foo is a foo")
        # Priority 10 is lower → 'high' must be marked primary.
        primary_line = [l for l in ctx.splitlines() if 'primary="true"' in l]
        self.assertEqual(len(primary_line), 1, f"ctx={ctx!r}")
        self.assertIn('skill="high"', primary_line[0])

    def test_default_priority_is_100(self):
        _write_skill(self.plug_root, "explicit", ["bar"], priority=5)
        _write_skill(self.plug_root, "default", ["bar"])  # no priority → 100
        ctx = self._run("bar appears here")
        primary_line = [l for l in ctx.splitlines() if 'primary="true"' in l]
        self.assertEqual(len(primary_line), 1)
        self.assertIn('skill="explicit"', primary_line[0])

    def test_priority_attribute_always_emitted(self):
        _write_skill(self.plug_root, "solo", ["baz"], priority=7)
        ctx = self._run("baz fires")
        self.assertIn('priority="7"', ctx)


if __name__ == "__main__":
    unittest.main()
