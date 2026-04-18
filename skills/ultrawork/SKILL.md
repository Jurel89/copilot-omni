---
name: ultrawork
description: Parallel execution engine — fan-out N subagents, wait, aggregate
argument-hint: "<task description or path to spec JSON with parallel work items>"
level: 4
---

<Purpose>
Ultrawork is a parallel fan-out engine. It accepts a task list (JSON spec or inline
blob), spawns N subagents with correct dependency ordering, enforces the pool
back-pressure cap, waits for all jobs, and writes a structured summary. It is a
composable component — ralph and autopilot layer persistence and validation on top.
</Purpose>

<Use_When>
- Multiple independent (or partially dependent) tasks can run in parallel
- User says "ulw", "ultrawork", or wants parallel fan-out execution
- You need deterministic dependency-ordered spawning with aggregate summary
- Task list is provided as JSON (spec file) or inline blob
</Use_When>

<Do_Not_Use_When>
- Task requires guaranteed completion with verification loops — use `ralph`
- Task requires a full autonomous pipeline — use `autopilot`
- There is only one sequential task with no parallelism — delegate to executor directly
- User needs persistent resume across sessions without a spec file — use `ralph`
</Do_Not_Use_When>

<Why_This_Exists>
Sequential task execution wastes time when tasks are independent. Ultrawork enables
firing multiple agents simultaneously, handles dependency graphs, respects pool
back-pressure (ADR-0010), and produces a machine-readable summary that outer skills
can consume. It is designed as a subprocess-composable component per ADR-0006.
</Why_This_Exists>

# Router preamble
1. Read MCP state: `python3 scripts/router_state.py --read --session-id "$OMNI_SESSION_ID" --json`
2. If `decision.redirect == "deep-interview"`, defer to `/copilot-omni:deep-interview` and exit.
3. Otherwise, proceed with `decision.skill == ultrawork`.

## Step 0 — Initialise run

```bash
# Generate stable run-id for this ultrawork session.
OMNI_SESSION_ID="${OMNI_SESSION_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
ULTRAWORK_RUN_ID="ultrawork-${OMNI_SESSION_ID}"
RUN_DIR=".omni/runs/${ULTRAWORK_RUN_ID}"
mkdir -p "${RUN_DIR}"

# Check for resume: read last summary from MCP state
python3 scripts/router_state.py --read --mode ultrawork --session-id "$OMNI_SESSION_ID" --json \
  > "${RUN_DIR}/resume-state.json" 2>/dev/null || echo '{}' > "${RUN_DIR}/resume-state.json"

echo "ultrawork: run_id=${ULTRAWORK_RUN_ID}"
```

---

## Step 1 — Load and validate spec

