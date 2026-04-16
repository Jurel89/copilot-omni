# Team Orchestration

`/copilot-omni:team` spawns N workers on a shared goal using isolated git worktrees,
tmux (or subprocess fallback), and `scripts/subagent_pool.py` back-pressure.

## Overview

```
User: "/copilot-omni:team 3 fix all TypeScript errors"
              |
              v
      [omni_team.py create]    -- writes manifest.json + status.json
              |
      [omni_team.py dispatch]  -- creates git worktrees, spawns workers
              |
      [omni_team.py collect]   -- waits for all workers to finish
              |
      [omni_team.py cleanup]   -- removes worktrees, clears state
```

Each worker operates in its own branch (`team-<id>/<slug>`) and worktree
(`.omni/runs/team-<id>/workers/<slug>/worktree/`), preventing file conflicts.

## tmux vs Subprocess Fallback

| Condition | Host Used |
|-----------|-----------|
| Linux/macOS + `tmux` on PATH | `_TmuxWorkerHost` (one window per worker) |
| `use_tmux=False` OR tmux absent | `_SubprocessWorkerHost` (detached processes) |
| Windows + `OMNI_EXPERIMENTAL_TEAM=1` | tmux attempted (WARNING emitted) |
| Windows without flag | `_SubprocessWorkerHost` always |

The subprocess fallback is first-class and works identically on all platforms.
Set `use_tmux=False` explicitly to disable tmux even when it is available.

## Plan Schema (manifest.json)

```json
{
  "run_id": "team-<uuid12>",
  "name": "<team-name>",
  "session_id": "<session>",
  "created_at": "2026-01-01T00:00:00Z",
  "tmux_session": "omni-team-<run_id>" ,
  "use_tmux": true,
  "base_branch": "main",
  "workers": [
    {
      "slug": "worker-1",
      "skill": "ralph",
      "prompt": "Fix type errors in src/auth/",
      "category": "deep",
      "worktree_path": ".omni/runs/team-<id>/workers/worker-1/worktree",
      "branch": "team-<id>/worker-1",
      "run_dir": ".omni/runs/team-<id>/workers/worker-1",
      "status": "pending|running|done|failed|cancelled"
    }
  ]
}
```

## Running Your First Team

### 1. Write a plan file

```bash
cat > /tmp/my-plan.json << 'EOF'
{
  "base_branch": "main",
  "workers": [
    {
      "slug": "auth-fixer",
      "skill": "ralph",
      "prompt": "Fix all TypeScript errors in src/auth/. Run tsc --noEmit to verify.",
      "category": "deep"
    },
    {
      "slug": "api-fixer",
      "skill": "ralph",
      "prompt": "Fix all TypeScript errors in src/api/. Run tsc --noEmit to verify.",
      "category": "deep"
    }
  ]
}
EOF
```

### 2. Create the team

```bash
python3 scripts/omni_team.py create "fix-ts-errors" \
  --plan /tmp/my-plan.json \
  --session-id "$OMNI_SESSION_ID"
# -> {"run_id": "team-abc123def456", "manifest_path": "...", ...}
```

### 3. Dispatch workers

```bash
python3 scripts/omni_team.py dispatch team-abc123def456
# -> [{"slug": "auth-fixer", "pid": 12345, ...}, ...]
```

### 4. Monitor progress

```bash
python3 scripts/omni_team.py status team-abc123def456
# -> {run_id, state, workers: [{slug, state, started_at, ...}]}
```

### 5. Collect results

```bash
python3 scripts/omni_team.py collect team-abc123def456 --timeout 3600
# Blocks until all workers finish
# -> {"run_id": "...", "state": "done", "workers": [...]}
```

### 6. Cleanup

```bash
python3 scripts/omni_team.py cleanup team-abc123def456
# Removes worktrees, prunes git state
```

### Smoke test with fake workers

```bash
OMNI_SUBAGENT_FAKE=1 OMNI_SESSION_ID=ws6-smoke \
  python3 scripts/omni_team.py create "demo" --plan /tmp/my-plan.json
# -> {"run_id": "team-<id>", ...}

python3 scripts/omni_team.py dispatch team-<id>
python3 scripts/omni_team.py collect team-<id>
python3 scripts/omni_team.py cleanup team-<id>
```

## Composing Teams with Ralph / Autopilot

Set `"skill": "ralph"` or `"skill": "autopilot"` per worker in the plan.

Each worker spawns the corresponding skill as a subprocess with `--parent-run-id`
pointing to the team run-dir. This enables cancel cascade: writing
`cancel.signal` at the team level propagates to all worker skills.

**Nested mode keys** (ADR-0006 §3):

| Mode key | Description |
|----------|-------------|
| `team` | Outer team orchestration state |
| `team.<slug>` | Per-worker team state |
| `team.<slug>.ralph` | Inner ralph run nested under worker |
| `team.<slug>.autopilot` | Inner autopilot run nested under worker |

## Cancel and Cleanup Semantics

### Cancel

```bash
python3 scripts/omni_team.py cancel team-<id> [--reason TEXT]
```

1. Writes `cancel.signal` at `.omni/runs/team-<id>/cancel.signal` (team root).
2. Writes `cancel.signal` in each worker's run-dir.
3. Workers (subagent.py) poll `PARENT_RUN_DIR/cancel.signal` and stop.
4. All worker `status.json` files transition to `state: "cancelled"`.
5. Team `status.json` transitions to `state: "cancelled"`.

### Cleanup

```bash
python3 scripts/omni_team.py cleanup team-<id> [--force]
```

1. Calls `omni_worktree.remove()` for each worker — removes worktree + branch.
2. Kills tmux session (if present).
3. Writes `state: "cleaned"` to team `status.json`.
4. Clears MCP state (best-effort).

Use `--force` to continue past errors (e.g. manually deleted worktree dirs).

### Orphan Recovery

If a worktree dir was manually deleted, `cleanup --force` still succeeds:
- `omni_worktree.remove` calls `git worktree prune` first to clear stale entries.
- Prune handles the case where the dir is already gone.

## Windows Experimental Caveat

tmux is not natively available on Windows. To use tmux on Windows, set:

```bash
set OMNI_EXPERIMENTAL_TEAM=1
```

**WARNING:** tmux on Windows requires a compatible tmux binary (e.g. via WSL or
Cygwin). This is experimental and unsupported. Without the env-var, the
subprocess fallback is used automatically — this is the recommended path on Windows.

## Limitations

- **Single-host only**: no distributed or cross-machine workers.
- **Per-host cap**: `min(8, cpu_count)` concurrent workers (ADR-0010 back-pressure).
- **No dynamic scaling**: add/remove workers after dispatch not supported.
- **Windows tmux**: experimental only (`OMNI_EXPERIMENTAL_TEAM=1` required).
- **No result merging**: each worker's worktree branch must be merged manually
  after collection (or via a post-collect step in the team recipe).

## CLI Reference

```
python3 scripts/omni_team.py create <name> --plan <plan.json> [--session-id ID]
python3 scripts/omni_team.py dispatch <run_id>
python3 scripts/omni_team.py collect <run_id> [--timeout SECS]
python3 scripts/omni_team.py cancel <run_id> [--reason TEXT]
python3 scripts/omni_team.py cleanup <run_id> [--force]
python3 scripts/omni_team.py status <run_id>
```
