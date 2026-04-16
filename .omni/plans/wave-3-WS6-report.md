# WS6 Completion Report — Team Orchestration Rebuild

## Orchestrator Architecture

`scripts/omni_team.py` (~500 LOC) implements the full team lifecycle:

```
create_team()  → writes manifest.json + status.json
dispatch_workers() → creates worktrees, spawns workers via host
collect_results() → polls status.json via wait_for_jobs
cancel_team() → writes cancel.signal at team + worker level
cleanup_team() → removes worktrees, kills tmux, clears state
status_team() → returns per-worker snapshot
```

### tmux vs subprocess hosts

| Host | Class | When used |
|------|-------|-----------|
| `_TmuxSession` | tmux session manager | Linux/macOS + tmux on PATH + use_tmux=True |
| `_TmuxWorkerHost` | tmux-backed worker host | Same as above |
| `_SubprocessWorkerHost` | subprocess fallback | tmux absent, use_tmux=False, or Windows |

Both hosts satisfy the same interface: `launch(worker)`, `is_worker_alive(slug)`,
`collect_log(slug)`, `kill_worker(slug)`.

## Worker Lifecycle + Status Protocol

Worker status.json schema:
```json
{
  "state": "pending|running|done|failed|cancelled",
  "slug": "<slug>",
  "run_id": "<run_id>",
  "pid": 12345,
  "started_at": "ISO",
  "ended_at": "ISO | null"
}
```

Lifecycle: `pending → running → done|failed|cancelled`

`wait_for_jobs.py` polls all worker `status.json` files with configurable
poll_interval (default 1s) and timeout (default 3600s).

## Worktree Layout + Branch Naming

```
.omni/runs/team-<id>/
  manifest.json
  status.json
  cancel.signal          # created on cancel
  workers/
    <slug>/
      worktree/          # git worktree root (branch: team-<id>/<slug>)
      status.json
      stdout.log
      stderr.log
      inner/             # inner skill (ralph/autopilot) run-dir
```

`scripts/omni_worktree.py` (~280 LOC) wraps `git worktree add/remove/list/prune`:
- Sanitizes slugs and run-ids to safe branch-name components.
- Falls back to HEAD if the specified base_branch doesn't exist.
- Calls `git worktree prune` before remove to handle manually-deleted dirs.

## Composition with Ralph / Autopilot (Nested Run-Dirs + Mode Keys)

Workers are spawned via `subagent.py --background --parent-run-id <team-run-id>`.
The `skill` field in the worker spec maps to `ralph` or `autopilot`:

```
team                                   (outer orchestration)
  team.worker-1                        (per-worker state)
    team.worker-1.ralph                (inner ralph state, written by ralph skill)
  team.worker-2
    team.worker-2.autopilot            (inner autopilot state)
```

`--parent-run-id` passes the team run-dir path to subagent.py via environment:
```
PARENT_RUN_ID=team-<id>
PARENT_RUN_DIR=.omni/runs/team-<id>
```

Workers poll `PARENT_RUN_DIR/cancel.signal` for cascade cancellation.

## Cancel Cascade Flow

```
omni_team.py cancel <run_id>
  │
  ├── writes .omni/runs/team-<id>/cancel.signal
  │
  └── for each worker:
        writes .omni/runs/team-<id>/workers/<slug>/cancel.signal
        updates status.json → state="cancelled"

Workers (subagent.py) poll cancel.signal via PARENT_RUN_DIR
  → transitions to state="cancelled"
  → exits cleanly

Team status.json → state="cancelled"
```

Cancel.signal files contain JSON: `{reason, requested_at, run_id}`.

## Cleanup Semantics + Orphan Recovery

Normal cleanup:
1. `omni_worktree.remove(run_id, slug)` for each worker.
2. `git worktree prune` to clean stale entries.
3. Kills tmux session if present.
4. Writes `state: "cleaned"` to team status.json.

Force mode (`--force`):
- Continues past individual errors (e.g. git errors on missing worktrees).
- Uses `git worktree prune` before every remove to handle orphan dirs.

If a worktree dir was manually deleted, `git worktree prune` removes the stale
registry entry, so subsequent `git worktree remove` succeeds without error.

## Test Coverage Summary

`tests/test_omni_team.py` — 18 tests:
1. create_team writes manifest + status files
2. dispatch_workers creates worker dirs
3. Cap-respecting dispatch via SubagentPool
4. tmux session creates when available (skip if no tmux)
5. Subprocess fallback when use_tmux=False
6. collect_results aggregates worker summaries
7. Cancel cascade: cancel.signal + worker states
8. Cleanup removes worktrees via omni_worktree
9. Windows experimental guard
10. Windows subprocess fallback always works
11. Team + ralph composition (--parent-run-id in cmd)
12. Team + autopilot composition
13. Orphan-worktree recovery with force=True
14. MCP state writes under team / team.<slug> modes
15. Cancel signal pairing validator
16. Concurrent teams share pool back-pressure
17. status_team returns per-worker states
18. CLI --help shows all subcommands + collect fails on worker failure

`tests/test_omni_worktree.py` — 7 tests:
1. add creates worktree + branch
2. remove deletes worktree
3. list_for_team filters correctly
4. prune runs without error
5. remove robust to manually deleted dir
6. add falls back when base branch missing
7. CLI add command

## Windows Posture

- Subprocess fallback is **first-class** on all platforms (no tmux needed).
- `create_team` auto-selects `use_tmux=False` on Windows when
  `OMNI_EXPERIMENTAL_TEAM` is not set.
- `_TmuxSession.create()` raises `RuntimeError` on Windows without guard.
- Guard test validates this behavior at the API level.

## Residual TODO-Phase-C Items

- **Distributed teams**: cross-host orchestration (different machines) not supported.
- **Branch merging**: post-collect merge of worker branches not automated.
- **Dynamic scaling**: add/remove workers mid-run not supported.
- **Worker health monitoring**: no active watchdog beyond status.json polling.
- **Result aggregation**: no structured output format beyond log tail.

## Handoff for WS10 (Test Strategy)

- `OMNI_SUBAGENT_FAKE=1` + `OMNI_SUBAGENT_FAKE_RESPONSE_FILE` patterns work for
  team worker determinism; extend response files for multi-worker scenarios.
- `tests/test_omni_team.py` test 15 (concurrent teams + pool) demonstrates the
  pattern for testing back-pressure across multiple orchestrators.
- tmux tests are gated with `pytest.mark.tmux` and `shutil.which("tmux")` skip.

## Handoff for WS11 (Documentation)

- `docs/TEAM.md` is the user-facing reference (linked from SKILL.md header).
- `skills/team/SKILL.md` rewritten to use omni_team.py recipe steps.
- `docs/STATE_MODES.md` updated with team + team.<worker-slug> + nested keys.
- All `SendMessage(`, `TeamCreate(`, `TeamDelete(` primitives removed from skills/.

## Validator Additions

`scripts/verify_plugin_contract.py` gained two new checks:

- `check_team_modes_declared`: verifies team modes in code are in STATE_MODES.md
- `check_worktree_hygiene`: detects orphan worktrees in non-terminal team runs

Both are registered in `CHECKS` and run under `--all`.

## Doctor Integration

`scripts/omni.py` `_cmd_doctor` now calls `_doctor_team_runs(root, strict=strict)`:
- Shows active team runs with worker counts.
- In `--strict` mode, warns if any team has been `dispatched` for >24h.
