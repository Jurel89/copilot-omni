# Phase-B Wave 2 — Architectural Review

## 0. Verdict

Wave 2 is a **structurally sound but contractually leaky** delivery. The five new ADRs (0003 categories, 0005 router rubric, 0006 mode composition, 0007 state ownership, 0010 back-pressure) are coherent and the seven workstreams (~14,000 lines added across 76 files) implement the bulk of what they promise. The subprocess-composition spine (subagent.py + subagent_pool.py + wait_for_jobs.py + cancel.signal polling) is real, exercised by 273 passing tests, and gives Phase-B a defensible primitive layer.

However three structural gaps will bite Wave 3:
- (a) The *nested-mode-key* convention from ADR-0006 §3 is documented and tested but **never actually wired** — autopilot's SKILL.md spawns ralplan without exporting `RALPLAN_MODE=autopilot.ralplan`, so the dotted keys exist only in tests and in the `_mcp_write_best_effort('autopilot.ralplan', ...)` literal at `skills/autopilot/SKILL.md:213`.
- (b) The WS3 `router_state.py` still hard-codes a `_WS5_STUB` for autopilot/ralph/ultrawork/team modes even though all four are now LIVE.
- (c) The Windows portability story in ADR-0010 is largely speculative — `msvcrt.locking` is wired but never CI-tested, and `start_new_session=True` at `scripts/subagent.py:646` is POSIX-only with no documented Windows fallback.

None of these are blockers for the merge, but each is a small "hidden contract violation" that compounds. Wave 3 should not start until items §11.1–§11.3 are decided.

## 1. State model coherence

ADR-0007 declares `state` table is canonical for "Skill/mode runtime state". ADR-0006 §3 introduces dotted convention `<outer>.<inner>` with five examples.

| Mode key | Declared in | Reality |
|---|---|---|
| `router` | ADR-0007 §6 | LIVE |
| `subagent` | scripts/subagent.py docstring | LIVE but undeclared in any ADR |
| `autopilot` | ADR-0006 §3 | LIVE |
| `autopilot.ralplan` | ADR-0006 §3 | **Half-live**: written by autopilot outer; ralplan inner writes under `RALPLAN_MODE` which defaults to `"ralplan"` because autopilot does NOT export `RALPLAN_MODE=autopilot.ralplan`. Only test sets it. |
| `autopilot.ralph` | ADR-0006 §3 | **Phantom**: not written by any code path. |
| `ralph` | implicit | LIVE |
| `ralplan.architect` / `ralplan.critic` | ADR-0006 §3 + WS5d report | **Phantom**: ralplan never writes sub-keys. |
| `ultrawork` | not in ADR | LIVE but undeclared |
| `ultraqa` | not in ADR | LIVE but undeclared |

**Validator check.** `check_state_store_canonical` only verifies no Python file outside `mcp/server.py` writes directly to MCP-owned tables. Does NOT validate `mode` column value-domain. Drift invisible to CI.

Severity: Medium-High.

## 2. Composition contract: ADR-0006 vs. implementation

ADR-0006 §1-2 unambiguous: autopilot Phase 2 spawns ralplan as subprocess. `skills/autopilot/SKILL.md:166-181` confirmed. Cancel-cascade enforced via `check_cancel_signal_pairing`.

**Real holes:**
1. **Nested mode keys are documented in tests, not in code.** Only test sets `RALPLAN_MODE=autopilot.ralplan`. Production has both records under different keys.
2. **`autopilot.ralph` is documented but never written.**
3. **OMNI_SUBAGENT_FAKE is the only execution path actually tested.** All e2e tests set `OMNI_SUBAGENT_FAKE=1`. Zero integration coverage proving cancel-cascade works against real `copilot` process.

Severity: Medium.

## 3. Back-pressure architecture

`scripts/subagent_pool.py` well-structured (296 LOC). Cross-process semantics work. POSIX/Windows shim clean.

**Failure modes:**
- **SIGKILL of holder:** kernel releases flock; bucket entry persists with dead PID. `_prune_stale` only evicts where `_is_pid_alive AND age > 300s`. So SIGKILL'd job locks one slot for 5 minutes before pruning. With cap=8, burst of 8 SIGKILLs ties up entire pool for 5 min.
- **`omni doctor --strict`** doesn't actually exit non-zero on stuck slots — that's in `verify_plugin_contract.py`, not in doctor itself. Documentation/implementation drift.

Severity: Low.

## 4. Router-state stub debt

`scripts/router_state.py:28-58` still encodes WS3-era stub: `_PIPELINE_MODES_WS5 = {autopilot, ralph, ultrawork, team}` returning `{"status":"unknown","reason":"WS5 not yet shipped"}`. WS5b/c/d shipped. **The unit test asserts the lie.** `tests/test_router_state.py:21-46` requires "WS5 not yet shipped" to be returned.

WS3 report explicitly says: "WS5b should: 2. Replace the stub in `scripts/router_state.py` for those modes." WS5b's report makes no mention. Forgotten.

Severity: High.

## 5. Category resolution

`scripts/category_resolver.py:114-165` correctly walks fallback chain, fails open with `available_check="failed"`. `omni doctor --strict` is a real drift detector via `_doctor_categories`.

Gap: `omni doctor` doesn't separately verify ADR-0003's declared menu against the live menu. New Copilot models go undetected.

Severity: Low.

## 6. ADR-implementation drift table

