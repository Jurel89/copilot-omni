# WS5c Completion Report — ultrawork + ultraqa rewrite

**Branch:** `phase-b/wave-2/WS5c-ultrawork-ultraqa`
**Date:** 2026-04-16
**Author:** WS5c executor

---

## 1. Summary

WS5c applied the WS5b `subagent.py + wait_for_jobs.py + MCP state + ADR-0006
cancel-cascade` pattern to `ultrawork` (parallel fan-out engine) and `ultraqa`
(QA cycling loop). Both SKILL.md files were rewritten from Claude-primitive recipes
to subprocess-only runbooks. Nine e2e pipeline tests were added. The doctor skill
was extended to surface ultrawork/ultraqa active runs.

---

## 2. ultrawork SKILL.md rewrite shape

**File:** `skills/ultrawork/SKILL.md`  
**Size:** ~430 lines (from ~250)

### Recipe structure

| Step | Description |
|------|-------------|
| Router preamble | 3-line canonical (read MCP state, redirect check, proceed) |
| Step 0 — Init | Generate `ultrawork-<id>` run-id; read resume state from MCP |
| Step 1 — Load/validate spec | Load JSON from `spec.json` or inline PROMPT; validate fields, deps, cycles, count cap |
| Step 2 — Fan-out | Dependency-ordered spawn via `subagent.py --background`; pool back-pressure via subagent_pool |
| Step 3 — Wait + aggregate | `wait_for_jobs.py` block; write `summary.json`; MCP `state_write(mode="ultrawork")` |
| Step 4 — Cancel/status | cancel.signal check; write run-level `status.json` |

### Validation rules

1. Required fields per task: `id`, `agent`, `category`, `prompt`
2. No duplicate task IDs
3. All `depends_on` references must resolve to known IDs
4. No cycles in `depends_on` graph (DFS-based, exit code 2)
5. Total task count ≤ `runtime.max_parallel_subagents * 4`

### Run-dir layout

```
.omni/runs/ultrawork-<id>/
  spec.json          # normalised task list + cap
  spawn-log.jsonl    # one line per spawned task with timestamp
  fanout-manifest.json  # completed/failed/cancelled/pending at fan-out exit
  summary.json       # aggregate: total/done/failed/cancelled/duration_s/by_task
  status.json        # run-level state: done|failed|cancelled
  cancel.signal      # written to abort
  <task-id>/         # per-job run-dir (from subagent.py)
    spec.json
    status.json
    stdout.log
    stderr.log
```

### MCP state

`state_write(mode="ultrawork", session_id=..., body={run_id, fanout_count, completed, failed, cancelled, duration_s, status})`

---

## 3. ultraqa SKILL.md rewrite shape

**File:** `skills/ultraqa/SKILL.md`  
**Size:** ~420 lines (from ~250)

### Recipe structure

| Step | Description |
|------|-------------|
| Router preamble | 3-line canonical |
| Step 0 — Init | Generate `ultraqa-<id>` run-id; read resume state |
| Step 1 — Write spec | Parse `--commands`, `--max-cycles`, `--repeat-threshold` from PROMPT; write `spec.json` |
| Step 2 — Cycle loop | Up to max_cycles: run commands, check pass/fail, compute error-sig, detect stall, spawn fix agent |
| Step 3 — Final status | Write `status.json` with `state=converged|stalled|cancelled|cycles_exhausted`; exit accordingly |

### Cycle-dir layout

```
.omni/runs/ultraqa-<id>/
  spec.json
  status.json         # final run state
  cycle-<n>/
    status.json       # {cycle, all_pass, results[]}
    <cmd-name>/
      stdout.log
      stderr.log
      exit.txt
    qa-classify.md    # qa-tester output (failure classification)
    executor-fix.md   # executor output (fix applied)
```

### Error-signature algorithm

```
raw = command_name + first_200_chars_of_stderr
strip: lines matching /^\s*\d+[:|]/ (line-numbers)
       ISO timestamps \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}
sig = sha256(raw.encode()).hexdigest()[:16]
```

The dominant failure is the command with the highest (non-zero) exit code. Ties broken
by command order. If the same signature appears in `>= repeat_threshold` consecutive
cycles, the run exits with `state="stalled"`.

### Exit conditions

| Condition | State | Exit code |
|-----------|-------|-----------|
| All commands pass in any cycle | `converged` | 0 |
| Same error ≥ repeat_threshold | `stalled` | 1 |
| Max cycles without convergence | `cycles_exhausted` | 1 |
| cancel.signal detected | `cancelled` | 1 |

