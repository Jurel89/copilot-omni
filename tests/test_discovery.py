"""Unit tests for plugin discovery layout and frontmatter validity."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    meta = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


class TestDiscovery(unittest.TestCase):

    def test_plugin_manifest_valid(self):
        manifest = ROOT / ".claude-plugin" / "plugin.json"
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "copilot-omni")
        self.assertEqual(data["version"], "1.0.0")
        for field in ("description", "author", "license"):
            self.assertIn(field, data)

    def test_mcp_json_valid(self):
        mcp = ROOT / ".mcp.json"
        self.assertTrue(mcp.exists())
        data = json.loads(mcp.read_text(encoding="utf-8"))
        self.assertIn("copilot-omni", data["mcpServers"])
        cmd = data["mcpServers"]["copilot-omni"]["command"]
        self.assertEqual(cmd, "python3")

    def test_hooks_json_valid(self):
        hooks = ROOT / "hooks" / "hooks.json"
        self.assertTrue(hooks.exists())
        data = json.loads(hooks.read_text(encoding="utf-8"))
        self.assertIn("hooks", data)

    def test_skills_count(self):
        skills = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 25)

    def test_agents_count(self):
        agents = list((ROOT / "agents").glob("*.md"))
        self.assertGreaterEqual(len(agents), 15)

    def test_commands_count(self):
        commands = list((ROOT / "commands").glob("*.md"))
        self.assertGreaterEqual(len(commands), 6)

    def test_all_skills_have_name_and_description(self):
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            meta = _parse_frontmatter(skill.read_text(encoding="utf-8"))
            self.assertIn("name", meta, f"{skill} missing name")
            self.assertIn("description", meta, f"{skill} missing description")

    def test_all_agents_have_name_and_description(self):
        for agent in (ROOT / "agents").glob("*.md"):
            meta = _parse_frontmatter(agent.read_text(encoding="utf-8"))
            self.assertIn("name", meta, f"{agent} missing name")
            self.assertIn("description", meta, f"{agent} missing description")

    def test_no_go_files(self):
        leftovers = []
        for pattern in ("**/*.go", "**/go.mod", "**/go.sum"):
            for p in ROOT.glob(pattern):
                if ".git" in p.parts:
                    continue
                leftovers.append(p)
        self.assertEqual(leftovers, [], f"Go leftovers: {leftovers}")

    def test_no_third_party_imports(self):
        allowed = {
            "json", "sys", "os", "sqlite3", "pathlib", "subprocess",
            "argparse", "logging", "hashlib", "re", "datetime", "uuid",
            "threading", "queue", "tempfile", "shutil", "urllib", "unittest",
            "io", "typing", "dataclasses", "enum", "time", "platform", "py_compile",
            "__future__",
        }
        for p in (ROOT / "mcp").rglob("*.py"):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("import ") or line.startswith("from "):
                    mod = line.split()[1].split(".")[0]
                    if mod not in allowed:
                        self.fail(f"{p}: disallowed import {mod!r}")


if __name__ == "__main__":
    unittest.main()
