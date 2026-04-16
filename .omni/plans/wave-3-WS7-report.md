# WS7 Completion Report — Hook/Trigger Hardening

**Branch:** `phase-b/wave-3/WS7-hooks-hardening`
**Date:** 2026-04-16
**Status:** Complete

---

## 1. Hardening Items Status

| # | Item | Status | File(s) |
|---|---|---|---|
| A1 | Kill switches (5 vars, 4 hooks, shared helper) | DONE | `hooks/_hook_lib.py`, all 4 hooks |
| A2 | shlex fallback → fail-safe single-token | DONE | `hooks/pre_tool_use.py:94-104` |
| A3 | Atomic audit logging with file-lock | DONE | `hooks/_hook_lib.py:_atomic_append`, `_append_audit` |
| A4 | Cross-platform launch_python.py simplification | SKIPPED — file not present in this codebase | — |
| A5 | Frontmatter-aware skill trigger hints | DONE | `hooks/user_prompt_submit.py:_build_trigger_map`, `_match_skill_triggers` |
| A6 | Deprecation warnings for legacy OMC vars | DONE | `hooks/_hook_lib.py:_deprecation_warn`, sentinel de-dup | <!-- omni-rename-allow: OMC is the legacy brand name being deprecated -->
| B1 | Session-start banner with cached tree hash | DONE | `hooks/session_start.py:_get_banner`, `_compute_banner` |
| B2 | Metrics writer (`_write_metric`) | DONE | `hooks/_hook_lib.py:_write_metric` |
| B3 | Policy file permission check | DONE | `hooks/session_start.py:_check_policy_permissions` |

Total: **8/9 done** (A4 skipped — prerequisite file absent).

---

## 2. File-Lock Semantics + Benchmark

### POSIX (`fcntl.flock`)
- `flock(LOCK_EX | LOCK_NB)` attempted first (non-blocking).
- On `EWOULDBLOCK`, spins in 50ms increments up to **1 second** budget.
- On budget breach: drops the write, warns to stderr — hook never blocks.
- `flock(LOCK_UN)` in finally block.

### Windows (`msvcrt.locking`)
- Uses a sidecar `.lock` file alongside the log file.
- `locking(fd, LK_NBLCK, 1)` — non-blocking 1-byte lock.
- Same 50ms spin / 1s budget logic as POSIX path.
- `locking(fd, LK_UNLCK, 1)` in finally block.

### Fallback (no locking available)
- Plain `open("a")` — best-effort, no lock. For environments without `fcntl` or `msvcrt`.

### Benchmark (expected)
- Single append under no contention: **< 1ms** (file open + flock + write + unlock).
- 20 threads × 5 writes each (concurrent test): all 100 lines valid JSON, **< 500ms total** on a local disk.
- Audit write adds **< 2ms** to each hook's latency budget.

---

## 3. Banner Cache Hit Rate Expectation

The tree hash is computed from `mtime + size` of three manifest files:
- `.claude-plugin/plugin.json`
- `AGENTS.md`
- `hooks/hooks.json`

**Expected hit rate in normal usage:** > 99% (files rarely change between sessions).

**Cache miss triggers:** any of the three manifest files being written (new skill installs, version bumps, hook updates).

**Cache write:** atomic `Path.write_text()` — single OS write, no lock needed (single writer at session start).

---

## 4. Deprecation Timeline

| Version | Change |
|---|---|
| v2.0.0 | `OMC_SKIP_HOOKS` and `DISABLE_OMC` accepted with one-time stderr warning |
| v3.0.0 | `OMC_SKIP_HOOKS` and `DISABLE_OMC` removed; env vars silently ignored or error |

Migration path: replace `OMC_SKIP_HOOKS=1` → `OMNI_SKIP_HOOKS=1`, `DISABLE_OMC=1` → `DISABLE_OMNI=1`.

---

## 5. Test Count Delta

| Test file | New tests |
|---|---|
| `tests/test_hooks_kill_switch.py` | 22 tests (5 kill-switch combos × 4 hooks + 2 "not active" tests) |
| `tests/test_hooks_audit_logging.py` | 14 tests (atomic append, concurrent, metrics, deprecation warn) |
| `tests/test_hooks_banner.py` | 14 tests (cache hit/miss, format, policy warnings, integration) |
| `tests/test_hooks.py` (modified) | 0 new; 1 updated (`test_banner_includes_version`) |

**Total new tests:** +48 (from 358 → 406+)

---

## 6. Acceptance Gate Results

### Kill-switch acceptance test

```
OMNI_SKIP_HOOKS=1 python3 hooks/user_prompt_submit.py <<< '{"prompt":"test"}'
# stdout: {}  exit: 0  (hook bypassed)

OMC_SKIP_HOOKS=1 python3 hooks/user_prompt_submit.py <<< '{"prompt":"test"}'
# stdout: {}  exit: 0  (hook bypassed)
# stderr: [copilot-omni WARN] OMC_SKIP_HOOKS / DISABLE_OMC are deprecated...
```

### Banned token check

```
git grep -nE '\.omc/|oh-my-claudecode' hooks/
# (no hits)
```

### Banner cache

```
# First call (cache miss): computes + writes .omni/cache/banner.json
# Second call (same tree): reads from cache, returns same banner
```

---

## 7. Residual TODO-Phase-C Items

1. **Unicode NFC/NFD path normalization** (audit finding 2.3): protected path matching does not normalise Unicode. Low priority on Linux; medium on macOS with non-ASCII filenames. Punted to Phase-C.

2. **MCP connection pool** (audit finding 11.2): each tool call opens a new SQLite connection. Phase-C hardening target.

3. **MCP context manager consistency** (audit finding 11.3): some handlers use `_Conn`, some call `.close()` manually. Phase-C cleanup.

4. **Audit log directory permissions** (audit finding 10.4): `.omni/audit/` created with default `0755`. Consider `0700` for sensitive audit data. Phase-C.

5. **Trigger priority / disambiguation** (audit finding 5.1): when multiple skill triggers match, no primary skill is declared. Phase-C UX improvement.

6. **launch_python.py cross-platform shim**: not present in this codebase; no action needed unless Windows CI adds a Python launcher.

---

## 8. Files Changed

| File | Change |
|---|---|
| `hooks/_hook_lib.py` | NEW ~220 LOC: kill-switch, audit, metrics, deprecation-warn |
| `hooks/pre_tool_use.py` | Refactored: use `_hook_lib`, fix shlex fallback, add audit/metrics |
| `hooks/post_tool_use.py` | Refactored: use `_hook_lib` for atomic audit + metrics |
| `hooks/session_start.py` | Rewritten: cached banner, policy permission check, audit/metrics |
| `hooks/user_prompt_submit.py` | Extended: frontmatter trigger map, skill-trigger-hint, audit/metrics |
| `tests/test_hooks.py` | Updated `test_banner_includes_version` for new banner format |
| `tests/test_hooks_kill_switch.py` | NEW: 22 kill-switch tests |
| `tests/test_hooks_audit_logging.py` | NEW: 14 audit/metrics/deprecation tests |
| `tests/test_hooks_banner.py` | NEW: 14 banner/cache/policy tests |
| `docs/HOOK_CONTRACT.md` | NEW: full hook contract reference |
| `CHANGELOG.md` | Added v2.0.0 WS7 entry + v3.0.0 deprecation note |
| `.omni/plans/wave-3-WS7-report.md` | This file |
