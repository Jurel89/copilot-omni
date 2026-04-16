# Phase A — Consolidated Findings & Recommendations

*Synthesis date: 2026-04-16. Source reports: 5 Claude subagents + 2 Codex (gpt-5.4) passes on the same questions. Citations use the form `[<report-slug> §<section>]` or `[<report-slug> <anchor>]`. Where Claude and Codex both saw the same thing, the claim is weighted higher and marked "corroborated". Where they diverge, the divergence is called out and a verification step is proposed.*

---

## 0. Executive summary (10 bullets — punchlines only)

1. **The plugin is split-brain.** The executable harness is `.omni/` + SQLite; the Markdown skill layer is still `.omc/` + Claude-native. Both Claude and Codex flag this as the single largest correctness problem. **[codex-internal-audit.md §2 Critical-2] [int-pipeline-harness.md §10.1]**
2. **Most tier-0 skills are paper-only in Copilot CLI.** `autopilot`, `ralph`, `team`, `ralplan`, `deep-interview`, `plan`, `cancel`, `ultraqa`, `ultrawork` all depend on Claude primitives (`Task()`, `Skill()`, `SendMessage`, `TeamCreate`, `AskUserQuestion`, `state_list_active`, `state_get_status`, `run_in_background`) that this harness does not implement. **[codex-internal-audit.md §1] [int-pipeline-harness.md §2-§7]**
3. **Kill switches `DISABLE_OMC` / `OMC_SKIP_HOOKS` are referenced in `CLAUDE.md` but not implemented in any hook.** Users cannot disable the harness without editing code. **[int-hooks-triggers-audit.md §8.1 Critical]**
4. **Front-door intent routing is advisory regex — no precedence, no deterministic handoff.** Hook emits a comma-separated hint; the LLM is free to ignore it. All three upstreams have stronger front doors (OMC: keyword+injector+ralplan gate; OMOA: IntentGate; GSD: `/gsd-do` + `/gsd-next`). **[int-hooks-triggers-audit.md §5.1] [codex-internal-audit.md §3] [codex-external-repos.md §Cross-plugin]**
5. **MCP server publishes JSON schemas but never validates inputs.** Arguments flow through `spec["handler"](args)` with no schema enforcement. Raw exceptions leak back to the client as `str(exc)`. **[codex-internal-audit.md §5 High] [int-hooks-triggers-audit.md §11.1]**
6. **`scripts/subagent.py` is weaker than its contract.** `AGENTS.md` advertises `--allow-all` and "collects output"; the script defaults to `--no-allow-all` and returns only an exit code. Any skill assuming captured output is broken. **[codex-internal-audit.md §2 High]**
7. **Windows story is overstated.** `.mcp.json`, `hooks/hooks.json`, `scripts/omni.cmd`, and every `/omni-*` command hardcode `python3`, which is not a default Windows shim. **[codex-internal-audit.md §2 High]**
8. **MCP surface has dead tools.** `session_search` has no writer; `trace_summary` / `trace_timeline` have no writer; `subtask.route` always returns `{"route": "executor"}`. **[codex-internal-audit.md §5 Medium]**
9. **Upstream landscape lesson.** OMC teaches hook-as-runtime and mode composition; OMOA teaches IntentGate + categories + named orchestrators; GSD teaches artifact-first lifecycle with on-disk state. All three dwarf copilot-omni on agent count, skill depth, and verification discipline. **[codex-external-repos.md §Takeaways]**
10. **Tests validate the small executable core, not the behavioral contract.** `test_discovery.py` checks counts and frontmatter; no test asserts that a SKILL.md's referenced commands/tools exist. The repo can pass CI while shipping non-runnable orchestration docs. **[codex-internal-audit.md §6]**

---

## 1. Upstream landscape snapshot

### 1.1 oh-my-claudecode — what they do that we don't

Deep-hook runtime layer (20 scripts across 11 lifecycle events), MCP-centric state (~40 tools under a single `t` server exposing notepad/project-memory/wiki/state/shared-memory/trace/session-search/LSP/ast-grep/python), composable mode grammar where `ultrawork ⊂ ralph ⊂ autopilot` and `ralplan` front-doors them **[ext-oh-my-claudecode.md §5, §6, §7]**. Session-id isolation with 2-hour staleness window, reinforcement circuit breakers (autopilot 20 reinforcements), context-guard at 75%/95% **[ext-oh-my-claudecode.md §9, §11]**. Read-only reviewer agents are structurally enforced via `disallowedTools: Write, Edit` on `architect`/`critic`/`code-reviewer`/`security-reviewer` **[ext-oh-my-claudecode.md §4]**. Multi-provider routing (`omc ask claude|codex|gemini`, `ccg`, `omc-teams`) **[ext-oh-my-claudecode.md §3]**. **Corroboration**: Codex independently flags the same mode composition and hook-heaviness, plus documents drift (README "29 agents" vs 19 on disk vs 37 skill dirs vs "32 skills" doc) **[codex-external-repos.md §1]**.

### 1.2 oh-my-openagent — what they do that we don't

Explicit **IntentGate** classifier (research / implementation / investigation / evaluation / fix) that runs before routing **[ext-oh-my-openagent.md §6, §8]**. Clean three-layer mental model: intent classification → named strategic/orchestration agents (Sisyphus/Prometheus/Metis/Momus/Atlas) → category workers (`ultrabrain`, `visual-engineering`, `quick`, `deep`, `artistry`, `writing`) **[ext-oh-my-openagent.md §5, §7]**. **Dual-prompt agents** that auto-detect Claude vs GPT family at runtime and swap XML-tagged principles (~300 lines) vs detailed checklists (~1,100 lines) — `isGptModel()` in code **[ext-oh-my-openagent.md §5]**. Per-agent `fallback_models` chains, model-capability normalization (auto-downgrades unsupported reasoning/thinking/temperature), hashline edit-tool (`LINE#ID` content hashes) that claims 6.7% → 68.3% on Grok Code Fast 1 **[ext-oh-my-openagent.md §10, §6]**. Wisdom-accumulation notepads (`.sisyphus/notepads/{plan}/learnings.md` + `decisions.md` + `issues.md` + `verification.md` + `problems.md`) + `boulder.json` for cross-session continuity **[ext-oh-my-openagent.md §7, §9]**. **Corroboration**: Codex independently identifies IntentGate as OMOA's cleanest design point and flags the same rename-compat leakage **[codex-external-repos.md §2]**.

### 1.3 get-shit-done — what they do that we don't

