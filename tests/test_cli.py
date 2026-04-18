"""Unit tests for the omni CLI."""
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


def run(args, cwd=ROOT, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(OMNI), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=merged_env,
        timeout=15,
    )
    return proc.stdout, proc.stderr, proc.returncode


def seed_navigation_db(omni_home: Path) -> None:
    omni_home.mkdir(parents=True, exist_ok=True)
    db_path = omni_home / "omni.db"
    now = time.time()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE memory (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                tags TEXT,
                project TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE state (
                mode TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE wiki (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT,
                updated_at REAL NOT NULL
            );
            CREATE TABLE notepad (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE shared_memory (
                key TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE trace (
                id TEXT PRIMARY KEY,
                observation TEXT NOT NULL,
                hypothesis TEXT,
                evidence TEXT,
                verdict TEXT,
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO memory(id, scope, key, content, tags, project, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "mem-1",
                "project",
                "guide",
                "memory hello world",
                "cli,test",
                str(ROOT),
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO state(mode, body, updated_at) VALUES (?, ?, ?)",
            ("router", json.dumps({"decision": "go"}), now),
        )
        conn.executemany(
            "INSERT INTO wiki(slug, title, body, tags, updated_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("home", "Home", "See [[about]].", "start", now),
                ("about", "About", "Welcome home.", "docs", now - 10),
            ],
        )
        conn.execute(
            "INSERT INTO notepad(id, kind, body, created_at) VALUES (?, ?, ?, ?)",
            ("note-1", "working", "remember this note", now),
        )
        conn.execute(
            "INSERT INTO shared_memory(key, body, updated_at) VALUES (?, ?, ?)",
            ("team-status", json.dumps({"workers": 2}), now),
        )
        conn.executemany(
            "INSERT INTO trace(id, observation, hypothesis, evidence, verdict, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "trace-1",
                    "investigate failure",
                    "maybe race",
                    json.dumps({"files": 1}),
                    "open",
                    now - 5,
                ),
                (
                    "trace-2",
                    "deploy success",
                    "fixed config",
                    json.dumps({"result": "green"}),
                    "done",
                    now,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


class TestCli(unittest.TestCase):
    def test_version(self):
        out, _, rc = run(["version"])
        self.assertEqual(rc, 0)
        self.assertIn("1.0.0", out)

    def test_init_creates_config(self):
        with tempfile.TemporaryDirectory() as td:
            out, _, rc = run(["init", "--path", td])
            self.assertEqual(rc, 0, out)
            cfg = Path(td) / ".omni" / "config.json"
            self.assertTrue(cfg.exists())
            data = json.loads(cfg.read_text())
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["profile"], "standard")

    def test_list_all(self):
        out, _, rc = run(["list", "all"])
        self.assertEqual(rc, 0)
        self.assertIn("# Skills", out)
        self.assertIn("# Agents", out)

    def test_doctor_returns_ok_in_repo(self):
        out, _, rc = run(["doctor"])
        self.assertIn(rc, (0, 1))
        self.assertIn("python:", out)
        self.assertIn("plugin.json:", out)


class TestCliStoreNavigation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.omni_home = Path(self.tmpdir.name)
        self.env = {"OMNI_HOME": self.tmpdir.name}
        seed_navigation_db(self.omni_home)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_memory_navigation_preserves_existing_surface(self):
        out, err, rc = run(["memory", "list", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["entries"][0]["key"], "guide")

    def test_state_and_wiki_navigation(self):
        out, err, rc = run(["state", "list"], env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertIn("router", out)

        out, err, rc = run(["state", "show", "router", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["body"]["decision"], "go")

        out, err, rc = run(["wiki", "list"], env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertIn("home", out)
        self.assertIn("about", out)

        out, err, rc = run(["wiki", "search", "Welcome", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["slug"], "about")

        out, err, rc = run(["wiki", "show", "home"], env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Slug: home", out)
        self.assertIn("See [[about]].", out)

        out, err, rc = run(["wiki", "graph", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["node_count"], 2)
        self.assertEqual(body["edge_count"], 1)
        self.assertEqual(body["dangling_count"], 0)

    def test_notepad_shared_memory_and_trace_navigation(self):
        out, err, rc = run(["notepad", "list", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notes"][0]["id"], "note-1")

        out, err, rc = run(["notepad", "show", "note-1"], env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertIn("remember this note", out)

        out, err, rc = run(["shared-memory", "show", "team-status", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["body"]["workers"], 2)

        out, err, rc = run(["trace", "list"], env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertIn("trace-2", out)

        out, err, rc = run(["trace", "show", "trace-1", "--json"], env=self.env)
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["hypothesis"], "maybe race")

        out, err, rc = run(
            ["trace", "timeline", "--contains", "deploy", "--json"], env=self.env
        )
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["timeline"][0]["id"], "trace-2")


if __name__ == "__main__":
    unittest.main()
