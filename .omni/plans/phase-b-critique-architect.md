# Phase B Plan — Architectural Review

*Reviewer: Architect. Read-only. Review date: 2026-04-16. Scope: structural coherence of `.omni/plans/phase-b-master-plan.md` against Phase-A SYNTHESIS, `int-pipeline-harness.md`, `int-hooks-triggers-audit.md`, and the current repo. The 8 locked decisions in §1 are not relitigated.*

## 0. Architectural verdict (one paragraph)

The plan is structurally the right plan for the locked decisions, and its workstream inventory covers every Critical/High finding in the Phase-A audits (§12 appendix). It is, however, **over-decomposed at the mechanical layer (WS1/WS2/WS9) and under-decomposed at the runtime-primitive layer (WS3/WS4/WS5/WS6/WS8)** — the riskiest truth the plan buries is that WS3, WS5, WS6 and WS8 jointly define a new Copilot-CLI runtime contract (router → state → background jobs → tmux/worktree lifecycle) and no WS owns that contract end-to-end. The `.omni` consolidation (P0-1) is only half-solved: WS1 collapses the directory split but leaves the **dual-state problem** — SQLite at `$OMNI_HOME/omni.db`, `.omni/runs/`, `.omni/plans/`, `.omni/specs/`, `.omni/state/*-state.json`, and the new `.omni/teams/` — untouched as a consolidation target. The dependency graph has one real cycle around WS3↔WS8 (router emits decisions into a state slot owned by an API that has not landed yet). Net: approve with restructuring of Waves 1–2 and a new **runtime-contract pre-gate** that locks router payload, state schema, and subagent background protocol before WS5 opens.

## 1. Does the architecture deliver the locked decisions? (WS-by-WS check)

**Decision 1 (Copilot-CLI-only) — delivered by WS2 + WS9.** Validator coverage is the right mechanism. Risk: the validator (WS9) is introduced *after* WS2 is editing the tree, so Wave-1 WS2 PRs have no automated proof of their acceptance criteria until WS9's skeleton is in place. The plan acknowledges this but the dependency should be tightened — WS9's skeleton must merge *first* in Wave 1.

**Decision 2 (OMC-style composable autonomous) — under-delivered by WS5.** WS5 rewrites the tier-0 skills one at a time but does not call out **mode composition** as a first-class deliverable. SYNTHESIS §10 P2-5 ("Mode composition grammar") is parked at `docs/PIPELINE.md` as documentation. That is insufficient: OMC's claim is that `ultrawork ⊂ ralph ⊂ autopilot` is a runtime fact. Without a composition contract, every SKILL.md is free to redefine the composition and it breaks silently.

**Decision 3 (front-door router + vague-prompt gating) — strongest WS in the plan.** WS3 is architecturally complete: classifier + precedence + structured decision + bypass + 40-prompt regression + `sync_triggers.py`. The weakness is that **the router is a hook but the handoff is a shared state slot (`state_read(mode="router")`)**, and that slot's semantics (TTL, cancel signal, session scoping) are not defined in WS3. The router implicitly assumes WS8 will deliver a router-compatible slot. Make `omni.router` a named deliverable of WS8 with WS3 as caller.

**Decision 4 (`.omc → .omni` rename) — mostly delivered by WS1.** WS1 is mechanical and well-scoped. Hole: directory rename and brand rename are called out, but the **command-namespace** rename (`/oh-my-claudecode:X → /omni-X`) is folded into WS2's "removes references". Treating a user-facing command namespace as a decontamination side-effect invites missing commands. Move it into WS1's acceptance criteria.

**Decision 5 (native team rebuild) — architecturally feasible.** tmux + git worktrees + stdlib-only Python orchestrator is a known-good pattern. Feasibility concerns in §2 and §6.

**Decision 6 (semantic model categories) — clean scope in WS4.** Resolver as a Python module, `.omni/config.json` override store, falsifiable grep test. Minor concern: both WS4 (`--category`) and WS5 (`--background`) edit `scripts/subagent.py` in Wave 2 — keep them in separate PRs with a documented merge order.

**Decision 7 (no external CLIs) — enforced by WS12's `check_stdlib_only.py` and implicit in WS2's forbidden-primitive map.** No structural gap.

