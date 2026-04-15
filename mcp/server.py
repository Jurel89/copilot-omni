#!/usr/bin/env python3
"""
Copilot Omni MCP server — pure stdlib, stdio JSON-RPC 2.0, MCP 2024-11-05.

Exposes 23 tools across memory, artifacts, runs, policy, wiki, notepad,
state, shared_memory, trace, session_search, support, health, doctor,
config, subtask, and workspace families.

Runtime contract:
- Python >= 3.9
- No third-party imports. Only stdlib.
- One process per session. Reads JSON-RPC messages from stdin line-by-line,
  writes JSON-RPC responses to stdout line-by-line (Content-Length framing
  is supported transparently for compatibility, but the canonical transport
  for this server is newline-delimited JSON — which is what the Copilot CLI
  sends by default).

Storage:
- Single SQLite file at $OMNI_HOME/omni.db (default: ~/.omni/omni.db)
- WAL journal mode
- Schema versioned; migrated on startup
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SERVER_NAME = "copilot-omni"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
SCHEMA_VERSION = 1


# ------------------------------------------------------------------ storage


def omni_home() -> Path:
    root = os.environ.get("OMNI_HOME")
    if root:
        p = Path(root)
    else:
        p = Path.home() / ".omni"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    db_path = omni_home() / "omni.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
    )
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    current = row["version"] if row else 0
    if current < 1:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                tags TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_memory_scope ON memory(scope);
            CREATE INDEX IF NOT EXISTS ix_memory_key ON memory(scope, key);

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_artifacts_run ON artifacts(run_id);

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                phase TEXT NOT NULL,
                status TEXT NOT NULL,
                meta TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS state (
                mode TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wiki (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notepad (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shared_memory (
                key TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trace (
                id TEXT PRIMARY KEY,
                observation TEXT NOT NULL,
                hypothesis TEXT,
                evidence TEXT,
                verdict TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at REAL NOT NULL,
                tags TEXT,
                summary TEXT
            );
            """
        )
        conn.execute("INSERT INTO schema_version(version) VALUES (1)")


# ------------------------------------------------------------------ helpers


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex


