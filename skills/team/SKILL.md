---
name: team
description: Orchestrate N workers on a shared goal using tmux+worktrees+subagent back-pressure
argument-hint: "[N] [ralph|autopilot] <task description>"
aliases: []
level: 4
---

# Team Skill

> User-facing reference: `docs/TEAM.md`

Spawn N coordinated workers on a shared goal using `scripts/omni_team.py`. Each worker
runs in an isolated git worktree with its own branch. Workers are dispatched via
`scripts/subagent.py --background` (with tmux windows on Linux/macOS when available). <!-- omni-ref-allow: example -->
Back-pressure is enforced via `scripts/subagent_pool.py` (cap = `min(8, cpu_count)`).

## Resume preamble

Before running, load the session-scoped state and check for an active team run:

```bash
state_read(mode="team", session_id="$OMNI_SESSION_ID")
```

If `body.active == true` and a `run_id` is present → **Resume** the existing run
instead of creating a new one (see Resume section below).

## Usage

```
/copilot-omni:team N "task description"
/copilot-omni:team ralph "task description"
/copilot-omni:team autopilot "task description"
/copilot-omni:team 4 ralph "build a REST API"
```

### Parameters

- **N** — Number of workers (1-20). Optional; auto-sized from task decomposition.
- **ralph** — Wrap workers in ralph persistence loop (nested mode `team.<slug>.ralph`).
- **autopilot** — Wrap workers in autopilot (nested mode `team.<slug>.autopilot`).
- **task** — High-level task to decompose and distribute.

### Examples

```bash
/copilot-omni:team 3 "fix all TypeScript errors across the project"
/copilot-omni:team ralph "build a complete REST API for user management"
/copilot-omni:team 4 autopilot "implement responsive layouts for all pages"
```

## Architecture

```
User: "/copilot-omni:team 3 fix all TypeScript errors"
              |
              v
      [omni_team.py create]
              |
              +-- Writes .omni/runs/team-<id>/manifest.json
              |
      [Analyze & decompose task into worker plans]
              |
              v
      [omni_team.py dispatch <run_id>]
              |
              +-- For each worker:
              |     1. omni_worktree.add(run_id, slug, base_branch)
              |        -> .omni/runs/team-<id>/workers/<slug>/worktree/
              |        -> branch: team-<id>/<slug>
              |     2. subagent.py <skill> <prompt> --background
              |           --run-id team-<id>/<slug>
              |           --parent-run-id team-<id>
              |     (tmux: each worker gets its own window)
              |     (subprocess: each worker is a detached process)
              |
      [omni_team.py collect <run_id>]
              |
              +-- wait_for_jobs polls .../workers/<slug>/status.json
              |
      [omni_team.py cleanup <run_id>]
              |
              +-- Removes worktrees, clears MCP state
```

**Run-directory layout:**
```
.omni/runs/team-<id>/
  manifest.json          # team definition + worker list
  status.json            # team-level status
  cancel.signal          # presence = cancel requested
  workers/
    <slug>/
      worktree/          # git worktree (isolated branch)
      status.json        # worker status (polled by wait_for_jobs)
      stdout.log
      stderr.log
      inner/             # inner skill (ralph/autopilot) run-dir
```

## Manifest JSON

```json
{
  "run_id": "team-<uuid>",
  "name": "<team-name>",
  "session_id": "<session>",
  "created_at": "<iso>",
  "tmux_session": "<name>" ,
  "use_tmux": true,
  "workers": [
    {
      "slug": "<slug>",
      "skill": "ralph|autopilot",
      "prompt": "...",
      "category": "quick|deep|ultrabrain",
      "worktree_path": ".omni/runs/team-<id>/workers/<slug>/worktree",
      "branch": "team-<id>/<slug>",
      "run_dir": ".omni/runs/team-<id>/workers/<slug>",
      "status": "pending|running|done|failed|cancelled"
    }
  ]
}
```

## Workflow

### Phase 1: Decompose

Analyze the task and produce a worker plan list. Each worker needs:
- `slug`: short identifier (e.g. `worker-1`, `auth-fixer`)
- `skill`: `ralph` (persistence loop) or `autopilot` (staged pipeline) — default `ralph`
- `prompt`: full task instruction including context from codebase exploration
- `category`: `quick` / `deep` / `ultrabrain` (affects model tier via category_resolver)

For 1-3 workers: `ralph` skill is usually sufficient.
For complex parallel work: `autopilot` skill provides staged verify/fix loops.

### Phase 2: Create Team

```bash
# Write plan JSON
cat > /tmp/plan.json << 'EOF'
{
  "base_branch": "main",
  "workers": [
    {"slug": "worker-1", "skill": "ralph", "prompt": "Fix type errors in src/auth/", "category": "deep"},
    {"slug": "worker-2", "skill": "ralph", "prompt": "Fix type errors in src/api/", "category": "deep"}
  ]
}
EOF

python3 scripts/omni_team.py create "fix-ts-errors" --plan /tmp/plan.json --session-id "$OMNI_SESSION_ID"
# -> {"run_id": "team-abc123", "manifest_path": "...", "status_path": "...", "created_at": "..."}
```

Write state (session-scoped per ADR-0006):
```
state_write(mode="team", session_id="$OMNI_SESSION_ID", body={
  "active": true,
  "run_id": "team-abc123",
  "name": "fix-ts-errors",
  "phase": "created",
  "worker_count": 2
})
```

### Phase 3: Dispatch Workers

