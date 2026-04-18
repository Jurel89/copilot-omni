"""Session-aware state tool tests (Commit 1 of contract reset).

Covers state_write / state_read / state_clear with session_id, plus the
v4→v6 migration that normalizes NULL session_id rows and swaps the
expression index for a plain composite unique index.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Load mcp/server.py as a module against an isolated OMNI_HOME."""
    monkeypatch.setenv("OMNI_HOME", str(tmp_path))
    # Drop any previously-cached module so migrations re-run against the new DB.
    sys.modules.pop("mcp_server_under_test", None)
    spec = importlib.util.spec_from_file_location(
        "mcp_server_under_test", REPO / "mcp" / "server.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_server_under_test"] = mod
    spec.loader.exec_module(mod)
    # Wipe the connection pool so subsequent tests do not reuse an old DB handle.
    try:
        with mod._POOL_COND:  # type: ignore[attr-defined]
            while mod._POOL_IDLE:
                mod._POOL_IDLE.pop().close()
    except Exception:
        pass
    return mod


def _body_of(result):
    """Pull the JSON body out of the tool wire envelope."""
    return json.loads(result["content"][0]["text"])


def test_write_and_read_without_session_id(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write({"mode": "ralph", "body": {"phase": 1}})
    got = _body_of(srv._tool_state_read({"mode": "ralph"}))
    assert got["mode"] == "ralph"
    assert got["body"] == {"phase": 1}
    assert got["session_id"] == ""


def test_write_and_read_with_session_id(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write(
        {"mode": "ralph", "body": {"phase": 2}, "session_id": "s1"}
    )
    got = _body_of(
        srv._tool_state_read({"mode": "ralph", "session_id": "s1"})
    )
    assert got["body"] == {"phase": 2}
    assert got["session_id"] == "s1"


def test_two_sessions_same_mode_are_isolated(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write(
        {"mode": "team", "body": {"worker": "a"}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "team", "body": {"worker": "b"}, "session_id": "s2"}
    )
    a = _body_of(srv._tool_state_read({"mode": "team", "session_id": "s1"}))
    b = _body_of(srv._tool_state_read({"mode": "team", "session_id": "s2"}))
    assert a["body"] == {"worker": "a"}
    assert b["body"] == {"worker": "b"}


def test_clear_scoped_to_single_row(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 1}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 2}, "session_id": "s2"}
    )
    out = _body_of(
        srv._tool_state_clear({"mode": "ralph", "session_id": "s1"})
    )
    assert out["deleted"] == 1
    # s2 row still present
    b = _body_of(srv._tool_state_read({"mode": "ralph", "session_id": "s2"}))
    assert b["body"] == {"x": 2}


def test_clear_mode_only_targets_empty_session_row(tmp_path, monkeypatch):
    """Legacy `state_clear({"mode": "ralph"})` must scope to the default
    empty-session row. Per-session rows for the same mode must be left
    intact — otherwise a pre-v6 caller can silently wipe an active
    session's state. Codex P1.
    """
    srv = _load_server(tmp_path, monkeypatch)
    # Default empty-session row
    srv._tool_state_write({"mode": "ralph", "body": {"x": "default"}})
    # Per-session rows for the same mode — must survive the legacy clear.
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 1}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 2}, "session_id": "s2"}
    )

    out = _body_of(srv._tool_state_clear({"mode": "ralph"}))
    assert out["deleted"] == 1, (
        "mode-only clear must remove exactly the default row, not all sessions"
    )

    # Default row gone
    default = _body_of(srv._tool_state_read({"mode": "ralph"}))
    assert default["body"] is None

    # Per-session rows still present
    s1 = _body_of(srv._tool_state_read({"mode": "ralph", "session_id": "s1"}))
    s2 = _body_of(srv._tool_state_read({"mode": "ralph", "session_id": "s2"}))
    assert s1["body"] == {"x": 1}
    assert s2["body"] == {"x": 2}


def test_clear_mode_plus_all_purges_every_session(tmp_path, monkeypatch):
    """Opt-in broad purge: `state_clear({"mode": "ralph", "all": True})`
    wipes every session's row for that mode, including the default one.
    """
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write({"mode": "ralph", "body": {"x": "default"}})
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 1}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 2}, "session_id": "s2"}
    )
    srv._tool_state_write(
        {"mode": "team", "body": {"y": 1}, "session_id": "s1"}
    )

    out = _body_of(srv._tool_state_clear({"mode": "ralph", "all": True}))
    assert out["deleted"] == 3  # default + s1 + s2

    # Unrelated mode row untouched
    team = _body_of(srv._tool_state_read({"mode": "team", "session_id": "s1"}))
    assert team["body"] == {"y": 1}


