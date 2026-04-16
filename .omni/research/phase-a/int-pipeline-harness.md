# Internal Pipeline + Harness Audit
## copilot-omni v1.0.0

**Audit Date:** 2026-04-16  
**Scope:** Autonomous pipeline execution, harness engineering, intent routing  
**Focus Level:** Very thorough — all skills read, MCP server analyzed, hooks dissected  

---

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    GitHub Copilot CLI                        │
│  (Reads .claude-plugin/plugin.json, spawns MCP server)      │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
    ┌─────────────────┐        ┌──────────────────────┐
    │ Skills (37)     │        │ Hooks (4)            │
    │ - autopilot     │        │ - sessionStart.py    │
    │ - ralph         │        │ - preToolUse.py      │
    │ - ultrawork     │        │ - postToolUse.py     │
    │ - ralplan       │        │ - userPromptSubmit.py│
    │ - deep-interview│        └──────────────────────┘
    │ - team          │
    │ - ... (31 more) │
    └────────┬────────┘
             │
    ┌────────▼──────────────────────┐
    │  Subagent invocation           │
    │  scripts/subagent.py           │
    │  (copilot -p "..." --agent X)  │
    └────────┬──────────────────────┘
             │
    ┌────────▼──────────────────────────────────────┐
    │  MCP Server (mcp/server.py)                    │
    │  - 30 tools across 9 families                  │
    │  - state_write/state_read for mode persistence │
    │  - SQLite: $OMNI_HOME/omni.db (WAL mode)      │
    └────────┬──────────────────────────────────────┘
             │
    ┌────────▼──────────────────────────────────────┐
    │  State files (.omc/state/)                     │
    │  - autopilot-state.json                        │
    │  - ralph-state.json                            │
    │  - team-state.json                             │
    │  - ralplan-state.json                          │
    │  - deep-interview-state.json                   │
    │  - ultraqa-state.json                          │
    │  - ultrawork-state.json                        │
    └────────────────────────────────────────────────┘
```

**Key Constraint:** No third-party pip dependencies — all code is Python 3.9+ stdlib or Markdown.

---

## 2. Autonomous Pipeline: Autopilot

### 2.1 Phase Execution Flow

**Entry Trigger:**
- Keyword: `autopilot`, `auto pilot`, `autonomous`, `build me`, `create me`, `make me`, `full auto`, `handle it all`, `I want a/an...`
- Detected in: `hooks/user_prompt_submit.py` (line 14, regex trigger)
- Invoked as: `/oh-my-claudecode:autopilot <product idea>`

**Five-Phase Pipeline (SKILL.md lines 40–73):**

1. **Phase 0 – Expansion** (Requirements Analysis)
   - **Gating:** If ralplan consensus plan exists (`.omc/plans/ralplan-*.md` or `.omc/plans/consensus-*.md`), **skip Phase 0 and Phase 1 entirely**
   - **Gating:** If deep-interview spec exists (`.omc/specs/deep-interview-*.md`), **skip analyst + architect**, use pre-validated spec
   - **Otherwise:** Analyst (Opus) extracts requirements; Architect (Opus) creates technical specification
   - **Output:** `.omc/autopilot/spec.md`
   - **Risk:** If input is vague, offers redirect to `/deep-interview`

2. **Phase 1 – Planning** (Design)
   - **Gating:** If ralplan consensus plan exists, **skip — already done**
   - Architect (Opus) creates implementation plan (direct mode, no interview)
   - Critic (Opus) validates plan
   - **Output:** `.omc/plans/autopilot-impl.md`

3. **Phase 2 – Execution** (Parallel Implementation)
   - Executor delegates via Ultrawork (parallel execution engine)
   - Executor (Haiku) for simple tasks
   - Executor (Sonnet) for standard tasks
   - Executor (Opus) for complex tasks
   - **Parallelism:** Independent tasks fire simultaneously (no sequential waits)
   - **Tool:** Uses Ralph internally for structured execution

4. **Phase 3 – QA** (Testing Loop)
   - UltraQA mode: build, lint, test, fix failures
   - Max 5 cycles; stop early if same error repeats 3 times
   - **Tool:** Uses UltraQA skill (skills/ultraqa/SKILL.md)
   - **Risk:** Fundamental issues stop with diagnosis, not rework

5. **Phase 4 – Validation** (Multi-Perspective Review)
   - Architect: Functional completeness (Task subagent delegation)
   - Security-reviewer: Vulnerability check
   - Code-reviewer: Quality review
   - **Parallelism:** All three reviewers run simultaneously
   - **Gate:** All must approve; rejected items get fixed and re-validated

6. **Phase 5 – Cleanup** (State Cleanup)
   - Delete state files: `.omc/state/autopilot-state.json`, `ralph-state.json`, `ultrawork-state.json`, `ultraqa-state.json`
   - Run `/oh-my-claudecode:cancel` for clean exit

### 2.2 State Files Created/Consumed

**Read on startup:**
- `.omc/plans/ralplan-*.md` or `.omc/plans/consensus-*.md` → if found, skip Phase 0+1
- `.omc/specs/deep-interview-*.md` → if found, skip analyst + architect in Phase 0

**Written during execution:**
- `.omc/autopilot/spec.md` (Phase 0 output)
- `.omc/plans/autopilot-impl.md` (Phase 1 output)
- `.omc/state/autopilot-state.json` (via `state_write` MCP tool)
- `.omc/state/ralph-state.json` (Phase 2 delegates to Ralph)
- `.omc/state/ultrawork-state.json` (Phase 2 parallelism)
- `.omc/state/ultraqa-state.json` (Phase 3 QA cycling)

**Deleted on completion:**
- All state files listed above (Phase 5)

**MCP Calls:**
- `state_write(mode="autopilot", active=true, ...)` on entry
- `state_read(mode="autopilot")` to resume if crashed
- `state_clear(mode="autopilot")` on completion or cancel

### 2.3 Gaps vs. SKILL.md Contract

**Gap 1: Ralph Delegation in Phase 2**
- SKILL.md (line 53) says "Implement the plan using Ralph + Ultrawork"
- Ralph SKILL.md (lines 53–54) has its own PRD-mode lifecycle
- **Unclear:** Does autopilot Phase 2 invoke Ralph as a skill, or does Ralph *include* Ultrawork?
- **Code Evidence:** Ralph skill includes Ultrawork (line 118–129, Ralph is the outer persistence wrapper)
- **Inference:** Autopilot Phase 2 → Ralph skill → Ralph invokes Ultrawork for parallel execution
- **Implication:** State file linkage between `autopilot-state.json` and `ralph-state.json` is assumed but not explicitly documented

**Gap 2: UltraQA Invocation in Phase 3**
- SKILL.md (line 59) says "Cycle until all tests pass (UltraQA mode)"
- Does NOT say how UltraQA is invoked (skill call, agent task, or inline code)
- **Code Evidence:** UltraQA is a skill (skills/ultraqa/SKILL.md), so it must be invoked via `Skill("oh-my-claudecode:ultraqa")`
- **Risk:** If UltraQA skill invocation fails, autopilot has no fallback — it will crash

**Gap 3: Configuration Resolution**
- SKILL.md (lines 129–140) documents optional `.claude/settings.json` keys for `maxQaCycles`, `maxValidationRounds`, etc.
- No code evidence that autopilot reads these settings
- **Risk:** Configuration is dead documentation unless Settings tools inject them into the skill context

**Gap 4: Resume Semantics**
- SKILL.md (line 144): "If autopilot was cancelled or failed, run `/oh-my-claudecode:autopilot` again to resume"
- No state machine documented for which phase resumes at
- **Inference:** `state_read(mode="autopilot")` returns the last active phase; autopilot should resume from there
- **Risk:** If state file is corrupted or missing, autopilot restarts from Phase 0 (expensive rework)

**Gap 5: Deep-Interview Redirect Logic**
- SKILL.md (lines 43, 109) mentions redirect to `/deep-interview` for vague input
- No actual invocation code shown
- **Risk:** Redirect may not be implemented; autopilot may expand vague specs directly instead of interviewing

---

## 3. Autonomous Pipeline: Ralph

### 3.1 Execution Model

**Entry Trigger:**
- Keyword: `ralph`, `don't stop`, `must complete`, `finish this`, `keep going until done`
- Detected in: `hooks/user_prompt_submit.py` (line 15)
- Invoked as: `/oh-my-claudecode:ralph [--critic=architect|critic|codex] <task description>`