```bash
python3 scripts/omni_team.py dispatch team-abc123
# -> [{"slug": "worker-1", "pid": 12345, "status_path": "...", ...}, ...]
```

State update (session-scoped):
```
state_write(mode="team", session_id="$OMNI_SESSION_ID",
            body={"phase": "dispatched"})
state_write(mode="team.worker-1", session_id="$OMNI_SESSION_ID",
            body={"active": true, "run_id": "team-abc123", "skill": "ralph"})
state_write(mode="team.worker-2", session_id="$OMNI_SESSION_ID",
            body={"active": true, "run_id": "team-abc123", "skill": "ralph"})
```

### Phase 4: Collect Results

```bash
python3 scripts/omni_team.py collect team-abc123 --timeout 3600
# Blocks until all workers reach terminal state (done/failed/cancelled)
# -> {"run_id": "...", "state": "done", "workers": [...]}
```

### Phase 5: Cleanup

```bash
python3 scripts/omni_team.py cleanup team-abc123
# Removes worktrees, prunes git state, clears transient artifacts
```

State cleanup:
```
state_clear(mode="team", session_id=<id>)
state_clear(mode="team.worker-1", session_id=<id>)
state_clear(mode="team.worker-2", session_id=<id>)
```

## Team + Ralph Composition

When the `ralph` modifier is used, each worker's skill is set to `ralph`. The worker
runs a full ralph persistence loop in its isolated worktree. Nested mode keys:

- `team` — outer team orchestration state
- `team.<slug>` — per-worker team state
- `team.<slug>.ralph` — inner ralph run (written by ralph skill inside the worker)

Worker prompts should include `--parent-run-id team-<id>` so ralph's cancel cascade
can propagate from the team level down to individual worker runs.

## Team + Autopilot Composition

Same pattern but with `autopilot` skill. Nested mode keys:

- `team.<slug>.autopilot` — inner autopilot run

## tmux vs Subprocess

| Condition | Host Used |
|-----------|-----------|
| Linux/macOS + tmux on PATH + `use_tmux=True` | `_TmuxWorkerHost` (one window per worker) |
| `use_tmux=False` OR tmux absent | `_SubprocessWorkerHost` (detached processes) |
| Windows + `OMNI_EXPERIMENTAL_TEAM=1` | tmux attempted (WARNING emitted) |
| Windows + no `OMNI_EXPERIMENTAL_TEAM` | `_SubprocessWorkerHost` always |

The subprocess fallback is first-class and works identically on all platforms.

## Cancel Protocol

Cancel cascade follows ADR-0006 signal-file protocol:

1. `omni_team.py cancel <run_id>` writes `cancel.signal` at:
   - `.omni/runs/team-<id>/cancel.signal` (team root)
   - `.omni/runs/team-<id>/workers/<slug>/cancel.signal` (each worker)
2. Worker processes (subagent.py) poll `PARENT_RUN_DIR/cancel.signal` and stop.
3. Worker status.json transitions to `state: "cancelled"`.
4. Team status.json transitions to `state: "cancelled"`.

```bash
python3 scripts/omni_team.py cancel team-abc123 --reason "user"
```

## Resume

If `state_read(mode="team", session_id="$OMNI_SESSION_ID")` returns `body.active == true` with a `run_id`:

1. Check `omni_team.py status <run_id>` for current phase.
2. If `state: "created"` → jump to dispatch phase.
3. If `state: "dispatched"` → jump to collect phase.
4. If `state: "done"|"failed"|"cancelled"` → report results.

## Worker Status Protocol

Each worker's `status.json` schema:
```json
{
  "state": "pending|running|done|failed|cancelled",
  "slug": "<slug>",
  "run_id": "<run_id>",
  "pid": 12345,
  "started_at": "2026-01-01T00:00:00Z",
  "ended_at": null
}
```

`wait_for_jobs.py` polls these files until all reach terminal state.

## State Schema

```
state_write(mode="team", session_id="$OMNI_SESSION_ID", body={
  "active": true,
  "run_id": "team-abc123",
  "name": "<team-name>",
  "phase": "created|dispatched|collecting|done|failed|cancelled",
  "worker_count": N,
  "use_tmux": true|false
})
```

Per-worker state:
```
state_write(mode="team.<slug>", session_id="$OMNI_SESSION_ID", body={
  "active": true,
  "run_id": "team-abc123",
  "slug": "<slug>",
  "skill": "ralph|autopilot",
  "state": "pending|running|done|failed|cancelled"
})
```

## Error Handling

### Worker Fails

1. `collect_results` detects `state: "failed"` in worker's status.json.
2. Overall team state becomes `"failed"` if any worker failed.
3. Log tail is available in `workers/<slug>/stdout.log`.

### Worker Stuck

1. `omni_team.py status <run_id>` shows per-worker states.
2. If stuck > 30 min: `omni_team.py cancel <run_id>` to terminate.
3. Investigate `workers/<slug>/stdout.log` for root cause.

### Orphan Worktree Recovery

If a worktree dir was deleted manually, `cleanup_team --force` still succeeds:
- `omni_worktree.remove` calls `git worktree prune` first.
- If dir is already gone, prune handles the stale entry.

```bash
python3 scripts/omni_team.py cleanup team-abc123 --force
```

## Limitations

- Single-host only (no distributed / cross-machine workers).
- Per-host cap: `min(8, cpu_count)` concurrent workers (ADR-0010).
- No dynamic scaling mid-run (add/remove workers after dispatch not supported).
- Windows tmux is experimental (`OMNI_EXPERIMENTAL_TEAM=1` required).
