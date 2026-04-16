# Phase-B Wave 2 — Code Review

## 0. Verdict — REQUEST CHANGES

Wave 2 is genuinely substantial work. The core design is sound: WS3 router is small and tested to 40+ cases; WS5a subagent primitive nicely mirrors `Task(subagent_type=...)`; MCP hardening (validator + connection pool + sanitizer) is the kind of plumbing easy to skip and Wave 2 didn't; validator now has 14 checks that actually defend the invariants. Stdlib-only is held throughout. Tests are real, not theatre.

But the work is not green: there are **2 Blocker** issues (one is a security-relevant injection vector, one is a deadlock on the connection pool) and **6 Major** issues that are likely to bite in production within weeks of merge.

Recommendation: address the two Blockers before merge; create issues for Majors and gate them on the next patch release.

## 1. Critical bugs (Blocker)

### B1 — Subprocess command injection via `OMNI_SUBAGENT_FAKE_STDERR` and scripted response — `scripts/subagent.py:399-405`

The fake-mode codepath builds a Python `-c` one-liner by string-concatenating env-var content into source code. Escaping handles backslash, single-quote, and newline — but **not carriage return** (`\r`), **not unicode line separator** (`\u2028`). Crucially, `fake_stderr` and `fake_output` (the latter pulled from a JSON file at `OMNI_SUBAGENT_FAKE_RESPONSE_FILE`) are *not* sanitized for any character outside the three replaced.

This is reachable when `OMNI_SUBAGENT_FAKE=1` (single env var). The JSON response file is read from any user-supplied path, so anyone running an OMC test in a hostile checkout (e.g. CI on a fork PR) gets arbitrary code execution in the test runner.

**Suggested fix**: do not build source by concatenation. Pass values via env vars and have inline Python read via `os.environ`.

### B2 — Connection-pool deadlock on `_make_connection()` failure — `mcp/server.py:203-224`

`_pool_acquire` increments `_POOL_ACTIVE` *before* attempting to create a new connection, then runs `_make_connection()` outside the lock. If `_make_connection()` raises (sqlite locked, `OMNI_HOME` unwritable, migration failure), the function reraises after the retry loop — but `_POOL_ACTIVE` is **never decremented**, and `_POOL_COND.notify()` is never called.

After 4 failed acquires the pool is permanently full and every future `_pool_acquire` blocks forever in `_POOL_COND.wait()`.

**Suggested fix**: wrap the `_make_connection()` block in try/except that decrements `_POOL_ACTIVE` and notifies before reraising.

## 2. Major issues

### M1 — `_spawn_background` wrapper interpolates raw Python source from runtime values — `scripts/subagent.py:567-633`

f-string interpolation of dynamic values into Python source. Today escaping is sufficient; surface is unnecessary. **Fix**: replace template with static module file that reads config from JSON sidecar.

### M2 — `_looks_sensitive` over-redacts harmless messages — `mcp/server.py:321-328`

`(/[a-zA-Z0-9_.-]{2,})` matches **any** forward slash followed by ≥2 word chars. Fires on `"unknown action: /create"`, `"invalid URL path /api/v1"`. `[A-Z_]{3,}=` matches `"HTTP=2"`, `"GET=true"`. Real bugs become undebuggable.

**Fix**: tighten to actual filesystem absolute paths (`/home/`, `/Users/`, `/var/`, `/etc/`, `/tmp/`, `C:\\`, `\\\\`) and well-known sensitive env-var names.

### M3 — Pool double-release / acquired twice in foreground — `scripts/subagent.py:306-316, 433-435`

`spawn()` calls `pool.acquire(job_id)` once. `_spawn_foreground()` re-loads the pool module and constructs a brand new `SubagentPool` instance. Acquired once, released via two paths. Any exception path between acquire and release leaks a pool slot until process exit.

**Fix**: pass acquired pool instance into `_spawn_foreground`, use try/finally for release.

