# Phase-B Wave 3 — Code Review

## 0. Verdict: COMMENT — merge acceptable with follow-up for MEDIUMs

No CRITICAL blockers. 2 HIGH issues should be addressed. Multiple MEDIUM/LOW for robustness.

## 1. Critical Bugs

None.

## 2. Major Issues

**[HIGH] Shell injection in `_TmuxWorkerHost.launch`** — `scripts/omni_team.py:364-375`. f-string interpolates `prompt` + `skill` + `session_arg` into `tmux send-keys` command. `json.dumps` adds quotes but NOT shell-escapes. Prompt with `$(...)` or backticks executes. Fix: `shlex.quote()` on every interpolation OR build argv + `shlex.join()`.

**[HIGH] FDs closed before subprocess exits** — `scripts/omni_team.py:274-282`. `with open(...)` context closes `fout`/`ferr` as `with` exits; subprocess inherits via dup but behavior not guaranteed across platforms. Fragile. Fix: open without `with`, store handles alongside proc; or `subprocess.DEVNULL` + redirect inside cmd.

## 3. Minor Issues

- **[MEDIUM] `_PLUGIN_ROOT` falsy-Path bug** — `hooks/session_start.py:61`, `hooks/user_prompt_submit.py:76`. `Path("")` is truthy, so `or` fallback never triggers.
- **[MEDIUM] `measure_coverage.py` 100%/0 bug** — `scripts/measure_coverage.py:182-183`. Report `pct=0.0` or `status="unmeasured"`.
- **[MEDIUM] `_sanitize_name` imports `re` per-call** — `scripts/omni_worktree.py:62`. Hoist to module top.
- **[MEDIUM] Windows `lock_fd` leaks** — `hooks/_hook_lib.py:182-210`. Inner `except OSError` may return without closing. Single outer `try/finally`.
- **[MEDIUM] `collect_results` ignores pytest RC** — `scripts/measure_coverage.py:269`. Check `run_result.returncode != 0` and warn.
- **[MEDIUM] `_poll_status_paths` stringifies paths** — `scripts/omni_team.py:939`. Use `p.resolve()` or keep Paths.
- **[LOW] Module-level exit in hooks** — `hooks/session_start.py:40-43`. Un-importable for tests. Wrap in `if __name__ == "__main__":` or move into `main()`. Same for all 4 hooks.
- **[LOW] `_pool_cap` regex reads whole file** — `hooks/session_start.py:126-137`. Cached so not a perf issue, but brittle.
- **[LOW] `cancel.signal` non-atomic write** — `scripts/omni_team.py:737`. Mid-write kill leaves partial JSON. Use `_write_json_atomic` or check existence only.
- **[LOW] `_TmuxWorkerHost.launch` returns 0 unconditionally** — `scripts/omni_team.py:378`. Caller at line 588 marks all tmux workers "failed" immediately.
- **[LOW] Duplicate `import importlib.util`** — `hooks/user_prompt_submit.py:61,68`. Consolidate.
- **[LOW] Hardcoded path resolution in `_load_config`** — `hooks/user_prompt_submit.py:178`. Use `_PLUGIN_ROOT`.

## 4. Style and Consistency

- Consistent stdlib-only imports, PEP 8 naming, `from __future__ import annotations`, docstrings.
- All 4 hooks follow same pattern (good).
- `_load_module` / `_load_worktree_mod` / `_load_wait_mod` pattern consistent across `omni_team.py`.
- `shutil` imported both at module level and locally as `_shutil` in `omni_team.py` — dead re-import.
- Test files mix pytest classes + `unittest.TestCase` — transitional, should converge.

## 5. Performance

- `_build_trigger_map` reads all SKILL.md per hook invocation — ~20ms for 30 skills, within 100ms budget. Cache if skill count grows.
- `_repo_root()` spawns `git rev-parse` per call in `omni_worktree.py:27`. Functions like add/remove/list each call it — redundant subprocesses.
- `_mcp_write_best_effort` opens new SQLite conn per call — N+1 during dispatch.
- No O(N²) patterns.

## 6. Robustness Gaps

- Read-only FS: hooks graceful; `omni_team.py:737` cancel.signal NOT guarded → raise.
- Missing `copilot`/`tmux` binaries: handled (FAKE for tests; RuntimeError + subprocess fallback).
- SIGTERM mid-write: `_write_json_atomic` leaves `.tmp` file (benign).
- Missing env vars: `.get()` with defaults everywhere. No KeyError risk.

## 7. Security Findings

**[HIGH]** Shell injection in tmux construction — see Major #1.
**[LOW]** `pre_tool_use.py:211` protected-path uses substring match — defense-in-depth, over-deny direction safe.
**[LOW]** Audit log path from `os.getcwd()` — unexpected cwd → audit gaps.

No hardcoded secrets. No SQL injection (parameterized `_mcp_write_best_effort`). No path traversal beyond substring match. `shlex.split` fix in `pre_tool_use.py` handles unclosed-quote injection correctly.

## 8. Test Quality

- **`test_omni_team.py`** (18): strong happy-path + edge coverage. Missing: tmux host path, poll timeout=124 branch.
- **`test_omni_worktree.py`** (7): uses real git repo fixture (excellent). Missing: `_sanitize_name` special chars.
- **`test_hooks_banner.py`** (11): good cache coverage. `test_cache_invalidated_on_tree_change` weak assertion (banner valid ≠ cache invalidated).
- **`test_hooks_kill_switch.py`** (20): thorough 5×4 matrix via subprocess.
- **`test_hooks_audit_logging.py`** (10): 20-thread × 5-record concurrency test with exact line count (strong invariant).
- **`test_hooks_lib_gaps.py`** (11): documents a gap where `_write_metric` does NOT catch `_atomic_append` errors, only serialization.
- **`test_migrate_v1_to_v2.py`** (13): clean 3-case structure. Missing: `_git_mv` path (tmp_path not a git repo).
- **`test_integration_phase_b.py`** (8): good cross-wave smokes. Uses FAKE appropriately.
- **`test_omni_team_gaps.py`** (11): gap-fill for cleanup edges, Windows branches.

## 9. API Consistency

`omni_team.py` return shapes:
- `create_team` / `dispatch_workers` / `cleanup_team` — consistent dict shapes
- `cancel_team` — returns `None` while peers return dicts (inconsistency)
- `status_team` — error path drops fields (inconsistent with success shape)
- `collect_results` — adds `rc` field not in other shapes

`measure_coverage.py`: 100%/0-statements JSON output is a schema-level bug.

## 10. Top 10 Line-Level Edits

1. `omni_team.py:364-375` — shell-quote all tmux interpolations.
2. `session_start.py:61`, `user_prompt_submit.py:76` — fix `_PLUGIN_ROOT` falsy-Path.
3. `measure_coverage.py:182-183` — `pct=0.0` + `status="unmeasured"` when `total==0`.
4. `_hook_lib.py:182-210` — single outer `try/finally` for Windows `lock_fd`.
5. `omni_team.py:378` — non-zero sentinel from `_TmuxWorkerHost.launch`.
6. `omni_team.py:737` — wrap `cancel.signal` in try/except or use atomic helper.
7. `omni_worktree.py:62` — hoist `import re` to module top.
8. `omni_team.py:815` — drop redundant `import shutil as _shutil`.
9. `measure_coverage.py:269` — warn on pytest non-zero exit.
10. `user_prompt_submit.py:178` — use `_PLUGIN_ROOT` for config lookup.
