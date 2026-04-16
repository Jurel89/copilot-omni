# WS8 + WS8b Completion Report

**Branch:** `phase-b/wave-2/WS8-mcp-hardening`
**Date:** 2026-04-16
**Status:** COMPLETE — all acceptance gates green

---

## 1. Validator Design (JSON Schema Subset)

**File:** `mcp/schema_validator.py` — 226 LOC (including blank lines and comments)

### Supported subset
| Keyword | Notes |
|---|---|
| `type` | object, string, integer, number, boolean, array, null; also list-of-types |
| `properties` | per-property recursive validation |
| `required` | missing field → pointer + message |
| `enum` | exact membership check |
| `additionalProperties` | `false` blocks extras; dict schema validates extra values |
| `items` | per-element recursive validation |
| `minItems` / `maxItems` | array length bounds |
| `minLength` / `maxLength` | string length bounds |
| `pattern` | compiled regex (cached in `_PATTERN_CACHE`) |
| `minimum` / `maximum` | numeric bounds |
| `oneOf` | exactly-one match, terminal combinator |
| `anyOf` | at-least-one match, terminal combinator |

### Returns
`List[Tuple[json_pointer, error_message]]` — empty = valid.

### Wire-up
`_validate_tool_input()` in `mcp/server.py` runs before every `tools/call` dispatch.
Bad input → JSON-RPC error code **-32602** with `data.errors` list.

### Testing strategy
- 11 bad-input cases in `tests/test_mcp_schema_validation.py`
- 6 good-input (false-positive) cases
- Covers: type mismatch, missing required, enum violation, additionalProperties, array items

---

## 2. Migration Framework + SCHEMA_VERSION=2

**Changed in:** `mcp/server.py`

### Framework design
- `MIGRATIONS: List[Tuple[int, str]]` — ordered list of `(target_version, sql)` tuples
- `_migrate(conn)` drives from the list; wrapped in `_MIGRATE_LOCK` for thread safety
- Each migration is applied only if `current < target_version`
- `ALTER TABLE` idempotency: catches `OperationalError("duplicate column name")` for concurrent pool connections
- Newer-DB guard: if `db.schema_version > SCHEMA_VERSION` → `RuntimeError` at startup

### SCHEMA_VERSION=2 migration
```sql
ALTER TABLE state ADD COLUMN session_id TEXT;
```
- **Purpose:** unblocks WS3 router state slot and WS5b session threading
- NULLable column (additive-only, per ADR-0010 discipline)
- No FK constraint in Phase B (TODO Phase C)

### Tests
- `tests/test_mcp_migration.py`: v1→v2 migration, fresh-DB=v2, newer-DB guard

---

## 3. Connection Pool Design

**Changed in:** `mcp/server.py`

### Design
- Module-level `_POOL_IDLE: List[sqlite3.Connection]` + `_POOL_ACTIVE: int`
- `threading.Condition(_POOL_LOCK)` for blocking when at cap
- `_POOL_MAX = 4` — matches spec
- `_pool_acquire()` / `_pool_release()` pair; `_Conn` context manager wraps both
- `check_same_thread=False` on connection creation (required for pool reuse across threads)
- `atexit.register(_pool_close_all)` for clean shutdown

### Benchmark (informal, from pool test)
- 5 threads × 100 writes = 500 operations, 0 errors, ~0.3s elapsed in test suite
- Pool idle count > 0 after sequential use (reuse confirmed)

---

## 4. Exception Sanitization

**Helper:** `_sanitize_error(exc, tool_name)` in `mcp/server.py`

### Before (original)
```python
except Exception as exc:
    return _rpc_response(rpc_id, error={"code": -32000, "message": str(exc)})
```
`str(exc)` could contain full filesystem paths, env var values, or traceback text.

### After
```python
except Exception as exc:
    error = _sanitize_error(exc, name)
    return _rpc_response(rpc_id, error=error)
```

`_sanitize_error`:
- Logs full `traceback.format_exc()` to stderr (operator-visible)
- Applies `_looks_sensitive()` heuristic: blocks messages containing `/path/...`, `VAR=`, `Traceback (`
- Returns `{"code": -32000, "message": "<tool>: <short reason>", "data": {"tool": "<name>"}}`

### Tests
`tests/test_mcp_sanitization.py` — 7 integration cases + 2 unit tests on `_sanitize_error` directly.

---

## 5. Dead Tools Deleted

Baseline: **30 tools**. Current: **22 tools**. Reduction: **8 tools removed**.

