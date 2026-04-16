---
id: ADR-0010
title: Subagent Back-Pressure via File-Lock Semaphore
status: accepted
date: 2026-04-16
authors: [WS5a executor]
supersedes: []
---

# ADR-0010: Subagent Back-Pressure via File-Lock Semaphore

## Context

Wave-2 skills (autopilot, ralph, ultrawork, ultraqa, ralplan) and WS6 team
workers all spawn subagents via `scripts/subagent.py`. Without a concurrency
cap, a single skill invocation can fan out to dozens of parallel `copilot`
processes, exhausting RAM, Copilot API rate limits, and OS file-descriptor
budgets simultaneously.

The cap must be enforced **across processes** — multiple skill invocations
from different terminal sessions or background daemons must share the same
token bucket.

## Decision

Implement a file-lock semaphore (`scripts/subagent_pool.py`, class
`SubagentPool`) with the following properties:

| Property | Value |
|---|---|
| Default cap | `min(8, os.cpu_count() or 4)` |
| Config override | `.omni/config.json > runtime.max_parallel_subagents` |
| Lock file | `$OMNI_HOME/locks/subagent_pool.lock` |
| Bucket format | JSON: `{"acquired": [{job_id, pid, ts}], "cap": N}` |
| Blocking policy | Block (spin with 100 ms sleep) until a slot is free |
| Stale-entry pruning | On every `acquire()`: evict entries where pid is dead AND age > 5 min |
| Stdlib only | `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) |

## Why Semaphore, Not Queue

A proper priority queue would add ~300 LOC, require persistent state, and
introduce ordering semantics that no current caller needs. The semaphore is
sufficient: callers block until a slot opens, which is the correct back-
pressure behaviour for interactive skill invocations. Priority and OOM
accounting are deferred to Phase-C (see §Deferrals).

## Why Blocking, Not Failing

Failing fast (returning an error when all slots are taken) would propagate
errors up to skill orchestrators that have no retry logic. Blocking transfers
the wait to the caller's process, which is already idle waiting for the
subagent — the net latency is identical but error-handling complexity is zero.

The `timeout` parameter (default 60 s) still surfaces `TimeoutError` for
genuinely stuck situations (e.g. orphaned processes that consume slots
indefinitely). `omni doctor --strict` flags acquired entries older than 30 min.

## File-Lock Implementation

### POSIX (Linux, macOS)
```python
import fcntl
fcntl.flock(fd, fcntl.LOCK_EX)   # acquire
fcntl.flock(fd, fcntl.LOCK_UN)   # release
```
`flock` is process-local: if the holder process dies, the OS automatically
releases the lock. The JSON token bucket is used to track *semantic* slot
holders (PIDs + timestamps) separately from the flock, so a crash mid-bucket-
write is handled by stale-entry pruning on the next `acquire()`.

### Windows
```python
import msvcrt
msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
```
If `msvcrt` is unavailable (edge case), locking degrades to best-effort
(no lock taken). The JSON bucket still provides weak cross-process semantics
in that case.

## Per-Process vs Cross-Process Semantics

`flock` alone provides mutual exclusion around the bucket read-modify-write
cycle. The pid+timestamp entries inside the bucket track *semantic* holders
across the lifetime of a spawned process — including background processes that
detach from the parent with `start_new_session=True`.

Background spawn flow:
1. Parent calls `pool.acquire(job_id)` — slot reserved while parent is alive.
2. Parent writes `_wrapper.py` into the job run-dir and detaches it.
3. Wrapper releases the slot on its own exit via `pool.release(job_id)`.
4. Parent registers `atexit` handler as a safety net in case it dies before
   the wrapper starts.

Foreground spawn flow:
1. `spawn()` calls `pool.acquire(job_id)` before the Popen call.
2. After the process completes (success, failure, or timeout),
   `pool.release(job_id)` is called in the finally block.

## `omni doctor` Integration

`omni doctor` (implemented in WS5a) prints:

```
subagent pool: cap=N, acquired=K (job ids: [...])
recent runs: <last 5 run_ids with state counts>
```

`omni doctor --strict` exits non-zero if any `acquired` entry is older than
30 minutes (likely orphaned).

## Validation

`scripts/verify_plugin_contract.py` gains `check_run_directory_invariants`
(WS5a) which scans `.omni/runs/` for jobs with missing or unparseable
`status.json`, and warns on jobs stuck in `running` for > 30 min.

## Phase-C Deferrals

- **Per-agent priority lanes**: high-priority agents (critic, security-reviewer)
  could bypass the cap or use a dedicated sub-pool.
- **OOM accounting**: weight each slot by estimated model size to prevent
  simultaneous ultrabrain spawns from exhausting RAM.
- **Persistent priority queue**: if blocking semantics prove insufficient for
  long-running orchestration pipelines.
- **Metrics**: emit pool utilisation to MCP `trace` table for visibility.

## Consequences

Positive:
- Copilot API rate-limit errors reduced to near-zero under fan-out workloads.
- Predictable memory footprint: max `N` concurrent `copilot` processes.
- Cross-process enforcement means shell aliases, test runners, and daemon
  invocations all share the same cap.

Negative:
- Adds a file I/O round-trip on every `acquire()` / `release()` call (~1 ms
  on local disk; negligible compared to subagent spawn latency of seconds).
- Windows support is best-effort if `msvcrt` is unavailable (rare).