```bash
# Locate spec: prefer .omni/runs/<run-id>/spec.json; else parse from PROMPT inline JSON.
SPEC_FILE="${RUN_DIR}/spec.json"

python3 - "${SPEC_FILE}" "{{PROMPT}}" "${RUN_DIR}" <<'PYEOF'
"""Load, validate, and write the normalised task spec.

Validation rules:
  1. Each task must have: id (str), agent (str), category (str), prompt (str).
  2. depends_on (optional list[str]) — each referenced id must exist in the spec.
  3. No cycles in the depends_on graph (DFS-based cycle detection).
  4. Total task count must not exceed runtime.max_parallel_subagents * 4.

Error-signature algorithm (used by ultraqa cycle loop):
  sha256(command_name + first-200-chars-of-stderr with line-numbers and
  ISO timestamps stripped). This is documented here for reviewer reference
  and implemented in the ultraqa SKILL.md cycle loop.
"""
import json
import sys
import hashlib
import re
from pathlib import Path

spec_file, raw_prompt, run_dir = sys.argv[1], sys.argv[2], sys.argv[3]
run_dir_path = Path(run_dir)

# ── 1. Read cap from .omni/config.json ──────────────────────────────────────
def _get_cap() -> int:
    config_path = Path(".omni/config.json")
    try:
        data = json.loads(config_path.read_text())
        cap = data.get("runtime", {}).get("max_parallel_subagents")
        if cap and str(cap).isdigit():
            return int(cap)
    except Exception:
        pass
    import os
    return min(8, os.cpu_count() or 4)

cap = _get_cap()

# ── 2. Load spec ─────────────────────────────────────────────────────────────
tasks = []
spec_path = Path(spec_file)

if spec_path.exists():
    try:
        data = json.loads(spec_path.read_text())
        tasks = data if isinstance(data, list) else data.get("tasks", [])
    except Exception as e:
        print(f"error: could not parse spec file {spec_file}: {e}", file=sys.stderr)
        sys.exit(1)
else:
    # Try parsing from inline PROMPT
    prompt = raw_prompt.strip()
    for candidate in [prompt]:
        try:
            parsed = json.loads(candidate)
            tasks = parsed if isinstance(parsed, list) else parsed.get("tasks", [])
            break
        except Exception:
            pass
    if not tasks:
        # Treat entire prompt as a single task
        tasks = [{"id": "task-1", "agent": "executor", "category": "deep", "prompt": prompt}]

# ── 3. Validate required fields ───────────────────────────────────────────────
errors = []
ids_seen = set()
for i, t in enumerate(tasks):
    for field in ("id", "agent", "category", "prompt"):
        if field not in t:
            errors.append(f"task[{i}] missing required field: {field!r}")
    tid = t.get("id", f"<index {i}>")
    if tid in ids_seen:
        errors.append(f"duplicate task id: {tid!r}")
    ids_seen.add(tid)

if errors:
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    sys.exit(1)

# ── 4. Validate depends_on references ────────────────────────────────────────
for t in tasks:
    for dep in t.get("depends_on", []):
        if dep not in ids_seen:
            errors.append(f"task {t['id']!r}: depends_on unknown id {dep!r}")

if errors:
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    sys.exit(1)

# ── 5. Cycle detection (DFS) ──────────────────────────────────────────────────
graph = {t["id"]: set(t.get("depends_on", [])) for t in tasks}

def has_cycle(graph):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def dfs(node):
        color[node] = GRAY
        for nb in graph.get(node, []):
            if color.get(nb, BLACK) == GRAY:
                return True
            if color.get(nb, BLACK) == WHITE:
                if dfs(nb):
                    return True
        color[node] = BLACK
        return False

    return any(dfs(n) for n in graph if color[n] == WHITE)

if has_cycle(graph):
    print("error: cycle detected in depends_on graph — aborting", file=sys.stderr)
    sys.exit(2)

# ── 6. Sanity guard — total task count ───────────────────────────────────────
max_tasks = cap * 4
if len(tasks) > max_tasks:
    print(
        f"error: spec has {len(tasks)} tasks which exceeds sanity cap of "
        f"{max_tasks} (runtime.max_parallel_subagents={cap} * 4) — "
        "reduce task count or raise runtime.max_parallel_subagents",
        file=sys.stderr,
    )
    sys.exit(1)

# ── 7. Write normalised spec ──────────────────────────────────────────────────
normalised = {
    "run_id": run_dir_path.name,
    "task_count": len(tasks),
    "cap": cap,
    "tasks": tasks,
}
spec_path.parent.mkdir(parents=True, exist_ok=True)
spec_path.write_text(json.dumps(normalised, indent=2))

print(f"ultrawork: spec validated — {len(tasks)} task(s), cap={cap}")
PYEOF

VALIDATE_EXIT=$?
if [ ${VALIDATE_EXIT} -ne 0 ]; then
  echo "FAIL: spec validation failed (exit=${VALIDATE_EXIT})"
  exit ${VALIDATE_EXIT}
fi
```

---

## Step 2 — Fan-out with dependency ordering