### M4 — `wait_for_jobs.py` exit-code semantics conflict with documented contract — `scripts/wait_for_jobs.py:121-123, 180-185`

Docstring: `1 = at least one job ended in failed/cancelled`. Implementation returns `1` for "no status paths provided" — config error, not job failure.

**Fix**: use `2` for config errors; reserve `1` strictly for job failures.

### M5 — `extract_verdict` doesn't strip code fences — `scripts/parse_critic_verdict.py:25, 43-47`

Last `VERDICT: <X>` line wins, regardless of whether it's inside a fenced code block illustrating what a critic should output. Critic agent emitting `VERDICT: REJECT` in an example is misread as terminal REJECT.

**Fix**: strip code fences before scanning, OR restrict to last 5 lines of the file.

### M6 — `cap-sanity-guard` referenced in tests but not implemented — `tests/test_pipeline_e2e_ultra.py:328-331`

Test asserts on string "sanity cap" that doesn't exist in any code/skill file. Test passes vacuously.

**Fix**: implement the guard or delete the dead assertion.

## 3. Minor issues (10 items)

m1. `_RE_FILE_PATH` regex catastrophic backtracking risk — `scripts/router.py:48`
m2. `_tool_state_clear` returns `deleted=None` if SQLite returns `-1` rowcount
m3. `_SAFE_ID_RE` allows leading dot (`..` recovered later by traversal guard, but defense in depth)
m4. `category_resolver._default_availability_checker` shells out per resolution; cache the model list
m5. `read_pipeline_state` returns WS5 stub even though WS5 shipped (echoes Critic #2)
m6. `mcp/server.py` `_handle` doesn't validate `args` is a dict
m7. `subagent_pool.acquire` busy-loops with `time.sleep(0.1)`; consider exponential backoff
m8. `wait_for_jobs._read_status` retries on JSONDecodeError but silently returns None after 3 retries
m9. `parse_critic_verdict.main` swallows KeyboardInterrupt, returns 1
m10. `subagent.py` writes `_wrapper.py` to job dir but never cleans it up — disk hygiene

## 4. Style and consistency notes

- `mcp/schema_validator.py` mixes PEP 585 generics with `typing` legacy — pick one
- `scripts/subagent.py` mixes `from typing import Optional` with PEP 604 `str | None`
- Several files do `import json as _json` inside functions — dead aliases when already imported at module level
- All new files have shebangs, docstrings, 4-space indent — good

## 5. Performance observations

- `mcp/server.py:_tool_memory_search` uses unindexable `LIKE '%query%'` — acceptable for ≤10K rows
- `scripts/router.py:282` compiles fresh regex per word in `_TECH_NAMES` per classify — pre-compile at module load
- `scripts/wait_for_jobs.py` reads every status.json on every poll-interval; 50 jobs × 30 min = 90,000 reads
- `scripts/verify_plugin_contract.py` rglobs the tree ~14 times per `--all` run; cache once

## 6. Robustness gaps

- MCP DB locked: leaks `_POOL_ACTIVE` (Blocker B2)
- `.omni/runs/` read-only: `PermissionError` propagates with full path; combined with M2 over-redaction, user gets PermissionError with no path
- Concurrent migrations: schema_version DELETE/INSERT not atomic but benign at v2
- Two checkouts of repo running subagents simultaneously share the same lock file if `OMNI_HOME` unset — different config caps, weird back-pressure
- Wrapper script doesn't inherit FAKE settings via env; bakes them at spawn time

## 7. Security findings (OWASP)

- **A03 Injection — B1** subprocess construction
- **A03 Injection — M1** wrapper script template
- **A04 Insecure Design — m3** leading dot in _SAFE_ID_RE
- **A05 Security Misconfiguration — M2** _looks_sensitive over-redaction (usability/observability problem; doesn't under-redact)
- **A09 Logging Failures** _sanitize_error writes full unsanitized traceback to stderr (line 299-304)
- Path traversal: `_safe_child_path` symlink-aware, correct ✓
- Shell injection in policy_check: tokens via `shlex.split(posix=True)`, no shell invoked ✓
- JSON-RPC error leakage: WS8 promised fixed; verified ✓ (with M2 caveat)

## 8. Test-quality assessment

- **`tests/test_router.py` — Excellent.** 40+ regression cases with explicit expected scores. Adversarial cases. Boundary at threshold 0.40.
- **`tests/test_pipeline_e2e.py` — Acceptable, leaky.** FAKE mode means subagent.py codepath never exercised end-to-end. Many `if X.exists():` and `or result.exit_code in (0,1)` guards pass trivially when bash blocks fail without writing artifacts.
- **`tests/test_pipeline_e2e_ultra.py` — Mixed.**
  - `test_ultrawork_cycle_detection`: real, solid.
  - `test_ultrawork_cap_enforcement`: dead assertion (M6).
  - `test_ultraqa_converges`: extracts hand-copied Python script from SKILL.md and runs directly — bypasses SKILL bash entirely. **High false-confidence risk.**
  - `test_ultraqa_stops_on_repeat`: accepts `state in ("stalled","cycles_exhausted")` — both passing means regression that breaks repeat-detection still passes.
- **`tests/test_pipeline_e2e_ralplan.py` — Acceptable.** Fixture-driven approach legitimate. State-transition assertions real. Many guarded `if`s — silent no-op when SKILL doesn't reach expected state.

**Overall**: WS3 router tests great. Pipeline e2e tests **better than nothing but soft**.

## 9. API consistency

### `subagent.spawn()` foreground vs background

Different return shapes (foreground has stdout/stderr/exit_code; background has pid). Plus 5 different error shapes. Pick one shape and stick to it.

### `wait_for_jobs.main` exit-code map

| exit | docstring | actual |
|---|---|---|
| 0 | all done | ✓ |
| 1 | ≥1 failed/cancelled | ✓ AND "no jobs found" AND "no paths provided" (collision) |
| 124 | timeout | ✓ |

### `router.classify` decision-branch shape

Three branches: `bypass`/`redirect`/`proceed`. All return identical shape via `_build_result()`. **Clean.**

### `category_resolver.resolve` shape

All branches return same dict. **Clean.**

### MCP `tools/call` error envelope

All errors funnel through `_sanitize_error`. **Clean.**

## 10. Top 10 line-level edits I would make immediately

1. `mcp/server.py:213-224` — try/except decrements `_POOL_ACTIVE` on failure (B2)
2. `scripts/subagent.py:399-405` — env-var passing instead of source-string interpolation (B1)
3. `scripts/subagent.py:567-633` — wrapper template reads config from JSON sidecar (M1)
4. `mcp/server.py:321-322` — tighten `_SENSITIVE_RE` (M2)
5. `scripts/subagent.py:316` — pass acquired pool instance, try/finally release (M3)
6. `scripts/wait_for_jobs.py:123, 240, 250` — return `2` for config errors (M4)
7. `tests/test_pipeline_e2e_ultra.py:328-331` — implement guard or delete assertion (M6)
8. `scripts/router.py:281-285` — pre-compile per-tech regex at module load (perf)
9. `tests/test_pipeline_e2e.py` — replace `if X:` guards with explicit asserts (test quality)
10. `scripts/subagent.py:561, 635` — clean up `_wrapper.py` after run (m10)

## Summary

Net assessment: Wave 2 is real engineering. Router classifier well-tested, MCP hardening competent, validator's 14 checks codify hard-won invariants, subagent primitive is the right abstraction. Blockers concentrated in two areas: (a) fake-mode subprocess construction (real injection vector), (b) connection-pool acquire path leaks under exact failure mode the prompt asked about. Both are 5-line fixes. Once those land, this is a clean merge.
