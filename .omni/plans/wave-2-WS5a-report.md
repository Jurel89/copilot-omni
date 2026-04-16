# WS5a Completion Report: Subagent Primitive

Branch: `phase-b/wave-2/WS5a-subagent-primitive`
Date: 2026-04-16

---

## Public API Additions

### `scripts/subagent.py` — `spawn()` function

```python
def spawn(
    agent: str,
    prompt: str,
    *,
    category: str | None = None,
    model: str | None = None,
    allow_all: bool | None = None,
    background: bool = False,
    session_id: str | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
    timeout: int = 1800,
) -> dict:
    """
    Foreground: {job_id, run_id, exit_code, stdout, stderr, status_path}
    Background: {job_id, run_id, pid, status_path}  (returns immediately)
    """
```

CLI additions: `--background`, `--session-id`, `--run-id`, `--job-id`, `--timeout`.
Legacy `run_agent()` kept for backward compatibility (WS4 tests pass unchanged).

---

## Run-Directory Layout

```
.omni/runs/<run-id>/<job-id>/
    spec.json       # written BEFORE spawn (agent, category, model_used, session_id, prompt_excerpt)
    status.json     # atomic os.replace writes at every state transition
    stdout.log      # tee'd in foreground; direct redirect in background
    stderr.log      # tee'd in foreground; direct redirect in background
    _wrapper.py     # generated for background spawns; auto-deleted after completion
```

### status.json schema

```json
{
  "job_id": "uuid",
  "run_id": "uuid",
  "agent": "general-purpose",
  "category": null,
  "state": "pending|running|done|failed|cancelled",
  "started_at": "2026-01-01T00:00:00Z",
  "ended_at": "2026-01-01T00:00:01Z",
  "exit_code": 0,
  "error": null,
  "model_used": "claude-sonnet-4.5",
  "prompt_excerpt": "first 200 chars of prompt"
}
```

State transitions: `pending → running → done | failed | cancelled`.
All writes use `os.replace` for atomicity (no partial reads).

---

## Back-Pressure Design

### `scripts/subagent_pool.py` — `SubagentPool`

- Cross-process file-lock semaphore at `$OMNI_HOME/locks/subagent_pool.lock`
- Token bucket JSON: `{"acquired": [{job_id, pid, ts}], "cap": N}`
- Default cap: `min(8, os.cpu_count() or 4)`; overridable via `.omni/config.json > runtime.max_parallel_subagents`
- `acquire(job_id)`: blocks with 100 ms sleep until slot free; raises `TimeoutError` after `timeout` (default 60 s)
- `release(job_id)`: removes job from bucket
- Stale-entry pruning: entries with dead PID and age > 5 min evicted on every `acquire()`

### Cross-Platform Notes

| Platform | Lock mechanism |
|---|---|
| POSIX (Linux, macOS) | `fcntl.flock(LOCK_EX)` — OS releases on process death |
| Windows | `msvcrt.locking(LK_NBLCK)` — best-effort |
| Fallback (neither) | No locking; JSON bucket provides weak semantics |

### Benchmark Numbers (CI, `OMNI_SUBAGENT_FAKE_SLEEP_SECS=0.3`)

- Cap=4, 12 threads: wall time ~0.9 s (3 waves × 0.3 s), max concurrent = 4 ✓
- Cap=4, 8 cross-process subprocesses: wall time ≥ 0.5 s, all 8 completed ✓

---

## `wait_for_jobs.py` CLI

```
python3 scripts/wait_for_jobs.py <status_path>...          # explicit paths
python3 scripts/wait_for_jobs.py --run-id <id>             # all jobs in run
python3 scripts/wait_for_jobs.py --session-id <id>         # all jobs in session
```

Options: `--timeout SECS` (default 1800), `--poll-interval SECS` (default 1.0).

### Exit Code Semantics

| Code | Meaning |
|---|---|
| 0 | All jobs ended in `done` |
| 1 | At least one job ended in `failed` or `cancelled` |
| 124 | Timeout elapsed |

Output: one JSONL line per job at terminal state:
`{job_id, run_id, state, exit_code, duration_s, stdout_path, stderr_path}`

Robust to mid-write status.json: retries up to 3 times on `JSONDecodeError`.

---

## ADR-0010 Cross-References

- `docs/ADR/ADR-0010-subagent-back-pressure.md` — created in this workstream
- Covers: semaphore vs queue, blocking vs failing, file-lock impl, cross-process semantics, `omni doctor` integration, Phase-C deferrals

---

## Test Coverage Summary

| File | Tests | Notes |
|---|---|---|
| `tests/test_subagent_background.py` | 9 | background mode, run-dir layout, status schema, CLI flags |
| `tests/test_subagent_backpressure.py` | 9 | cap enforcement, stale pruning, cross-process, TimeoutError |
| `tests/test_wait_for_jobs.py` | 12 | done/failed/cancelled/timeout/mid-write/duration/log-paths |

**Total new tests: 30. Grand total: 230.**

Round-trip targets met:
- 3 parallel background jobs (1 s each): all done ≤ 30 s ✓
- Back-pressure test (cap=4, 12 jobs, 0.3 s sleep): ~0.9 s wall time ✓

---

## Validator Output

```
[ok] run-directory-invariants: checked=19, missing=0, corrupt=0, stuck_warn=0 OK
[ok] state-store-canonical: passed (subagent.py best-effort writes allowlisted)
[ok] stdlib-only-imports: passed
... all 13 checks green, exemption total 17/25
```

---

## Manual Smoke Evidence

```bash
$ OMNI_SUBAGENT_FAKE=1 python3 scripts/subagent.py general-purpose 'echo' --background
{"job_id": "4224997b-a8d0-4fb1-98c8-8b231f880f2e",
 "run_id": "81d3b48c-e3f9-46a6-8846-67add9634b84",
 "pid": 557577,
 "status_path": ".../.omni/runs/81d3b48c-.../4224997b-.../status.json"}
```

Returns immediately. status.json exists at the announced path. After ~1 s the
wrapper transitions it from `pending → running → done`.

---

## Handoff Notes

### WS5b (autopilot/ralph)
- Use `spawn(..., background=True)` to fire-and-forget skill subagents.
- Pass `run_id` to group related jobs; use `wait_for_jobs --run-id` to collect.

### WS5c (ultrawork/ultraqa fan-out)
- Fan out N jobs with the same `run_id`; `wait_for_jobs --run-id` gives JSONL
  summary per job with exit codes and log paths.
- Back-pressure is automatic — pool serializes excess spawns.

### WS6 (team workers)
- Team workers are spawned via `spawn()` with `category="deep"` or `"ultrabrain"`.
- Pool cap shared with other callers; team orchestrator should set `run_id` to
  the team session ID for easy monitoring.

---

## TODO Phase-C Items

- Per-agent priority lanes (critic/security get dedicated sub-pool slots)
- OOM accounting (weight slots by model size)
- Persistent priority queue for long-running orchestration pipelines
- Pool utilisation metrics emitted to MCP `trace` table