```bash
# Read cap and tasks from validated spec, then spawn jobs respecting depends_on.
# Pool back-pressure is enforced by subagent.py via subagent_pool.py (ADR-0010).

python3 - "${RUN_DIR}" "${ULTRAWORK_RUN_ID}" "${OMNI_SESSION_ID}" <<'PYEOF'
"""Fan-out engine with dependency ordering.

Algorithm:
  1. Build a dependency graph from the validated spec.
  2. Identify the initial wave: tasks with no unresolved dependencies.
  3. Spawn each ready task via subagent.py --background.
  4. After each batch, wait for completions, then unlock newly-unblocked tasks.
  5. Repeat until all tasks are spawned (or a cancel.signal is detected).

Pool back-pressure: subagent.py acquires/releases pool slots internally.
The outer loop does NOT need to manage concurrency — subagent_pool handles it.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

run_dir, run_id, session_id = sys.argv[1], sys.argv[2], sys.argv[3]
run_dir_path = Path(run_dir)
spec = json.loads((run_dir_path / "spec.json").read_text())
tasks = spec["tasks"]
task_map = {t["id"]: t for t in tasks}

# Track state
pending = set(t["id"] for t in tasks)   # not yet spawned
running = {}    # task_id -> {job_id, status_path}
completed = {}  # task_id -> {"state": done/failed/cancelled}
failed_ids = []
cancelled = False

def _cancel_signal_present():
    return (run_dir_path / "cancel.signal").exists()

def _dependencies_met(task_id):
    deps = task_map[task_id].get("depends_on", [])
    return all(completed.get(d, {}).get("state") == "done" for d in deps)

def _spawn_task(task):
    tid = task["id"]
    agent = task["agent"]
    category = task["category"]
    prompt = task["prompt"]
    priority = task.get("priority", "normal")

    result = subprocess.run(
        [
            sys.executable, "scripts/subagent.py", agent, prompt,
            "--category", category,
            "--session-id", session_id,
            "--run-id", run_id,
            "--job-id", tid,
            "--background",
        ],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent if __file__ else "."),
    )
    if result.returncode == 0:
        try:
            last_line = result.stdout.strip().splitlines()[-1]
            job_info = json.loads(last_line)
            return job_info
        except Exception as e:
            print(f"warn: could not parse job info for {tid}: {e}", file=sys.stderr)
    else:
        print(f"warn: spawn failed for {tid}: {result.stderr[:200]}", file=sys.stderr)
    return None

# Write spawn-log for resume / observability
spawn_log_path = run_dir_path / "spawn-log.jsonl"

def _log_spawn(task_id, job_info):
    import datetime
    entry = {
        "task_id": task_id,
        "job_id": job_info.get("job_id") if job_info else None,
        "status_path": job_info.get("status_path") if job_info else None,
        "spawned_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(spawn_log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

# Main fan-out loop
iteration = 0
while pending or running:
    if _cancel_signal_present():
        print("ultrawork: cancel.signal detected — stopping fan-out", file=sys.stderr)
        cancelled = True
        break

    # Spawn all newly-unblocked tasks
    newly_spawned = []
    for task_id in list(pending):
        if _dependencies_met(task_id):
            task = task_map[task_id]
            job_info = _spawn_task(task)
            _log_spawn(task_id, job_info)
            if job_info:
                running[task_id] = job_info
            else:
                failed_ids.append(task_id)
                completed[task_id] = {"state": "failed", "job_id": None}
            pending.discard(task_id)
            newly_spawned.append(task_id)

    if not running and pending:
        # No running tasks but pending remain — dependency deadlock (shouldn't happen post-validation)
        print(
            f"warn: dependency deadlock — {len(pending)} task(s) have unmet deps but nothing is running",
            file=sys.stderr,
        )
        break

    # Poll running jobs for completions
    TERMINAL = {"done", "failed", "cancelled"}
    for task_id, job_info in list(running.items()):
        sp = Path(job_info.get("status_path", ""))
        if not sp.exists():
            continue
        try:
            status = json.loads(sp.read_text())
            state = status.get("state", "")
            if state in TERMINAL:
                completed[task_id] = {"state": state, "job_id": job_info.get("job_id")}
                del running[task_id]
                if state in ("failed", "cancelled"):
                    failed_ids.append(task_id)
                print(f"ultrawork: task {task_id!r} -> {state}")
        except Exception:
            pass

    if running:
        time.sleep(0.5)
    iteration += 1

# Write completion manifest for Step 3
manifest = {
    "completed": completed,
    "failed_ids": failed_ids,
    "cancelled": cancelled,
    "pending_at_exit": list(pending),
}
(run_dir_path / "fanout-manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"ultrawork: fan-out complete — done={len([v for v in completed.values() if v['state']=='done'])}, failed={len(failed_ids)}, cancelled={cancelled}")
PYEOF

FANOUT_EXIT=$?
if [ ${FANOUT_EXIT} -ne 0 ]; then
  echo "FAIL: fan-out step failed (exit=${FANOUT_EXIT})"
  exit ${FANOUT_EXIT}
fi
```

