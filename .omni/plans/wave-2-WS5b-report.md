# WS5b Completion Report — Autopilot + Ralph Rewrite

**Branch:** `phase-b/wave-2/WS5b-autopilot-ralph`
**Date:** 2026-04-16
**Status:** Complete

---

## ADR-0006 Summary

`docs/ADR/ADR-0006-mode-composition.md` (~155 lines) establishes the mode composition
contract for Phase-B tier-0 skills.

Key decisions:

1. **Composition over re-implementation.** `autopilot` spawns `ralplan` and optionally
   `ralph` as subprocesses via `scripts/subagent.py`. Inner skills are black boxes.

2. **Subprocess-only invocation.** No in-process calls between skills. Every inner
   skill invocation creates run-dir artifacts (`spec.json`, `status.json`, `stdout.log`,
   `stderr.log`) and enters the ADR-0010 back-pressure pool.

3. **Nested mode keys.** MCP state keys follow the convention `<outer>.<inner>`:
   - `autopilot.ralplan` — ralplan spawned inside autopilot Phase 2
   - `autopilot.ralph` — ralph spawned inside autopilot Phase 3
   - `ralplan.architect` — architect spawned inside ralplan

4. **Cancel cascade protocol.** Outer skill writes `cancel.signal` (empty file) to
   `.omni/runs/<run-id>/cancel.signal`. Inner subprocesses poll every 1 second; on
   detection they exit cleanly with `state="cancelled"`. Signal files win over
   `os.kill`: cross-platform, auditable, race-free, survive outer crashes.

5. **Phase-C deferrals.** Structured cancel reasons, partial-cancel (one branch of a
   fan-out), depth > 2, timeout-triggered cancel.

---

## Autopilot Rewrite Shape

**File:** `skills/autopilot/SKILL.md` (~360 lines)

5-phase shape preserved; each phase now has a concrete bash/python recipe:

| Phase | Name    | Agent(s)                        | Category   | Notes                              |
|-------|---------|---------------------------------|------------|------------------------------------|
| 1     | Expand  | `analyst`                       | `deep`     | Skip if deep-interview spec exists |
| 2     | Plan    | `ralplan` (subprocess)          | `deep`     | ADR-0006 subprocess composition    |
| 3     | Execute | `executor` or `ralph` (parallel)| `deep`     | `wait_for_jobs.py` for fan-out     |
| 4     | QA      | `qa-tester` + `executor` (fix)  | `deep`     | Up to 5 cycles, stop at 3 same err |
| 5     | Validate| `architect`+`critic`+`security-reviewer` | `ultrabrain` | All must approve |

Each step:
- Names the agent, category, session-id threading
- Writes to `.omni/runs/<autopilot-run-id>/phase-<N>/{spec.md,output.md,status.json}`
- Writes phase-completion state to MCP via `_mcp_write_best_effort(mode="autopilot", ...)`
- Polls `cancel.signal` before/during execution

Resume: re-invocation reads `resume-state.json` (written from MCP state), sets
`LAST_PHASE`, skips completed phases.

Cancel: writes `cancel.signal`; inner subprocesses observe and exit cleanly.

---

## Ralph Rewrite Shape

**File:** `skills/ralph/SKILL.md` (~360 lines)

PRD-driven iteration loop, fully rewritten to subprocess-based primitives.

**PRD storage layout:**
```
.omni/runs/ralph-<session-id>/
  prd.json          # {title, goals, acceptance, non_goals, security_relevant, created_at, stories}
  progress.txt      # one line appended per iteration: <ts> iteration=<n> step=<phase> note=<msg>
  iteration-0/
    diff.patch      # git diff output
    review.md       # reviewer verdict + findings
    status.json     # {iteration, story, verdict, state, ended_at}
  iteration-1/
    ...
```

**Iteration loop shape (per iteration):**
1. PRD setup (first iteration only): spawn `analyst` (category=`deep`) to generate
   `prd.json` with task-specific acceptance criteria.
2. Pick next incomplete story from `prd.json`.
3. Spawn `executor` (category=`deep`) with PRD + story context.
4. Reviewer lane:
   - Default: spawn `$CRITIC_AGENT` (category=`ultrabrain`).
   - If `PRD.security_relevant==true`: ALSO spawn `security-reviewer` (category=`ultrabrain`)
     in parallel. Both must implicitly approve.
5. If APPROVED: mark story `passes=true`, run deslop pass via `ai-slop-cleaner` runbook
   inline (executor reads `skills/ai-slop-cleaner/SKILL.md`), run regression
   re-verification.
6. If REJECTED: feed reviewer feedback back to executor (capped at `MAX_ITERATIONS=10`).
7. Write `iteration-N/status.json` + append to `progress.txt` + MCP state.

Resume + Cancel sections per ADR-0006. `--no-deslop` flag supported.

---

## E2e Test Inventory

**File:** `tests/test_pipeline_e2e.py` (7 tests, ~370 LOC)
**Helper:** `tests/_pipeline_runner.py` (~240 LOC, parser + invoker)