**Decision 8 (deep-interview redesign deferred) — correctly scoped.** But WS3's vagueness redirect targets a destination (deep-interview) that is one of the nine paper-only skills in the synthesis. See §6.

## 2. Load-bearing assumptions not surfaced

**A1. `copilot -p --agent <name>` is a stable, non-interactive primitive** that supports parallel invocation. WS5 (ultrawork fan-out), WS6 (tmux panes), ralph background reviewer all depend on this. The plan never states it as a locked assumption. If Copilot `-p` (a) buffers stdout past parent timeout, (b) requires a TTY, or (c) rate-limits concurrent subscription requests, WS5/WS6 degrade to sequential execution.

**A2. Hook event semantics on Copilot CLI match Claude Code.** WS7 renames `${CLAUDE_PLUGIN_ROOT}` → `${COPILOT_PLUGIN_ROOT}` but never asserts that Copilot fires sessionStart / preToolUse / postToolUse / userPromptSubmit with the same JSON event shape. If the shape differs, WS3's router parses junk.

**A3. Skill frontmatter fields Copilot actually reads are unknown.** If Copilot ignores `triggers: [...]`, `sync_triggers.py` becomes a lint tool for a field nothing reads — skill-level autotrigger breaks silently.

**A4. Copilot has no `Task` primitive; everything routes through `copilot --agent`.** The plan is built on this. But it never distinguishes **one-turn vs multi-turn** agent invocation. WS6's tmux architecture assumes fresh conversations; WS5's ralph reviewer may assume continuity. Test in Wave 0.

**A5. Grep-zero is sufficient to prove rename semantics.** Mechanically verifiable, but a skill body referencing `/oh-my-claudecode:autopilot` inside a code fence can influence LLM imitation even when the command resolves. Probably fine, but surface the assumption.

**A6. Background `subagent.py &` will work with Copilot auth tokens.** If Copilot caches auth per-PID or needs a terminal for token refresh, ultrawork fan-out fails intermittently on long sessions.

Recommendation: Wave-0 smoke spike that exercises three parallel `subagent.py &` invocations, captures real hook event JSON to `.omni/audit/hook-shapes.jsonl`, and tests one-turn vs multi-turn agent dispatch. Block WS5/WS6 on the smoke's pass.

## 3. Workstream joints — right cuts or wrong cuts?

**WS1 + WS2 should stay separate but sequence tighter.** Merging rename and decontamination would collapse two different review concerns. The split is correct; the deficiency is WS2's Wave-1 parallelism creates merge conflicts on every SKILL.md. Land WS1 first in Wave 1, then open WS2. 1–2 days added, churn prevented.

**WS7 + WS8 should be one "runtime hardening" stream.** They co-define hooks' audit + policy and MCP's state + tools; both touch `.omni/audit/`; both need exception sanitization and connection discipline. Running them three waves apart (WS8 in Wave 2, WS7 in Wave 4) means WS3 and WS5 code against an MCP server with stale state API and a hook layer with the shlex bug. Move WS7's **schema-level** work (kill switches, env-var rename, shlex fix, launch_python) into early Wave 2 next to WS8; keep WS7's **content** work (banner, audit schema) in Wave 4.

**WS9 should be a cross-cutting gate, not a sibling WS.** The plan already treats it as half-parallel. In practice it is *the test harness for every other WS's acceptance criteria*. Rename to "W0-gate", commit skeleton on the Wave-0 branch, and let each WS grow its own subcommand in its own PR.

**WS10 + WS12 could merge.** Both gate PR mergeability. The split is ADR-readability only. Not a blocker.

**WS11 (docs) correctly last.** No change.

## 4. Dependency graph honesty check

**Cycle 1: WS3 ↔ WS8.** WS3 emits `omni.router.decision` into state slot `mode="router"`, which is part of WS8's state API. The DAG draws WS3 and WS8 as parallel siblings under WS1. They're not; WS3 consumes WS8. Either land WS8's state-API expansion in Wave 1 next to WS1, or admit the dependency and sequence it.

