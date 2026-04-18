# STATE_CONTRACT.md — MCP State Table Contract

Canonical contract for the MCP `state` table and the `state_write` /
`state_read` / `state_clear` tools that operate on it.

---

## 1. Schema

**Current version:** `SCHEMA_VERSION = 6`.

```sql
CREATE TABLE state (
    mode       TEXT NOT NULL,
    body       TEXT NOT NULL,             -- JSON payload
    session_id TEXT NOT NULL DEFAULT '',  -- '' for session-agnostic rows
    updated_at REAL NOT NULL,             -- Unix timestamp
    PRIMARY KEY (mode, session_id)
);
CREATE UNIQUE INDEX idx_state_mode_session ON state(mode, session_id);
```

Each `(mode, session_id)` combination addresses exactly one row. The
empty-string session slot (`session_id = ''`) is the default, legacy,
"global-by-mode" row.

### Migrations that shaped this

| Version | Change |
|---------|--------|
| 1       | Initial `state(mode PRIMARY KEY, body, updated_at)` |
| 2       | Add nullable `session_id` column |
| 3       | Add expression index `UNIQUE(mode, COALESCE(session_id, ''))` |
| 5       | Normalize NULL session_id rows to `''` |
| 6       | Rebuild table with composite `PRIMARY KEY(mode, session_id)`, plain `UNIQUE(mode, session_id)` index |

---

## 2. Tool contract

### `state_write(mode, body, session_id?)`

- Upserts a row keyed by `(mode, session_id or '')`.
- `session_id` is optional. When omitted, writes the default empty-session row.

### `state_read(mode?, session_id?, list?)`

Back-compat preserved so pre-schema-v6 callers see no shape change:

| Args                         | Result shape |
|------------------------------|--------------|
| `mode` only                  | the default empty-session row: `{mode, session_id:"", body, updated_at}` |
| `mode + session_id`          | that specific row |
| neither `mode` nor `list`    | `{modes: [{mode, updated_at}, ...]}` — only empty-session rows (legacy listing) |
| `list=true`                  | `{rows: [{mode, session_id, updated_at}, ...]}` — full enumeration |

### `state_clear(mode?, session_id?, all?)`

| Args                         | Effect |
|------------------------------|--------|
| `mode + session_id`          | delete one row |
| `mode` only                  | delete all rows for that mode across sessions |
| `session_id` only            | delete all rows for that session across modes |
| `all=true`                   | wipe every row |

At least one of `mode`, `session_id`, or `all=true` must be set.

---

## 3. Session scoping discipline

Each registered mode is either **session-scoped** or **global**:

- **Session-scoped** modes should always receive the current
  `OMNI_SESSION_ID`. Example: `ralph`, `ultrawork`, `team` — each worker
  run is distinct from another on a shared machine.
- **Global** modes intentionally omit `session_id` (empty string) so the
  value is shared across sessions. Example: `subagent` (per-job key is
  embedded in the mode string, so there is no cross-session conflict).

`docs/STATE_MODES.md` marks each registered mode with its session scope.
Callers that mix scopes get unpredictable overlap; the validator warns.

---

## 4. Invariants

1. `session_id` is never NULL in schema v6+; callers pass `""` for global rows.
2. `(mode, session_id)` is unique per row.
3. `body` is always a valid JSON object.
4. `updated_at` is a Unix float timestamp set at write time.
5. `state_clear` always reports the number of rows deleted.
6. External MCP consumers that followed the pre-v6 contract (no `session_id`, `mode`-keyed reads) continue to work unchanged against the empty-session slot.

---

## 5. Cancel contract

Cancellation for a running skill uses two layers:

1. **Process signal:** `scripts/cancel_signal.py` writes `.omni/runs/<run-id>/cancel.signal`.
2. **State invalidation:** orchestrators call
   `state_clear(session_id="$OMNI_SESSION_ID")` to wipe all session-scoped
   state rows in one pass, or target a specific mode with
   `state_clear(mode="ralph", session_id="$OMNI_SESSION_ID")`.

Skills that want to discover which modes are active for the current
session before clearing should call
`state_read(list=true)` and filter by `session_id`.