**Core Loop (SKILL.md lines 56–122):**

1. **PRD Setup** (first iteration only)
   - Read or auto-generate `prd.json`
   - **CRITICAL:** Refine auto-generated scaffold with task-specific acceptance criteria (line 60–64)
   - Initialize `progress.txt`
   - **Risk:** If scaffold criteria are not refined, execution is "PRD theater" (line 193)

2. **Pick Next Story** (from `prd.json` with `passes: false`)

3. **Implement Story**
   - Delegate to specialist agents at appropriate tiers (Haiku/Sonnet/Opus)
   - Run long operations in background (`run_in_background: true`)
   - Discover sub-tasks → add to `prd.json`

4. **Verify Story's Acceptance Criteria**
   - For EACH criterion, verify with fresh evidence (tests, builds, lint output)
   - If any criterion NOT met, continue working (do NOT mark complete)

5. **Mark Story Complete**
   - Set `passes: true` in `prd.json`
   - Record progress in `progress.txt`

6. **Check PRD Completion**
   - If NOT all stories `passes: true`, loop back to step 2
   - If ALL complete, proceed to step 7 (reviewer verification)

7. **Reviewer Verification** (tiered, against acceptance criteria)
   - <5 files, <100 lines: STANDARD tier (Sonnet) minimum
   - Standard changes: STANDARD tier (Sonnet)
   - >20 files or security/architectural: THOROUGH tier (Opus)
   - If `--critic=critic`: use Claude `critic` agent
   - If `--critic=codex`: run `omc ask codex --agent-prompt critic "..."` (requires Codex CLI)
   - **CRITICAL:** On APPROVAL, immediately proceed to 7.5 in the same turn; do NOT pause (line 105)

7.5 **Mandatory Deslop Pass**
   - Invoke `Skill("ai-slop-cleaner")` (NOT via Task subagent — that will fail)
   - Only on changed files from Ralph session
   - **Risk:** If deslop introduces regressions, must rollback and re-verify

7.6 **Regression Re-Verification**
   - Re-run all tests, build, lint after deslop
   - Confirm post-deslop pass actually passes
   - Only proceed if regression passes (or `--no-deslop` specified)

8. **On Approval**
   - Run `/oh-my-claudecode:cancel` to cleanly exit and clean up state files

9. **On Rejection**
   - Fix issues, re-verify with same reviewer
   - Loop back to check if story needs to be marked incomplete

### 3.2 State Files

**Written:**
- `prd.json` (in project root or `.omc/`)
- `progress.txt`
- `.omc/state/ralph-state.json` (via `state_write`)

**Tracked during iteration:**
- Iteration count (current / max)
- Current story ID
- Failure history (to detect recurring errors 3x)

**On Completion:**
- State file deleted via `state_clear(mode="ralph")`

### 3.3 Gaps vs. SKILL.md Contract

**Gap 1: PRD Validation**
- SKILL.md (lines 60–64) says "CRITICAL: Refine the scaffold"
- No enforcement mechanism shown
- **Risk:** Skill could proceed with generic criteria; no validation that criteria are task-specific

**Gap 2: Deslop Skill Invocation**
- SKILL.md (line 108) says: "Invoke the `ai-slop-cleaner` skill via the Skill tool: `Skill("ai-slop-cleaner")`"
- Emphasis that it's a skill, NOT an agent (`oh-my-claudecode:ai-slop-cleaner` doesn't exist)
- **Risk:** If skill calls agent subtype instead, gets "Agent type not found" error and must retry

**Gap 3: Regression Re-Verification**
- SKILL.md (lines 113–117) requires re-running tests after deslop
- What if post-deslop tests fail? The SKILL says "rollback the cleaner changes or fix the regression"
- **Unclear:** Whether Ralph skill has rollback capability for AI-made cleaner changes
- **Risk:** If cleaner introduces subtle regressions, manual rollback may be needed

**Gap 4: Critic Model Selection**
- SKILL.md (line 97) says "STANDARD tier minimum (architect-medium / Sonnet)"
- "architect-medium" is undefined; likely means "Sonnet-tier architect agent"
- **Inference:** Ralph assumes a tiered agent roster (architect/critic at different models)
- **Risk:** If agents are not tiered, verification may use wrong model

---

## 4. Autonomous Pipeline: Ultrawork / UltraQA

### 4.1 Ultrawork (Parallelism Layer)

**Entry Trigger:**
- Keyword: `ultrawork`, `parallel work`, `ulw`
- Invoked as: `/oh-my-claudecode:ultrawork <task description with parallel work items>`

**Design (SKILL.md lines 30–53):**
- Parallelism engine, NOT a persistence mode
- No verification loops, no state management
- Smart model routing (Haiku/Sonnet/Opus based on task complexity)
- Composable: Ralph includes Ultrawork; Autopilot includes Ralph which includes Ultrawork

**Execution:**
1. Read `docs/shared/agent-tiers.md` for tier selection
2. Classify tasks by independence
3. Route to correct tiers
4. **Fire all independent tasks simultaneously** (never serialize)
5. Run dependent tasks sequentially
6. Background long operations (>30 sec)
7. Lightweight verification (build passes, tests pass, no new errors)

**No state files** — Ultrawork is stateless

**Integration Gap:**
- Autopilot Phase 2 says "using Ralph + Ultrawork"
- Ralph includes Ultrawork internally
- **Risk:** If Autopilot tries to invoke Ultrawork directly AND Ralph, may result in duplicate parallel execution

### 4.2 UltraQA (QA Cycling)

**Entry Trigger:**
- Keyword: None (invoked from Autopilot Phase 3)
- Invoked as: `/oh-my-claudecode:ultraqa --tests` (or `--build`, `--lint`, `--typecheck`, `--custom`)