**Cycle 2: WS5 ↔ WS6.** WS6 depends on "WS5 partially done (ralph must exist)". That's sequential with a soft boundary, not parallel. Also, both WSes need the same run-directory layout for background jobs (`.omni/runs/<run-id>/<job-id>/{status.json, stdout.log, stderr.log}`), and neither owns it. Carve a micro-WS **"subagent background protocol"** (S, 1 day) landed at top of Wave 2; both WS5 and WS6 consume it.

**Sequencing issue: WS4 vs WS5/WS6.** WS4's grep-0 on raw model names can only be *met* after WS5/WS6 finish rewriting skills. Today WS4 edits existing skills and then WS5 re-edits them. Split WS4's acceptance: "resolver works" (Wave 2) and "grep-0 in skills/agents" (end of Wave 3, asserted by validator on every later PR).

## 5. Single source of truth — state consolidation gap

**The plan collapses the `.omc`/`.omni` directory split but leaves the state-source split.** Today the plugin has four parallel stores: (1) SQLite at `$OMNI_HOME/omni.db`, (2) markdown under `.omni/runs/<run-id>/`, (3) markdown under `.omni/plans/` + `.omni/specs/`, (4) JSON flat files under `.omni/state/*-state.json`. Phase B hardens #1 (WS8), renames #2–#4's directories (WS1), and WS6 adds a *fifth* store (`.omni/teams/<slug>/`) with its own state machine. After Phase B, five stores exist and each skill decides at write-time which one it trusts.

`int-pipeline-harness.md` §10.1 and §10.2 confirm several SKILL.md bodies still reference the JSON flat files and assume MCP is a parallel store, not the authoritative one. The plan interprets "collapse split-brain" as directory naming; I read SYNTHESIS P0-1 as **state-source ownership**. Recommendation: add a §WS8 deliverable **"State source-of-truth contract"** in `docs/CONTRACT.md` stating for each data class (state, artifacts, specs, plans, audit, trace, session, team worker state) which store is authoritative and which is derivative. Add `scripts/verify_plugin_contract.py --check-storage` to assert no skill writes to more than one store per data class. Explicitly retire or declare-mirror-only `.omni/state/*-state.json`. Without this, the rename is cosmetic.

## 6. First-to-break analysis

**WS6 (team) will blow up first.** Reasons, ranked:

- **New architecture on unverified primitives.** WS6 is the only XL workstream introducing a net-new runtime mechanism (tmux + worktrees + per-pane `copilot -p --agent --category`). Every failure mode of A1/A4/A6 in §2 lands here first.
- **Cross-platform cost is hidden.** "Fall back to plain subprocess.Popen + per-worker log" is another execution model to implement, test, and doc. XL becomes XL+fallback, still budgeted as L–XL.
- **State is not truly parallel.** SQLite WAL mode helps, but the 100-line stress test is not five long-running `copilot` subprocesses racing on human timelines. Races will surface in usage, not testing.
- **Cleanup is brittle.** `tmux kill-session + git worktree remove + state_clear` is three failure points. Half-killed tmux sessions with detached `copilot` children need PID-tracked kill, not session-scoped.
- **Windows fallback = "requires WSL"** is a product decision buried in INSTALL.md, not ADR'd. If corporate Windows laptops are in scope (WS7's Windows-Python-shim implies they are), this is a capability gap.

Mitigation: rescope WS6 as an M MVP (tmux + subprocess parallelism + single-stage handoff, `--experimental` flag) plus a later L full state-machine.

**Second-most-likely: WS3 router ↔ WS5 skill integration.** Router emits a payload; downstream skills must read `state_read(mode="router")` in their opening step. No structural enforcement — only a test. A forgotten preamble in one rewritten skill silently ignores the router. Require each tier-0 skill in WS5 to open with a canonical 3-line router-consumption preamble, lintable by `--check-pipeline`.

## 7. Architectural recommendations

1. **Add a runtime-contract pre-gate (S, 1 day) at top of Wave 1** that locks hook event JSON shape, `${COPILOT_PLUGIN_ROOT}` resolution, `copilot -p --agent` stdout + exit-code contract, parallel invocation behavior, skill frontmatter fields. Output: `docs/RUNTIME_CONTRACT.md`. Blocks WS3/WS5/WS6. *Why:* §2 A1–A6 are untested assumptions.

2. **Promote WS9 validator skeleton to Wave 0** so Wave-1 WS1/WS2 PRs cannot green-merge without it. Skeleton includes `--check-rename` and `--check-no-claude-primitives` stubs. *Why:* §3.

