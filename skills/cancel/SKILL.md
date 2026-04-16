---
name: cancel
description: Cancel any active copilot-omni mode (autopilot, ralph, ultrawork, ultraqa, swarm, ultrapilot, pipeline, team)
argument-hint: "[--force|--all]"
level: 2
---

# Cancel Skill

Intelligent cancellation that detects and cancels the active copilot-omni mode.

**The cancel skill is the standard way to complete and exit any copilot-omni mode.**
When the stop hook detects work is complete, it instructs the LLM to invoke
this skill for proper state cleanup. If cancel fails or is interrupted,
retry with `--force` flag, or wait for the 2-hour staleness timeout as
a last resort.

## What It Does

Automatically detects which mode is active and cancels it:
- **Autopilot**: Stops workflow, preserves progress for resume
- **Ralph**: Stops persistence loop, clears linked ultrawork if applicable
- **Ultrawork**: Stops parallel execution (standalone or linked)
- **UltraQA**: Stops QA cycling workflow
- **Swarm**: Stops coordinated agent swarm, releases claimed tasks
- **Ultrapilot**: Stops parallel autopilot workers
- **Pipeline**: Stops sequential agent pipeline
- **Team**: Signals all workers via cancel cascade (`omni_team.py cancel`), waits for responses, runs cleanup, clears linked ralph if present
- **Team+Ralph (linked)**: Cancels team first (graceful shutdown), then clears ralph state. Cancelling ralph when linked also cancels team first.

## Usage

```
/copilot-omni:cancel
```

Or say: "cancelomc", "stopomc"

## Critical: Deferred Tool Handling

The state management tools (`state_clear`, `state_read`, `state_write`, `state_list`,
`state_get_status`) may be registered as **deferred tools** by Claude Code. Before calling
any state tool, you MUST first load all of them via `ToolSearch`:

```bash
# Load state MCP tools before calling any state_* function
# (Copilot CLI: use scripts/subagent.py state_clear / state_read / state_write as fallback)
python3 scripts/subagent.py state_read "check active mode" 2>/dev/null || true
```

If `state_clear` is unavailable or fails, use this **bash fallback** as an **emergency
escape from the stop hook loop**. This is NOT a full replacement for the cancel flow —
it only removes state files to unblock the session. Linked modes (e.g. ralph→ultrawork,
autopilot→ralph/ultraqa) must be cleared separately by running the fallback once per mode.

Replace `MODE` with the specific mode (e.g. `ralplan`, `ralph`, `ultrawork`, `ultraqa`).

**WARNING:** Do NOT use this fallback for `autopilot` or `omni-teams`. Autopilot requires
`state_write(active=false)` to preserve resume data. omni-teams requires tmux session
cleanup that cannot be done via file deletion alone.

```bash
# Fallback: direct file removal when state_clear MCP tool is unavailable
SESSION_ID="${OMNI_SESSION_ID:-}"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || { d="$PWD"; while [ "$d" != "/" ] && [ ! -d "$d/.omni" ]; do d="$(dirname "$d")"; done; echo "$d"; })"

# Resolve state directory (OMNI_PLUGIN_ROOT primary, CLAUDE_PLUGIN_ROOT legacy fallback)
PLUGIN_ROOT="${OMNI_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}"
if [ -n "${OMNI_STATE_DIR:-}" ]; then
  OMNI_STATE="$OMNI_STATE_DIR/state"
  [ ! -d "$OMNI_STATE" ] && { echo "ERROR: State dir not found at $OMNI_STATE" >&2; exit 1; }
elif [ "$REPO_ROOT" != "/" ] && [ -d "$REPO_ROOT/.omni" ]; then
  OMNI_STATE="$REPO_ROOT/.omni/state"
else
  echo "ERROR: Could not locate .omni state directory" >&2
  exit 1
fi
MODE="ralplan"  # <-- replace with the target mode

# Clear session-scoped state for the specific mode
if [ -n "$SESSION_ID" ] && [ -d "$OMNI_STATE/sessions/$SESSION_ID" ]; then
  rm -f "$OMNI_STATE/sessions/$SESSION_ID/${MODE}-state.json"
  rm -f "$OMNI_STATE/sessions/$SESSION_ID/${MODE}-stop-breaker.json"
  rm -f "$OMNI_STATE/sessions/$SESSION_ID/skill-active-state.json"
  # Write cancel signal so stop hook detects cancellation in progress
  NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  EXPIRES_ISO="$(date -u -d "+30 seconds" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || python3 - <<'PY'\nfrom datetime import datetime, timedelta, timezone\nprint((datetime.now(timezone.utc) + timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%SZ'))\nPY\n)"
  printf '{"active":true,"requested_at":"%s","expires_at":"%s","mode":"%s","source":"bash_fallback"}' \
    "$NOW_ISO" "$EXPIRES_ISO" "$MODE" > "$OMNI_STATE/sessions/$SESSION_ID/cancel-signal-state.json"
fi

# Clear legacy state only if no session ID (avoid clearing another session's state)
if [ -z "$SESSION_ID" ]; then
  rm -f "$OMNI_STATE/${MODE}-state.json"
fi
```

