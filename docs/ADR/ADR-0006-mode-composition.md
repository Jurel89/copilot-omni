# ADR-0006 — Mode Composition + Cancel Cascade

- **Status:** Accepted
- **Date:** 2026-04-16
- **Author:** WS5b
- **Related:** ADR-0010 (back-pressure), ADR-0007 (state store)
- **Companion plan:** `.omni/plans/phase-b-master-plan.md` §2.WS5b

---

## Context

Phase-B skills (`autopilot`, `ralph`, `ralplan`, `ultrawork`) are each implemented as
SKILL.md runbooks that invoke lower-level agents via `scripts/subagent.py`. Prior to
WS5b, autopilot's Phase 2 (Planning) and Phase 3 (Execution) called `ralplan` and
`ralph` as logical sub-skills — but there was no cross-process composition contract
governing how:

- mode state keys nest between outer and inner orchestrators,
- cancellation propagates cleanly from the outer skill down to an in-flight inner
  subprocess,
- the back-pressure pool (ADR-0010) is shared across all spawned jobs,
- the audit trail (run-dir artifacts) captures inner-skill work as a cohesive unit.

This ADR establishes the composition contract that WS5b skills implement.

---

## Decision

### 1. Composition over re-implementation

`autopilot` does **not** re-implement planning logic; it spawns `ralplan` as a
subprocess and waits for it.  `ralph` does not re-implement PRD-driven iteration; it
is invoked by `autopilot` Phase 3 when a task is large enough.  Inner skills are
black boxes to the outer skill: the outer skill only observes the exit code and the
run-dir artifacts produced by the inner skill.

**Why:** Re-implementing inner logic duplicates maintenance surface and introduces
drift between standalone `ralph` runs and autopilot-embedded `ralph` runs.  Subprocess
composition ensures that a `ralph` run spawned inside `autopilot` behaves identically
to a standalone `ralph` run.

### 2. Subprocess-only invocation

All outer-to-inner skill calls are made via `python3 scripts/subagent.py <skill-name>
"<prompt>" --category <cat> --session-id <id> [--background]`.  There is no in-process
function call between skills.

**Why:**
- **Back-pressure:** ADR-0010's semaphore pool is cross-process; subprocess invocation
  enters the pool correctly.  In-process calls would bypass the cap.
- **Audit trail:** Each subprocess creates its own run-dir job entry under
  `.omni/runs/<run-id>/<job-id>/` including `spec.json`, `status.json`, `stdout.log`,
  and `stderr.log`.  In-process calls leave no per-job artifact.
- **Cancellation safety:** A signal file (`cancel.signal`) is detectable by the
  subprocess polling loop regardless of whether the outer process is alive.  In-process
  threading would require cross-thread cancellation primitives.
- **Isolation:** A crash in an inner skill does not crash the outer skill; the outer
  skill reads the terminal `status.json` and decides how to proceed.

### 3. Nested mode keys

MCP state writes from inner skills use a dotted composite key:

| Outer skill  | Inner skill   | Mode key            |
|--------------|---------------|---------------------|
| `autopilot`  | `ralplan`     | `autopilot.ralplan` |
| `autopilot`  | `ralph`       | `autopilot.ralph`   |
| `ralph`      | (none so far) | `ralph`             |
| `ralplan`    | `architect`   | `ralplan.architect` |

The convention is `<outer>.<inner>`.  Outer skills write their own top-level key
(`mode="autopilot"`) for phase-level state; inner skills write under the composite key.
Readers can query all `autopilot.*` keys to enumerate in-progress inner work.

**Why dotted keys:** Flat keys would collide when `ralph` is run both standalone and
inside `autopilot`.  A dotted prefix lets `state_read(mode="autopilot.ralph")` return
only the ralph runs that belong to the current autopilot session.

### 4. Cancel cascade protocol

Cancellation flows **outward to inward** via a signal file:

1. The **outer skill** (or the user via `/copilot-omni:cancel`) creates an empty file
   at `.omni/runs/<run-id>/cancel.signal`.
2. Each **inner subprocess** polls for the signal file every 1 second during its work
   loop (before each iteration / agent spawn).