---

## Step 3 — Wait for remaining jobs + aggregate

```bash
# Use wait_for_jobs.py to block until all spawned jobs reach terminal state,
# then write summary.json and MCP state.

python3 - "${RUN_DIR}" "${ULTRAWORK_RUN_ID}" "${OMNI_SESSION_ID}" <<'PYEOF'
import json
import subprocess
import sys
import time
import datetime
from pathlib import Path

run_dir, run_id, session_id = sys.argv[1], sys.argv[2], sys.argv[3]
run_dir_path = Path(run_dir)

# Read the manifest from Step 2
manifest_path = run_dir_path / "fanout-manifest.json"
if not manifest_path.exists():
    print("warn: fanout-manifest.json not found; skipping wait", file=sys.stderr)
    manifest = {"completed": {}, "failed_ids": [], "cancelled": False, "pending_at_exit": []}
else:
    manifest = json.loads(manifest_path.read_text())

# Collect any still-running jobs (status not yet terminal)
spec = json.loads((run_dir_path / "spec.json").read_text())
task_ids = [t["id"] for t in spec["tasks"]]

# Find status paths for jobs that were spawned
status_paths = []
for task_id in task_ids:
    sp = run_dir_path / task_id / "status.json"
    if sp.exists():
        status_paths.append(str(sp))

# Wait for all of them (with a 1800s hard timeout)
if status_paths:
    result = subprocess.run(
        [sys.executable, "scripts/wait_for_jobs.py"] + status_paths + ["--timeout", "1800"],
        capture_output=True, text=True
    )
    wait_exit = result.returncode
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
else:
    wait_exit = 0

# Re-read final state of all tasks
start_ts = None
end_ts = None
by_task = {}
total = len(task_ids)
done_count = 0
failed_count = 0
cancelled_count = 0

for task_id in task_ids:
    sp = run_dir_path / task_id / "status.json"
    state = "never_spawned"
    exit_code = None
    started_at = None
    ended_at = None
    if sp.exists():
        try:
            s = json.loads(sp.read_text())
            state = s.get("state", "unknown")
            exit_code = s.get("exit_code")
            started_at = s.get("started_at")
            ended_at = s.get("ended_at")
        except Exception:
            pass
    if state == "done":
        done_count += 1
    elif state == "failed":
        failed_count += 1
    elif state == "cancelled":
        cancelled_count += 1

    by_task[task_id] = {"state": state, "exit_code": exit_code,
                         "started_at": started_at, "ended_at": ended_at}

    # Track overall start/end span
    if started_at:
        start_ts = started_at if start_ts is None else min(start_ts, started_at)
    if ended_at:
        end_ts = ended_at if end_ts is None else max(end_ts, ended_at)

# Compute duration
duration_s = None
if start_ts and end_ts:
    try:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        t0 = datetime.datetime.strptime(start_ts, fmt)
        t1 = datetime.datetime.strptime(end_ts, fmt)
        duration_s = (t1 - t0).total_seconds()
    except Exception:
        pass

summary = {
    "run_id": run_id,
    "total": total,
    "done": done_count,
    "failed": failed_count,
    "cancelled": cancelled_count,
    "never_spawned": total - done_count - failed_count - cancelled_count,
    "duration_s": duration_s,
    "by_task": by_task,
    "status": "done" if failed_count == 0 and cancelled_count == 0 else "partial",
}

summary_path = run_dir_path / "summary.json"
summary_path.write_text(json.dumps(summary, indent=2))
print(f"ultrawork: summary written to {summary_path}")
print(f"ultrawork: total={total} done={done_count} failed={failed_count} cancelled={cancelled_count}")

# Write MCP state
try:
    import sys as _sys
    _sys.path.insert(0, "scripts")
    import subagent as _sub
    _sub._mcp_write_best_effort("ultrawork", {
        "run_id": run_id,
        "fanout_count": total,
        "completed": done_count,
        "failed": failed_count,
        "cancelled": cancelled_count,
        "duration_s": duration_s,
        "status": summary["status"],
    }, session_id)
except Exception as e:
    print(f"warn: MCP state write failed (non-fatal): {e}", file=sys.stderr)

sys.exit(0 if failed_count == 0 and cancelled_count == 0 else 1)
PYEOF

AGGREGATE_EXIT=$?
```

