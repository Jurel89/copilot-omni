#!/usr/bin/env python3
"""
Copilot Omni MCP server — pure stdlib, stdio JSON-RPC 2.0, MCP 2024-11-05.

Exposes 28 tools across memory, state, wiki, notepad,
shared_memory, trace, policy, health, doctor, LSP, and ast-grep families.

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

import atexit
import hashlib as _hashlib
import importlib.util as _importlib_util
import json
import os
import re
import shlex
import shutil
import sqlite3
import sys
import threading
import time
import traceback as _traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SERVER_NAME = "copilot-omni"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
SCHEMA_VERSION = 4


# ------------------------------------------------------------------ storage


def omni_home() -> Path:
    root = os.environ.get("OMNI_HOME")
    if root:
        p = Path(root)
    else:
        p = Path.home() / ".omni"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _current_project() -> str:
    """Return a project identifier (git repo root or cwd hash)."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


# ------------------------------------------------------------------ migration framework

# Each entry: (target_version: int, sql_statements: str)
# Migrations MUST be additive-only: no DROP COLUMN, no rename, no destructive ALTER.
# New columns must be NULLable or have defaults.
MIGRATIONS: List[Tuple[int, str]] = [
    (
        1,
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
    """,
    ),
    (
        2,
        """
        ALTER TABLE state ADD COLUMN session_id TEXT;
    """,
    ),
    (
        3,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_state_mode_session
            ON state(mode, COALESCE(session_id, ''));
    """,
    ),
    (
        4,
        """
        ALTER TABLE memory ADD COLUMN project TEXT NOT NULL DEFAULT '';
        UPDATE memory SET project = '' WHERE project = '';
    """,
    ),
]

# Serialize migrations across all threads in this process.
_MIGRATE_LOCK = threading.Lock()


def _migrate(conn: sqlite3.Connection) -> None:
    with _MIGRATE_LOCK:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row["version"] if row else 0

        # Guard: refuse to run if DB is from a newer version of the plugin.
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"DB is from a newer plugin version (db={current}, server={SCHEMA_VERSION}); "
                "please update your plugin."
            )

        for target_version, sql in MIGRATIONS:
            if current < target_version:
                try:
                    conn.executescript(sql)
                except sqlite3.OperationalError as exc:
                    # Idempotency: ignore "duplicate column name" from ALTER TABLE
                    # that was already applied by a concurrent connection.
                    if "duplicate column name" not in str(exc).lower():
                        raise
                conn.execute("DELETE FROM schema_version")
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (target_version,),
                )
                current = target_version


# ------------------------------------------------------------------ connection pool

_POOL_LOCK = threading.Lock()
_POOL_MAX = 4
_POOL_IDLE: List[sqlite3.Connection] = []
_POOL_ACTIVE = 0
_POOL_COND = threading.Condition(_POOL_LOCK)