## Auto-Detection

`/copilot-omni:cancel` follows the session-aware state contract:
- By default the command inspects the current session via `state_list` and `state_get_status`, navigating `.omni/state/sessions/{sessionId}/…` to discover which mode is active.
- When a session id is provided or already known, that session-scoped path is authoritative. Legacy files in `.omni/state/*.json` are consulted only as a compatibility fallback if the session id is missing or empty.
- Swarm is a shared SQLite/marker mode (`.omni/state/swarm.db` / `.omni/state/swarm-active.marker`) and is not session-scoped.
- The default cleanup flow calls `state_clear` with the session id to remove only the matching session files; modes stay bound to their originating session.

Active modes are still cancelled in dependency order:
1. Autopilot (includes linked ralph/ultraqa/ cleanup)
2. Ralph (cleans its linked ultrawork or )
3. Ultrawork (standalone)
4. UltraQA (standalone)
5. Swarm (standalone)
6. Ultrapilot (standalone)
7. Pipeline (standalone)
8. Team (Claude Code native)
9. copilot-omni Teams (tmux CLI workers)
10. Plan Consensus (standalone)
11. Self-Improve (standalone — clear state, clean orphaned worktrees, preserve iteration_state for resume, set status: "user_stopped" in .omni/self-improve/state/agent-settings.json)

## Force Clear All

Use `--force` or `--all` when you need to erase every session plus legacy artifacts, e.g., to reset the workspace entirely.

```
/copilot-omni:cancel --force
```

```
/copilot-omni:cancel --all
```

Steps under the hood:
1. `state_list` enumerates `.omni/state/sessions/{sessionId}/…` to find every known session.
2. `state_clear` runs once per session to drop that session’s files.
3. A global `state_clear` without `session_id` removes legacy files under `.omni/state/*.json`, `.omni/state/swarm*.db`, and compatibility artifacts (see list).
4. Team artifacts (`~/.claude/teams/*/`, `~/.claude/tasks/*/`, `.omni/state/team-state.json`) are best-effort cleared as part of the legacy fallback.
   - Cancel for native team does NOT affect omni-teams state, and vice versa.

Every `state_clear` command honors the `session_id` argument, so even force mode still uses the session-aware paths first before deleting legacy files.

Legacy compatibility list (removed only under `--force`/`--all`):
- `.omni/state/autopilot-state.json`
- `.omni/state/ralph-state.json`
- `.omni/state/ralph-plan-state.json`
- `.omni/state/ralph-verification.json`
- `.omni/state/ultrawork-state.json`
- `.omni/state/ultraqa-state.json`
- `.omni/state/swarm.db`
- `.omni/state/swarm.db-wal`
- `.omni/state/swarm.db-shm`
- `.omni/state/swarm-active.marker`
- `.omni/state/swarm-tasks.db`
- `.omni/state/ultrapilot-state.json`
- `.omni/state/ultrapilot-ownership.json`
- `.omni/state/pipeline-state.json`
- `.omni/state/omni-teams-state.json`
- `.omni/state/plan-consensus.json`
- `.omni/state/ralplan-state.json`
- `.omni/state/boulder.json`
- `.omni/state/hud-state.json`
- `.omni/state/subagent-tracking.json`
- `.omni/state/subagent-tracker.lock`
- `.omni/state/rate-limit-daemon.pid`
- `.omni/state/rate-limit-daemon.log`
- `.omni/state/checkpoints/` (directory)
- `.omni/state/sessions/` (empty directory cleanup after clearing sessions)

## Implementation Steps

When you invoke this skill:

### 1. Parse Arguments

```bash
# Check for --force or --all flags
FORCE_MODE=false
if [[ "$*" == *"--force"* ]] || [[ "$*" == *"--all"* ]]; then
  FORCE_MODE=true
fi
```

### 2. Detect Active Modes

