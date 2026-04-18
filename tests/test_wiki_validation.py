"""CLI tests for wiki graph + validation behavior."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMNI = ROOT / "scripts" / "omni.py"


def run(args, *, env):
    merged_env = os.environ.copy()
    merged_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(OMNI), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=merged_env,
        timeout=15,
    )
    return proc.stdout, proc.stderr, proc.returncode


def seed_wiki(omni_home: Path, pages):
    omni_home.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(omni_home / "omni.db")
    now = time.time()
    try:
        conn.execute(
            "CREATE TABLE wiki (slug TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, tags TEXT, updated_at REAL NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO wiki(slug, title, body, tags, updated_at) VALUES (?, ?, ?, ?, ?)",
            [(slug, title, body, tags, now + index) for index, (slug, title, body, tags) in enumerate(pages)],
        )
        conn.commit()
    finally:
        conn.close()


class TestWikiValidationCli(unittest.TestCase):
    def test_wiki_graph_reports_edges_and_dangling_targets(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"OMNI_HOME": td}
            seed_wiki(
                Path(td),
                [
                    ("home", "Home", "See [[about]] and [[missing]].", "start"),
                    ("about", "About", "Return to [[home]].", "docs"),
                ],
            )
            out, err, rc = run(["wiki", "graph", "--json"], env=env)
            self.assertEqual(rc, 0, err)
            body = json.loads(out)
            self.assertEqual(body["node_count"], 2)
            self.assertEqual(body["edge_count"], 2)
            self.assertEqual(body["dangling_count"], 1)
            self.assertIn({"source": "home", "target": "about"}, body["edges"])
            self.assertIn({"source": "home", "target": "missing"}, body["dangling"])

    def test_wiki_validate_fails_for_dangling_links(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"OMNI_HOME": td}
            seed_wiki(
                Path(td),
                [("home", "Home", "See [[missing]].", "start")],
            )
            out, err, rc = run(["wiki", "validate"], env=env)
            self.assertEqual(rc, 1, err)
            self.assertIn("Wiki validation: FAIL", out)
            self.assertIn("missing", out)

    def test_wiki_validate_succeeds_when_graph_is_closed(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"OMNI_HOME": td}
            seed_wiki(
                Path(td),
                [
                    ("home", "Home", "See [[about]].", "start"),
                    ("about", "About", "Return to [[home]].", "docs"),
                ],
            )
            out, err, rc = run(["wiki", "validate", "--json"], env=env)
            self.assertEqual(rc, 0, err)
            body = json.loads(out)
            self.assertTrue(body["ok"])
            self.assertEqual(body["dangling_count"], 0)


if __name__ == "__main__":
    unittest.main()