3. **Name a state-source-of-truth deliverable inside WS8** — one table in `docs/CONTRACT.md` naming authoritative vs derivative store per data class. Add `--check-storage` to the validator. *Why:* §5.

4. **Carve a "subagent background protocol" micro-WS (S) between WS4 and WS5.** Locks run-directory layout, `status.json` schema, `wait_for_jobs.py` polling contract. WS5 ultrawork and WS6 team both consume it. *Why:* §4 Cycle 2.

5. **Move WS7's schema-level work to Wave 1/early Wave 2** (kill switches, env-var rename, shlex fix, launch_python). These are small, security-relevant, and unblock WS3. Keep banner + audit schema expansion in Wave 4. *Why:* §3; P0-2 (kill switches) should not wait until Wave 4.

6. **Add a mode-composition contract deliverable in WS5** — single markdown + state-slot naming convention answering: does autopilot Phase 2 call ralph as subprocess or inline? Does ralph's state nest under autopilot's? How do they share session_id? What cancels at each nesting level? *Why:* Decision 2 composition is a runtime property, not a doc one.

7. **Make router state slot `mode="router"` a named WS8 deliverable** with TTL, cancel semantics, session scoping, concurrent-writer behavior. WS3 declared as consumer. *Why:* §1 Decision 3; §4 Cycle 1.

8. **Rescope WS6 as M MVP + L state machine**, MVP behind `--experimental` for one release. MVP validates the runtime contract; full version adds worktrees + multi-stage + ralph compose. *Why:* §6.

9. **Add ADR-0006 "state-source authority" and ADR-0007 "team-mode Windows posture".** Both are product decisions the plan makes implicitly. *Why:* §5, §6.

10. **Retire `.omni/state/*-state.json` or declare it a derivative read-only mirror** inside WS8. The current plan inherits v1.0.0's ambiguity. *Why:* §5.

11. **Require canonical 3-line router-consumption preamble in every tier-0 skill** (WS5), lintable by `--check-pipeline`. *Why:* §6 router-skill integration weakness.

12. **Split WS4 acceptance: "resolver works" Wave 2, "grep-0 in skills/agents" end of Wave 3.** Enforced by validator on every later PR. *Why:* §4 sequencing.

## 8. Items the plan should escalate to the user before Wave 0

The plan's §11 lists three (skill deletions, bypass syntax, CLAUDE.md redirect). The items below are **architectural** and should not be delegated to agent judgment.

1. **State source-of-truth policy.** MCP SQLite authoritative for machine-readable state with `.omni/` markdown strictly derivative? Or do `.omni/runs/*/spec.md` and `.omni/plans/*.md` remain authoritative inputs for resume semantics? ADR decision. Recommend: MCP authoritative; markdown is content-only.

2. **Windows team-mode posture.** ADR: (a) native via subprocess fallback, (b) WSL-only with installer refusal, or (c) deferred to Phase C. Plan drifts toward (a) but markets WSL.

3. **Router payload ownership.** `omni.router.decision` schema owner — WS3 (emitter) or WS8 (storage)? Recommend WS8.

4. **Mode composition contract scope.** Does `autopilot` call `ralph` as subprocess (fresh Copilot session) or inline (same LLM turn)? OMC does inline. Answer constrains `scripts/subagent.py` re-entry semantics.

5. **Background protocol: MCP tool or filesystem convention?** `subagent.py --background` writes run directory via MCP (queryable) or direct FS (simpler)? Determines whether WS6's team status monitor is a tool call or a glob+read loop.

6. **Accepted breakage surface for v2.0.0.** Plan promises "breaking changes called out" but never enumerates the known set: (a) `.omc/ → .omni/` migration mandatory, (b) `/oh-my-claudecode:* → /omni-*` breaks user scripts, (c) `OMC_SKIP_HOOKS → OMNI_SKIP_HOOKS`, (d) `CLAUDE_PLUGIN_ROOT → COPILOT_PLUGIN_ROOT`, (e) skills deleted per ADR-0002. User should sign off on the full break list before Wave 0, not discover it in the v2.0.0 CHANGELOG.

---

*End of review.*