| Tool | Last-known callers | Disposition |
|---|---|---|
| `memory_export` | None (0 refs outside tests+server) | DELETED |
| `memory_prune` | None (0 refs) | DELETED |
| `session_search` | None (0 refs) | DELETED |
| `resume_context` | None (0 refs) | DELETED |
| `support_bundle` | None (0 refs) | DELETED |
| `config_resolve` | None (0 refs) | DELETED |
| `notepad_prune` | None (0 refs) | DELETED |
| `artifact_read` | None (0 refs) | DELETED |
| `run_status` | `tests/test_mcp_server.py` (1 ref) | `# UNUSED-OUTSIDE-TESTS` |
| `artifact_write` | `tests/test_security.py` (4 refs) | `# UNUSED-OUTSIDE-TESTS` |

Handlers for deleted tools also removed. Dead-import cleanup: `shutil` moved top-level; inline `import traceback`, `import shutil`, `import importlib.util` eliminated.

---

## 6. mode=router State Slot

The `state` table now accepts `mode="router"` for WS3's router decision artifact.

**Body schema:**
```json
{
  "prompt_excerpt": "<string: first 200 chars of prompt>",
  "classifier_score": "<number: 0.0–1.0>",
  "decision": "<string: route name>",
  "redirect_to": "<string | null>",
  "ts": "<number: Unix timestamp>"
}
```

Documented in `docs/STATE_CONTRACT.md`. Demonstrated in `tests/test_mcp_schema_validation.py::TestGoodInputsPassThrough::test_state_family_happy_path` which writes `mode="router"` and reads it back.

---

## 7. ADR-0007 Summary + state-canonical Validator

**ADR:** `docs/ADR/ADR-0007-state-store-ownership.md`

### Canonical stores
- MCP SQLite `omni.db`: memory, artifacts (mirror), runs, state, wiki, notepad, shared_memory, trace, sessions
- Filesystem-only: `.omni/plans/`, `.omni/research/`, `.omni/specs/`, `.omni/audit/`, `.omni/deferred/`, `.omni/cache/`, `.omni/workspaces/`

### Split-brain found and resolved
| Data class | Split | Resolution |
|---|---|---|
| Run artifacts | SQLite mirror + filesystem | Canonical = filesystem; SQLite is derived index |
| Plan artifacts | Skills write filesystem + artifact_write | Canonical = filesystem; redundant calls are safe |

### Validator: `check_state_store_canonical`
- **File:** `scripts/verify_plugin_contract.py`
- **Logic:** Scans Python files under `scripts/`, `hooks/`, `mcp/` for SQL write statements (INSERT/UPDATE/DELETE/REPLACE) targeting MCP-owned tables. Any match outside `mcp/server.py` is a split-brain violation.
- **Skills excluded:** `.md` files call MCP tools by name (correct API usage) and are not scanned.
- **Result:** 0 violations on current codebase.

---

## 8. Test Count Delta

| Suite | Before | After | Delta |
|---|---|---|---|
| All tests | 70 | 103 | +33 |
| `test_mcp_schema_validation` | 0 | 17 | +17 |
| `test_mcp_migration` | 0 | 4 | +4 |
| `test_mcp_pool` | 0 | 3 | +3 |
| `test_mcp_sanitization` | 0 | 9 | +9 |

---

## 9. Final Acceptance Gate Output

```
python3 scripts/verify_plugin_contract.py --all  → EXIT 0
  [ok] rename, rename-stub, no-claude-primitives, writable-frontmatter,
       frontmatter-schema, skill-agent-refs, command-refs, mcp-tool-refs,
       exemption-budget, stdlib-only-imports, state-store-canonical

python3 -m pytest -q                             → 103 passed
python3 scripts/discovery_smoke.py --probe layout → PASS (skills=29, agents=19, cmds=8)
python3 scripts/mcp_smoke.py                     → PASS: 22 tools, 5 responses OK
python3 -c "import mcp.server"                   → no errors
Tool count: 30 → 22 (reduced by 8)
```

---

## 10. Handoff Notes

### WS3 (router)
- Call `state_write` with `mode="router"` and body `{prompt_excerpt, classifier_score, decision, redirect_to, ts}`
- Read back with `state_read` `mode="router"` to inspect the routing decision
- See `docs/STATE_CONTRACT.md` for full schema

### WS5a (subagent.py / session threading)
- `state.session_id` column now exists (nullable TEXT, SCHEMA_VERSION=2)
- When calling `state_write`, pass `session_id` in the body or extend the schema to write it directly
- See `docs/STATE_CONTRACT.md` → "session_id Column" section

---

## TODO Phase C

- Re-introduce `memory_prune` and `notepad_prune` with TTL-based cleanup
- Add FK constraint on `state.session_id` → `sessions.id`
- Deprecate SQLite `artifacts` mirror in `artifact_write` (canonical = filesystem)
- Remove `artifact_write` and `run_status` tools if still UNUSED-OUTSIDE-TESTS at Phase C gate