Full phase state machine: `discuss-phase → ui-phase → plan-phase → execute-phase → verify-work → ui-review → ship` with fixed artifact contract (`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, per-phase `CONTEXT.md`/`RESEARCH.md`/`PLAN.md`/`SUMMARY.md`/`VALIDATION.md`/`VERIFICATION.md`/`UAT.md`) **[ext-get-shit-done.md §2, §7, §8]**. **Four-gate taxonomy** (Pre-flight / Revision / Escalation / Abort) with consistent vocabulary **[ext-get-shit-done.md §8]**. XML task schema (`<read_first>`, `<action>`, `<verify>`, `<acceptance_criteria>`, `<must_haves>`) forces concreteness, Nyquist validation maps tests → requirements before code **[ext-get-shit-done.md §2, §6.1]**. Wave-based parallel execution with worktree isolation and post-wave regression gate **[ext-get-shit-done.md §4.4]**. **Deterministic intent routers**: `/gsd-do` (freeform → command) and `/gsd-next` (state → next step) **[ext-get-shit-done.md §10]**. 14-runtime installer (Claude, Copilot, OpenCode, Cursor, Codex, Qwen, Cline, CodeBuddy, Gemini, Kilo, Windsurf, Antigravity, Augment, Trae) **[ext-get-shit-done.md §1, §11]**. **Corroboration**: Codex independently notes `/gsd-do` + `/gsd-next` as the cleanest command-dispatch story among the three **[codex-external-repos.md §3]**.

### 1.4 Common patterns across all three upstreams

All three ship: a tiered planner/executor/reviewer agent separation, a "don't stop" persistence loop (ralph / ralph-loop / autonomous), a parallel fan-out primitive (ultrawork / background agents / wave execution), mandatory verification/deslop passes, on-disk state under a project-root directory, keyword triggers + explicit slash commands, multi-provider/multi-runtime ambitions, and a "deep interview / discuss phase" front-door gate for vague requests **[codex-external-repos.md §Cross-plugin table]**. All three also exhibit surface-area inflation: doc/code count drift, rename baggage, runtime fragility — flagged by Codex as a common anti-pattern copilot-omni should resist **[codex-external-repos.md §Takeaways]**.

### 1.5 Claude vs Codex agreement matrix (external)

| Claim | Claude (5 subagents) | Codex (gpt-5.4) | Verdict |
|---|---|---|---|
| OMC has doc/code drift on agent & skill counts | Yes **[ext-oh-my-claudecode.md §12.2]** | Yes **[codex-external-repos.md §1]** | Corroborated, high confidence |
| OMC's ralph was recently hardened against self-approval | Yes **[ext-oh-my-claudecode.md §13]** | Yes **[codex-external-repos.md §1 Recent direction]** | Corroborated |
| OMOA's rename `oh-my-opencode → oh-my-openagent` is incomplete | Yes **[ext-oh-my-openagent.md §1, §12]** | Yes **[codex-external-repos.md §2 Notable weaknesses]** | Corroborated |
| OMOA targets OpenCode, not Claude Code (despite "compatibility" marketing) | Yes **[ext-oh-my-openagent.md §2]** | Yes **[codex-external-repos.md §2 Positioning]** | Corroborated |
| GSD is workflow-ceremony-heavy | Yes **[ext-get-shit-done.md §13]** | Yes **[codex-external-repos.md §3 Notable weaknesses]** | Corroborated |
| GSD's `/gsd-do` + `/gsd-next` is the cleanest command-dispatch front door | Implied via §10 **[ext-get-shit-done.md §10]** | Explicit **[codex-external-repos.md §3 Intent-routing]** | Corroborated |
| OMOA's IntentGate is the cleanest front-door classifier | Implied via §8 **[ext-oh-my-openagent.md §8]** | Explicit **[codex-external-repos.md §2 Intent-routing]** | Corroborated |
| OMC has 37 skill dirs (filesystem) vs ~32 documented | Both report the same mismatch **[ext-oh-my-claudecode.md §3]** / **[codex-external-repos.md §1 Skill catalog]** | Corroborated |
| OMOA recently added custom agent support (`agent_definitions`) as a major feature | Yes **[ext-oh-my-openagent.md §14]** | Yes **[codex-external-repos.md §2 Recent direction]** | Corroborated |
| GSD v1.36 added knowledge-graph (`/gsd-graphify`) and SDK query | Yes **[ext-get-shit-done.md §14]** | Yes **[codex-external-repos.md §3 Recent direction]** | Corroborated |
| OMC's `mcp-server.cjs` is bundled/minified — hard to audit | Yes **[ext-oh-my-claudecode.md §12.1]** | Not explicitly mentioned | Claude-only; verify by attempting to read the file |
| OMOA's hashline edit tool claims 6.7% → 68.3% on Grok | Yes **[ext-oh-my-openagent.md §6, §11]** | Not explicitly mentioned | Claude-only; benchmark claim worth spot-checking |
| OMC's ralplan "cancel window" (state_clear disables stop-hook enforcement) | Yes **[ext-oh-my-claudecode.md §7, §10]** | Not mentioned | Claude-only; important for any copilot-omni adoption |

No material disagreement between Claude and Codex on external-repo findings. Divergences are scope (Claude reports were deeper per-repo; Codex produced a synthesis already) rather than conflicting facts.

---

## 2. Gap analysis: copilot-omni vs upstreams

| Capability | oh-my-claudecode | oh-my-openagent | GSD | copilot-omni | Gap severity |
|---|---|---|---|---|---|
| Orchestration depth | Modes composable (`ultrawork ⊂ ralph ⊂ autopilot`, `ralplan` gates) **[ext-oh-my-claudecode.md §7]** | Intent-gate + named personas + categories **[ext-oh-my-openagent.md §7]** | Phase state machine w/ 4-gate taxonomy **[ext-get-shit-done.md §8]** | Skill docs describe modes but runtime primitives absent **[codex-internal-audit.md §1]** | **CRITICAL** |
| Agent catalog size | 19 files + tier variants → "28" **[ext-oh-my-claudecode.md §4]** | 11 built-ins + 8 categories + dynamic custom agents **[ext-oh-my-openagent.md §5]** | 31 specialist files **[ext-get-shit-done.md §5]** | 19 agent files **[int-pipeline-harness.md §8.1]** | Medium |
| Hook surface | 20 scripts / 11 events **[ext-oh-my-claudecode.md §5]** | 52 hooks / 3 tiers / 10 OpenCode handlers **[ext-oh-my-openagent.md §6]** | 10 ops-focused hooks **[ext-get-shit-done.md §9]** | 4 hooks: sessionStart/pre/post/userPromptSubmit **[int-hooks-triggers-audit.md §1]** | **High** |
| MCP tool surface | ~40 tools (`t` server) **[ext-oh-my-claudecode.md §6]** | 3 built-in + skill-embedded + `.mcp.json` tier **[ext-oh-my-openagent.md §4.3]** | No MCP server; `gsd-tools.cjs` single CLI **[ext-get-shit-done.md §9]** | 30 tools in 9 families but several dead (`session_search`, trace, `subtask.route`) **[codex-internal-audit.md §5]** | **High** |
| State persistence model | `.omc/` + MCP `state_*` + session-id iso + staleness **[ext-oh-my-claudecode.md §9]** | `.sisyphus/` + boulder + notepads + plugin cache **[ext-oh-my-openagent.md §9]** | `.planning/` with STATE.md progression engine **[ext-get-shit-done.md §7]** | `.omni/` (executable) + `.omc/` (skills) — split-brain **[codex-internal-audit.md §2]** | **CRITICAL** |
| Intent routing sophistication | Keyword detector + scored injector + ralplan gate + pre-tool-enforcer **[ext-oh-my-claudecode.md §8]** | IntentGate + keyword-detector + auto-slash-command + ultrawork override **[ext-oh-my-openagent.md §8]** | `/gsd-do` freeform router + `/gsd-next` deterministic state router **[ext-get-shit-done.md §10]** | Regex hint-only, no precedence, no handoff **[int-hooks-triggers-audit.md §5.1]** | **CRITICAL** |
| Test coverage | Vitest + integration fixtures + PR review CI **[ext-oh-my-claudecode.md §13]** | Bun test + test-setup.ts + CI isolation for `mock.module()` **[ext-oh-my-openagent.md §10]** | Vitest + c8 coverage threshold 70% **[ext-get-shit-done.md §3]** | pytest covering CLI/MCP/hooks happy path; no contract tests **[codex-internal-audit.md §6]** | **High** |
| Docs | 11 translated READMEs + AGENTS.md + CHANGELOG **[ext-oh-my-claudecode.md §2]** | docs/guide + docs/reference + 4 translated READMEs **[ext-oh-my-openagent.md §3]** | docs/ARCH + USER-GUIDE + COMMANDS + AGENTS + 4 translated **[ext-get-shit-done.md §1]** | README + CLAUDE.md + AGENTS.md, session banner stale **[codex-internal-audit.md §2]** | Medium |
| Distribution | Claude plugin marketplace + `oh-my-claude-sisyphus` npm **[ext-oh-my-claudecode.md §1]** | `oh-my-opencode` npm + 11 platform binaries **[ext-oh-my-openagent.md §1]** | `get-shit-done-cc` npx + 14-runtime installer **[ext-get-shit-done.md §1]** | Single plugin, Python stdlib only **[int-pipeline-harness.md §8.4]** | Low (corp-safe by design) |
| Cross-platform story | Tested on mac/linux; Windows via WSL **[ext-oh-my-claudecode.md §12]** | Windows built on `windows-latest` (Bun segfault workaround); hardcoded `/tmp/oh-my-opencode.log` **[ext-oh-my-openagent.md §10, §12]** | WSL detection in installer; MCP stdio deadlocks documented **[ext-get-shit-done.md §13]** | `python3` hardcoded everywhere; `scripts/omni.cmd` still calls `python3` **[codex-internal-audit.md §2 High]** | **High** |
| Kill switches | `DISABLE_OMC`, `OMC_SKIP_HOOKS` referenced in user CLAUDE.md **[ext-oh-my-claudecode.md §10]** | `OMO_SEND_ANONYMOUS_TELEMETRY=0`, `OMO_DISABLE_POSTHOG=1` **[ext-oh-my-openagent.md §12]** | `GSD_SKIP_SCHEMA_CHECK=true`; `gsd-prompt-guard.js` non-disableable **[ext-get-shit-done.md §13]** | None implemented; CLAUDE.md references them anyway **[int-hooks-triggers-audit.md §8.1 Critical]** | **CRITICAL** |
| Adversarial review loop | Ralph step 7.5 mandatory deslop + 7.6 regression re-verify + reviewer tiers **[ext-oh-my-claudecode.md §7]** | Momus ruthless reviewer (OKAY when 100% file refs) + review-work 5-agent fan-out **[ext-oh-my-openagent.md §5]** | gsd-plan-checker (3-iter cap + stall detect) + gsd-code-reviewer + audit-fix **[ext-get-shit-done.md §4.5]** | Reviewer lanes documented in SKILL.md but not wired to runtime **[codex-internal-audit.md §1 Ralph]** | **High** |
| Deep-interview gating | `deep-interview` with mathematical ambiguity (≤0.2), challenge agents (Contrarian r4+, Simplifier r6+, Ontologist r8+), soft limit 10 hard 20 **[ext-oh-my-claudecode.md §3]** | Prometheus interview + Metis gap analyzer + Momus review loop **[ext-oh-my-openagent.md §7]** | `/gsd-discuss-phase` (interview/auto/chain/power/all modes) + assumptions-analyzer **[ext-get-shit-done.md §4.3]** | `deep-interview/SKILL.md` exists but depends on missing `AskUserQuestion` + `Task()` + `.omc` **[codex-internal-audit.md §1 Deep-Interview]** | **High** |
| Wiki / memory | `wiki` (Karpathy keyword+tag, no embeddings) + `notepad` + `project-memory` + `remember` + `learner` + `skillify` **[ext-oh-my-claudecode.md §3]** | `.sisyphus/notepads/{plan}/` wisdom accumulation + session-search **[ext-oh-my-openagent.md §7, §9]** | `.planning/intel/` + `.planning/graphs/` + global learnings `~/.gsd/knowledge/` **[ext-get-shit-done.md §11]** | `wiki_*` MCP tools exist + `notepad_*` + `remember` skill, but no ingestion hooks **[int-pipeline-harness.md §8.3]** | Medium |
| UI-spec / AI-spec templates | None explicit (`designer` agent produces UI ad-hoc) | `frontend-ui-ux` skill + Gemini-routed category **[ext-oh-my-openagent.md §5]** | `XX-UI-SPEC.md` (6 pillars) + `XX-AI-SPEC.md` (framework + eval strategy) **[ext-get-shit-done.md §4.3, §6.1]** | None | Medium |
| QA cycling | `ultraqa` (5 cycles, stop on 3 identical) **[ext-oh-my-claudecode.md §3]** | review-work (5 parallel sub-agents) + runtime-fallback + model-fallback **[ext-oh-my-openagent.md §4.2, §6]** | verify-work + validate-phase + audit-fix + Nyquist auditor **[ext-get-shit-done.md §4.5]** | `ultraqa/SKILL.md` exists but relies on `Task()` + `.omc/state/` **[codex-internal-audit.md §1 UltraQA]** | **High** |
| Phase state machine | Mode state in `.omc/state/*-state.json` per mode **[ext-oh-my-claudecode.md §9]** | `.sisyphus/boulder.json` + tasks/*.json **[ext-oh-my-openagent.md §9]** | `STATE.md` with `gsd-tools.cjs state validate/sync/advance-plan` **[ext-get-shit-done.md §7, §9]** | Mode state flat in `.omc/state/`; split between file + MCP; no formal state machine **[int-pipeline-harness.md §10.1]** | **High** |
| Resume semantics | `persistent-mode.cjs` Stop hook with session-id isolation + 2-hour staleness + reinforcement counter (autopilot 20 max) **[ext-oh-my-claudecode.md §7]** | `boulder.json` + session recovery hook **[ext-oh-my-openagent.md §7]** | `STATE.md` + `.continue-here.md` + `/gsd-resume-work` **[ext-get-shit-done.md §4.4]** | Skill docs mention resume; no state-machine validation; single source of failure (MCP) **[int-pipeline-harness.md §2.3 Gap 4]** | **High** |

---

## 3. Autonomous pipeline — does it actually work?

| Skill | Copilot CLI verdict | Claude Code verdict | Evidence |
|---|---|---|---|
| **autopilot** | Broken (paper-only). Depends on `.omc` discovery, `Task()` subagents, `Skill()`, `/oh-my-claudecode:cancel` | Likely works (its upstream home) | **[codex-internal-audit.md §1 Autopilot]** + **[int-pipeline-harness.md §2.3 Gap 1-5]** |
| **ralph** | Broken. Needs `Task(run_in_background)`, `Skill("ai-slop-cleaner")`, `omc ask codex`, `docs/shared/agent-tiers.md`, `/oh-my-claudecode:cancel` — none exist | Partially (runs in Claude Code plugin) | **[codex-internal-audit.md §1 Ralph]** + **[int-pipeline-harness.md §3.3]** |
| **ultrawork** | Broken (prose only). No parallel runtime; `scripts/subagent.py` is single synchronous subprocess. Missing `agent-tiers.md` | Works | **[codex-internal-audit.md §1 Ultrawork]** + **[int-pipeline-harness.md §4.1]** |
| **ultraqa** | Broken. Cycle loop relies on `Task(...)`, writes to `.omc/state/`, depends on `/oh-my-claudecode:cancel` | Works | **[codex-internal-audit.md §1 UltraQA]** + **[int-pipeline-harness.md §4.2]** |
| **ralplan** | Broken. Alias to non-existent `/oh-my-claudecode:omc-plan` (shipped command is `/omni-plan`); needs `AskUserQuestion`, Skill handoffs | Works | **[codex-internal-audit.md §1 Ralplan]** + **[int-pipeline-harness.md §5.3 Gap in Code]** |
| **team** | Broken. Requires `TeamCreate`/`TaskCreate`/`TaskUpdate`/`SendMessage`/`TeamDelete` + `cleanup-orphans.mjs` + `omc team` subcommand — none exist | Works | **[codex-internal-audit.md §1 Team]** + **[int-pipeline-harness.md §6.4]** |
| **deep-interview** | Broken. Needs `AskUserQuestion`, `Task()`, `.omc/specs/` writes, `Skill()` handoffs | Works | **[codex-internal-audit.md §1 Deep-Interview]** |
| **plan** | Broken. Needs `AskUserQuestion`, `Task()`, `Skill("compact")`, `Skill("oh-my-claudecode:team")`, `state_write(session_id=)` — server has none of these | Works | **[codex-internal-audit.md §1 Plan]** |
| **cancel** | Broken. Calls `state_list_active`, `state_get_status`, `SendMessage`, `TeamDelete`, `cleanup-orphans.mjs`; none exist. Bash fallback is `.omc`-based and Unix-first | Works | **[codex-internal-audit.md §1 Cancel]** + **[int-pipeline-harness.md §11 Bug 9]** |

**Bottom line**: nine of the flagship autonomous skills are Claude Code re-ports that have not been translated to the Copilot CLI runtime. The harness has code for 4 hooks, an MCP server with 30 tools, a subagent bridge, and a CLI; the skills talk to a much larger surface that was never ported.

---

## 4. Harness engineering findings

Merged and deduped from internal reports. Citation format: `file:line` where the source report gave one.

### Critical

| # | Area | Description | Citation | Flagged by |
|---|---|---|---|---|
| C1 | State API mismatch | Skills use `state_list_active` / `state_get_status` / `session_id` / cancel-signal; server only has `state_write`/`state_read`/`state_clear` with `mode`+`body` | `mcp/server.py:470-508, 857-881` | Codex **[codex-internal-audit.md §2 Critical-1]** |
| C2 | Storage split-brain | Executable harness uses `.omni/`; skills/agents still reference `.omc/*` throughout | `AGENTS.md:77-90` vs skills; `mcp/server.py:349-359` | Codex **[codex-internal-audit.md §2 Critical-2]** + Claude **[int-pipeline-harness.md §10.1]** |
| C3 | Team primitives absent | `TeamCreate`/`TaskCreate`/`TaskUpdate`/`SendMessage`/`TeamDelete`/`cleanup-orphans.mjs` missing | `skills/team/SKILL.md:53-76, 577-582` | Codex **[codex-internal-audit.md §2 Critical-3]** + Claude **[int-pipeline-harness.md §11 Bug 6]** |
| C4 | `omc ask codex` undefined | Plan/ralph call it; `scripts/omni.py` has no `ask` subcommand | `scripts/omni.py:165-194` vs `skills/plan/SKILL.md:74-75` | Codex **[codex-internal-audit.md §2 Critical-4]** |
| C5 | Kill switches unimplemented | `DISABLE_OMC` / `OMC_SKIP_HOOKS` referenced in CLAUDE.md, zero matches in source | grep confirms zero matches | Claude **[int-hooks-triggers-audit.md §8.1 Critical]** |

### High

| # | Area | Description | Citation | Flagged by |
|---|---|---|---|---|
| H1 | MCP schema enforcement missing | `TOOLS` publishes schemas but `_handle()` never validates | `mcp/server.py:1053-1061` | Codex **[codex-internal-audit.md §2 High-1]** + Claude **[int-hooks-triggers-audit.md §11.1]** |
| H2 | `scripts/subagent.py` weaker than AGENTS.md | Defaults `--no-allow-all`, captures no output, returns int only | `scripts/subagent.py:32-42` vs `AGENTS.md:72-75` | Codex **[codex-internal-audit.md §2 High-2]** |
| H3 | Windows: `python3` hardcoded everywhere | `.mcp.json`, `hooks/hooks.json`, `scripts/omni.cmd`, every `/omni-*` command | `.mcp.json:3-7`, `hooks/hooks.json:5-32`, `scripts/omni.cmd:1-3` | Codex **[codex-internal-audit.md §2 High-3]** |
| H4 | `${CLAUDE_PLUGIN_ROOT}` expansion assumed | JSON is not shell-interpreted; silent failure if harness does not expand | `hooks/hooks.json:8,15,22,29` | Claude **[int-hooks-triggers-audit.md §1.1 Critical]** |
| H5 | `planner` agent routes to non-existent `/oh-my-claudecode:start-work` | | `agents/planner.md:31-34, 51-52, 94-97` | Codex **[codex-internal-audit.md §2 High-4]** |
| H6 | Hook trigger coverage misses declared skill triggers | Autopilot `auto pilot`/`autonomous`/`build me`/`create me`/`make me`/`I want a/an`; Ralph `don't stop`/`must complete`; Ultrawork `ulw` — none matched | `hooks/user_prompt_submit.py:13-24` vs each SKILL.md | Codex **[codex-internal-audit.md §2 High-5]** + Claude **[int-hooks-triggers-audit.md §Bug 8]** |
| H7 | `shlex.split(posix=True)` fallback bypasses token checks | On ValueError falls back to `.split()`; `rm'-rf /` evades `rm` token match | `hooks/pre_tool_use.py:80-82` | Claude **[int-hooks-triggers-audit.md §2.1 Critical]** |
| H8 | Audit log race / corruption | Concurrent appenders can interleave JSON lines on Windows; `log_dir.mkdir` TOCTOU on some filesystems | `hooks/post_tool_use.py:19-27` | Claude **[int-hooks-triggers-audit.md §3.1 Critical]** |

### Medium

| # | Area | Description | Citation | Flagged by |
|---|---|---|---|---|
| M1 | Dead MCP tools | `session_search` has no writer; `trace_summary`/`trace_timeline` have no writer; `subtask.route` always returns `executor` | `mcp/server.py:650-658, 624-647, 675-676` | Codex **[codex-internal-audit.md §5]** |
| M2 | Raw exception leak | `_handle()` returns `str(exc)` — exposes paths and internals | `mcp/server.py:1062-1063` | Codex **[codex-internal-audit.md §5]** |
| M3 | Validation scripts shallow | `validate_plugin.py`/`discovery_smoke.py` never verify referenced command/tool names | `scripts/validate_plugin.py:28-69`, `scripts/discovery_smoke.py:16-63` | Codex **[codex-internal-audit.md §2 Medium-3]** |
| M4 | Stale session banner | `session_start.py` says "29 MCP tools, 28+ skills, 17+ agents" vs actual 30/37/19 | `hooks/session_start.py:8-12` | Codex **[codex-internal-audit.md §2 Medium-4]** + Claude **[int-hooks-triggers-audit.md §4.1]** |
| M5 | Tests dirty the repo | `tests/test_security.py` + artifact mirror creates `.omni/runs/run-2/spec.md` in-place | `tests/test_security.py:138-151`, `mcp/server.py:349-359` | Codex **[codex-internal-audit.md §2 Low-1]** |
| M6 | Connection pool absent + leaks | Each tool call opens new SQLite conn; not all handlers use `_Conn` context manager | `mcp/server.py:56-72`, various | Claude **[int-hooks-triggers-audit.md §11.2, §11.3]** |
| M7 | Policy file trust boundary | World-writable `.omni/policy-<profile>.json` silently accepted; no permission check | `hooks/pre_tool_use.py:51-52` | Claude **[int-hooks-triggers-audit.md §10.2]** |
| M8 | Tool reference asymmetry | Agents reference `lsp_diagnostics`, `ast_grep_search`, `WebSearch`, `WebFetch` — none implemented locally | `agents/executor.md:58-62`, etc. | Codex **[codex-internal-audit.md §4]** |
| M9 | Command naming mismatch | Shipped commands are `/omni-*`; skills/agents reference `/oh-my-claudecode:*` | `commands/*.md` vs skills | Codex **[codex-internal-audit.md §4]** |

### Low

| # | Area | Description | Citation | Flagged by |
|---|---|---|---|---|
| L1 | No ranking in hint routing | All matches joined comma-separated; no precedence | `hooks/user_prompt_submit.py:33-40` | Both |
| L2 | `fullauto` matches autopilot regex `\b(... full\s*auto ...)\b` (zero spaces allowed) | | `hooks/user_prompt_submit.py:14` | Claude **[int-hooks-triggers-audit.md §5.2]** |
| L3 | Audit data incomplete | No args, return value, session id — only tool name + status | `hooks/post_tool_use.py:21-25` | Claude **[int-hooks-triggers-audit.md §3.3]** |
| L4 | Silent error in post_tool_use | `except Exception: pass` drops audit writes without signal | `hooks/post_tool_use.py:27-29` | Claude **[int-hooks-triggers-audit.md §3.2]** |
| L5 | `pre_tool_use.py` uses Claude-era `CLAUDE_PLUGIN_ROOT` name + fail-open | Acknowledged but a semantic drift | `hooks/pre_tool_use.py:4-6` | Codex **[codex-internal-audit.md §2 Low-3]** |
| L6 | Substring protected-path match | `.omni/config.jsonXX` false-positives; traversal cases safe-by-normpath | `hooks/pre_tool_use.py:121` | Claude **[int-hooks-triggers-audit.md §2.4]** |
| L7 | Tight hook timeouts | 5–10s; I/O under load could miss | `hooks/hooks.json:9-30` | Claude **[int-hooks-triggers-audit.md §1.3]** |

---

## 5. Front-door intent routing — the single most important gap

Today copilot-omni's front door is a **single regex-based hint**: `hooks/user_prompt_submit.py` matches 10 trigger patterns against the user prompt, emits `{"additionalContext": "copilot-omni: matched skill trigger(s): X, Y. Consider invoking..."}`, and hopes the LLM will pick the right skill **[int-hooks-triggers-audit.md §5.1]**. There is no precedence model, no disambiguation, no deterministic handoff, no vagueness detection, no resume hint on session start, and no `cancel` trigger even though cancel is how every mode is supposed to exit **[codex-internal-audit.md §3]**. Multiple matches ("autopilot plan and verify") produce a three-way hint with no primary choice **[int-hooks-triggers-audit.md §5.1]**. All three upstreams do this dramatically better: OMC has a keyword-detector → scored skill injector → ralplan gate → pre-tool-enforcer defense-in-depth chain **[ext-oh-my-claudecode.md §8]**; OMOA has an explicit IntentGate that classifies into research/implementation/investigation/evaluation/fix before routing **[ext-oh-my-openagent.md §8]**; GSD has deterministic `/gsd-do` (freeform → command) + `/gsd-next` (state → next workflow step) with 8 ordered routing rules and hard safety gates **[ext-get-shit-done.md §10]**. This is copilot-omni's single biggest leverage point.

**Concrete design for copilot-omni's front-door router (6 requirements):**

- **R1. Two-stage router.** Stage 1: *classify* (research / implement / debug / verify / plan / ship / remember / cancel) — cheap regex + keyword scoring, always runs. Stage 2: *resolve* (pick one skill or redirect to deep-interview if ambiguity ≥ threshold) — runs only when classification confidence is high enough.
- **R2. Precedence table, not a flat list.** `cancel > deep-interview > ralplan > autopilot > ralph > team > ultrawork > plan > verify > debug > wiki > remember > ship`. When multiple match, emit one winner plus at most one runner-up; do not dump everything.
- **R3. Deterministic "what's next" command.** A `/omni-next` command (analogue of `/gsd-next`) that reads MCP state + on-disk artifacts and deterministically picks the next action: resume active mode, advance phase, or ask for intent.
- **R4. Vagueness gate.** If classification is "implement" and concreteness signals are absent (file path, symbol casing, issue #, error string, code block, numbered steps, acceptance criteria), redirect to `deep-interview` — not to autopilot.
- **R5. Session-aware banner.** `session_start.py` must read MCP state + `.omni/state/` and surface a resume hint ("autopilot paused at Phase 2 — `/omni-resume` to continue") instead of a static string.
- **R6. Deterministic handoff, not hints.** When router picks a skill, emit a structured payload — `{"omni.router.decision": {"skill": "autopilot", "confidence": 0.82, "runner_up": "plan", "redirect": null}}` — that downstream skills and tests can assert on, rather than a free-text hint the LLM may ignore.

One paragraph: copilot-omni should adopt GSD's deterministic router shape (`/omni-do` + `/omni-next`) with OMOA's IntentGate classifier as the primary router, OMC's ralplan gate as the vagueness redirect, and drop the advisory hint pattern entirely. The router should emit structured output that CI can assert on; the LLM is free to override, but only by explicit user instruction, not by silent drift.

---

## 6. Hooks & triggers — ranked bug list

Merged from `int-hooks-triggers-audit.md` (21 findings) + `codex-internal-audit.md §3` + `int-pipeline-harness.md §9`. Deduped; same bug flagged by two reports is marked "both".

| Rank | Severity | File:line | Description | Fix direction | Flagged by |
|---|---|---|---|---|---|
| 1 | Critical | hooks/* (all) | `OMC_SKIP_HOOKS` / `DISABLE_OMC` unimplemented; CLAUDE.md references them | Add env-var check at top of every hook; exit cleanly | Claude **[int-hooks-triggers-audit.md §8.1]** |
| 2 | Critical | hooks/pre_tool_use.py:80-82 | `shlex.split` ValueError fallback bypasses token matching | Reject malformed cmd as deny, not parse | Claude **[int-hooks-triggers-audit.md §2.1]** |
| 3 | Critical | hooks/post_tool_use.py:19-27 | Concurrent appenders may interleave JSON; `mkdir` TOCTOU | Lock file or per-pid log; fsync on write | Claude **[int-hooks-triggers-audit.md §3.1]** |
| 4 | High | hooks/user_prompt_submit.py:33-40 | No precedence, no disambiguation, no cancel trigger | See §5 design | Both **[int-hooks-triggers-audit.md §5.1]** + **[codex-internal-audit.md §3]** |
| 5 | High | hooks/hooks.json:8,15,22,29 | `${CLAUDE_PLUGIN_ROOT}` assumed to be shell-expanded by harness | Document contract, test in CI on Copilot CLI + Claude Code | Claude **[int-hooks-triggers-audit.md §1.1]** |
| 6 | High | hooks/user_prompt_submit.py:13-24 | Hook misses skill-declared triggers (`ulw`, `auto pilot`, `autonomous`, `don't stop`, `must complete`, `finish this`, etc.) | Sync hook regex table with SKILL.md frontmatter triggers | Both **[int-hooks-triggers-audit.md §Bug 8]** + **[codex-internal-audit.md §2 High-5]** |
| 7 | High | hooks/user_prompt_submit.py:21 | `knowledge\s+base` regex is very generic → false positives | Tighten or require anchor keyword | Claude **[int-hooks-triggers-audit.md §5.3]** |
| 8 | High | hooks/pre_tool_use.py:39-55 | Policy file trusted without permission check | Reject 0666 policy files; warn on world-writable | Claude **[int-hooks-triggers-audit.md §10.2]** |
| 9 | Medium | hooks/session_start.py:8-12 | Stale counts (29/28/17) vs actual (30/37/19); static banner ignores resume state | Compute counts at install; inject resume hints | Both **[codex-internal-audit.md §2 Medium-4]** + **[int-hooks-triggers-audit.md §4.1]** |
| 10 | Medium | hooks/post_tool_use.py:21-25 | Only captures `ts`/`tool`/`status`; no args, no return, no session | Expand entry schema; document in `.omni/audit/AUDIT.md` | Claude **[int-hooks-triggers-audit.md §3.3]** |
| 11 | Medium | hooks/hooks.json:9-30 | Timeouts may be tight (5-10s) under load | Make configurable via env; backoff on transient timeouts | Claude **[int-hooks-triggers-audit.md §1.3]** |
| 12 | Medium | hooks/pre_tool_use.py:113,120 | Unicode NFC/NFD normalization on macOS not handled | `unicodedata.normalize('NFC', …)` before compare | Claude **[int-hooks-triggers-audit.md §2.3]** |
| 13 | Medium | hooks/post_tool_use.py:27-29 | `except Exception: pass` silently drops audit on failure | Log failure to stderr (harness captures); don't block tool | Claude **[int-hooks-triggers-audit.md §3.2]** |
| 14 | Low | hooks/user_prompt_submit.py:14 | `full\s*auto` matches `fullauto` (zero-space) | Decide if intentional; document | Claude **[int-hooks-triggers-audit.md §5.2]** |
| 15 | Low | hooks/post_tool_use.py:20 | Audit dir created with default 0755 | Create with 0700 if policy treats audit as sensitive | Claude **[int-hooks-triggers-audit.md §10.4]** |
| 16 | Low | hooks/pre_tool_use.py:121 | Substring protected-path match causes false positives (`.omni/config.jsonXX`) | Prefix-match after normalization | Claude **[int-hooks-triggers-audit.md §2.4]** |
| 17 | Low | hooks/user_prompt_submit.py:34 | IGNORECASE hard-codes English casing assumption | Document as English-only; add i18n issue | Claude **[int-hooks-triggers-audit.md §5.4]** |

---

## 7. Skill/agent contract violations and paper-only claims

| Skill / agent | Promises | Reality | Citation |
|---|---|---|---|
| **autopilot** | Reads `.omc/plans/ralplan-*.md`, spawns `Task(subagent_type="oh-my-claudecode:architect")`, etc. | Harness uses `.omni/`; no `Task()` dispatcher on Copilot CLI | **[codex-internal-audit.md §1 Autopilot]** |
| **ralph** | `Task(run_in_background=true)`, `Skill("ai-slop-cleaner")`, `omc ask codex --agent-prompt critic`, reads `docs/shared/agent-tiers.md` | No background mode in `subagent.py`; no Skill dispatcher; no `omc ask`; `agent-tiers.md` missing | **[codex-internal-audit.md §1 Ralph]** |
| **ultrawork** | Parallel task fan-out; model tiers `haiku/sonnet/opus`; `docs/shared/agent-tiers.md` | `subagent.py` is synchronous; tiers undefined; file missing | **[codex-internal-audit.md §1 Ultrawork]** |
| **ultraqa** | Task-driven QA cycle; `.omc/state/ultraqa-state.json`; `/oh-my-claudecode:cancel` | No Task dispatcher; state goes to `.omni/`/MCP SQLite; cancel command absent | **[codex-internal-audit.md §1 UltraQA]** |
| **ralplan** | Alias to `/oh-my-claudecode:omc-plan`; uses `AskUserQuestion`, `Skill()` handoffs | Shipped command is `/omni-plan`; `AskUserQuestion` and `Skill()` absent | **[codex-internal-audit.md §1 Ralplan]** |
| **team** | `TeamCreate`, `TaskCreate/Update`, `SendMessage`, `TeamDelete`, `cleanup-orphans.mjs`, `omc team …` | None exist in `scripts/`, `commands/`, or `mcp/server.py` | **[codex-internal-audit.md §1 Team]** |
| **deep-interview** | `AskUserQuestion`, `Task("explore")`, `.omc/specs/` writes, skill-to-skill handoffs | None of those primitives exist | **[codex-internal-audit.md §1 Deep-Interview]** |
| **plan** | `AskUserQuestion`, `Skill("compact")`, `Skill("oh-my-claudecode:team")`, `state_write(session_id=…)` | `compact` skill absent; session-id state not supported | **[codex-internal-audit.md §1 Plan]** |
| **cancel** | `state_list_active`, `state_get_status`, `SendMessage`, `TeamDelete`, `cleanup-orphans.mjs`; `.omc`-based bash fallback | Only `state_write/read/clear` exist; fallback script missing; wrong dir | **[codex-internal-audit.md §1 Cancel]** |
| **agent `planner`** | Handoff to `/oh-my-claudecode:start-work` | Command undefined | **[codex-internal-audit.md §2 High-4]** |
| **agents `executor`/`verifier`/`code-reviewer`/`document-specialist`** | Use `lsp_diagnostics`, `ast_grep_search`, `WebSearch`, `WebFetch` | None implemented in this MCP server | **[codex-internal-audit.md §4]** |
| **agents `planner`/`executor`/`git-master`/`scientist`** | Write to `.omc/*` | Harness scaffolds `.omni/*` only | **[codex-internal-audit.md §4]** |

---

## 8. MCP server — security and correctness

| Severity | Finding | Citation |
|---|---|---|
| Critical | State API surface too small: missing `state_list_active`, `state_get_status`, session scoping, cancel-signal semantics | **[codex-internal-audit.md §5]** |
| High | Schemas published but not enforced; handlers receive unvalidated args | `mcp/server.py:1053-1061` **[codex-internal-audit.md §5]** + **[int-hooks-triggers-audit.md §11.1]** |
| High | `_handle()` serializes raw `str(exc)` — internal paths/validation leak to clients | `mcp/server.py:1062-1063` **[codex-internal-audit.md §5]** |
| Medium | `session_search` reader exists; no writer anywhere in the codebase | `mcp/server.py:650-658` **[codex-internal-audit.md §5]** |
| Medium | `trace_summary` / `trace_timeline` readers exist; no writer | `mcp/server.py:624-647` **[codex-internal-audit.md §5]** |
| Medium | `subtask.route` is a stub returning `{"route": "executor"}` unconditionally | `mcp/server.py:675-676` **[codex-internal-audit.md §5]** |
| Medium | No connection pool; per-call `sqlite3.connect()`; exception paths may leak connections | `mcp/server.py:56-72` **[int-hooks-triggers-audit.md §11.2, §11.3]** |
| Low | Policy-backed rejections include path fragments useful to fingerprint directory layout | **[int-hooks-triggers-audit.md §10.2]** |
| Low | Policy profile fallback is silent — stricter profile not loaded when malformed | `hooks/pre_tool_use.py:54` **[int-pipeline-harness.md §10.4]** |
| Low | No rate limiting / quota | **[int-hooks-triggers-audit.md §11.5]** |

SQLite hygiene is good: parameterized queries (no injection), WAL mode, 10s timeout, retry with exponential backoff **[int-hooks-triggers-audit.md §10.5, §11.4]**.

---

## 9. Test coverage gaps

**What is tested today** (from `tests/` inspection):
- `test_cli.py`: `version`, `init`, `list`, partial `doctor` **[codex-internal-audit.md §6]**
- `test_mcp_server.py`: `initialize`, `tools/list`, `health`, `memory`, `policy_check`, `wiki`, unknown-tool handling, Content-Length framing **[codex-internal-audit.md §6]**
- `test_hooks.py`: two policy cases, one autopilot trigger, the banner **[codex-internal-audit.md §6]**
- `test_security.py`: path traversal, policy regressions **[codex-internal-audit.md §6]**
- `test_discovery.py`: manifest existence, counts, frontmatter, `mcp/*.py` import allowlist **[codex-internal-audit.md §6]**

**What is claimed but untested:**
- No skill referentially validates that `/oh-my-claudecode:X` commands exist
- No test asserts that tools named in an agent or skill are registered in the MCP server
- No test checks `.omni` vs `.omc` coherence
- No test exercises session-aware cancel (the server doesn't support it)
- No test validates hook trigger regex against each SKILL.md's declared triggers
- No Windows-path / launcher test for `.mcp.json`, `hooks/hooks.json`, `scripts/omni.cmd`

**What should be added before any GA push:**
- Contract test: every `Skill("oh-my-claudecode:X")` reference resolves; every `Task(subagent_type=...)` agent name exists; every `/omni-*` or `/oh-my-claudecode:*` command exists
- Storage-coherence test: grep for `.omc/` in `skills/` and `agents/`; fail if found
- MCP schema test: every `inputSchema` is valid JSON Schema, and each handler rejects obviously bad args
- Intent-router test: table of sample prompts → expected classification (regression harness for R1-R6)
- Platform matrix test: run smoke on Windows + Linux + macOS via CI; catch `python3` shim issues early

---

## 10. Recommendations (prioritized)

### P0 — must-fix before any further feature work (5 max)

**1. Collapse the `.omc`/`.omni` split-brain.** Pick one directory root (I recommend `.omni/` — it's what the executable harness already uses) and rewrite every skill/agent reference. Add a test that greps for `.omc/` in `skills/` + `agents/` and fails CI. **Evidence:** **[codex-internal-audit.md §2 Critical-2]**. **Shape:** medium. **Success signal:** zero grep hits for `.omc/` in skill/agent files; contract test green.

**2. Implement kill switches.** Add `if os.environ.get("OMC_SKIP_HOOKS") or os.environ.get("DISABLE_OMC"): sys.stdout.write("{}"); sys.exit(0)` at the top of all four hook scripts. Document in README. **Evidence:** **[int-hooks-triggers-audit.md §8.1 Critical]**. **Shape:** small. **Success signal:** env var test proves hooks become no-ops.

**3. Decide the runtime contract: Copilot-native or port-in-Claude primitives.** Either (a) replace all `Task()`/`Skill()`/`SendMessage`/`TeamCreate`/`AskUserQuestion` references in skills with Copilot-equivalent patterns (e.g., documented `scripts/subagent.py` recipes), or (b) build a shim layer in the MCP server that reifies these as tool calls. Without one of the two, nine flagship skills remain paper-only on Copilot CLI. **Evidence:** **[codex-internal-audit.md §1]** across all nine skills. **Shape:** large. **Success signal:** each tier-0 skill has a green smoke test that invokes its main path on both harnesses.

**4. Replace the regex hint router with a real intent gate.** Implement §5 R1-R6: classifier → resolver → vagueness redirect → session-aware banner → structured decision payload. **Evidence:** **[int-hooks-triggers-audit.md §5.1]** + **[codex-internal-audit.md §3]**. **Shape:** medium. **Success signal:** intent-router table tests green; ambiguous prompts redirect to deep-interview instead of emitting multi-skill hints.

**5. Harden MCP: schema validation + expanded state API + fix dead tools.** Validate `arguments` against `inputSchema` in `_handle()`; add `state_list_active` and `state_get_status` + session-scoped writes; either implement writers for `session_search`/`trace_*` or remove the tools; remove or fix the `subtask.route` stub. **Evidence:** **[codex-internal-audit.md §5]**. **Shape:** medium. **Success signal:** MCP contract tests green; no tool is a reader with no writer.

### P1 — high-impact hardening (6–10 items)

1. **Windows compatibility pass.** Replace `python3` with a `launch_python()` helper that tries `python3`, `python`, then `py -3`. Fix `.mcp.json`, `hooks/hooks.json`, `scripts/omni.cmd`, every command doc. Add Windows CI matrix. **[codex-internal-audit.md §2 High-3]**. **Shape:** medium. **Success:** Windows CI green.

2. **Sync hook trigger table with SKILL.md frontmatter.** Generate `hooks/user_prompt_submit.py` TRIGGERS from each SKILL.md's declared triggers, plus a precedence field. **[codex-internal-audit.md §2 High-5]**. **Shape:** small. **Success:** new skills automatically pick up hook coverage.

3. **Fix `pre_tool_use.py` shlex fallback.** On `shlex.split` ValueError, deny the command rather than falling back to `.split()`. **[int-hooks-triggers-audit.md §2.1]**. **Shape:** small. **Success:** regression test with `rm'-rf /` is blocked.

4. **Fix audit log race.** Per-pid logfile or fcntl lock; fsync on each append. **[int-hooks-triggers-audit.md §3.1]**. **Shape:** small. **Success:** parallel stress-test produces valid JSONL.

5. **Upgrade `scripts/subagent.py` to match its own docs.** Capture stdout/stderr, return structured result, support a `background=True` spawn mode, document `OMNI_SUBAGENT_ALLOW_ALL`. **[codex-internal-audit.md §2 High-2]**. **Shape:** medium. **Success:** skills can read agent output; ultrawork can actually run in parallel.

6. **Build `/omni-cancel` and `/omni-next`.** `/omni-cancel` replaces all `/oh-my-claudecode:cancel` references; `/omni-next` implements §5 R3. **[codex-internal-audit.md §1 Cancel]**. **Shape:** medium. **Success:** every mode exits cleanly; session banner shows correct resume state.

7. **Session-aware session_start banner.** Read `.omni/state/` + MCP state; emit dynamic `additionalContext` with active-mode hint, staleness, resume command. **[int-hooks-triggers-audit.md §4.1]**. **Shape:** small. **Success:** crashed autopilot resumes are user-visible.

8. **Storage-contract test.** CI step that greps every skill/agent for deprecated references (`.omc/`, `oh-my-claudecode:X` that doesn't exist locally, `AskUserQuestion`, `TeamCreate`, etc.) and fails loudly. **[codex-internal-audit.md §6]**. **Shape:** small. **Success:** doc drift cannot merge.

9. **Connection-pool the MCP server.** Use a pooled `sqlite3.connect()` with `_Conn` context manager everywhere; fix leaks in exception paths. **[int-hooks-triggers-audit.md §11.2, §11.3]**. **Shape:** medium. **Success:** load test shows steady-state connection count.

10. **Policy-file safety.** Reject world-writable policy files; warn on non-0600 perms. **[int-hooks-triggers-audit.md §10.2]**. **Shape:** small. **Success:** chmod 666 policy denied with error.

### P2 — upstream parity features worth stealing (6–10 items)

1. **IntentGate classifier (from OMOA).** Dedicated classifier before routing, outputs `research/implementation/investigation/evaluation/fix`. One sentence: adopt OMOA's separation of intent classification from execution. **[ext-oh-my-openagent.md §8]**.
2. **Deterministic state-machine router (from GSD).** `/omni-do` (freeform → command) + `/omni-next` (state → next step) with 8 ordered rules. **[ext-get-shit-done.md §10]**.
3. **Four-gate taxonomy (from GSD).** Pre-flight / Revision / Escalation / Abort gate types with consistent recovery semantics. **[ext-get-shit-done.md §8]**.
4. **Artifact-first lifecycle (from GSD).** Per-phase `XX-CONTEXT.md` / `XX-RESEARCH.md` / `XX-PLAN.md` / `XX-SUMMARY.md` / `XX-VERIFICATION.md` as atomic units, consumed by next step. **[ext-get-shit-done.md §7]**.
5. **Mode composition grammar (from OMC).** Formally document `ultrawork ⊂ ralph ⊂ autopilot` + `ralplan` front-gate as a compositional grammar; single source of truth. **[ext-oh-my-claudecode.md §7]**.
6. **Wisdom accumulation notepads (from OMOA).** Per-plan `learnings.md` / `decisions.md` / `issues.md` / `verification.md` / `problems.md` injected into subsequent subagents. **[ext-oh-my-openagent.md §7]**.
7. **Category-based delegation (from OMOA).** Swap `haiku/sonnet/opus` direct model names for semantic categories (`quick`, `ultrabrain`, `deep`, `visual-engineering`) that map to models via config. **[ext-oh-my-openagent.md §5]**.
8. **Read-only reviewer enforcement (from OMC).** `architect`/`critic`/`code-reviewer`/`security-reviewer` should have `disallowedTools: Write, Edit` enforced at tool-dispatch time. **[ext-oh-my-claudecode.md §11]**.
9. **Ambiguity-scored deep interview (from OMC).** Math-gated interview (ambiguity ≤ 0.2) before autopilot handoff; soft limit round 10, hard cap 20. **[ext-oh-my-claudecode.md §3 deep-interview]**.
10. **Session search + trace writers (from OMC).** Implement the write side of `session_search` and `trace_*` so the existing tools become useful. **[codex-internal-audit.md §5]**.

---

## 11. Open questions to bring back to the user

1. **Keep Copilot CLI as primary host, or pivot to Claude Code?** The current repo is optimised as a Python/stdlib Copilot plugin, but every flagship skill was ported from the Claude Code world and still assumes `Task()`/`Skill()`/team primitives. Either the skills get rewritten to `scripts/subagent.py`-based patterns, or copilot-omni becomes a Claude Code plugin that happens to work on Copilot for a subset of skills.
2. **Adopt GSD-style phase state machine or keep flat skills?** GSD's six-phase lifecycle buys predictable resume + audit + test-coverage at the cost of ceremony. OMC's composable modes are lighter. OMOA's IntentGate+categories sits in the middle. Pick one architecture and commit.
3. **Embed deep-interview as mandatory front-door gate?** OMC gates autopilot/ralph/team behind ralplan when prompts lack concreteness signals. Do we mandate the same? If yes, what's the bypass syntax (`force:`, `!`, `--skip-interview`)?
4. **Kill `.omc/` in favor of `.omni/`, or vice versa?** Both exist. Executable uses `.omni/`; skills use `.omc/`. Picking one is a mechanical but large rewrite. Recommend `.omni/`.
5. **Build or shim team orchestration?** `team/SKILL.md` is 900+ lines of Claude-native team code. On Copilot we either build an equivalent (worktrees + tmux + state machine), shim it via `scripts/subagent.py` sequential fallback, or delete the skill from the Copilot-first distribution.
6. **Adopt OMOA category delegation or stay on `haiku/sonnet/opus`?** Moving to semantic categories (`quick`, `deep`, `ultrabrain`) decouples from specific model names and gives users a single knob.
7. **License / trademark posture.** OMC is MIT, GSD is MIT, OMOA is SUL-1.0 (non-OSI). If we want to borrow patterns verbatim, OMOA borrowing is highest-risk — do we scope our borrowing to OMC + GSD only?
8. **What does "corporate-safe" mean for telemetry and external CLIs?** OMC calls out Codex/Gemini; OMOA defaults PostHog on. Where does copilot-omni draw the line? (Currently: no third-party pip, stdlib only — worth formalising as an ADR.)
9. **Is `team` worth keeping as a Copilot skill at all?** Without native team primitives, `team` on Copilot would have to be reimplemented entirely. A `tmux + worktrees` (OMC-teams-style) path is ~1 month; a shim is 1 week; deletion is 1 hour.

---

## 12. Source file index

| # | Path | Author | Word count (approx) |
|---|---|---|---|
| 1 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/ext-oh-my-claudecode.md` | Claude subagent | 5,400 |
| 2 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/ext-oh-my-openagent.md` | Claude subagent | 6,900 |
| 3 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/ext-get-shit-done.md` | Claude subagent | 6,500 |
| 4 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/codex-external-repos.md` | Codex (gpt-5.4) | 6,200 |
| 5 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/int-pipeline-harness.md` | Claude subagent | 7,850 |
| 6 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/int-hooks-triggers-audit.md` | Claude subagent | 5,900 |
| 7 | `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/codex-internal-audit.md` | Codex (gpt-5.4) | 4,500 |

Total source: ~43,250 words. This synthesis: ~3,500 words.