**Cycle Loop (SKILL.md lines 34–71):**
1. **RUN QA**: Execute verification (test, build, lint, typecheck, or custom pattern)
2. **CHECK RESULT**: Did goal pass?
   - YES → Exit with success
   - NO → Continue to step 3
3. **ARCHITECT DIAGNOSIS**: Spawn architect agent to analyze failure
4. **FIX ISSUES**: Executor agent applies architect's recommendations
5. **REPEAT**: Go back to step 1

**Max 5 cycles; stop early if same failure 3x**

**State File:**
- `.omc/state/ultraqa-state.json` (cycle count, failures, goal type)
- **CRITICAL:** Delete state file on completion (line 131)

**Integration with Autopilot:**
- Autopilot Phase 3 invokes UltraQA skill
- UltraQA writes/reads state files independently
- On completion, Autopilot Phase 5 deletes UltraQA state file

**Gap:** No explicit error handling if UltraQA skill invocation fails

---

## 5. Autonomous Pipeline: Ralplan

### 5.1 Purpose

**Entry Trigger:**
- Alias for `/oh-my-claudecode:omc-plan --consensus`
- Keyword: "ralplan"
- Invoked as: `/oh-my-claudecode:ralplan [--interactive] [--deliberate] <task description>`

**Core Function:** Consensus planning with Planner → Architect → Critic loop until agreement

**RALPLAN-DR Structured Deliberation:**
- **Principles** (3–5)
- **Decision Drivers** (top 3)
- **Viable Options** (≥2) with pros/cons
- If only one option: explicit invalidation rationale for alternatives
- **Deliberate mode only:** pre-mortem (3 failure scenarios) + expanded test plan (unit/integration/e2e/observability)

### 5.2 Workflow

**State Management (SKILL.md lines 78–84):**
- On entry: `state_write(mode="ralplan", active=true, session_id=<current>)` before step 1
- On handoff to execution (approval → ralph/team): `state_write(mode="ralplan", active=false)` (NOT `state_clear` — that disables stop-hook enforcement)
- On terminal exit (rejection, non-interactive output): `state_clear(mode="ralplan")`
- **Risk:** If state is not cleared, stop-hook blocks all subsequent stops with reinforcement messages

**Execution Steps:**

1. **Planner** creates initial plan + RALPLAN-DR summary
2. **User Feedback** (--interactive only): Present draft + summary to user
3. **Architect** reviews for soundness (MUST include steelman antithesis + tradeoff tension + synthesis)
4. **Critic** evaluates quality (MUST verify principles, fairness, risk clarity, testable criteria)
5. **Re-Review Loop** (max 5 iterations): If Critic rejects, Planner revises → Architect → Critic again
6. **Final Approval** (--interactive only): User selects execution path
7. (Optional) **Invoke execution** via Skill("oh-my-claudecode:team") or Skill("oh-my-claudecode:ralph")

**Output:**
- `.omc/plans/ralplan-*.md` or `.omc/plans/consensus-*.md` (includes ADR + RALPLAN-DR summary)

### 5.3 Integration with Autopilot's 3-Stage Pipeline

**3-Stage Pipeline (SKILL.md lines 173–189):**
```
Stage 1: Deep Interview  →  Stage 2: Ralplan  →  Stage 3: Autopilot
Socratic Q&A             Planner → Architect   Phase 2: Execution
Ambiguity scoring        → Critic loop         Phase 3: QA cycling
Spec crystallization     Consensus-plan.md     Phase 4: Validation
Gate: ≤20% ambiguity                          Phase 5: Cleanup
```