def _make_connection() -> sqlite3.Connection:
    db_path = omni_home() / "omni.db"
    conn = sqlite3.connect(
        str(db_path), isolation_level=None, timeout=10.0, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _pool_acquire() -> sqlite3.Connection:
    global _POOL_ACTIVE
    with _POOL_COND:
        while not _POOL_IDLE and _POOL_ACTIVE >= _POOL_MAX:
            _POOL_COND.wait()
        if _POOL_IDLE:
            conn = _POOL_IDLE.pop()
            _POOL_ACTIVE += 1
            return conn
        # Spawn new connection (within cap)
        _POOL_ACTIVE += 1

    # Create outside lock to avoid holding it during I/O.
    # B3 fix: if _make_connection() fails, decrement _POOL_ACTIVE and notify
    # waiters so the pool is not permanently deadlocked.
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            return _make_connection()
        except sqlite3.OperationalError as exc:
            last_err = exc
            time.sleep(0.1 * (2**attempt))
    # All attempts failed — restore the slot we reserved
    with _POOL_COND:
        _POOL_ACTIVE -= 1
        _POOL_COND.notify()
    assert last_err is not None
    raise last_err


def _pool_release(conn: sqlite3.Connection) -> None:
    global _POOL_ACTIVE
    with _POOL_COND:
        _POOL_ACTIVE -= 1
        _POOL_IDLE.append(conn)
        _POOL_COND.notify()


def _pool_close_all() -> None:
    global _POOL_ACTIVE
    with _POOL_LOCK:
        for conn in _POOL_IDLE:
            try:
                conn.close()
            except Exception:
                pass
        _POOL_IDLE.clear()


atexit.register(_pool_close_all)


# Legacy _connect() kept for compatibility — uses pool.
def _connect() -> sqlite3.Connection:
    return _pool_acquire()


class _Conn:
    """Context manager that returns connection to pool on all exit paths."""

    def __enter__(self) -> sqlite3.Connection:
        self._conn = _pool_acquire()
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            _pool_release(self._conn)
        except Exception:
            pass


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_identifier(name: str, label: str) -> str:
    """Validate a user-provided path segment for filesystem safety."""
    if not name or not _SAFE_ID_RE.fullmatch(name):
        raise ValueError(f"invalid {label}: must match {_SAFE_ID_RE.pattern!r}")
    return name


def _safe_child_path(root: Path, relative: str) -> Path:
    """Resolve `relative` against `root` and refuse to escape."""
    root_resolved = root.resolve()
    # Forbid absolute paths and leading drive letters; normalize separators.
    if os.path.isabs(relative) or (len(relative) > 1 and relative[1] == ":"):
        raise ValueError("absolute paths are not allowed")
    target = (root_resolved / relative).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise ValueError("path escapes artifact root")
    return target


# ------------------------------------------------------------------ error sanitization


def _sanitize_error(exc: Exception, tool_name: str) -> Dict[str, Any]:
    """Return a sanitized JSON-RPC error dict that does not leak internals.

    Full traceback is written to stderr. The response only contains a short
    reason that does not include filesystem paths, env vars, or tracebacks.
    """
    print(
        f"[{tool_name}] unhandled exception: {type(exc).__name__}: {exc}\n"
        + _traceback.format_exc(),
        file=sys.stderr,
        flush=True,
    )

    # Extract a short safe reason: use the exception type name only.
    reason = type(exc).__name__
    # Include the message only if it doesn't look like it contains a path or env var.
    raw_msg = str(exc)
    if raw_msg and not _looks_sensitive(raw_msg):
        # truncate to 120 chars
        reason = raw_msg[:120]

    return {
        "code": -32000,
        "message": f"{tool_name}: {reason}",
        "data": {"tool": tool_name},
    }


# T3: tightened sensitive-content detector.
# Matches:
# - Absolute filesystem paths starting with well-known root dirs
# - Windows absolute paths (C:\...)
# - UNC paths (\\server\share)
# - Well-known sensitive env-var name patterns (API_KEY, TOKEN, etc.)
# - Python tracebacks
_SENSITIVE_RE = re.compile(
    r"(?:"
    # POSIX absolute paths with well-known root dirs
    r"/(home|Users|var|etc|tmp|root|opt)/[a-zA-Z0-9_./ -]+"
    r"|"
    # Windows drive paths: C:\ or C:/
    r"[A-Za-z]:[/\\][a-zA-Z0-9_./ \\-]+"
    r"|"
    # UNC paths: \\server
    r"\\\\[a-zA-Z0-9_.-]+"
    r"|"
    # Sensitive env-var names (standalone words)
    r"\b(API_KEY|TOKEN|PASSWORD|SECRET|PRIVATE_KEY|CREDENTIAL)\b"
    r"|"
    # Python traceback header
    r"Traceback \(most recent"
    r")"
)


def _looks_sensitive(msg: str) -> bool:
    """Heuristic: return True if msg likely contains a sensitive path, env var, or traceback."""
    return bool(_SENSITIVE_RE.search(msg))


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
    return _json_result(
        {
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "python": sys.version.split()[0],
            "omni_home": str(omni_home()),
        }
    )


def _tool_doctor(_: Dict[str, Any]) -> Dict[str, Any]:
    checks = []
    checks.append(
        {
            "name": "python_version",
            "ok": sys.version_info >= (3, 9),
            "value": sys.version.split()[0],
        }
    )
    try:
        conn = _pool_acquire()
        conn.execute("SELECT 1")
        _pool_release(conn)
        checks.append({"name": "sqlite", "ok": True, "value": sqlite3.sqlite_version})
    except Exception as e:
        checks.append({"name": "sqlite", "ok": False, "value": str(e)})
    checks.append(
        {"name": "omni_home", "ok": omni_home().exists(), "value": str(omni_home())}
    )
    return _json_result({"checks": checks, "ok": all(c["ok"] for c in checks)})


def _tool_memory_capture(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = args.get("scope", "project")
    key = args.get("key")
    content = args.get("content")
    tags = ",".join(args.get("tags", []) or [])
    _ensure(isinstance(content, str) and content, "content required")
    mem_id = _new_id()
    project = _current_project()
    now = _now()
    with _Conn() as conn:
        conn.execute(
            "INSERT INTO memory(id, scope, key, content, tags, project, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mem_id, scope, key, content, tags, project, now, now),
        )
    return _json_result({"id": mem_id, "scope": scope, "key": key, "project": project})


def _tool_memory_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    scope = args.get("scope")
    limit = int(args.get("limit", 20))
    project = _current_project()
    with _Conn() as conn:
        if scope:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at FROM memory"
                " WHERE scope=? AND (content LIKE ? OR key LIKE ?)"
                " AND project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (scope, f"%{query}%", f"%{query}%", project, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at FROM memory"
                " WHERE (content LIKE ? OR key LIKE ?)"
                " AND project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", project, limit),
            ).fetchall()
    return _json_result({"results": [dict(r) for r in rows]})


