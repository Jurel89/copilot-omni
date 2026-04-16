---
id: ADR-0007
title: State Store Ownership Matrix
status: accepted
date: 2026-04-16
deciders: [WS8b]
---

# ADR-0007 — State Store Ownership Matrix

## Context

Copilot Omni uses several persistent stores that have grown organically across Phase A and Phase B. Phase-A audits identified split-brain risk where the same logical data was being written to both the MCP SQLite database (`omni.db`) and the filesystem under `.omni/`. This ADR establishes canonical ownership for each data class, defines the read/write API surface, and sets lifecycle rules.

## Decision

### 1. Canonical Store per Data Class

| Data Class | Canonical Store | Location | API Surface |
|---|---|---|---|
| Agent memory (long-term facts) | MCP SQLite `memory` table | `$OMNI_HOME/omni.db` | `memory_capture`, `memory_search` |
| Run artifacts (specs, plans, reports) | Filesystem + SQLite mirror | `.omni/runs/<run_id>/` + `artifacts` table | `artifact_write` (writes both) |
| Run metadata (status, phase) | MCP SQLite `runs` table | `$OMNI_HOME/omni.db` | `run_status`, `subtask` |
| Skill/mode runtime state | MCP SQLite `state` table | `$OMNI_HOME/omni.db` | `state_write`, `state_read`, `state_clear` |
| Router decision artifacts | MCP SQLite `state` table, mode=`router` | `$OMNI_HOME/omni.db` | `state_write`, `state_read` |
| Wiki entries | MCP SQLite `wiki` table | `$OMNI_HOME/omni.db` | `wiki_write`, `wiki_read`, `wiki_query`, `wiki_list` |
| Notepad entries | MCP SQLite `notepad` table | `$OMNI_HOME/omni.db` | `notepad_write`, `notepad_read` |
| Cross-agent shared memory | MCP SQLite `shared_memory` table | `$OMNI_HOME/omni.db` | `shared_memory_write`, `shared_memory_read` |
| Debug/hypothesis traces | MCP SQLite `trace` table | `$OMNI_HOME/omni.db` | `trace_summary`, `trace_timeline` |
| Session metadata | MCP SQLite `sessions` table | `$OMNI_HOME/omni.db` | `session_search` |
| Plan artifacts | Filesystem only | `.omni/plans/` | Direct file I/O (skills/agents) |
| Research artifacts | Filesystem only | `.omni/research/` | Direct file I/O |
| Spec artifacts | Filesystem only | `.omni/specs/` | Direct file I/O |
| Workspace dirs | Filesystem only | `.omni/workspaces/<name>/` | `workspace` MCP tool |
| Audit logs | Filesystem only | `.omni/audit/` | Direct file I/O |
| Deferred work | Filesystem only | `.omni/deferred/` | Direct file I/O (skills) |
| Cache | Filesystem only | `.omni/cache/` | Direct file I/O |
| Plugin config | Filesystem only | `.omni/config.json` | `config_resolve` (read-only) |

### 2. Read/Write API Surface

**MCP tool API (via `mcp/server.py`):**
- `memory_capture`, `memory_search` — sole writers/readers of `memory` table
- `artifact_write` — writes `artifacts` table AND mirrors to `.omni/runs/<id>/`
- `run_status`, `subtask` — read/write `runs` table
- `state_write`, `state_read`, `state_clear` — sole writers/readers of `state` table
- `wiki_write`, `wiki_read`, `wiki_query`, `wiki_list` — sole writers/readers of `wiki` table
- `notepad_write`, `notepad_read` — sole writers/readers of `notepad` table
- `shared_memory_write`, `shared_memory_read` — sole writers/readers of `shared_memory` table
- `trace_summary`, `trace_timeline` — readers of `trace` table (writers: future WS)
- `workspace` — filesystem create/remove/list under `.omni/workspaces/`

**Filesystem-only stores** (no MCP tool wraps them):
- `.omni/plans/`, `.omni/research/`, `.omni/specs/` — plan/research/spec artifacts written by skills/agents directly
- `.omni/audit/`, `.omni/deferred/`, `.omni/cache/` — operational stores written by skills/hooks

### 3. Lifecycle / Cleanup Rules

Per ADR-0010 (Phase B retention policy): retention is **unbounded for Phase B** with a TODO for Phase C to implement TTL-based cleanup.

| Store | Cleanup trigger |
|---|---|
| `memory` table | Manual via `memory_prune` (removed in WS8; TODO Phase C: reintroduce with TTL) |
| `artifacts` table | Manual; keyed to run lifecycle |
| `runs` table | Manual; keyed to run lifecycle |
| `state` table | `state_clear` per mode or `all=true` |
| `wiki` table | No automated cleanup in Phase B |
| `notepad` table | Manual via `notepad_prune` (removed in WS8; TODO Phase C) |
| `shared_memory` table | No automated cleanup in Phase B |
| `trace` table | No automated cleanup in Phase B |
| `.omni/runs/` | TODO Phase C: cleanup after run TTL |
| `.omni/workspaces/` | `workspace` remove action |
| `.omni/plans/`, `.omni/research/` | Manual; never auto-deleted |

### 4. Cross-Store Referential Integrity

- A `run_id` in the `artifacts` table SHOULD correspond to a directory `.omni/runs/<run_id>/`. However this is a **soft reference** only — the DB record is canonical, and a missing directory is a recoverable inconsistency (mirror may have failed).
- A `session_id` stored in `state.session_id` (added in SCHEMA_VERSION=2) is a soft reference to a `sessions.id`. No FK enforcement in Phase B (foreign_keys=ON applies to the SQLite file, but no FK constraint is declared on this column intentionally — Phase C TODO).
- Plan artifact paths stored in `.omni/plans/` are not registered in the DB; they are tracked by filename convention only.

### 5. Split-Brain Analysis

The following data classes were found to have dual-write patterns or overlap that must be resolved:

| Data Class | Current split | Resolution |
|---|---|---|
| Run artifacts | Written to both `artifacts` table AND `.omni/runs/` by `artifact_write` | **Canonical = filesystem**. SQLite `artifacts` table is a derived index for search. Phase C can deprecate the mirror. |
| Plan artifacts | Skills write directly to `.omni/plans/` AND may call `artifact_write` with kind=plan | **Canonical = filesystem**. `artifact_write` calls for plans are redundant. Phase C TODO: remove artifact_write for plan kind. |
| Plugin config | `.omni/config.json` is read by `config_resolve` tool AND directly by skills | **Canonical = filesystem**. `config_resolve` is read-only; no split-brain. |

### 6. mode=router State Slot

The `state` table's `mode` column now accepts the value `router` for WS3's router decision artifact. The schema for the router body is documented in `docs/STATE_CONTRACT.md`.

## Consequences

- All new code must write to exactly one canonical store per data class.
- `check_state_store_canonical()` in `scripts/verify_plugin_contract.py` guards against future regressions by asserting exactly one writer module per data class.
- Phase C TODO items: implement TTL cleanup, add FK constraint on `state.session_id`, deprecate SQLite mirror in `artifact_write`.