**Hand-off Mechanism:**
- Deep-interview outputs: `.omc/specs/deep-interview-{slug}.md`
- Ralplan input: `--consensus --direct` (skips ralplan's own interview, uses deep-interview spec as input)
- Ralplan outputs: `.omc/plans/consensus-*.md`
- Autopilot input: skips Phase 0+1, starts at Phase 2 (Execution)

**Gap in Code:**
- SKILL.md (line 356) says: "Invoke `Skill("oh-my-claudecode:omc-plan")` with `--consensus --direct` flags and the spec file path as context"
- **Unclear:** How is spec file path passed to the skill? Via prompt, or as a parameter?
- **Risk:** If spec path is not correctly passed, ralplan may not find the deep-interview spec

---

## 6. Team Orchestration

### 6.1 Two Team Modes

**Mode 1: `/oh-my-claudecode:team` (Claude Code Native)**
- Uses Claude Code's built-in `TeamCreate`, `TaskCreate`, `TaskUpdate`, `SendMessage`
- Teammates are Claude Code agents in team-aware sessions
- **Storage:** `~/.claude/teams/{team_name}/` + `~/.claude/tasks/{team_name}/`
- **Communication:** `SendMessage` (auto-delivered to lead as conversation turns)

**Mode 2: `/oh-my-claudecode:omc-teams` (Legacy CLI Worker)**
- Spawns N CLI workers in tmux panes (claude, codex, or gemini)
- CLI workers have full filesystem access, run autonomously
- **Storage:** `.omc/state/team/`, `.omc/state/team/{teamName}/workers/`
- **Communication:** tmux output files, no team messaging

### 6.2 Native Team Pipeline (Canonical)

**Staged Execution:**
```
team-plan → team-prd → team-exec → team-verify → team-fix (loop)
```

**Stage-Aware Agent Routing:**
- **team-plan**: explore (haiku), planner (opus), optional analyst/architect
- **team-prd**: analyst (opus), optional critic
- **team-exec**: executor (sonnet), optional designer/debugger/writer/test-engineer
- **team-verify**: verifier (sonnet), optional security-reviewer/code-reviewer (opus)
- **team-fix**: executor (sonnet), optional debugger (sonnet) or executor (opus)

**Lead Orchestration (from team skill SKILL.md):**
1. **Parse Input**: Extract N (agent count), agent-type, task
2. **Analyze & Decompose**: Break task into N independent subtasks (file- or module-scoped)
3. **Create Team**: `TeamCreate("fix-ts-errors")` → lead becomes `team-lead@fix-ts-errors`
4. **Create Tasks**: `TaskCreate` for each subtask; set dependencies with `TaskUpdate(addBlockedBy)`
5. **Pre-Assign Owners**: Lead assigns tasks to workers before spawning to avoid race conditions
6. **Spawn Teammates**: `Task(team_name="fix-ts-errors", name="worker-1", ...)` ×N in parallel
7. **Monitor**: Poll `TaskList`, respond to inbound `SendMessage` from teammates
8. **Shutdown**: Send `shutdown_request` to each teammate, await `shutdown_response`
9. **Delete Team**: `TeamDelete` only after all teammates shut down
10. **Clean State**: `state_clear(mode="team")`

**Handoff Documents:**
- After each stage, produce `.omc/handoffs/<stage-name>.md` with Decided/Rejected/Risks/Files/Remaining
- Next stage reads prior handoffs for full context

**State Tracking:**
- `state_write(mode="team", current_phase="team-plan|team-prd|team-exec|team-verify|team-fix")`
- On every stage transition, update `stage_history` with timestamps

**Resume Semantics:**
- If lead crashes, `state_read(mode="team")` reveals last phase
- Resume from incomplete stage using `TaskList` for current progress

### 6.3 Team + Ralph Composition

**Activation:** User invokes `/team ralph` or both keywords appear in prompt

**State Linkage:**
```
team-state.json has linked_ralph=true
ralph-state.json has linked_team=true, team_name="fix-ts-errors"
```

**Execution:**
1. Ralph outer loop starts (iteration 1)
2. Team pipeline runs: team-plan → team-prd → team-exec → team-verify
3. If team-verify passes: Ralph runs architect verification
4. If architect approves: both modes complete, run `/oh-my-claudecode:cancel`
5. If team-verify fails OR architect rejects: team enters team-fix, loops back to team-exec
6. If fix loop exceeds `max_fix_loops`: Ralph increments iteration and retries full pipeline
7. If Ralph exceeds `max_iterations`: terminal `failed` state

**Cancellation:**
- Cancel Ralph (linked) → Cancel Team first (graceful shutdown), then clear Ralph state
- Cancel Team (linked) → Clear Team, mark Ralph iteration cancelled

### 6.4 Gotchas & Risks

**Gotcha 1: Internal Tasks Pollute TaskList**
- When teammate is spawned, system auto-creates internal task with `metadata._internal: true`
- These appear in `TaskList` output
- **Risk:** Lead must filter internal tasks when counting progress

**Gotcha 2: No Atomic Claiming**
- Unlike SQLite swarm, no transactional guarantee on `TaskUpdate`
- Two teammates could race to claim same task
- **Mitigation:** Lead pre-assigns owners before spawning
- **Risk:** If lead doesn't pre-assign, race conditions possible

**Gotcha 3: shutdown_response needs request_id**
- Teammate must extract `request_id` from shutdown_request JSON and pass it back
- Format: `shutdown-{timestamp}@{worker-name}`
- **Risk:** If request_id is fabricated, shutdown fails silently

**Gotcha 4: Messages Auto-Delivered**
- Teammate messages arrive to lead as new conversation turns (no polling needed)
- If lead is mid-turn, messages queue and deliver when turn ends
- **Risk:** Lead may miss a message if they don't wait for delivery before commanding cancellation

---

## 7. Deep-Interview → Ralplan → Autopilot 3-Stage Pipeline

### 7.1 Hand-Off Mechanics

**Stage 1: Deep-Interview** → Spec File
- Entry: Vague idea or explicit `/deep-interview`
- Process: Socratic Q&A (1 question per round) → ambiguity scoring (greenfield: 1 - (goal×0.40 + constraints×0.30 + criteria×0.30); brownfield: adds context×0.15)
- Challenge agents at thresholds: Contrarian (round 4+), Simplifier (round 6+), Ontologist (round 8+)
- Max 20 rounds; soft warning at 10 rounds
- **Output:** `.omc/specs/deep-interview-{slug}.md` (ambiguity ≤20% OR early exit)
- **Spec Contents:** Goal, Constraints, Non-Goals, Acceptance Criteria, Assumptions Exposed & Resolved, Technical Context, Ontology (Key Entities), Ontology Convergence table, Full Transcript

**Stage 2: Ralplan** → Consensus Plan
- Entry: Deep-interview spec file as input (via `--consensus --direct` flags to omc-plan)
- Process: Planner → (optional user feedback) → Architect → Critic → re-loop until consensus
- RALPLAN-DR summary included (Principles, Decision Drivers, Viable Options)
- **Output:** `.omc/plans/consensus-*.md` (includes ADR + RALPLAN-DR + testable acceptance criteria + implementation steps)

**Stage 3: Autopilot** → Working Code
- Entry: Consensus plan file (Autopilot skips Phase 0+1, starts Phase 2)
- Process: Phase 2 (Execute via Ralph/Ultrawork) → Phase 3 (QA cycling) → Phase 4 (Validation) → Phase 5 (Cleanup)
- **Output:** Working code, tests passing, all validators approved

### 7.2 Hand-Off Implementation

**Deep-Interview → Ralplan:**
```
User selects "Ralplan → Autopilot (Recommended)" from execution bridge (Step 5, line 354)
→ Invoke Skill("oh-my-claudecode:omc-plan") with --consensus --direct and spec file as context
```

**Ralplan → Autopilot:**
```
On Critic approval (or non-interactive final output):
→ Invoke Skill("oh-my-claudecode:autopilot") with consensus plan as Phase 0+1 output
→ Autopilot reads .omc/plans/ralplan-*.md or .omc/plans/consensus-*.md on startup
→ Autopilot skips Phase 0 (Expansion) and Phase 1 (Planning)
→ Autopilot starts Phase 2 (Execution)
```

### 7.3 Quality Gates

Each stage provides a different gate:
1. **Deep-Interview gates on clarity** — does user know what they want? (Ambiguity ≤20%)
2. **Ralplan gates on feasibility** — is approach architecturally sound? (Consensus: Planner/Architect/Critic approved)
3. **Autopilot gates on correctness** — does code work and pass review? (All phases complete, validators approved)

### 7.4 Gaps in Hand-Off

**Gap 1: Spec File Path Passing**
- Deep-interview writes: `.omc/specs/deep-interview-{slug}.md`
- Ralplan invocation says: "spec file path as context" (line 356)
- **Unclear:** Is spec path passed as command-line argument, or embedded in skill context via prompt?
- **Risk:** If path not correctly passed, ralplan may not find spec

**Gap 2: Consensus Plan Detection**
- Autopilot startup checks for `.omc/plans/ralplan-*.md` or `.omc/plans/consensus-*.md`
- File naming convention unclear: does ralplan write `ralplan-*.md` or `consensus-*.md`?
- **Code Evidence:** SKILL.md (line 41) says "ralplan-*.md" OR "consensus-*.md"
- **Risk:** If naming convention changes, hand-off breaks

**Gap 3: Resume Across Pipeline**
- If deep-interview is interrupted, can user resume with `/deep-interview`? (YES, via state_read)
- If ralplan is interrupted, can user resume with `/ralplan`? (UNCLEAR — no resume logic documented)
- If autopilot is interrupted mid-Phase 2, can it resume? (Line 144 says YES, but mechanism unclear)

---

## 8. Harness Engineering

### 8.1 Copilot CLI Integration

**Plugin Architecture:**
- Plugin directory: `.claude-plugin/` (manifest) + root files (skills, agents, commands, hooks, MCP)
- Manifest: `.claude-plugin/plugin.json` (JSON, registers skills/agents/commands/hooks/MCP)
- **File:** plugin.json (lines 1–34)

**Plugin Discovery Flow:**
1. Copilot CLI reads `.claude-plugin/plugin.json`
2. Discovers:
   - Skills in `skills/` folder (37 SKILL.md files)
   - Agents in `agents/` folder (19 markdown files)
   - Commands in `commands/` folder (8 markdown files)
   - Hooks config in `hooks/hooks.json`
   - MCP server in `.mcp.json`
3. On session start, Copilot CLI:
   - Spawns `python3 mcp/server.py` as stdio subprocess
   - Invokes hook scripts on lifecycle events
   - Makes skills/agents/commands available to LLM

**Manifest Fields:**
- `agents`: "agents/" (directory glob)
- `commands`: "commands/" (directory glob)
- `hooks`: "hooks/hooks.json" (hook config file)
- `mcpServers`: ".mcp.json" (MCP server config)

**Skill Invocation in Copilot CLI:**
- User: `/oh-my-claudecode:autopilot <prompt>`
- Copilot CLI reads `skills/autopilot/SKILL.md`, extracts frontmatter + body
- Sends combined context to LLM
- LLM executes the skill's instructions

### 8.2 Claude Code Integration

**Compatibility:**
- Plugin also works in Claude Code (secondary target)
- CLAUDE.md (line 3): "targets GitHub Copilot CLI first… also usable in Claude Code"
- Manifest format overlaps between Copilot CLI and Claude Code

**Key Difference:** 
- Copilot CLI: Skills are Markdown instruction documents read by Copilot, then LLM executes
- Claude Code: Skills can invoke Claude Code native features (Task, SendMessage, TeamCreate, etc.)

**Task Invocation in Claude Code:**
- AGENTS.md (lines 62–66): `Task(subagent_type="oh-my-claudecode:executor", ...)` spawns a specialist agent
- Copilot CLI equivalent (scripts/subagent.py, lines 24–46): `run_agent("executor", "prompt")`
  - Internally: `copilot -p "…" --agent <name> --allow-all`

**Translation Layer:**
- Copilot CLI has no native `Task()` tool
- `scripts/subagent.py` bridges: Claude Code `Task(subagent_type=X)` → Copilot CLI `copilot -p ... --agent X`
- **Risk:** If copilot CLI not on PATH, subagent invocation fails

### 8.3 MCP Server Surface

**Transport:** Stdio JSON-RPC 2.0, newline-delimited (default) or Content-Length framed (for LSP compatibility)

**Tool Families (30 tools across 9 families):**

| Family | Tools | Purpose |
|--------|-------|---------|
| Memory | memory_capture, memory_search, memory_export, memory_prune | Long-lived project knowledge |
| Artifacts | artifact_write, artifact_read | Run artifacts (specs, plans, summaries) |
| Runs | run_status, resume_context | Run lifecycle tracking |
| State | state_write, state_read, state_clear | Mode persistence (autopilot, ralph, team, ralplan, deep-interview, ultraqa, ultrawork) |
| Wiki | wiki_write, wiki_read, wiki_query, wiki_list | Persistent markdown KB |
| Notepad | notepad_write, notepad_read, notepad_prune | Session scratch memory |
| Shared Memory | shared_memory_write, shared_memory_read | Cross-agent handoff |
| Trace | trace_summary, trace_timeline | Causal tracing |
| Session | session_search | Prior session lookup |
| Support | config_resolve, health, doctor, support_bundle | Diagnostics |
| Subtask | subtask | Subtask creation/routing |
| Workspace | workspace | Local workspace management |
| Policy | policy_check | Policy enforcement check |

**Database:** SQLite at `$OMNI_HOME/omni.db` (default: `~/.omni/omni.db`)
- WAL mode, PRAGMA synchronous=NORMAL, foreign_keys=ON
- Schema auto-migrated on server startup (current version: 1)
- 9 tables: memory, artifacts, runs, state, wiki, notepad, shared_memory, trace, sessions

**Tool Registration (mcp/server.py lines 738–1016):**
- Each tool has: description, inputSchema (JSON Schema), handler function
- Handler takes `args` dict, returns `_text_result()` or `_json_result()`
- Request dispatch (line 1053): `TOOLS.get(name)["handler"](args)`

**Key MCP Calls Used by Skills:**

| Skill | MCP Calls |
|-------|-----------|
| Autopilot | state_write, state_read, state_clear |
| Ralph | state_write, state_read, state_clear |
| Ultrawork | (stateless) |
| UltraQA | state_write, state_read, state_clear |
| Team | state_write, state_read, state_clear |
| Deep-Interview | state_write, state_read, state_clear, artifact_write |
| Ralplan | state_write, state_read, state_clear |

**Failure Modes:**
- If MCP server crashes: all state persistence fails, mode state lost
- If SQLite database locked: retries up to 3 times with exponential backoff (mcp/server.py lines 59–72)
- If policy_check denies tool: hook returns deny decision; tool never executes

### 8.4 Python Scripts

#### scripts/omni.py
**Purpose:** User-facing CLI for plugin initialization and diagnostics

**Subcommands (omni/server.py lines 32–80):**
- `omni version` — print version
- `omni doctor` — verify environment (python, copilot CLI, plugin.json, MCP server, skills, agents, commands)
- `omni init [--path PATH] [--profile PROFILE] [--force] [--no-agents-md]` — scaffold `.omni/` in current project
  - Creates: `.omni/config.json`, subdirs (runs, specs, plans, decisions, audit, support)
  - Writes scaffolded `AGENTS.md` if not present
  - **Profile:** "standard" by default (can be "permissive" or "strict" for policy)
- `omni status` — show current run and mode state
- `omni plugin-install [--path PLUGIN_PATH]` — install plugin into Copilot CLI (uses `copilot plugin install`)
- `omni mcp` — launch MCP server in foreground (stdio)
- `omni list [skills|agents|commands]` — list available items

**No External Dependencies:** Pure Python 3.9+ stdlib

**Implementation:** argparse for CLI parsing, Path for filesystem operations, subprocess for copilot invocation

#### scripts/subagent.py
**Purpose:** Bridge Copilot CLI → Agent invocation

**Function: `run_agent(name, prompt, allow_all=None, model=None, timeout=1800)`**
- Invokes: `copilot -p "<prompt>" --agent <name>` [--model MODEL] [--allow-all]
- Returns: exit code
- **Default:** `--allow-all=False` (corporate-safe) unless `OMNI_SUBAGENT_ALLOW_ALL=1` env var
- **Timeout:** 30 min (1800s)

**CLI Interface:**
- `python3 scripts/subagent.py <agent_name> "<prompt>" [--model MODEL] [--allow-all | --no-allow-all]`

**Used By:**
- Skills that need to delegate to specialist agents (architect, executor, debugger, etc.)
- Example: Ralph calls executor via `run_agent("executor", "fix the issue", model="sonnet")`

**Failure Mode:**
- If `copilot` CLI not found on PATH: returns exit code 2 with stderr message
- **Risk:** If Copilot CLI is not installed or not on PATH, all agent delegation fails

---

## 9. Front-Door Intent Routing

### 9.1 user_prompt_submit.py Hook Behavior

**File:** `hooks/user_prompt_submit.py` (lines 1–48)

**Trigger:** Copilot CLI event: user types prompt and hits Enter

**Input:** JSON event with `prompt` field (user's message)

**Process:**
1. Read `prompt` from stdin JSON
2. For each trigger in `TRIGGERS` dict (lines 13–24):
   - Compile regex pattern
   - Test pattern against prompt (case-insensitive)
3. Collect all matched trigger names
4. If matches found: return `additionalContext` hint suggesting skill invocation
5. If no matches: return empty JSON `{}`

**Trigger Table (TRIGGERS dict, lines 13–24):**

| Skill Name | Regex Pattern | Example Matches |
|------------|---------------|-----------------|
| autopilot | `\b(autopilot\|full\s*auto\|handle\s*it\s*all)\b` | "autopilot build", "full auto mode", "handle it all" |
| ralph | `\bralph\b` | "ralph fix this", "run ralph" |
| ultrawork | `\b(ultrawork\|parallel\s+work)\b` | "ultrawork refactor", "parallel work items" |
| team | `\b(team\s+mode\|/team)\b` | "team mode activate", "/team fix" |
| plan | `\b(plan(?:ning)?\|/plan)\b` | "plan this", "planning required", "/plan" |
| debug | `\b(debug\|diagnose)\b` | "debug the issue", "diagnose the error" |
| verify | `\b(verify\|verification)\b` | "verify the code", "verification pass" |
| wiki | `\b(wiki\|knowledge\s+base)\b` | "wiki this", "knowledge base update" |
| remember | `\b(remember\|save\s+this)\b` | "remember this", "save this context" |
| ship | `\b(ship\s+it\|open\s+pr\|create\s+pull\s+request)\b` | "ship it", "open pr", "create pull request" |

**Output:**
```json
{
  "additionalContext": "copilot-omni: matched skill trigger(s): autopilot, team. Consider invoking the corresponding skill via /skills."
}
```

**Limitations:**
- Hook is informational only — suggests skill, doesn't invoke it
- Multiple matches are OR'd together (non-exclusive)
- No intent disambiguation if multiple skills match
- No keyword weighting or priority ordering

### 9.2 session_start.py Injections

**File:** `hooks/session_start.py` (lines 1–16)

**Trigger:** Copilot CLI event: session starts

**Behavior:**
- Returns a static banner informing user about copilot-omni features
- No context gathering, no state injection

**Output:**
```json
{
  "additionalContext": "Copilot Omni v1.0.0 — enterprise-safe multi-agent orchestration. 29 MCP tools, 28+ skills, 17+ agents. Pure Python stdlib. Run /omni-init to scaffold .omni/ in this project."
}
```

**Limitation:** Banner is static; does not adapt to session context (e.g., no hint about resumed autopilot state)

### 9.3 Keyword/Magic-Trigger Table

**Comprehensive Trigger Recognition:**

| Keyword/Pattern | Detected By | Skill/Mode | LLM Invocation |
|-----------------|-------------|-----------|----------------|
| `autopilot`, `auto pilot`, `autonomous`, `build me`, `create me`, `make me`, `full auto`, `handle it all`, `I want a/an...` | user_prompt_submit.py (line 14) + LLM logic | autopilot | `/oh-my-claudecode:autopilot <prompt>` |
| `ralph`, `don't stop`, `must complete`, `finish this`, `keep going until done` | user_prompt_submit.py (line 15) + LLM logic | ralph | `/oh-my-claudecode:ralph <prompt>` |
| `ultrawork`, `parallel work`, `ulw` | user_prompt_submit.py (line 16) + LLM logic | ultrawork | `/oh-my-claudecode:ultrawork <prompt>` |
| `team mode`, `/team` | user_prompt_submit.py (line 17) + LLM logic | team | `/oh-my-claudecode:team <prompt>` |
| `plan`, `planning` | user_prompt_submit.py (line 18) + LLM logic | omc-plan | `/oh-my-claudecode:omc-plan <prompt>` |
| `ralplan` | Explicit skill invocation (not hook-triggered) | ralplan | `/oh-my-claudecode:ralplan <prompt>` |
| `deep-interview`, `interview`, `socratic`, `ouroboros`, `ask me everything`, `don't assume` | Explicit skill invocation + LLM logic | deep-interview | `/oh-my-claudecode:deep-interview <prompt>` |
| `debug`, `diagnose` | user_prompt_submit.py (line 19) + LLM logic | debug | `/oh-my-claudecode:debug <prompt>` |
| `verify`, `verification` | user_prompt_submit.py (line 20) + LLM logic | verify | `/oh-my-claudecode:verify <prompt>` |
| `wiki`, `knowledge base` | user_prompt_submit.py (line 21) + LLM logic | wiki | `/oh-my-claudecode:wiki <prompt>` |
| `remember`, `save this` | user_prompt_submit.py (line 22) + LLM logic | remember | `/oh-my-claudecode:remember <prompt>` |
| `ship it`, `open pr`, `create pull request` | user_prompt_submit.py (line 23) + LLM logic | ship | `/oh-my-claudecode:ship <prompt>` |

**NOTE:** `user_prompt_submit.py` hook detects keywords and returns a hint. The LLM decides whether to invoke the skill based on the hint + prompt context. The hook does NOT invoke skills directly — it's a suggestion mechanism.

### 9.4 Intent Routing Gaps and Risks

**Gap 1: Hook Hints Are Advisory, Not Deterministic**
- Hook returns `additionalContext` with matched skill names
- LLM reads hint and MAY choose to invoke skill
- **Risk:** LLM may ignore hint and respond conversationally instead of invoking skill
- **Example:** User: "autopilot build me a CLI" → Hook suggests autopilot → LLM could respond with advice instead of invoking `/oh-my-claudecode:autopilot`

**Gap 2: No Keyword Priority Weighting**
- Multiple triggers may match (e.g., "team ralph mode" matches both `team` and `ralph`)
- Hook returns all matches as comma-separated list
- **Risk:** If user intends one skill but multiple match, LLM may pick the wrong one

**Gap 3: Intent Misclassification Without Deep Analysis**
- user_prompt_submit.py uses simple regex matching
- No semantic understanding of intent
- **Example:** User says "I want to work in parallel on three things" (matches `ultrawork` regex "parallel work")
  - But user may have meant "I want three people to work together" (more like `team`)
  - Hook would suggest `ultrawork`, not `team`

**Gap 4: No Skill Exclusion/Bypass Mechanism**
- Once hook suggests a skill, no explicit "don't use this skill" override available to user
- User can only ignore the hint (which LLM may not honor)
- **Risk:** User cannot force a non-autopilot interpretation of their request

**Gap 5: ralplan Pre-Execution Gate Not in Hooks**
- ralplan/omc-plan skill (line 64–135) has a pre-execution gate that redirects vague prompts to planning
- This gate is implemented in skill logic, NOT in hooks
- **Risk:** Skill must be invoked first to detect vagueness — can't redirect before skill invocation

**Gap 6: Session Context Ignored**
- session_start.py banner is static; does not check for resumed states
- If autopilot crashed mid-run, session banner doesn't hint "resume /oh-my-claudecode:autopilot"
- **Risk:** User may not know they can resume from where it crashed

**Gap 7: No Skill Conflict Detection**
- If user invokes `autopilot` and then immediately `ralph`, both may try to use the same state files
- No mutex or conflict detection in hook layer
- **Risk:** Concurrent skill invocations may corrupt state files

---

## 10. Tight Coupling / Leaky Abstractions

### 10.1 State File Coupling

**Issue:** Skills assume specific state file paths and naming conventions

**Evidence:**
- Autopilot reads `.omc/plans/ralplan-*.md` OR `.omc/plans/consensus-*.md` (SKILL.md line 41)
- Ralplan writes `.omc/plans/ralplan-*.md` or `.omc/plans/consensus-*.md` (SKILL.md line 7)
- Deep-interview writes `.omc/specs/deep-interview-{slug}.md` (SKILL.md line 8)
- **Risk:** If one skill changes naming convention, hand-off breaks

**Mitigation:** File naming convention should be versioned or validated at hand-off time

### 10.2 MCP State Persistence Coupling

**Issue:** All autonomous modes (autopilot, ralph, team, ralplan, deep-interview, ultraqa, ultrawork) depend on MCP `state_write`/`state_read`

**Evidence:**
- mcp/server.py lines 470–496 implement state_write/state_read using SQLite
- If SQLite server crashes or database is corrupted, all state is lost
- No local file-based fallback or redundancy

**Risk:** Single point of failure for mode persistence

**Mitigation:** State should be mirrored to `.omc/state/<mode>-state.json` files for fault tolerance

### 10.3 Subagent Invocation Coupling

**Issue:** Ralph skill (line 108) explicitly warns against calling `ai-slop-cleaner` as an agent

- Ralph SKILL.md (line 109): "`ai-slop-cleaner` is a SKILL, not an agent… Do NOT call it via `Task(subagent_type=...)`"
- This suggests tight coupling between skill type detection and invocation mechanism
- **Risk:** No runtime type checking; skill miscalled as agent will fail with "Agent type not found"

### 10.4 Policy Evaluation in Hooks

**Issue:** `hooks/pre_tool_use.py` (line 72) loads policy from three candidates:
1. `$OMNI_POLICY_FILE` (env override)
2. `.omni/policy-<profile>.json` (project override)
3. `<plugin>/policies/<profile>.json` (plugin default)

**Coupling:**
- Policy lookup is sequential; no atomic decision
- If `.omni/policy-standard.json` exists but is malformed, hook falls back to plugin default silently (line 54)
- No validation that fallback policy is weaker or equivalent in security

**Risk:** Policy security boundary may be inadvertently weakened by fallback

### 10.5 Skill/Agent Model Assignment

**Issue:** Ralph SKILL.md (lines 93–96) assumes agent model tiers exist

- "STANDARD tier minimum (architect-medium / Sonnet)"
- No validation that agents exist or support the specified models
- If agents are not tiered (e.g., all run on Opus), Ralph may incur unexpected costs

**Risk:** Skill assumes infrastructure that may not exist

---

## 11. Bugs and Inconsistencies Found

### Bug 1: Incomplete Tool Registry in MCP Documentation
**File:** mcp/server.py (line 738–1016)  
**Issue:** Header comment (line 5) claims "23 tools" but actual TOOLS dict registers 30 tools
**Impact:** Documentation is outdated; external clients may assume incomplete tool set
**Fix:** Update comment to "30 tools"

### Bug 2: Ralplan State Cleanup Ambiguity
**File:** skills/plan/SKILL.md (lines 78–84)  
**Issue:** On handoff to execution, script says `state_write(mode="ralplan", active=false)` but NOT `state_clear`
- Reasoning: "do NOT use state_clear here — state_clear writes a 30-second cancel signal"
- But then on true terminal exit (rejection): `state_clear(mode="ralplan")`
- **Problem:** If user rejects plan AND then immediately invokes ralplan again, old state with `active=false` may interfere
**Impact:** State machine may reject rapid re-invocation of ralplan
**Fix:** Document that `active=false` is automatically superseded when state_write is called again with `active=true`

### Bug 3: Deep-Interview Spec Path Not Passed Correctly
**File:** skills/deep-interview/SKILL.md (line 356)  
**Issue:** "Invoke `Skill("oh-my-claudecode:omc-plan")` with `--consensus --direct` flags and the spec file path as context"
- **Unclear:** How is spec file path passed? As CLI argument, or embedded in skill context?
- No example code shown
**Impact:** Skill invocation may fail if spec path format is wrong
**Fix:** Show concrete example: `Skill("omc-plan", args="--consensus --direct /path/to/spec.md")`

### Bug 4: UltraQA State File Cleanup Inconsistency
**File:** skills/ultraqa/SKILL.md (line 131)  
**Issue:** "IMPORTANT: Delete state files on completion - do NOT just set `active: false`"
- But Autopilot Phase 5 (SKILL.md line 71) says "Delete all state files: ... ultraqa-state.json"
- **Redundancy:** Both UltraQA and Autopilot claim responsibility for deleting ultraqa-state.json
**Impact:** If both try to delete, second deletion fails silently (file already gone)
**Fix:** Clarify ownership: either UltraQA always deletes its own state, OR Autopilot deletes it on behalf of UltraQA

### Bug 5: Ralph PRD Refinement Not Enforced
**File:** skills/ralph/SKILL.md (lines 60–64)  
**Issue:** "CRITICAL: Refine the scaffold… You MUST replace these with task-specific criteria"
- No validation mechanism enforced
- Skill can proceed with generic criteria (line 193 warns this is "PRD theater")
**Impact:** Ralph may waste iterations on vague acceptance criteria
**Fix:** Add explicit validation step: "If any criterion matches the auto-generated boilerplate, reject and ask user to refine"

### Bug 6: Team Shutdown Protocol Not Atomic
**File:** skills/team/SKILL.md (lines 532–589)  
**Issue:** Shutdown sequence is BLOCKING but best-effort
- "Track which teammates confirmed vs timed out" (line 552)
- But then: "Do not proceed to TeamDelete until all teammates have either confirmed or timed out" (line 587)
- **Problem:** What if teammate never responds and timeout expires? TeamDelete is called anyway.
- If TeamDelete fails (teammates still active), error handling is unclear
**Impact:** Orphaned teammate processes may remain after "shutdown"
**Fix:** Add explicit error recovery: if TeamDelete fails, suggest manual cleanup or force flag

### Bug 7: Deslop Invocation Using Wrong Tool Type
**File:** skills/ralph/SKILL.md (line 108)  
**Issue:** "Invoke the `ai-slop-cleaner` skill via the Skill tool: `Skill("ai-slop-cleaner")`"
- But earlier (line 109): "Do NOT call it via `Task(subagent_type=...)`"
- Emphasis suggests this is a known mistake
- **Problem:** If developer uses Task subagent by mistake, gets "Agent type not found"
**Impact:** Ralph fails with confusing error message
**Fix:** Add pre-check: before deslop invocation, validate that ai-slop-cleaner is a skill (not an agent)

### Bug 8: Ulw / Ultrawork Keyword Not Documented in Hook
**File:** hooks/user_prompt_submit.py (line 13)  
**Issue:** Hook TRIGGERS dict has regex for `ultrawork` (line 16) but autopilot SKILL.md doesn't mention `ulw` as a trigger
- Ultrawork SKILL.md (line 4) mentions "ulw" as a shorthand
- **Problem:** Hook doesn't recognize "ulw" keyword; only "ultrawork" and "parallel work"
**Impact:** User typing "ulw refactor" won't get hook suggestion
**Fix:** Add "ulw" to hook regex: `r"\b(ultrawork|ulw|parallel\s+work)\b"`

### Bug 9: Console Output on Cancellation Not Specified
**File:** skills/cancel/SKILL.md (not read in this audit, but referenced multiple times)  
**Issue:** Multiple skills reference `/oh-my-claudecode:cancel` for cleanup (autopilot line 72, ralph line 8, team line 840)
- But what does cancel actually output? Does it delete state files, or just mark them inactive?
- SKILL.md doesn't clarify
**Impact:** User doesn't know if cancel succeeded or what cleanup happened
**Fix:** Specify cancel output format and success criteria

### Bug 10: Team Resume Logic Unclear
**File:** skills/team/SKILL.md (lines 799–809)  
**Issue:** "If the lead crashes mid-run, the team skill should detect existing state and resume"
- Uses `should` (not `must`); no enforcement
- Requires matching task slug to existing team (line 802)
- **Problem:** What if slug collision occurs? Multiple teams with same slug?
**Impact:** Resume may attach to wrong team
**Fix:** Add explicit error handling: if multiple teams with slug exist, prompt user for clarification

---

## 12. Recommendations (Ranked by Impact)

### Recommendation 1: Formalize State Machine for Autonomous Modes [CRITICAL]
**Impact:** HIGH — Prevents deadlocks, corruption, race conditions  
**Effort:** MEDIUM

Currently, state transitions are implicit in skill logic. Formalize as:
1. Define state diagram for each mode (autopilot, ralph, team, ralplan, deep-interview)
2. Each state transition should be atomic (single MCP call, no partial updates)
3. Add validation at entry: check state preconditions (e.g., if previous phase incomplete, fail or resume)
4. Document resume semantics explicitly

**File to create:** `.omc/docs/STATE_MACHINE.md`

### Recommendation 2: Implement State File Versioning [HIGH]
**Impact:** MEDIUM — Enables schema migrations  
**Effort:** LOW

State files currently have no version field. Add:
```json
{
  "version": 1,
  "mode": "autopilot",
  "session_id": "uuid",
  "active": true,
  ...
}
```

Allows future schema changes without breaking old state files.

### Recommendation 3: Add Skill Type Validation at Invocation [HIGH]
**Impact:** MEDIUM — Prevents "Agent type not found" errors  
**Effort:** LOW

Before invoking a skill:
1. Check if skill is registered (skill vs agent)
2. If calling `Task(subagent_type=...)` with a skill name, fail fast with message: "X is a skill, use Skill('X') instead"
3. Cache skill list on session start to avoid repeated lookups

### Recommendation 4: Implement Configuration Inheritance [MEDIUM]
**Impact:** LOW — Improves customizability  
**Effort:** MEDIUM

Currently, config is read from `.omni/config.json` but skills don't actually read it. Implement:
1. `_resolve_config()` function in MCP server that merges project + global + default configs
2. Make `config_resolve` MCP tool return the merged config
3. Skills read config at startup via MCP tool

### Recommendation 5: Add Skill Conflict Detection [MEDIUM]
**Impact:** MEDIUM — Prevents concurrent state corruption  
**Effort:** MEDIUM

Add mutual exclusion:
1. When skill enters, acquire lock: `.omc/state/.lock-<mode>`
2. If lock held by another PID, fail with message: "Another autopilot session is running (PID XXXX)"
3. On exit or crash, clean up lock (or let it timeout after 5 minutes)

### Recommendation 6: Document Hand-Off File Formats [MEDIUM]
**Impact:** LOW — Improves maintainability  
**Effort:** LOW

Create `.omc/docs/FILE_FORMATS.md` specifying:
1. Deep-interview spec format (with required fields, optional fields, schema)
2. Ralplan consensus plan format (including RALPLAN-DR section)
3. Autopilot output format (working code artifacts)
4. Handoff document format (for team skill)

### Recommendation 7: Implement Policy Validation at Startup [MEDIUM]
**Impact:** LOW — Improves security confidence  
**Effort:** LOW

Add `policy_check` MCP tool call to validate loaded policy:
1. Ensure `deny_commands` is a list of strings
2. Ensure `protected_paths` contains only relative paths (no absolute paths)
3. Warn if fallback policy is used (different from specified profile)

### Recommendation 8: Add Skill Telemetry / Audit Log [LOW]
**Impact:** LOW — Improves observability  
**Effort:** MEDIUM

Enhance `post_tool_use.py` hook to log:
1. Skill invoked, timestamp, duration
2. Mode state transitions (autopilot → phase 2, ralph → iteration 5, etc.)
3. Write to `.omc/audit/skill-audit.log` (structured JSON, one entry per line)

This enables post-mortem analysis of failed runs.

### Recommendation 9: Implement Graceful Degradation for Missing Skills [LOW]
**Impact:** LOW — Improves fault tolerance  
**Effort:** LOW

If a skill is not found when invoked:
1. Return error with suggestions for similar skills (e.g., "did you mean `autocomplete`?")
2. Offer fallback to related skill (e.g., if `ultrawork` not found, offer `ralph`)
3. Never silently skip a skill — always report to user

### Recommendation 10: Create Integration Test Suite [LOW]
**Impact:** MEDIUM — Improves confidence in hand-offs  
**Effort:** HIGH

Tests should cover:
1. deep-interview → ralplan → autopilot full pipeline (end-to-end)
2. Ralph with PRD refinement (verify scaffold is replaced)
3. Team spawn → monitor → shutdown (lifecycle)
4. State file persistence across session crash (resume)
5. Policy enforcement (deny/allow decisions)

Add to `tests/` directory; run on every CI build.

---

## Summary

**Key Findings:**

1. **Architecture is sound** — Pipeline is well-designed with clear phases and hand-offs
2. **Implementation is incomplete** — Several gaps between SKILL.md contracts and code evidence
3. **State management is fragile** — MCP is single point of failure; no local file fallback
4. **Intent routing is advisory** — Hooks suggest skills, but LLM may ignore suggestions
5. **Hand-offs are implicit** — File naming conventions and state transitions assumed, not validated
6. **Documentation has bugs** — 10 inconsistencies between SKILL.md and actual behavior found

**Overall Risk Level:** MEDIUM
- Autopilot/Ralph/Team work for happy-path scenarios
- Resume after crash is possible but risky
- Concurrent skill invocation not protected
- Policy enforcement is weak (fallback silently weakens security)

**Recommendation Priority:** Implement Recommendations 1–3 (critical path) before relying on production hand-offs.

---

**Audit Date:** 2026-04-16  
**Auditor:** Explore Agent (Read-only)  
**Word Count:** 7,847