def test_clear_by_session_removes_all_modes_for_that_session(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 1}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "ultrawork", "body": {"x": 2}, "session_id": "s1"}
    )
    srv._tool_state_write(
        {"mode": "ralph", "body": {"x": 3}, "session_id": "s2"}
    )
    out = _body_of(srv._tool_state_clear({"session_id": "s1"}))
    assert out["deleted"] == 2
    remaining = _body_of(
        srv._tool_state_read({"mode": "ralph", "session_id": "s2"})
    )
    assert remaining["body"] == {"x": 3}


def test_list_true_returns_all_scoped_rows(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write({"mode": "ralph", "body": {"x": 1}})
    srv._tool_state_write(
        {"mode": "team", "body": {"x": 2}, "session_id": "s1"}
    )
    got = _body_of(srv._tool_state_read({"list": True}))
    pairs = {(r["mode"], r["session_id"]) for r in got["rows"]}
    assert ("ralph", "") in pairs
    assert ("team", "s1") in pairs


def test_legacy_modes_listing_shape_preserved(tmp_path, monkeypatch):
    """No mode + no list flag → legacy {modes: [...]} shape, empty-session rows only.

    This is the explicit back-compat promise in docs/STATE_CONTRACT.md:
    external MCP consumers that never pass session_id see the exact
    pre-v6 shape. Per-session rows are deliberately excluded from this
    aggregate to prevent cross-session state bleed. `list=true` is the
    discovery path for per-session rows.
    """
    srv = _load_server(tmp_path, monkeypatch)
    srv._tool_state_write({"mode": "ralph", "body": {"x": 1}})
    srv._tool_state_write(
        {"mode": "per-session", "body": {"x": 2}, "session_id": "s1"}
    )
    got = _body_of(srv._tool_state_read({}))
    assert "modes" in got
    mode_names = {r["mode"] for r in got["modes"]}
    # Deliberate: per-session row MUST NOT leak into the legacy listing.
    assert "ralph" in mode_names
    assert "per-session" not in mode_names

    # And list=true IS the documented way to discover per-session rows.
    listed = _body_of(srv._tool_state_read({"list": True}))
    listed_pairs = {(r["mode"], r["session_id"]) for r in listed["rows"]}
    assert ("ralph", "") in listed_pairs
    assert ("per-session", "s1") in listed_pairs


def test_migration_v4_to_v6_normalizes_null_session_id(tmp_path, monkeypatch):
    """Simulate a v4 DB with NULL session_id rows, load server, check normalization."""
    db_path = tmp_path / "omni.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
        INSERT INTO schema_version(version) VALUES (4);
        CREATE TABLE state (
            mode TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            updated_at REAL NOT NULL,
            session_id TEXT
        );
        INSERT INTO state(mode, body, updated_at, session_id)
            VALUES ('ralph', '{"x":1}', 1.0, NULL);
        CREATE UNIQUE INDEX idx_state_mode_session
            ON state(mode, COALESCE(session_id, ''));
        """
    )
    conn.commit()
    conn.close()

    srv = _load_server(tmp_path, monkeypatch)
    # Trigger a migration run via a no-op tool call
    got = _body_of(srv._tool_state_read({"mode": "ralph"}))
    assert got["body"] == {"x": 1}
    assert got["session_id"] == ""

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT session_id FROM state WHERE mode='ralph'"
    ).fetchone()
    assert row[0] == ""  # normalized from NULL
    idx = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND name='idx_state_mode_session'"
    ).fetchone()
    assert idx is not None
    # New plain index — must not contain COALESCE anymore.
    assert "COALESCE" not in (idx[0] or "")
    conn.close()


def test_concurrent_writes_produce_single_row(tmp_path, monkeypatch):
    srv = _load_server(tmp_path, monkeypatch)
    errors = []

    def worker(n):
        try:
            for i in range(20):
                srv._tool_state_write(
                    {
                        "mode": "ralph",
                        "body": {"n": n, "i": i},
                        "session_id": "shared",
                    }
                )
        except Exception as exc:  # pragma: no cover - diagnostic only
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    got = _body_of(
        srv._tool_state_read({"mode": "ralph", "session_id": "shared"})
    )
    assert got["body"] is not None
    # Exactly one row in the unique index
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(tmp_path / "omni.db"))
    n = conn.execute(
        "SELECT COUNT(*) FROM state WHERE mode='ralph' AND session_id='shared'"
    ).fetchone()[0]
    assert n == 1
    conn.close()