The skill now relies on the session-aware state contract rather than hard-coded file paths:
1. Call `state_list` to enumerate `.omni/state/sessions/{sessionId}/…` and discover every active session.
2. For each session id, call `state_get_status` to learn which mode is running (`autopilot`, `ralph`, `ultrawork`, etc.) and whether dependent modes exist.
3. If a `session_id` was supplied to `/copilot-omni:cancel`, skip legacy fallback entirely and operate solely within that session path; otherwise, consult legacy files in `.omni/state/*.json` only if the state tools report no active session. Swarm remains a shared SQLite/marker mode outside session scoping.
4. Any cancellation logic in this doc mirrors the dependency order discovered via state tools (autopilot → ralph → …).

### 3A. Force Mode (if --force or --all)

Use force mode to clear every session plus legacy artifacts via `state_clear`. Direct file removal is reserved for legacy cleanup when the state tools report no active sessions.

### 3B. Smart Cancellation (default)

#### If Team Active (Claude Code native)

Teams are detected by checking for config files in `${CLAUDE_CONFIG_DIR:-~/.claude}/teams/`:

```bash
# Check for active teams
TEAM_CONFIGS=$(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/teams -name config.json -maxdepth 2 2>/dev/null)
```

**Cancellation protocol (WS6 — omni_team.py):**

**Pass 1: Signal workers via cancel cascade**
```bash
# Write cancel.signal at team root + every worker run-dir
python3 scripts/omni_team.py cancel <run_id> --reason "user-cancel"
# -> workers poll PARENT_RUN_DIR/cancel.signal and stop
# -> worker status.json transitions to state="cancelled"
# -> team status.json transitions to state="cancelled"
```

**Pass 2: Cleanup**
```bash
python3 scripts/omni_team.py cleanup <run_id>
# -> removes worktrees, prunes git state, clears transient artifacts
```

**State Cleanup:**
```
  1. state_clear(mode="team", session_id)
  2. For each worker slug: state_clear(mode="team.<slug>", session_id)
  3. If linked ralph: state_clear(mode="ralph", session_id)
  4. If linked ultrawork: state_clear(mode="ultrawork", session_id)
  5. Emit structured cancel report
```

**Orphan Detection (Post-Cleanup):**

After cleanup, verify no agent processes remain using the Python orchestrator:
```bash
# Check for orphan workers (processes still running after cancel+cleanup)
python3 scripts/omni_team.py cleanup <run_id> --force
```

The cleanup command removes worktrees, prunes git state, and clears transient artifacts.
Use `--force` to remove even workers that have not reached a terminal state.

**Structured Cancel Report:**
```
Team "{team_name}" cancelled:
  - Members signaled: N
  - Responses received: M
  - Unresponsive: K (list names if any)
  - Cleanup: success/failed
  - Manual cleanup needed: yes/no
    Path: .omni/runs/team-{run_id}/
```

**Implementation note:** The cancel skill is executed by the LLM, not as a bash script. When you detect an active team (WS6 runtime):
1. Read team state via `state_read(mode="team", session_id)` to get the `run_id`
2. Cancel via orchestrator: `python3 scripts/omni_team.py cancel <run_id> --reason "user-cancel"`
   (This writes cancel.signal at team root + each worker dir; workers poll and stop)
3. Wait up to 15s for worker status.json files to transition to `state="cancelled"`
4. Cleanup: `python3 scripts/omni_team.py cleanup <run_id>`
   (Removes worktrees, prunes git state)
5. Clear team state: `state_clear(mode="team", session_id)`
6. For each worker slug found in manifest: `state_clear(mode="team.<slug>", session_id)`
7. Report structured summary to user

#### If Autopilot Active

Autopilot handles its own cleanup including linked ralph and ultraqa.

1. Read autopilot state via `state_read(mode="autopilot", session_id)` to get current phase
2. Check for linked ralph via `state_read(mode="ralph", session_id)`:
   - If ralph is active and has `linked_ultrawork: true`, clear ultrawork first: `state_clear(mode="ultrawork", session_id)`
   - Clear ralph: `state_clear(mode="ralph", session_id)`
3. Check for linked ultraqa via `state_read(mode="ultraqa", session_id)`:
   - If active, clear it: `state_clear(mode="ultraqa", session_id)`
4. Mark autopilot inactive (preserve state for resume) via `state_write(mode="autopilot", session_id, state={active: false, ...existing})`

#### If Ralph Active (but not Autopilot)

1. Read ralph state via `state_read(mode="ralph", session_id)` to check for linked ultrawork
2. If `linked_ultrawork: true`:
   - Read ultrawork state to verify `linked_to_ralph: true`
   - If linked, clear ultrawork: `state_clear(mode="ultrawork", session_id)`
3. Clear ralph: `state_clear(mode="ralph", session_id)`

#### If Ultrawork Active (standalone, not linked)