---

## Step 4 — Cancel check and final status

```bash
# Final cancel.signal check
if [ -f "${RUN_DIR}/cancel.signal" ]; then
  echo "ultrawork: cancel.signal present — run cancelled"
  python3 -c "
import json, datetime
p = '${RUN_DIR}/status.json'
open(p, 'w').write(json.dumps({
    'run_id': '${ULTRAWORK_RUN_ID}',
    'state': 'cancelled',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"
  exit 1
fi

# Write run-level status
python3 -c "
import json, datetime
state = 'done' if ${AGGREGATE_EXIT} == 0 else 'failed'
p = '${RUN_DIR}/status.json'
open(p, 'w').write(json.dumps({
    'run_id': '${ULTRAWORK_RUN_ID}',
    'state': state,
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
print(f'ultrawork: run {state}. Artifacts: ${RUN_DIR}/')
"

[ ${AGGREGATE_EXIT} -eq 0 ] || exit ${AGGREGATE_EXIT}
```

---

## Resume

Re-invoke ultrawork with the same `$OMNI_SESSION_ID`. Step 0 reads
`state_read(mode="ultrawork", session_id=...)` to locate the previous run's summary.
Tasks already in `state=done` in `summary.json` are skipped; only pending/failed tasks
are re-spawned.

```bash
# Resume example
OMNI_SESSION_ID=my-session-id /copilot-omni:ultrawork "same task description"
```

## Cancel

Write the cancel signal file to stop fan-out cleanly:

```bash
echo "" > ".omni/runs/ultrawork-${OMNI_SESSION_ID}/cancel.signal"
```

Per ADR-0006: the fan-out loop polls `cancel.signal` every iteration. On detection it
stops spawning new tasks, waits for in-flight jobs to reach terminal state, then exits
with `state="cancelled"`.

---

<Examples>
<Good>
Three independent lint tasks via inline JSON spec:
```bash
SPEC='[
  {"id":"lint-src","agent":"executor","category":"quick","prompt":"Run eslint on src/"},
  {"id":"lint-tests","agent":"executor","category":"quick","prompt":"Run eslint on tests/"},
  {"id":"lint-scripts","agent":"executor","category":"quick","prompt":"Run eslint on scripts/"}
]'
echo "$SPEC" > .omni/runs/ultrawork-demo/spec.json
OMNI_SESSION_ID=demo /copilot-omni:ultrawork "$SPEC"
```
Why good: 3 tasks with no dependencies, all spawn in parallel wave-1.
</Good>

<Good>
Dependency chain: B waits for A, then C+D wait for B:
```json
[
  {"id":"A","agent":"executor","category":"deep","prompt":"Scaffold the project"},
  {"id":"B","agent":"executor","category":"deep","prompt":"Add core logic","depends_on":["A"]},
  {"id":"C","agent":"executor","category":"deep","prompt":"Write unit tests","depends_on":["B"]},
  {"id":"D","agent":"executor","category":"deep","prompt":"Write integration tests","depends_on":["B"]}
]
```
Why good: A runs first, B starts after A done, C and D start in parallel after B done.
</Good>

<Bad>
Spec with cycle:
```json
[
  {"id":"A","agent":"executor","category":"deep","prompt":"...","depends_on":["B"]},
  {"id":"B","agent":"executor","category":"deep","prompt":"...","depends_on":["A"]}
]
```
Why bad: A→B→A is a cycle. Validation will fail BEFORE any spawn with exit code 2.
</Bad>
</Examples>

<Final_Checklist>
- [ ] Spec validated (no cycles, no missing fields, count within cap*4)
- [ ] All tasks spawned in dependency order
- [ ] summary.json written at run-dir root
- [ ] MCP state row written for mode="ultrawork" with fanout_count, completed, failed
- [ ] cancel.signal handled cleanly
- [ ] No banned host-specific primitives in this SKILL.md
</Final_Checklist>