| ADR | Drift? | Severity |
|---|---|---|
| **0003** Categories — fallback chain, `--category` flag, raw model names banned | None | None |
| **0005** Router rubric — exact weights, `--skip-interview` bypass, signals audit trail | None | None |
| **0006** Subprocess composition | None | None |
| **0006** Nested mode keys (`<outer>.<inner>`) | **YES** — outer writes the composite key; inner writes its own root key (no composition). `autopilot.ralph`, `ralplan.architect`/`ralplan.critic` written by NO code | High |
| **0006** Cancel cascade — 1s polling per ADR | **Partial** — cascade exists, 1-second polling is aspirational (per-bash-block check, not continuous loop) | Medium |
| **0007** State store ownership matrix | **YES** — Wave-2 modes (`subagent`, `ultrawork`, `ultraqa`, `autopilot.*`, `ralplan.*`) missing from matrix | Medium |
| **0007** state-store-canonical validator | Drift type out of scope (table-level only, not mode-key) | Medium |
| **0010** File-lock semaphore | None | None |
| **0010** Stale-entry pruning on every acquire | 5-min window not surfaced in `omni doctor` | Low |
| **0010** Windows `msvcrt.locking` | **Speculative** — no Windows CI | Medium (Wave 3) |

## 7. Cross-OS portability

POSIX-shaped primitives:
1. **File locks.** Windows path syntactically present but never CI-tested.
2. **Background process spawning.** `start_new_session=True` is POSIX-only — Windows equivalent (`creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`) not used. **Windows: background subagents will not detach from parent's console group.**
3. **Atomic writes (`os.replace`).** Works cross-platform.
4. **`os.kill(pid, 0)`.** Should work on Windows but no evidence.
5. **`datetime.utcnow()`** in autopilot's heredocs — deprecated in Python 3.12.

Severity: Medium for Wave 3. Windows ~70% wired, ~0% tested.

## 8. Test-hatch / fake-subagent safety

`OMNI_SUBAGENT_FAKE=1` read at `subagent.py:392`, no production guard. Stale `OMNI_SUBAGENT_FAKE_RESPONSE_FILE` env-var would cause production runs to read scripted JSON instead of calling agents. Falls back to "OK" if file missing — silent misconfiguration.

Severity: Medium. Recommend hard guard requiring `OMNI_TEST_MODE=1` AND `OMNI_SUBAGENT_FAKE=1`.

## 9. Wave 3 prereqs Wave 2 didn't leave

1. Registry of valid `mode` values for `state_write`.
2. Real router-state reader for non-router modes.
3. Cross-process job lookup index by composite criteria.
4. Documented `parent_run_id` / `parent_job_id` link in `status.json`.
5. Standardised "skill manifest" of supported modes.
6. Windows CI lane.

## 10. Architectural recommendations

1. **Update `scripts/router_state.py:28-58`** to call MCP for `autopilot|ralph|ultrawork|team`; update tests in lockstep. Effort: 1-2h. Impact: HIGH.
2. **Wire nested-mode-key contract in autopilot.** Before spawning ralplan at line 166, `export RALPLAN_MODE=autopilot.ralplan`. Symmetrically for ralph. Effort: <1h.
3. **Add `mode` registry validator.** Enumerate all `state_write/state_read` calls; compare against `docs/STATE_MODES.md`. Effort: 4-6h. Impact: HIGH.
4. **Hard-guard `OMNI_SUBAGENT_FAKE`.** Require both FAKE=1 AND TEST_MODE=1 (or detect pytest). Effort: 30min. Impact: MEDIUM.
5. **Surface 5-min-to-30-min stuck-slot window in `omni doctor`.** Effort: 1h.
6. **Add Windows CI lane covering pool + background path.** Effort: 1d. Impact: HIGH for Wave 3.
7. **Add explicit `parent_run_id` / `parent_job_id` fields to `status.json` schema.** Effort: 2h.
8. **`_doctor_doctor` consistency check** between ADR-0010 promises and `omni doctor` behavior. Effort: 1h.
9. **Replace `datetime.utcnow()`** with `datetime.now(timezone.utc)` in heredocs. Effort: 30min.
10. **Document `omni-doctor` skill vs `omni doctor` CLI subcommand split.** Effort: TBD.
11. **Decouple cancel-signal polling cadence** from bash-block cadence (continuous poller wrapping each subagent.py spawn).
12. **Add regression test that proves cancel cascade works without `OMNI_SUBAGENT_FAKE`.** Effort: 1d. Impact: HIGH.

## 11. Items the user should decide before Wave 3 starts

1. **Is `RALPLAN_MODE` and the nested-key convention worth fixing, or amend ADR-0006 §3?**
2. **What's the `mode` value-domain governance model?** Enumerate + validate, or open string + remove implicit registry from ADR-0007.
3. **Is Windows a real target?** If yes, schedule WS6.5 hardening sprint. If no, mark `subagent_pool.py` POSIX-only.
4. **What's the `OMNI_SUBAGENT_FAKE` policy in production?** Hard-guard or accept the foot-gun.
5. **Should the router become pipeline-aware?**
6. **Is the `omni doctor` skill (markdown runbook) still needed alongside the CLI subcommand?**
7. **Should the back-pressure pool gain fairness ordering before WS6?**
8. **Are `ultrawork` / `ultraqa` modes "first-class" or tactical helpers?**