---

## 4. subagent.py FAKE env extensions (WS5c)

**File:** `scripts/subagent.py`

Three new env-var contract entries added to `_build_cmd()`:

| Env var | Default | Purpose |
|---------|---------|---------|
| `OMNI_SUBAGENT_FAKE_EXIT_CODE` | `0` | Exit code returned by fake subagent |
| `OMNI_SUBAGENT_FAKE_STDERR` | `""` | Text written to stderr by fake subagent |
| `OMNI_SUBAGENT_FAKE_SLEEP_SECS` | `1.0` | Sleep duration before exit (pre-existing) |

Contract is additive — existing tests using only `OMNI_SUBAGENT_FAKE=1` continue
to work unchanged (exit_code=0, stderr="").

---

## 5. E2e test inventory

**File:** `tests/test_pipeline_e2e_ultra.py`  
**Tests:** 9

| # | Test | What it verifies |
|---|------|-----------------|
| 1 | `test_ultrawork_3_parallel_lint` | 3 independent tasks fan-out; all complete in summary.json |
| 2 | `test_ultrawork_dependency_chain` | A→B→{C,D}: spawn-log ordering enforced |
| 3 | `test_ultrawork_cycle_detection` | Cycle A→B→A: validation fails (exit≠0) before any spawn |
| 4 | `test_ultrawork_cap_enforcement` | 12 tasks, cap=4: no cap sanity guard rejection (12≤16) |
| 5 | `test_ultraqa_converges` | Commands pass: cycle-1 all_pass=True, no-primitives check |
| 6 | `test_ultraqa_cycles_to_max` | Always-failing commands: state=stalled or cycles_exhausted |
| 7 | `test_ultraqa_stops_on_repeat` | Same stderr error every cycle: state=stalled at cycle 3 |
| 8 | `test_ultra_no_banned_primitives` | 0 banned Claude primitives in ultrawork + ultraqa SKILL.md |
| 9 | `test_ultraqa_cancel_cascade` | Pre-written cancel.signal: exit≠0, state≠converged |

---

## 6. Doctor extension

**File:** `skills/omni-doctor/SKILL.md` Step 7

Extended Step 7 "Active Autopilot and Ralph Runs" to also surface:
- `ultrawork-*` runs: reads `summary.json` (total/done/failed/status) or `status.json`
- `ultraqa-*` runs: reads run-level `status.json` plus cycle count

Header updated to: "Step 7: Active Autopilot, Ralph, Ultrawork, and UltraQA Runs (WS5b/WS5c)"

New diagnosis entries:
- `ultrawork` runs with `failed > 0`: WARN
- `ultraqa` runs with `state=stalled`: WARN

---

## 7. Validator output

```
[ok] rename
[ok] rename-stub
[ok] no-claude-primitives
[ok] writable-frontmatter
[ok] frontmatter-schema
[ok] skill-agent-refs
[ok] command-refs
[ok] mcp-tool-refs
[ok] exemption-budget  (17/25 — under budget)
[ok] stdlib-only-imports
[ok] state-store-canonical
[ok] no-raw-model-names
[ok] run-directory-invariants
[ok] cancel-signal-pairing
```

All checks green. Exemption count: 17/25.

---

## 8. Test count

- **WS5b baseline:** 237 passing
- **WS5c additions:** +9 ultra tests
- **Total at HEAD:** 246 passing

---

## 9. Handoff notes

### WS5d (ralplan rewrite)

WS5d's ralplan rewrite can reuse the ultrawork fan-out pattern directly:
- ralplan spawns `architect`, `planner`, `critic` as parallel subagents
- ultrawork's `spec.json` format (tasks with `depends_on`) maps cleanly to
  ralplan's parallel review phase
- The `wait_for_jobs.py` + spawn-log + summary.json pattern is identical

### WS6 (team workers)

WS6 team workers will use ultrawork primitives for parallel coordination:
- Team fan-out (dispatch N workers) = ultrawork with `depends_on=[]` for all tasks
- Team aggregation = ultrawork's `summary.json` + MCP `state_write(mode="ultrawork")`
- The pool back-pressure (ADR-0010) ensures team workers don't overload the system

### Known limitations

- `test_ultrawork_cap_enforcement`: verifies spec sanity guard but not actual
  concurrency wave timing (would require real subagents with controlled sleep).
  Full wave-timing assertion requires a mock pool; deferred to WS6 integration tests.
- ultraqa `--commands` parsing via regex is simple; complex commands with semicolons
  inside quotes are not supported. Use spec.json pre-write for complex command sets.