def _tool_memory_export(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = args.get("scope")
    export_format = args.get("format", "json")
    _ensure(export_format == "json", "format must be json")
    project = _current_project()
    with _Conn() as conn:
        if scope:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, created_at, updated_at FROM memory"
                " WHERE scope=? AND project=?"
                " ORDER BY updated_at DESC",
                (scope, project),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, created_at, updated_at FROM memory"
                " WHERE project=?"
                " ORDER BY updated_at DESC",
                (project,),
            ).fetchall()
    return _json_result({"entries": [dict(r) for r in rows], "count": len(rows)})


# ------------------------------------------------------------------ Phase-C C18: LSP + ast-grep


def _which(binary: str) -> Optional[str]:
    return shutil.which(binary)


def _run_subprocess(
    cmd: List[str], *, input_text: Optional[str] = None, timeout: float = 30.0
) -> Dict[str, Any]:
    import subprocess as _sp  # noqa: PLC0415

    try:
        proc = _sp.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"status": "skipped", "reason": f"{cmd[0]} not found on PATH"}
    except _sp.TimeoutExpired:
        return {"status": "error", "reason": f"{cmd[0]} timed out after {timeout}s"}
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr[:4000],
    }


def _tool_lsp_hover(args: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort LSP hover query.

    Requires an LSP server binary on PATH (``ls_binary`` arg, default
    ``pylsp``). Returns ``status: "skipped"`` when the binary is absent so
    callers degrade gracefully rather than error.
    """
    binary = args.get("ls_binary", "pylsp")
    path = args.get("path", "")
    line = int(args.get("line", 0))
    character = int(args.get("character", 0))
    if not _which(binary):
        return _json_result(
            {
                "status": "skipped",
                "reason": f"{binary!r} not found on PATH — install an LSP "
                f"server to enable this tool",
                "path": path,
            }
        )
    # We don't start a persistent LSP session here — the intent is a smoke
    # surface. A real handler would spawn the LSP over stdio JSON-RPC. For
    # now we echo the request back with status=stub so integrations can
    # probe and downstream tests can assert the call shape.
    return _json_result(
        {
            "status": "stub",
            "ls_binary": binary,
            "path": path,
            "line": line,
            "character": character,
            "note": "full LSP session not implemented; binary is present",
        }
    )


def _tool_lsp_goto_definition(args: Dict[str, Any]) -> Dict[str, Any]:
    binary = args.get("ls_binary", "pylsp")
    if not _which(binary):
        return _json_result(
            {
                "status": "skipped",
                "reason": f"{binary!r} not found on PATH",
            }
        )
    return _json_result(
        {
            "status": "stub",
            "ls_binary": binary,
            "path": args.get("path", ""),
            "line": int(args.get("line", 0)),
            "character": int(args.get("character", 0)),
        }
    )


def _tool_lsp_find_references(args: Dict[str, Any]) -> Dict[str, Any]:
    binary = args.get("ls_binary", "pylsp")
    if not _which(binary):
        return _json_result(
            {
                "status": "skipped",
                "reason": f"{binary!r} not found on PATH",
            }
        )
    return _json_result(
        {
            "status": "stub",
            "ls_binary": binary,
            "path": args.get("path", ""),
            "line": int(args.get("line", 0)),
            "character": int(args.get("character", 0)),
        }
    )


def _assert_no_flag_injection(*values: str) -> None:
    """Guard against flag-injection into subprocess argv.

    Even with shell=False, a user-controlled positional argument that starts
    with '-' is interpreted as a flag by the target tool. ast-grep's config
    loader can execute remote rule files, so a value like '--config=/tmp/evil.yml'
    is a realistic exploit.
    Raises ValueError when any value starts with '-'.
    """
    for v in values:
        if isinstance(v, str) and v.startswith("-"):
            raise ValueError(f"refusing ast-grep arg that begins with '-': {v[:40]!r}")


def _tool_ast_grep_search(args: Dict[str, Any]) -> Dict[str, Any]:
    pattern = args.get("pattern", "")
    target = args.get("path", ".")
    lang = args.get("lang")
    if not pattern:
        raise ValueError("pattern required")
    _assert_no_flag_injection(pattern, target, lang or "")
    if not _which("ast-grep") and not _which("sg"):
        return _json_result(
            {
                "status": "skipped",
                "reason": "ast-grep (or 'sg') not found on PATH",
            }
        )
    binary = _which("ast-grep") or _which("sg")
    # `--` separates flags from positional arguments so ast-grep cannot
    # reinterpret `target` as another flag.
    cmd = [binary, "run", "--pattern", pattern]
    if lang:
        cmd.extend(["--lang", lang])
    cmd.extend(["--", target])
    result = _run_subprocess(cmd, timeout=30.0)
    return _json_result(result)


def _tool_ast_grep_replace(args: Dict[str, Any]) -> Dict[str, Any]:
    pattern = args.get("pattern", "")
    replacement = args.get("replacement", "")
    target = args.get("path", ".")
    lang = args.get("lang")
    if not pattern or not replacement:
        raise ValueError("pattern and replacement required")
    _assert_no_flag_injection(pattern, replacement, target, lang or "")
    if not _which("ast-grep") and not _which("sg"):
        return _json_result(
            {
                "status": "skipped",
                "reason": "ast-grep (or 'sg') not found on PATH",
            }
        )
    binary = _which("ast-grep") or _which("sg")
    cmd = [
        binary,
        "run",
        "--pattern",
        pattern,
        "--rewrite",
        replacement,
        "--update-all",
    ]
    if lang:
        cmd.extend(["--lang", lang])
    # `--` barrier so *target* (user-supplied) can never be re-parsed as a flag
    cmd.extend(["--", target])
    result = _run_subprocess(cmd, timeout=60.0)
    return _json_result(result)


def _tool_policy_check(args: Dict[str, Any]) -> Dict[str, Any]:
    tool = args.get("tool", "")
    tool_args = args.get("args", {})
    cwd = Path(args.get("cwd") or os.getcwd())
    profile = args.get("profile", "standard")

    policy_file = cwd / ".omni" / f"policy-{profile}.json"
    default = {
        "deny_commands": [
            "sudo",
            "rm -rf /",
            "mkfs",
            "dd if=/dev/zero",
            ":(){ :|:& };:",
        ],
        "protected_paths": [
            ".omni/config.json",
            ".github/copilot-instructions.md",
            "plugin.json",
            "AGENTS.md",
        ],
    }
    policy = default
    if policy_file.exists():
        try:
            policy = json.loads(policy_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if tool in ("shell", "bash"):
        raw = str(tool_args.get("command", ""))
        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            tokens = raw.split()
        lower_cmd = raw.lower()
        token_set = {t.lower() for t in tokens}
        basenames = {os.path.basename(t).lower() for t in tokens}
        for deny in policy.get("deny_commands", []):
            dlow = deny.lower().strip()
            if not dlow:
                continue
            if " " in dlow:
                if dlow in lower_cmd:
                    return _json_result(
                        {
                            "decision": "deny",
                            "reason": f"policy({profile}): blocked pattern '{deny}'",
                        }
                    )
            elif dlow in token_set or dlow in basenames:
                return _json_result(
                    {
                        "decision": "deny",
                        "reason": f"policy({profile}): blocked command '{deny}'",
                    }
                )
    if tool in (
        "write",
        "edit",
        "edit_file",
        "multi_edit",
        "multiedit",
        "patch",
        "apply_patch",
        "str_replace_editor",
    ):
        raw_path = str(tool_args.get("file_path") or tool_args.get("path", ""))
        norm = os.path.normpath(raw_path).replace("\\", "/").lower()
        for prot in policy.get("protected_paths", []):
            if not prot:
                continue
            if prot.replace("\\", "/").lower() in norm:
                return _json_result(
                    {
                        "decision": "deny",
                        "reason": f"policy({profile}): protected path '{prot}'",
                    }
                )
    return _json_result({"decision": "allow"})


def _tool_state_write(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args["mode"]
    body = args.get("body", {})
    with _Conn() as conn:
        conn.execute(
            "INSERT INTO state(mode, body, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(mode) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
            (mode, json.dumps(body), _now()),
        )
    return _json_result({"mode": mode, "ok": True})


def _tool_state_read(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    with _Conn() as conn:
        if mode:
            row = conn.execute("SELECT * FROM state WHERE mode=?", (mode,)).fetchone()
            if not row:
                return _json_result({"mode": mode, "body": None})
            return _json_result(
                {
                    "mode": row["mode"],
                    "body": json.loads(row["body"]),
                    "updated_at": row["updated_at"],
                }
            )
        rows = conn.execute("SELECT mode, updated_at FROM state").fetchall()
    return _json_result({"modes": [dict(r) for r in rows]})


def _tool_state_clear(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    with _Conn() as conn:
        if mode:
            cur = conn.execute("DELETE FROM state WHERE mode=?", (mode,))
        elif args.get("all"):
            cur = conn.execute("DELETE FROM state")
        else:
            raise ValueError("mode or all=true required")
        deleted = cur.rowcount
    return _json_result({"deleted": deleted})


def _tool_wiki_write(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = args["slug"]
    title = args.get("title", slug)
    body = args["body"]
    tags = ",".join(args.get("tags", []) or [])
    with _Conn() as conn:
        conn.execute(
            "INSERT INTO wiki(slug, title, body, tags, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(slug) DO UPDATE SET title=excluded.title, body=excluded.body,"
            " tags=excluded.tags, updated_at=excluded.updated_at",
            (slug, title, body, tags, _now()),
        )
    return _json_result({"slug": slug, "ok": True})


def _tool_wiki_read(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = args["slug"]
    with _Conn() as conn:
        row = conn.execute("SELECT * FROM wiki WHERE slug=?", (slug,)).fetchone()
    return _json_result(dict(row) if row else {"error": "not found"})


def _tool_wiki_query(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    with _Conn() as conn:
        rows = conn.execute(
            "SELECT slug, title, updated_at FROM wiki"
            " WHERE body LIKE ? OR title LIKE ? OR tags LIKE ?"
            " ORDER BY updated_at DESC LIMIT 50",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    return _json_result({"results": [dict(r) for r in rows]})


def _tool_wiki_list(_: Dict[str, Any]) -> Dict[str, Any]:
    with _Conn() as conn:
        rows = conn.execute(
            "SELECT slug, title, updated_at FROM wiki ORDER BY updated_at DESC"
        ).fetchall()
    return _json_result({"entries": [dict(r) for r in rows]})


# ------------------------------------------------------------------ Phase-C C17: ingest + graph


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:80] or "untitled"


def _tool_wiki_ingest(args: Dict[str, Any]) -> Dict[str, Any]:
    """Append a wiki page; de-duplicates by content SHA-256.

    Ingesting the same *body* twice returns ``ok: true, deduped: true`` and
    does NOT bump updated_at. This is the contract the wave-1 content-lake
    plan called out — it lets external crawlers pipe documents in without
    re-writing identical bodies.
    """
    body = args.get("body")
    if not isinstance(body, str) or not body:
        raise ValueError("body required (non-empty string)")
    raw_slug = args.get("slug") or args.get("title") or "untitled"
    slug = _slugify(raw_slug)
    title = args.get("title", raw_slug)
    tags_list = args.get("tags", []) or []
    tags = ",".join(tags_list)
    sha = _hashlib.sha256(body.encode("utf-8")).hexdigest()
    now = _now()
    # The wiki table doesn't have a sha column; we encode the hash into the
    # tags column as a sentinel token using a namespaced prefix that cannot
    # collide with user-supplied tags. Matching is done on comma-split
    # tokens so a benign tag of the form "sha256=…" (not our sentinel
    # prefix) never triggers a false dedupe.
    sentinel = f"__omni_sha256__={sha}"
    with _Conn() as conn:
        existing = conn.execute(
            "SELECT slug, tags FROM wiki WHERE slug=?", (slug,)
        ).fetchone()
        if existing and existing["tags"]:
            existing_tokens = {
                t.strip() for t in (existing["tags"] or "").split(",") if t.strip()
            }
            if sentinel in existing_tokens:
                return _json_result(
                    {
                        "slug": slug,
                        "ok": True,
                        "deduped": True,
                        "sha256": sha,
                    }
                )
        merged_tags_parts: List[str] = []
        if tags:
            merged_tags_parts.append(tags)
        merged_tags_parts.append(sentinel)
        merged_tags = ",".join(merged_tags_parts)
        conn.execute(
            "INSERT INTO wiki(slug, title, body, tags, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(slug) DO UPDATE SET title=excluded.title,"
            " body=excluded.body, tags=excluded.tags,"
            " updated_at=excluded.updated_at",
            (slug, title, body, merged_tags, now),
        )
    return _json_result(
        {
            "slug": slug,
            "ok": True,
            "deduped": False,
            "sha256": sha,
        }
    )


# [[slug]] or [[Title|slug]] — when a pipe is present we capture the slug
# (the segment AFTER the pipe), not the display title. Codex P2 fix.
_WIKI_LINK_RE = re.compile(r"\[\[\s*(?:[^\]|]*\|)?\s*([^\]|]+?)\s*\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*?\]\(\s*([^)\s]+?)\s*\)")


def _extract_wiki_targets(body: str) -> List[str]:
    """Pull wiki-link targets from a body.

    Recognises:
    - [[other-slug]] and [[Title|slug]] (wiki-link syntax)
    - [anchor](./other-slug) or [anchor](other-slug.md) (Markdown links
      whose destination looks like a local slug reference rather than a URL)
    """
    out: List[str] = []
    for m in _WIKI_LINK_RE.finditer(body):
        out.append(_slugify(m.group(1)))
    for m in _MD_LINK_RE.finditer(body):
        dest = m.group(1)
        if "://" in dest or dest.startswith("#"):
            continue
        bare = dest.rsplit("/", 1)[-1]
        if bare.endswith(".md"):
            bare = bare[:-3]
        out.append(_slugify(bare))
    # Stable de-dupe while preserving order
    seen: set = set()
    unique: List[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _tool_wiki_graph(_args: Dict[str, Any]) -> Dict[str, Any]:
    """Return a knowledge graph {nodes: [...], edges: [...]} of the wiki.

    Nodes are every stored slug. Edges are extracted via _extract_wiki_targets
    applied to each body. Dangling targets (no matching slug) are omitted,
    but surface in ``dangling`` so callers can render them separately.
    """
    with _Conn() as conn:
        rows = conn.execute("SELECT slug, title, body FROM wiki").fetchall()
    slugs = {row["slug"] for row in rows}
    nodes = [{"slug": row["slug"], "title": row["title"]} for row in rows]
    edges: List[Dict[str, str]] = []
    dangling: List[Dict[str, str]] = []
    for row in rows:
        targets = _extract_wiki_targets(row["body"] or "")
        for target in targets:
            if target == row["slug"]:
                continue
            if target in slugs:
                edges.append({"source": row["slug"], "target": target})
            else:
                dangling.append({"source": row["slug"], "target": target})
    return _json_result({"nodes": nodes, "edges": edges, "dangling": dangling})


def _tool_notepad_write(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args.get("kind", "working")
    body = args["body"]
    note_id = _new_id()
    with _Conn() as conn:
        conn.execute(
            "INSERT INTO notepad(id, kind, body, created_at) VALUES (?, ?, ?, ?)",
            (note_id, kind, body, _now()),
        )
    return _json_result({"id": note_id, "kind": kind})


def _tool_notepad_read(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = args.get("kind")
    with _Conn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM notepad WHERE kind=? ORDER BY created_at DESC LIMIT 50",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notepad ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
    return _json_result({"notes": [dict(r) for r in rows]})


# ------------------------------------------------------------------ Phase-C C24: TTL prune


DEFAULT_MEM_TTL_DAYS = 30.0
DEFAULT_NOTEPAD_TTL_DAYS = 30.0


def _resolve_ttl(args: Dict[str, Any], env_var: str, default_days: float) -> float:
    """Resolve a TTL from the call args → env var → default."""
    raw = args.get("ttl_days")
    if raw is not None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"ttl_days must be numeric, got {raw!r}")
    else:
        env_raw = os.environ.get(env_var)
        if env_raw:
            try:
                value = float(env_raw)
            except ValueError:
                value = default_days
        else:
            value = default_days
    if value <= 0:
        raise ValueError(f"ttl_days must be > 0, got {value}")
    return value


def _tool_memory_prune(args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete memory rows whose updated_at is older than ttl_days."""
    ttl_days = _resolve_ttl(args, "OMNI_MEM_TTL_DAYS", DEFAULT_MEM_TTL_DAYS)
    dry_run = bool(args.get("dry_run", False))
    scope = args.get("scope")
    project = _current_project()
    cutoff = _now() - ttl_days * 86400
    with _Conn() as conn:
        if dry_run:
            if scope is not None:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM memory"
                    " WHERE updated_at < ? AND scope=?"
                    " AND project=?",
                    (cutoff, scope, project),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM memory"
                    " WHERE updated_at < ? AND project=?",
                    (cutoff, project),
                ).fetchone()
            deleted = int(row["n"] if row else 0)
        else:
            if scope is not None:
                cur = conn.execute(
                    "DELETE FROM memory WHERE updated_at < ? AND scope=? AND project=?",
                    (cutoff, scope, project),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM memory WHERE updated_at < ? AND project=?",
                    (cutoff, project),
                )
            deleted = cur.rowcount if cur.rowcount is not None else 0
    return _json_result(
        {
            "deleted": deleted,
            "ttl_days": ttl_days,
            "dry_run": dry_run,
            "scope": scope,
        }
    )