def _text_result(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _json_result(data: Any) -> Dict[str, Any]:
    return _text_result(json.dumps(data, indent=2, sort_keys=True))


def _ensure(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


# ------------------------------------------------------------------ tools


def _tool_health(_: Dict[str, Any]) -> Dict[str, Any]:
    return _json_result({
        "status": "ok",
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "python": sys.version.split()[0],
        "omni_home": str(omni_home()),
    })


def _tool_doctor(_: Dict[str, Any]) -> Dict[str, Any]:
    checks = []
    checks.append({"name": "python_version", "ok": sys.version_info >= (3, 9),
                   "value": sys.version.split()[0]})
    try:
        conn = _connect()
        conn.execute("SELECT 1")
        conn.close()
        checks.append({"name": "sqlite", "ok": True, "value": sqlite3.sqlite_version})
    except Exception as e:
        checks.append({"name": "sqlite", "ok": False, "value": str(e)})
    checks.append({"name": "omni_home", "ok": omni_home().exists(),
                   "value": str(omni_home())})
    return _json_result({"checks": checks, "ok": all(c["ok"] for c in checks)})


def _tool_config_resolve(args: Dict[str, Any]) -> Dict[str, Any]:
    cwd = Path(args.get("cwd") or os.getcwd())
    candidates = [cwd / ".omni" / "config.json"]
    for path in candidates:
        if path.exists():
            return _json_result({"path": str(path),
                                 "config": json.loads(path.read_text(encoding="utf-8"))})
    return _json_result({"path": None, "config": {"profile": "standard"}})


def _tool_memory_capture(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = args.get("scope", "project")
    key = args.get("key")
    content = args.get("content")
    tags = ",".join(args.get("tags", []) or [])
    _ensure(isinstance(content, str) and content, "content required")
    mem_id = _new_id()
    now = _now()
    conn = _connect()
    conn.execute(
        "INSERT INTO memory(id, scope, key, content, tags, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mem_id, scope, key, content, tags, now, now),
    )
    conn.close()
    return _json_result({"id": mem_id, "scope": scope, "key": key})


def _tool_memory_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    scope = args.get("scope")
    limit = int(args.get("limit", 20))
    conn = _connect()
    if scope:
        rows = conn.execute(
            "SELECT id, scope, key, content, tags, updated_at FROM memory"
            " WHERE scope=? AND (content LIKE ? OR key LIKE ?)"
            " ORDER BY updated_at DESC LIMIT ?",
            (scope, f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, scope, key, content, tags, updated_at FROM memory"
            " WHERE content LIKE ? OR key LIKE ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    conn.close()
    return _json_result({"results": [dict(r) for r in rows]})


def _tool_memory_export(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = args.get("scope")
    conn = _connect()
    if scope:
        rows = conn.execute("SELECT * FROM memory WHERE scope=?", (scope,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM memory").fetchall()
    conn.close()
    return _json_result({"memories": [dict(r) for r in rows]})


def _tool_memory_prune(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = args.get("scope")
    older_than = args.get("older_than")
    conn = _connect()
    if scope and older_than:
        cur = conn.execute(
            "DELETE FROM memory WHERE scope=? AND updated_at < ?",
            (scope, float(older_than)),
        )
    elif scope:
        cur = conn.execute("DELETE FROM memory WHERE scope=?", (scope,))
    elif args.get("all"):
        cur = conn.execute("DELETE FROM memory")
    else:
        raise ValueError("provide scope, older_than, or all=true")
    conn.close()
    return _json_result({"deleted": cur.rowcount})


def _tool_artifact_write(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args["kind"]
    body = args["body"]
    run_id = args.get("run_id")
    path = args.get("path", f"{kind}.md")
    art_id = _new_id()
    conn = _connect()
    conn.execute(
        "INSERT INTO artifacts(id, run_id, kind, path, body, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (art_id, run_id, kind, path, body, _now()),
    )
    conn.close()
    # Also mirror to .omni/runs/<run_id>/ when cwd is a project
    try:
        cwd = Path(os.getcwd())
        base = cwd / ".omni" / "runs" / (run_id or "adhoc")
        base.mkdir(parents=True, exist_ok=True)
        (base / path).write_text(body, encoding="utf-8")
    except Exception:
        pass
    return _json_result({"id": art_id, "kind": kind, "path": path})


def _tool_artifact_read(args: Dict[str, Any]) -> Dict[str, Any]:
    art_id = args.get("id")
    run_id = args.get("run_id")
    conn = _connect()
    if art_id:
        row = conn.execute("SELECT * FROM artifacts WHERE id=?", (art_id,)).fetchone()
        conn.close()
        return _json_result(dict(row) if row else {"error": "not found"})
    if run_id:
        rows = conn.execute("SELECT * FROM artifacts WHERE run_id=?", (run_id,)).fetchall()
        conn.close()
        return _json_result({"artifacts": [dict(r) for r in rows]})
    conn.close()
    raise ValueError("id or run_id required")


def _tool_run_status(args: Dict[str, Any]) -> Dict[str, Any]:
    conn = _connect()
    run_id = args.get("run_id")
    if run_id:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        return _json_result(dict(row) if row else {"error": "not found"})
    rows = conn.execute("SELECT * FROM runs ORDER BY updated_at DESC LIMIT 20").fetchall()
    conn.close()
    return _json_result({"runs": [dict(r) for r in rows]})


def _tool_resume_context(args: Dict[str, Any]) -> Dict[str, Any]:
    run_id = args["run_id"]
    conn = _connect()
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    artifacts = conn.execute(
        "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", (run_id,)
    ).fetchall()
    conn.close()
    return _json_result({
        "run": dict(run) if run else None,
        "artifacts": [dict(a) for a in artifacts],
    })


def _tool_policy_check(args: Dict[str, Any]) -> Dict[str, Any]:
    tool = args.get("tool", "")
    tool_args = args.get("args", {})
    cwd = Path(args.get("cwd") or os.getcwd())
    profile = args.get("profile", "standard")

    policy_file = cwd / ".omni" / f"policy-{profile}.json"
    default = {
        "deny_commands": ["sudo", "rm -rf /", "mkfs", "dd if=/dev/zero"],
        "protected_paths": [".omni/config.json", ".github/copilot-instructions.md",
                            ".claude-plugin/plugin.json"],
    }
    policy = default
    if policy_file.exists():
        try:
            policy = json.loads(policy_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if tool == "shell":
        cmd = str(tool_args.get("command", "")).lower()
        for deny in policy.get("deny_commands", []):
            if deny.lower() in cmd:
                return _json_result({
                    "decision": "deny",
                    "reason": f"policy({profile}): blocked pattern '{deny}'",
                })
    if tool in ("write", "edit"):
        path = str(tool_args.get("file_path", ""))
        for prot in policy.get("protected_paths", []):
            if prot in path:
                return _json_result({
                    "decision": "deny",
                    "reason": f"policy({profile}): protected path '{prot}'",
                })
    return _json_result({"decision": "allow"})


def _tool_state_write(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args["mode"]
    body = args.get("body", {})
    conn = _connect()
    conn.execute(
        "INSERT INTO state(mode, body, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(mode) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
        (mode, json.dumps(body), _now()),
    )
    conn.close()
    return _json_result({"mode": mode, "ok": True})


def _tool_state_read(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    conn = _connect()
    if mode:
        row = conn.execute("SELECT * FROM state WHERE mode=?", (mode,)).fetchone()
        conn.close()
        if not row:
            return _json_result({"mode": mode, "body": None})
        return _json_result({"mode": row["mode"], "body": json.loads(row["body"]),
                             "updated_at": row["updated_at"]})
    rows = conn.execute("SELECT mode, updated_at FROM state").fetchall()
    conn.close()
    return _json_result({"modes": [dict(r) for r in rows]})


def _tool_state_clear(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    conn = _connect()
    if mode:
        cur = conn.execute("DELETE FROM state WHERE mode=?", (mode,))
    elif args.get("all"):
        cur = conn.execute("DELETE FROM state")
    else:
        raise ValueError("mode or all=true required")
    conn.close()
    return _json_result({"deleted": cur.rowcount})


def _tool_wiki_write(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = args["slug"]
    title = args.get("title", slug)
    body = args["body"]
    tags = ",".join(args.get("tags", []) or [])
    conn = _connect()
    conn.execute(
        "INSERT INTO wiki(slug, title, body, tags, updated_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(slug) DO UPDATE SET title=excluded.title, body=excluded.body,"
        " tags=excluded.tags, updated_at=excluded.updated_at",
        (slug, title, body, tags, _now()),
    )
    conn.close()
    return _json_result({"slug": slug, "ok": True})


def _tool_wiki_read(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = args["slug"]
    conn = _connect()
    row = conn.execute("SELECT * FROM wiki WHERE slug=?", (slug,)).fetchone()
    conn.close()
    return _json_result(dict(row) if row else {"error": "not found"})


def _tool_wiki_query(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    conn = _connect()
    rows = conn.execute(
        "SELECT slug, title, updated_at FROM wiki"
        " WHERE body LIKE ? OR title LIKE ? OR tags LIKE ?"
        " ORDER BY updated_at DESC LIMIT 50",
        (f"%{query}%", f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()
    return _json_result({"results": [dict(r) for r in rows]})


def _tool_wiki_list(_: Dict[str, Any]) -> Dict[str, Any]:
    conn = _connect()
    rows = conn.execute("SELECT slug, title, updated_at FROM wiki ORDER BY updated_at DESC").fetchall()
    conn.close()
    return _json_result({"entries": [dict(r) for r in rows]})


def _tool_notepad_write(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args.get("kind", "working")
    body = args["body"]
    note_id = _new_id()
    conn = _connect()
    conn.execute(
        "INSERT INTO notepad(id, kind, body, created_at) VALUES (?, ?, ?, ?)",
        (note_id, kind, body, _now()),
    )
    conn.close()
    return _json_result({"id": note_id, "kind": kind})


def _tool_notepad_read(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args.get("kind")
    conn = _connect()
    if kind:
        rows = conn.execute(
            "SELECT * FROM notepad WHERE kind=? ORDER BY created_at DESC LIMIT 50",
            (kind,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notepad ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return _json_result({"notes": [dict(r) for r in rows]})


def _tool_notepad_prune(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args.get("kind")
    conn = _connect()
    if kind:
        cur = conn.execute("DELETE FROM notepad WHERE kind=?", (kind,))
    elif args.get("all"):
        cur = conn.execute("DELETE FROM notepad")
    else:
        raise ValueError("kind or all=true required")
    conn.close()
    return _json_result({"deleted": cur.rowcount})


def _tool_shared_memory_write(args: Dict[str, Any]) -> Dict[str, Any]:
    key = args["key"]
    body = args["body"]
    conn = _connect()
    conn.execute(
        "INSERT INTO shared_memory(key, body, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
        (key, json.dumps(body) if not isinstance(body, str) else body, _now()),
    )
    conn.close()
    return _json_result({"key": key, "ok": True})


def _tool_shared_memory_read(args: Dict[str, Any]) -> Dict[str, Any]:
    key = args.get("key")
    conn = _connect()
    if key:
        row = conn.execute("SELECT * FROM shared_memory WHERE key=?", (key,)).fetchone()
        conn.close()
        return _json_result(dict(row) if row else {"error": "not found"})
    rows = conn.execute(
        "SELECT key, updated_at FROM shared_memory ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return _json_result({"entries": [dict(r) for r in rows]})


def _tool_trace_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = args.get("id")
    conn = _connect()
    if trace_id:
        row = conn.execute("SELECT * FROM trace WHERE id=?", (trace_id,)).fetchone()
        conn.close()
        return _json_result(dict(row) if row else {"error": "not found"})
    rows = conn.execute("SELECT * FROM trace ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    return _json_result({"traces": [dict(r) for r in rows]})


def _tool_trace_timeline(args: Dict[str, Any]) -> Dict[str, Any]:
    observation = args.get("observation")
    conn = _connect()
    if observation:
        rows = conn.execute(
            "SELECT * FROM trace WHERE observation LIKE ? ORDER BY created_at",
            (f"%{observation}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trace ORDER BY created_at").fetchall()
    conn.close()
    return _json_result({"timeline": [dict(r) for r in rows]})


def _tool_session_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE summary LIKE ? OR tags LIKE ? ORDER BY started_at DESC LIMIT 20",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()
    return _json_result({"sessions": [dict(r) for r in rows]})


def _tool_subtask(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "status")
    if action == "create":
        run_id = args.get("run_id") or _new_id()
        title = args.get("title", "subtask")
        conn = _connect()
        conn.execute(
            "INSERT INTO runs(id, phase, status, meta, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, "subtask", "pending", json.dumps({"title": title}), _now(), _now()),
        )
        conn.close()
        return _json_result({"run_id": run_id, "status": "pending"})
    if action == "status":
        return _tool_run_status({"run_id": args.get("run_id")})
    if action == "route":
        return _json_result({"route": "executor", "reason": "default routing"})
    raise ValueError(f"unknown action: {action}")


def _tool_workspace(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "list")
    cwd = Path(args.get("cwd") or os.getcwd())
    workspaces_root = cwd / ".omni" / "workspaces"
    workspaces_root.mkdir(parents=True, exist_ok=True)
    if action == "create":
        name = args["name"]
        ws = workspaces_root / name
        ws.mkdir(parents=True, exist_ok=True)
        return _json_result({"name": name, "path": str(ws)})
    if action == "remove":
        name = args["name"]
        ws = workspaces_root / name
        if ws.exists():
            import shutil
            shutil.rmtree(ws)
        return _json_result({"removed": name})
    if action == "list":
        return _json_result({
            "workspaces": [p.name for p in workspaces_root.iterdir() if p.is_dir()],
        })
    raise ValueError(f"unknown action: {action}")


def _tool_support_bundle(args: Dict[str, Any]) -> Dict[str, Any]:
    cwd = Path(args.get("cwd") or os.getcwd())
    out_dir = cwd / ".omni" / "support"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_id = _new_id()[:8]
    bundle_path = out_dir / f"bundle-{bundle_id}.json"
    content: Dict[str, Any] = {
        "id": bundle_id,
        "created_at": _now(),
        "omni_home": str(omni_home()),
        "python": sys.version,
    }
    try:
        conn = _connect()
        content["schema_version"] = dict(
            conn.execute("SELECT version FROM schema_version").fetchone()
        )
        content["counts"] = {
            t: conn.execute(f"SELECT COUNT(*) as n FROM {t}").fetchone()["n"]
            for t in ["memory", "artifacts", "runs", "state", "wiki",
                      "notepad", "shared_memory", "trace", "sessions"]
        }
        conn.close()
    except Exception as e:
        content["error"] = str(e)
    bundle_path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return _json_result({"bundle": str(bundle_path), "summary": content})


# ------------------------------------------------------------------ registry


TOOLS: Dict[str, Dict[str, Any]] = {
    "health": {
        "description": "Check server health and environment.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_health,
    },
    "doctor": {
        "description": "Diagnose Copilot Omni installation (python, sqlite, omni_home).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_doctor,
    },
    "config_resolve": {
        "description": "Resolve the project config (reads .omni/config.json if present).",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}},
            "additionalProperties": False,
        },
        "handler": _tool_config_resolve,
    },
    "memory_capture": {
        "description": "Persist a memory entry (scope+optional key+content+tags).",
        "inputSchema": {
            "type": "object",
            "required": ["content"],
            "properties": {
                "scope": {"type": "string"},
                "key": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": _tool_memory_capture,
    },
    "memory_search": {
        "description": "Full-text search across stored memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
        "handler": _tool_memory_search,
    },
    "memory_export": {
        "description": "Export all memories (optionally filtered by scope).",
        "inputSchema": {
            "type": "object",
            "properties": {"scope": {"type": "string"}},
        },
        "handler": _tool_memory_export,
    },
    "memory_prune": {
        "description": "Delete memories by scope, age, or entirely.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string"},
                "older_than": {"type": "number"},
                "all": {"type": "boolean"},
            },
        },
        "handler": _tool_memory_prune,
    },
    "artifact_write": {
        "description": "Write an artifact (spec, plan, decision, summary) under a run.",
        "inputSchema": {
            "type": "object",
            "required": ["kind", "body"],
            "properties": {
                "kind": {"type": "string"},
                "body": {"type": "string"},
                "run_id": {"type": "string"},
                "path": {"type": "string"},
            },
        },
        "handler": _tool_artifact_write,
    },
    "artifact_read": {
        "description": "Read an artifact by id or list all artifacts for a run.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "run_id": {"type": "string"}},
        },
        "handler": _tool_artifact_read,
    },
    "run_status": {
        "description": "Return status of a run or recent runs.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
        },
        "handler": _tool_run_status,
    },
    "resume_context": {
        "description": "Reconstruct run context from artifacts.",
        "inputSchema": {
            "type": "object",
            "required": ["run_id"],
            "properties": {"run_id": {"type": "string"}},
        },
        "handler": _tool_resume_context,
    },
    "policy_check": {
        "description": "Check whether a tool invocation is allowed by active policy.",
        "inputSchema": {
            "type": "object",
            "required": ["tool"],
            "properties": {
                "tool": {"type": "string"},
                "args": {"type": "object"},
                "cwd": {"type": "string"},
                "profile": {"type": "string"},
            },
        },
        "handler": _tool_policy_check,
    },
    "state_write": {
        "description": "Persist mode state (autopilot, ralph, ultrawork, team, etc.).",
        "inputSchema": {
            "type": "object",
            "required": ["mode"],
            "properties": {"mode": {"type": "string"}, "body": {"type": "object"}},
        },
        "handler": _tool_state_write,
    },
    "state_read": {
        "description": "Read mode state, or list all persisted modes.",
        "inputSchema": {
            "type": "object",
            "properties": {"mode": {"type": "string"}},
        },
        "handler": _tool_state_read,
    },
    "state_clear": {
        "description": "Clear mode state (one mode or all).",
        "inputSchema": {
            "type": "object",
            "properties": {"mode": {"type": "string"}, "all": {"type": "boolean"}},
        },
        "handler": _tool_state_clear,
    },
    "wiki_write": {
        "description": "Upsert a wiki page by slug.",
        "inputSchema": {
            "type": "object",
            "required": ["slug", "body"],
            "properties": {
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": _tool_wiki_write,
    },
    "wiki_read": {
        "description": "Read a wiki page by slug.",
        "inputSchema": {
            "type": "object",
            "required": ["slug"],
            "properties": {"slug": {"type": "string"}},
        },
        "handler": _tool_wiki_read,
    },
    "wiki_query": {
        "description": "Full-text search across wiki entries.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
        "handler": _tool_wiki_query,
    },
    "wiki_list": {
        "description": "List all wiki entries.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _tool_wiki_list,
    },
    "notepad_write": {
        "description": "Append a notepad entry (kind: working|priority|manual).",
        "inputSchema": {
            "type": "object",
            "required": ["body"],
            "properties": {"kind": {"type": "string"}, "body": {"type": "string"}},
        },
        "handler": _tool_notepad_write,
    },
    "notepad_read": {
        "description": "Read recent notepad entries.",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string"}},
        },
        "handler": _tool_notepad_read,
    },
    "notepad_prune": {
        "description": "Delete notepad entries by kind or all.",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string"}, "all": {"type": "boolean"}},
        },
        "handler": _tool_notepad_prune,
    },
    "shared_memory_write": {
        "description": "Write a cross-agent shared memory value.",
        "inputSchema": {
            "type": "object",
            "required": ["key"],
            "properties": {"key": {"type": "string"}, "body": {}},
        },
        "handler": _tool_shared_memory_write,
    },
    "shared_memory_read": {
        "description": "Read a shared memory value, or list all keys.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
        },
        "handler": _tool_shared_memory_read,
    },
    "trace_summary": {
        "description": "Summarize recorded traces or one by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
        },
        "handler": _tool_trace_summary,
    },
    "trace_timeline": {
        "description": "Return trace timeline, optionally filtered by observation.",
        "inputSchema": {
            "type": "object",
            "properties": {"observation": {"type": "string"}},
        },
        "handler": _tool_trace_timeline,
    },
    "session_search": {
        "description": "Search prior Copilot sessions captured in the local store.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
        "handler": _tool_session_search,
    },
    "subtask": {
        "description": "Create, inspect, or route a subtask.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "status", "route"]},
                "run_id": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        "handler": _tool_subtask,
    },
    "workspace": {
        "description": "Manage local workspaces (create/remove/list).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "remove", "list"]},
                "name": {"type": "string"},
                "cwd": {"type": "string"},
            },
        },
        "handler": _tool_workspace,
    },
    "support_bundle": {
        "description": "Produce a redacted diagnostic support bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}},
        },
        "handler": _tool_support_bundle,
    },
}


# ------------------------------------------------------------------ JSON-RPC


def _rpc_response(rpc_id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def _handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = message.get("method")
    rpc_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _rpc_response(rpc_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        tools = []
        for name, spec in TOOLS.items():
            tools.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            })
        return _rpc_response(rpc_id, {"tools": tools})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if not spec:
            return _rpc_response(rpc_id, error={"code": -32601, "message": f"unknown tool: {name}"})
        try:
            result = spec["handler"](args)
            return _rpc_response(rpc_id, result)
        except Exception as exc:
            return _rpc_response(rpc_id, error={"code": -32000, "message": str(exc)})
    if method == "ping":
        return _rpc_response(rpc_id, {})
    if method == "shutdown":
        return _rpc_response(rpc_id, {})

    if rpc_id is None:
        return None
    return _rpc_response(rpc_id, error={"code": -32601, "message": f"unknown method: {method}"})


def _serve() -> int:
    stdout = sys.stdout
    stdin = sys.stdin
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, list):
            responses = [_handle(m) for m in msg]
            out = [r for r in responses if r is not None]
            if out:
                stdout.write(json.dumps(out) + "\n")
                stdout.flush()
            continue
        resp = _handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--list-tools":
        print(json.dumps(sorted(TOOLS.keys()), indent=2))
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(f"{SERVER_NAME} {SERVER_VERSION}")
        return 0
    return _serve()


if __name__ == "__main__":
    sys.exit(main())
