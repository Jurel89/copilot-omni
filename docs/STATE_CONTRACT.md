# STATE_CONTRACT.md — MCP State Table Contract

This document defines the contract for the MCP `state` table and all mode slots used by Copilot Omni skills and agents.

## Overview

The `state` table in `$OMNI_HOME/omni.db` is the canonical store for runtime mode state. Each row represents one named mode slot. Writes are via `state_write`, reads via `state_read`, and clears via `state_clear`.

**Schema (SCHEMA_VERSION=2):**

```sql
CREATE TABLE state (
    mode       TEXT PRIMARY KEY,
    body       TEXT NOT NULL,       -- JSON payload
    updated_at REAL NOT NULL,       -- Unix timestamp
    session_id TEXT                 -- nullable; links state to a session
);
```

---

## Mode Slots

### Existing Modes

| Mode | Owner skill/agent | Body schema |
|---|---|---|
| `autopilot` | skills/autopilot | `{active: bool, phase: string, ts: float}` |
| `ralph` | skills/ralph | `{active: bool, task: string, ts: float}` |
| `ultrawork` | skills/ultrawork | `{active: bool, task: string, ts: float}` |
| `team` | skills/team | `{active: bool, team_id: string, ts: float}` |

### mode=router (WS3 Router Decision Slot)

**Purpose:** WS3's router skill writes its classification/decision artifact here so downstream skills can inspect the routing decision without re-running the classifier.

**Mode value:** `"router"`

**Body schema:**

```json
{
  "prompt_excerpt": "<string: first 200 chars of the user prompt>",
  "classifier_score": "<number: 0.0–1.0, confidence of the selected route>",
  "decision": "<string: the selected route name, e.g. 'autopilot', 'ralph', 'direct'>",
  "redirect_to": "<string | null: target skill or agent if decision=redirect, else null>",
  "ts": "<number: Unix timestamp of the decision>"
}
```

**Example:**

```json
{
  "prompt_excerpt": "Run autopilot on this task",
  "classifier_score": 0.92,
  "decision": "autopilot",
  "redirect_to": null,
  "ts": 1713225600.0
}
```

**Lifecycle:**
- Written by WS3 router at the start of each routing decision.
- Read by orchestrators and skills to avoid re-routing.
- Cleared by `state_clear` with `mode="router"` at session end or on explicit reset.

**Handoff for WS3:**
- WS3 router skill should call `state_write` with `mode="router"` and the body above.
- Downstream skills call `state_read` with `mode="router"` to inspect the decision before proceeding.

---

## session_id Column

`state.session_id` (added in SCHEMA_VERSION=2) is an optional nullable field that links a state row to a session in the `sessions` table. It is populated by WS5b's session-threading logic.

**Handoff for WS5a:**
- `scripts/subagent.py` should populate `session_id` when calling `state_write` so that state rows can be scoped to a session lifecycle.
- The value should be the current session ID from the `sessions` table.

---

## Invariants

1. `mode` is the primary key — each mode has exactly one row.
2. `body` is always a valid JSON object (never a bare scalar).
3. `updated_at` is always a Unix float timestamp set by `state_write`.
4. `session_id` may be NULL — callers that don't use session threading omit it.
5. No FK constraint is declared in Phase B (Phase C TODO).