3. On detecting `cancel.signal`, the inner subprocess:
   a. Stops spawning new sub-jobs.
   b. Waits (up to 5 s) for any in-flight background jobs to reach a terminal state
      via `wait_for_jobs.py`.
   c. Writes `state="cancelled"` to its own `status.json`.
   d. Writes `state_write(mode="<composite-key>", body={status: "cancelled"})` to MCP.
   e. Exits with code 1.
4. The **outer skill**, upon seeing exit code 1 / `state=cancelled` in the inner
   job's `status.json`, propagates the cancel: it writes its own phase
   `status.json` with `state="cancelled"` and exits cleanly.
5. **Cleanup** is the outer skill's responsibility.  The outer skill deletes or
   archives the run-dir on successful cancellation to avoid stale artefacts.

#### Why signal files (not `os.kill`)

| Criterion         | Signal file                         | `os.kill`                     |
|-------------------|-------------------------------------|-------------------------------|
| Cross-process      | Yes                                 | Yes                           |
| Cross-platform     | Yes (all OS with a filesystem)      | POSIX only; Windows differs   |
| Auditable          | File is visible in run-dir          | Ephemeral; no record          |
| Race-free          | Polling is inherently race-free     | Signal delivery is async      |
| Survives crash     | File persists if outer crashes      | No effect after parent exit   |
| Nested depth       | Any depth: each level polls same dir| Each level needs PID lookup   |

Signal files win on auditability and cross-platform safety.  The 1-second polling
latency is acceptable for human-initiated cancellation.

### 5. Run-dir layout for composed runs

```
.omni/runs/
  <autopilot-run-id>/
    cancel.signal          # written by outer skill to cascade cancel
    phase-1/               # expand phase
      spec.md
      status.json          # {state, phase, started_at, ended_at}
    phase-2/               # plan phase (ralplan subprocess)
      spec.md
      status.json
    phase-3/               # execute phase (executor / ralph subprocesses)
      job-0/
        spec.json
        status.json
        stdout.log
        stderr.log
      job-1/ ...
    phase-4/               # QA phase
      status.json
    phase-5/               # validate phase
      status.json
  <ralph-run-id>/
    cancel.signal
    prd.json
    progress.txt
    iteration-0/
      diff.patch
      review.md
      status.json
    iteration-1/ ...
```

---

## Consequences

### Positive
- Inner skills (ralph, ralplan) can be tested and run standalone without any change.
- The back-pressure cap (ADR-0010) applies uniformly to all spawned jobs regardless of
  nesting depth.
- Cancel cascade is implementable in pure Python stdlib with no POSIX-specific code.
- Each run has a complete, inspectable audit trail in `.omni/runs/`.

### Negative / Trade-offs
- Subprocess overhead (~50–200 ms per spawn) is paid for every inner skill invocation.
  For very fast inner tasks this is noticeable but acceptable.
- Nested mode keys require callers to know the composition depth.  A `state_read`
  for top-level `ralph` will miss `autopilot.ralph` entries; callers must query both
  if they want the full picture.
- The 1-second cancel-poll latency means a cancel request can take up to 1 second to
  reach each inner subprocess level.  At depth 2 (autopilot → ralph → executor) the
  worst-case propagation delay is ~2 seconds.

---

## Phase-C deferrals

The following extensions are explicitly **out of scope for WS5b** and deferred to
Phase C:

- **Structured cancel reasons:** `cancel.signal` currently carries no reason payload.
  Phase C may extend the protocol to `cancel.signal` being a JSON file with
  `{reason, requested_by, timestamp}`.
- **Partial cancel (fan-out branch):** When autopilot Phase 3 spawns N parallel
  executor jobs, cancelling only one branch (leaving others running) is not supported.
  Current behaviour: cancel.signal cancels all branches.  Phase C may introduce
  per-branch signal files.
- **Cancel propagation depth > 2:** Currently tested and designed for depth 2
  (outer → inner).  Depth 3+ (outer → middle → inner) follows the same protocol
  but has no explicit test coverage until Phase C.
- **Timeout-triggered cancel:** Auto-cancel when a job exceeds a configurable wall
  clock limit.  Deferred to Phase C.