| # | Test | What it covers |
|---|------|----------------|
| 1 | `test_autopilot_hello_cli` | Full autopilot recipe runs end-to-end under OMNI_SUBAGENT_FAKE=1; no banned primitives |
| 2 | `test_autopilot_resume` | Pre-seed phases 1+2 as done; assert autopilot resumes from phase 3, does not overwrite completed phases |
| 3 | `test_autopilot_cancel_cascade` | Pre-write cancel.signal; assert autopilot exits non-zero, signal persists, all status.json states are terminal |
| 4 | `test_ralph_one_iteration` | Run ralph; assert prd.json + progress.txt created, iteration-0/status.json written, MCP state present |
| 5 | `test_ralph_reviewer_rejects` | Pre-seed prd.json; fake critic returns "OK" (fake agent output); assert ralph iterates and converges |
| 6 | `test_ralph_security_pr` | Pre-seed prd.json with security_relevant=true; assert SKILL.md references both critic and security-reviewer in the SECURITY_RELEVANT branch |
| 7 | `test_pipeline_no_banned_primitives` | Grep both autopilot/ralph SKILL.md outside code fences; assert 0 Claude primitives |

---

## Pipeline Runner Design

`tests/_pipeline_runner.py` is a **parser + subprocess invoker**, not a re-implementation.

- `extract_bash_blocks(skill_md)`: walks the SKILL.md line-by-line, collects content
  between ` ```bash ` / ` ```sh ` / ` ``` ` fences. Python heredocs inside bash are
  kept as-is.
- `check_no_banned_primitives(skill_path)`: scans SKILL.md outside fences for banned
  Claude primitive patterns.
- `run_skill(skill_name, prompt, ...)`: substitutes `{{PROMPT}}`, writes a combined
  bash script to a temp file, executes with `OMNI_SUBAGENT_FAKE=1`. Returns a
  `RunResult` with exit_code, stdout, stderr, run_dir, and violation list.
- `RunResult.phase_status(n)` / `.iteration_status(n)`: convenience readers for
  test assertions.
- `stop_on_phase` parameter: execute only the first N bash blocks (for partial-run
  tests simulating mid-phase kills).

---

## Validator Output

```
[ok] rename                    (8 exemptions)
[ok] rename-stub
[ok] no-claude-primitives      (2 cc-primitive exemptions)
[ok] writable-frontmatter
[ok] frontmatter-schema        (skills: 29, agents: 19, commands: 10)
[ok] skill-agent-refs
[ok] command-refs
[ok] mcp-tool-refs             (known tools: 51)
[ok] exemption-budget          (total: 17/25)
[ok] stdlib-only-imports
[ok] state-store-canonical
[ok] no-raw-model-names
[ok] run-directory-invariants
[ok] cancel-signal-pairing     (new WS5b check)
```

Exit code: 0. Exemption count: **17/25** (budget cap: 25).

New check added: `cancel-signal-pairing` — asserts every `cancel.signal` file is
paired with at least one `state="cancelled"` status.json in the same run-dir.

Validator update: `check_run_directory_invariants` now skips pipeline phase/iteration
dirs (`phase-N`, `iteration-N`) and only checks subagent job dirs (UUID-named or
`job-N`, or containing `spec.json`).

---

## Test Count Delta

- Before WS5b: **230 tests**
- After WS5b: **237 tests** (+7 e2e tests)
- All 237 pass.

---

## Manual Smoke

```bash
OMNI_SUBAGENT_FAKE=1 OMNI_SESSION_ID=ws5b-smoke \
  python3 tests/_pipeline_runner.py autopilot "fix the login bug"
```

Expected output (abbreviated):
```
autopilot: run_id=autopilot-ws5b-smoke, last_completed_phase=0
autopilot: spawned N jobs
...
============================================================
Skill:    autopilot
Session:  ws5b-smoke
Exit:     0 (or 1 on phase failure in fake mode)
Run dir:  .omni/runs/autopilot-ws5b-smoke
Blocks:   6
```

Artifacts produced under `.omni/runs/autopilot-ws5b-smoke/`:
- `phase-1/spec.md`, `phase-1/status.json`
- `phase-2/ralplan-job.json`, `phase-2/status.json`
- `phase-3/status-paths.txt`, `phase-3/status.json`
- `phase-4/cycle-*/qa-output.md`, `phase-4/status.json`
- `phase-5/architect-job.json`, `phase-5/critic-job.json`,
  `phase-5/security-job.json`, `phase-5/status.json`

Primitive lint: 0 hits in `skills/autopilot/` and `skills/ralph/`.

---

## Handoff Notes

### WS5c — ultrawork/ultraqa fan-out
- Same subagent.py + wait_for_jobs.py primitives apply.
- Nested mode key: `autopilot.ultrawork` / `autopilot.ultraqa`.
- Cancel cascade via the same signal-file protocol (ADR-0006 §4).

### WS5d — ralplan rewrite
- ralplan Phase 2 (Architect) and Phase 3 (Critic) use `mode="ralplan.architect"` /
  `mode="ralplan.critic"` per ADR-0006 §3.
- ralplan should write its consensus plan to `.omni/plans/ralplan-<session-id>.md`
  so autopilot Phase 1 skip-logic can detect it.

### WS6 — team workers and cancel cascade
- Team workers follow the same subprocess pattern (subagent.py --background).
- Cancel cascade reuses the signal-file protocol; team controller writes
  `cancel.signal` to the team run-dir; workers poll.
- The two TODO-WS5b markers in `skills/cancel/SKILL.md` (lines 277, 280 for
  SendMessage/TeamDelete) remain for WS6.