1. Read ultrawork state via `state_read(mode="ultrawork", session_id)`
2. If `linked_to_ralph: true`, warn user to cancel ralph instead (which cascades)
3. Otherwise clear: `state_clear(mode="ultrawork", session_id)`

#### If UltraQA Active (standalone)

Clear directly: `state_clear(mode="ultraqa", session_id)`

#### No Active Modes

Report: "No active copilot-omni modes detected. Use --force to clear all state files anyway."

## Implementation Notes

The cancel skill runs as follows:
1. Parse the `--force` / `--all` flags, tracking whether cleanup should span every session or stay scoped to the current session id.
2. Use `state_list` to enumerate known session ids and `state_get_status` to learn the active mode (`autopilot`, `ralph`, `ultrawork`, etc.) for each session.
3. When operating in default mode, call `state_clear` with that session_id to remove only the session’s files, then run mode-specific cleanup (autopilot → ralph → …) based on the state tool signals.
4. In force mode, iterate every active session, call `state_clear` per session, then run a global `state_clear` without `session_id` to drop legacy files (`.omni/state/*.json`, compatibility artifacts) and report success. Swarm remains a shared SQLite/marker mode outside session scoping.
5. Team artifacts (`~/.claude/teams/*/`, `~/.claude/tasks/*/`, `.omni/state/team-state.json`) remain best-effort cleanup items invoked during the legacy/global pass.
6. **Always** clear skill-active state as the final step, regardless of which mode was active or whether `--force` was used:
   ```
   state_clear(mode="skill-active", session_id)
   ```
   This ensures the stop hook does not keep firing skill-protection reinforcements after cancel due to a stale `skill-active-state.json`. See issue #2118.

State tools always honor the `session_id` argument, so even force mode still clears the session-scoped paths before deleting compatibility-only legacy state.

Mode-specific subsections below describe what extra cleanup each handler performs after the state-wide operations finish.
## Messages Reference

| Mode | Success Message |
|------|-----------------|
| Autopilot | "Autopilot cancelled at phase: {phase}. Progress preserved for resume." |
| Ralph | "Ralph cancelled. Persistent mode deactivated." |
| Ultrawork | "Ultrawork cancelled. Parallel execution mode deactivated." |
| UltraQA | "UltraQA cancelled. QA cycling workflow stopped." |
| Swarm | "Swarm cancelled. Coordinated agents stopped." |
| Ultrapilot | "Ultrapilot cancelled. Parallel autopilot workers stopped." |
| Pipeline | "Pipeline cancelled. Sequential agent chain stopped." |
| Team | "Team cancelled. Teammates shut down and cleaned up." |
| Plan Consensus | "Plan Consensus cancelled. Planning session ended." |
| Force | "All copilot-omni modes cleared. You are free to start fresh." |
| None | "No active copilot-omni modes detected." |

## What Gets Preserved

| Mode | State Preserved | Resume Command |
|------|-----------------|----------------|
| Autopilot | Yes (phase, files, spec, plan, verdicts) | `/copilot-omni:autopilot` |
| Ralph | No | N/A |
| Ultrawork | No | N/A |
| UltraQA | No | N/A |
| Swarm | No | N/A |
| Ultrapilot | No | N/A |
| Pipeline | No | N/A |
| Plan Consensus | Yes (plan file path preserved) | N/A |

## Notes

- **Dependency-aware**: Autopilot cancellation cleans up Ralph and UltraQA
- **Link-aware**: Ralph cancellation cleans up linked Ultrawork
- **Safe**: Only clears linked Ultrawork, preserves standalone Ultrawork
- **Local-only**: Clears state files in `.omni/state/` directory
- **Resume-friendly**: Autopilot state is preserved for seamless resume
- **Team-aware**: Detects native Claude Code teams and performs graceful shutdown

## MCP Worker Cleanup

When cancelling modes that may have spawned MCP workers (team bridge daemons), the cancel skill should also:

1. **Check for active MCP workers**: Look for heartbeat files at `.omni/state/team-bridge/{team}/*.heartbeat.json`
2. **Send shutdown signals**: Write shutdown signal files for each active worker
3. **Kill tmux sessions**: Run `tmux kill-session -t omni-team-{team}-{worker}` for each worker
4. **Clean up heartbeat files**: Remove all heartbeat files for the team
5. **Clean up shadow registry**: Remove `.omni/state/team-mcp-workers.json`

### Force Clear Addition

When `--force` is used, also clean up:
```bash
rm -rf .omni/state/team-bridge/       # Heartbeat files
rm -f .omni/state/team-mcp-workers.json  # Shadow registry
# Kill all omni-team-* tmux sessions
tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^omni-team-' | while read s; do tmux kill-session -t "$s" 2>/dev/null; done
```