def _tool_notepad_prune(args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete notepad rows whose created_at is older than ttl_days."""
    ttl_days = _resolve_ttl(args, "OMNI_NOTEPAD_TTL_DAYS", DEFAULT_NOTEPAD_TTL_DAYS)
    dry_run = bool(args.get("dry_run", False))
    kind = args.get("kind")
    cutoff = _now() - ttl_days * 86400
    with _Conn() as conn:
        if dry_run:
            if kind is not None:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notepad WHERE created_at < ? AND kind=?",
                    (cutoff, kind),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notepad WHERE created_at < ?",
                    (cutoff,),
                ).fetchone()
            deleted = int(row["n"] if row else 0)
        else:
            if kind is not None:
                cur = conn.execute(
                    "DELETE FROM notepad WHERE created_at < ? AND kind=?",
                    (cutoff, kind),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM notepad WHERE created_at < ?",
                    (cutoff,),
                )
            deleted = cur.rowcount if cur.rowcount is not None else 0
    return _json_result(
        {
            "deleted": deleted,
            "ttl_days": ttl_days,
            "dry_run": dry_run,
            "kind": kind,
        }
    )


def _tool_shared_memory_write(args: Dict[str, Any]) -> Dict[str, Any]:
    key = args["key"]
    body = args["body"]
    with _Conn() as conn:
        conn.execute(
            "INSERT INTO shared_memory(key, body, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
            (key, json.dumps(body) if not isinstance(body, str) else body, _now()),
        )
    return _json_result({"key": key, "ok": True})


def _tool_shared_memory_read(args: Dict[str, Any]) -> Dict[str, Any]:
    key = args.get("key")
    with _Conn() as conn:
        if key:
            row = conn.execute(
                "SELECT * FROM shared_memory WHERE key=?", (key,)
            ).fetchone()
            return _json_result(dict(row) if row else {"error": "not found"})
        rows = conn.execute(
            "SELECT key, updated_at FROM shared_memory ORDER BY updated_at DESC"
        ).fetchall()
    return _json_result({"entries": [dict(r) for r in rows]})


def _tool_trace_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = args.get("id")
    with _Conn() as conn:
        if trace_id:
            row = conn.execute("SELECT * FROM trace WHERE id=?", (trace_id,)).fetchone()
            return _json_result(dict(row) if row else {"error": "not found"})
        rows = conn.execute(
            "SELECT * FROM trace ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    return _json_result({"traces": [dict(r) for r in rows]})


def _tool_trace_timeline(args: Dict[str, Any]) -> Dict[str, Any]:
    observation = args.get("observation")
    with _Conn() as conn:
        if observation:
            rows = conn.execute(
                "SELECT * FROM trace WHERE observation LIKE ? ORDER BY created_at",
                (f"%{observation}%",),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM trace ORDER BY created_at").fetchall()
    return _json_result({"timeline": [dict(r) for r in rows]})


# ------------------------------------------------------------------ registry


TOOLS: Dict[str, Dict[str, Any]] = {
    "health": {
        "description": "Check server health and environment.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": _tool_health,
    },
    "doctor": {
        "description": "Diagnose Copilot Omni installation (python, sqlite, omni_home).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": _tool_doctor,
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
        "description": "Export memory entries (optionally filtered by scope).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "handler": _tool_memory_export,
    },
    "lsp_hover": {
        "description": (
            "Best-effort LSP hover query; skipped when no LSP server on PATH. "
            "Phase-C C18 knowledge layer."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "ls_binary": {"type": "string"},
                "path": {"type": "string"},
                "line": {"type": "integer"},
                "character": {"type": "integer"},
            },
        },
        "handler": _tool_lsp_hover,
    },
    "lsp_goto_definition": {
        "description": (
            "Best-effort LSP go-to-definition; skipped when no LSP server on PATH."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "ls_binary": {"type": "string"},
                "path": {"type": "string"},
                "line": {"type": "integer"},
                "character": {"type": "integer"},
            },
        },
        "handler": _tool_lsp_goto_definition,
    },
    "lsp_find_references": {
        "description": (
            "Best-effort LSP find-references; skipped when no LSP server on PATH."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "ls_binary": {"type": "string"},
                "path": {"type": "string"},
                "line": {"type": "integer"},
                "character": {"type": "integer"},
            },
        },
        "handler": _tool_lsp_find_references,
    },
    "ast_grep_search": {
        "description": (
            "Structural code search via ast-grep; skipped when binary not on PATH."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "lang": {"type": "string"},
            },
        },
        "handler": _tool_ast_grep_search,
    },
    "ast_grep_replace": {
        "description": (
            "Structural code rewrite via ast-grep; skipped when binary not on PATH."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["pattern", "replacement"],
            "properties": {
                "pattern": {"type": "string"},
                "replacement": {"type": "string"},
                "path": {"type": "string"},
                "lang": {"type": "string"},
            },
        },
        "handler": _tool_ast_grep_replace,
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
        "description": "Persist mode state (autopilot, ralph, ultrawork, team, router, etc.).",
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
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": _tool_wiki_list,
    },
    "wiki_ingest": {
        "description": (
            "Append a wiki page with SHA-256-based content de-duplication. "
            "Re-ingesting identical body returns deduped=true without a write. "
            "Slug auto-derived from title when omitted."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["body"],
            "properties": {
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": _tool_wiki_ingest,
    },
    "wiki_graph": {
        "description": (
            "Return the wiki knowledge graph: {nodes, edges, dangling}. "
            "Edges are derived from [[wiki-link]] and relative Markdown links."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": _tool_wiki_graph,
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
    "memory_prune": {
        "description": (
            "Delete memory rows older than ttl_days (default 30, or "
            "OMNI_MEM_TTL_DAYS). Optional scope filter. dry_run=true returns "
            "a count without deleting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ttl_days": {"type": "number"},
                "scope": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
        },
        "handler": _tool_memory_prune,
    },
    "notepad_prune": {
        "description": (
            "Delete notepad rows older than ttl_days (default 30, or "
            "OMNI_NOTEPAD_TTL_DAYS). Optional kind filter. dry_run=true "
            "returns a count without deleting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ttl_days": {"type": "number"},
                "kind": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
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
}
# NOTE: subtask and workspace tools were removed (CHANGELOG 2.0.0 §Breaking Changes).
# They are no longer registered or callable.


# ------------------------------------------------------------------ schema validation dispatch

_sv_path = Path(__file__).parent / "schema_validator.py"
_sv_spec = _importlib_util.spec_from_file_location("schema_validator", _sv_path)
_sv_mod = _importlib_util.module_from_spec(_sv_spec)  # type: ignore[arg-type]
_sv_spec.loader.exec_module(_sv_mod)  # type: ignore[union-attr]
_schema_validate = _sv_mod.validate  # type: ignore[attr-defined]


def _validate_tool_input(
    name: str, spec: Dict[str, Any], args: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Validate args against the tool's inputSchema. Return error dict or None."""
    schema = spec.get("inputSchema")
    if not schema:
        return None
    errors = _schema_validate(args, schema)
    if not errors:
        return None
    error_list = [{"pointer": ptr, "message": msg} for ptr, msg in errors]
    return {
        "code": -32602,
        "message": f"invalid params for tool '{name}'",
        "data": {"errors": error_list},
    }


# ------------------------------------------------------------------ JSON-RPC


def _rpc_response(
    rpc_id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
        return _rpc_response(
            rpc_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        tools = []
        for name, spec in TOOLS.items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["inputSchema"],
                }
            )
        return _rpc_response(rpc_id, {"tools": tools})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if not spec:
            return _rpc_response(
                rpc_id, error={"code": -32601, "message": f"unknown tool: {name}"}
            )
        # Validate input schema before dispatching.
        validation_error = _validate_tool_input(name, spec, args)
        if validation_error:
            return _rpc_response(rpc_id, error=validation_error)
        try:
            result = spec["handler"](args)
            return _rpc_response(rpc_id, result)
        except Exception as exc:
            error = _sanitize_error(exc, name)
            return _rpc_response(rpc_id, error=error)
    if method == "ping":
        return _rpc_response(rpc_id, {})
    if method == "shutdown":
        return _rpc_response(rpc_id, {})

    if rpc_id is None:
        return None
    return _rpc_response(
        rpc_id, error={"code": -32601, "message": f"unknown method: {method}"}
    )


def _write_response(stdout, resp: Any, framed: bool) -> None:
    payload = json.dumps(resp)
    if framed:
        body = payload.encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        stdout.buffer.write(header)
        stdout.buffer.write(body)
        stdout.buffer.flush()
    else:
        stdout.write(payload + "\n")
        stdout.flush()


def _read_framed_message(stdin) -> Optional[str]:
    """Read one Content-Length framed message from stdin.buffer.

    Returns the raw JSON body string, or None on EOF.
    Returns an empty string if the frame could not be parsed (caller continues).
    """
    buf = stdin.buffer
    headers: Dict[str, str] = {}
    # Read header lines until blank line.
    while True:
        line = buf.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            name, _, value = line.decode("ascii").partition(":")
            headers[name.strip().lower()] = value.strip()
        except Exception:
            return ""
    length_str = headers.get("content-length")
    if not length_str:
        return ""
    try:
        length = int(length_str)
    except ValueError:
        return ""
    body = buf.read(length)
    if not body:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _peek_line_framed(stdin) -> Optional[str]:
    """Peek the next non-empty line. Returns None on EOF."""
    while True:
        line = stdin.buffer.readline()
        if not line:
            return None
        text = line.decode("utf-8", errors="replace")
        if text.strip():
            return text


def _serve() -> int:
    """Serve MCP over stdio, accepting BOTH transports transparently:

    - Newline-delimited JSON (one message per line, used by Copilot CLI beta).
    - Content-Length framed JSON (LSP-style, used by reference MCP clients).

    We detect framing by sniffing the first non-empty line: if it starts with
    ``Content-Length:`` we enter framed mode for the rest of the session.
    """
    stdout = sys.stdout
    stdin = sys.stdin
    framed = False

    first = _peek_line_framed(stdin)
    if first is None:
        return 0
    if first.lower().startswith("content-length"):
        framed = True
        # Re-read the header block starting from `first`.
        headers: Dict[str, str] = {}
        name, _, value = first.partition(":")
        headers[name.strip().lower()] = value.strip()
        while True:
            line = stdin.buffer.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            try:
                nm, _, vl = line.decode("ascii").partition(":")
                headers[nm.strip().lower()] = vl.strip()
            except Exception:
                pass
        length_str = headers.get("content-length", "0")
        try:
            length = int(length_str)
        except ValueError:
            length = 0
        body = stdin.buffer.read(length) if length else b""
        raw_messages = [body.decode("utf-8", errors="replace")] if body else []
    else:
        raw_messages = [first.strip()]

    def _dispatch(raw: str) -> None:
        if not raw.strip():
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(msg, list):
            responses = [_handle(m) for m in msg]
            out = [r for r in responses if r is not None]
            if out:
                _write_response(stdout, out, framed)
            return
        resp = _handle(msg)
        if resp is not None:
            _write_response(stdout, resp, framed)

    for raw in raw_messages:
        _dispatch(raw)

    while True:
        if framed:
            raw = _read_framed_message(stdin)
            if raw is None:
                return 0
            _dispatch(raw)
        else:
            line = stdin.readline()
            if not line:
                return 0
            _dispatch(line.strip())


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
