# get-shit-done (gsd-build) — Deep Research

**Source**: https://github.com/gsd-build/get-shit-done
**Package name**: `get-shit-done-cc` (npm)
**License**: MIT
**Inspected version**: v1.36.0 (2026-04-14)
**Popularity (repo card)**: ~53.5k stars / 4.5k forks (per README hero)
**Research date**: 2026-04-16

> Primary docs consulted: `README.md`, `docs/ARCHITECTURE.md`, `docs/USER-GUIDE.md`, `docs/COMMANDS.md`, `docs/AGENTS.md`, `docs/FEATURES.md`, `docs/CONFIGURATION.md`, `docs/CLI-TOOLS.md`, `docs/workflow-discuss-mode.md`, plus `commands/gsd/*`, `agents/*`, `get-shit-done/{workflows,templates,references,contexts,hooks}/*`, `bin/install.js`, `package.json`, `CHANGELOG.md`, commit log (April 2026), open issues.

---

## 1. Project identity & positioning (what problem does GSD solve)

GSD bills itself as **"a light-weight and powerful meta-prompting, context engineering and spec-driven development system"** for Claude Code and peers (quote from README).

Core value framing:

- **Anti-"context rot."** GSD exists to prevent quality degradation as an AI editor's context window fills. Every "heavy" piece of work (research, planning, execution, verification) is pushed into a freshly spawned subagent with up to a 200K clean window while the orchestrator stays at 30–40% utilization.
- **Anti-"vibe coding."** It forces a spec-driven loop: discussion → plan → execute → verify → ship, with artifact files on disk (`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `CONTEXT.md`, `RESEARCH.md`, `PLAN.md`, `SUMMARY.md`, `VERIFICATION.md`).
- **Solo-dev ethos.** Creator quote: *"I'm a solo developer. I don't write code—Claude Code does."* The tagline: *"describe what you want and have it built correctly—without pretending they're running a 50-person engineering org."*
- **Multi-runtime by design.** One authoring format, installed into Claude Code, OpenCode, Gemini CLI, Kilo, Codex, GitHub Copilot, Cursor, Windsurf, Antigravity, Augment, Trae, Qwen Code, CodeBuddy, Cline (14 runtimes). Authored by "TÂCHES" (per `package.json` description).

Distributed as an npx-installable Node package: `npx get-shit-done-cc@latest`. Requires Node ≥22.

## 2. Core mental model (project → milestone → phase → plan → execution → verification → ship)

Work nests three levels:

1. **Project** (`/gsd-new-project`) — One-time bootstrap: deep Socratic questioning, optional domain research, `PROJECT.md` + `REQUIREMENTS.md` + `ROADMAP.md` + `config.json` + `STATE.md`.
2. **Milestone** (`/gsd-new-milestone`, `/gsd-audit-milestone`, `/gsd-complete-milestone`) — A release slice: N phases belong to a milestone. Auditing then archival produces `MILESTONES.md`.
3. **Phase** — The main unit of work, governed by a fixed lifecycle:

```
/gsd-discuss-phase N    → lock preferences (CONTEXT.md)
/gsd-ui-phase N         → design contract   (XX-UI-SPEC.md)  [frontend only, optional]
/gsd-plan-phase N       → research + plan   (XX-RESEARCH.md, XX-YY-PLAN.md, XX-VALIDATION.md)
/gsd-execute-phase N    → wave-parallel execution (XX-YY-SUMMARY.md, atomic commits)
/gsd-verify-work N      → conversational UAT (XX-UAT.md, XX-VERIFICATION.md)
/gsd-ship N             → PR creation
/gsd-ui-review N        → retrospective visual audit (XX-UI-REVIEW.md) [optional]
```

Phase progression quote from `docs/ARCHITECTURE.md`:

> `discuss-phase → ui-phase → plan-phase → execute-phase → verify-work → ui-review`

Each step emits files that the next step consumes. **Plans** (`XX-YY-PLAN.md`, where XX = phase index, YY = plan index within phase) are the atomic executable unit. Plans group into **waves** for parallel execution. Phases can be integers (`1`, `2`) or decimals (`2.1` = INSERTED urgent work).

The stated reason the model works:

- **XML-structured task prompts** (`<task>`, `<read_first>`, `<action>`, `<verify>`, `<acceptance_criteria>`, `<must_haves>`) remove ambiguity.
- **Fresh contexts per task** avoid rot.
- **Atomic git commits per task** enable bisection and safe undo.

## 3. Repository layout

Top of tree (from `github.com/gsd-build/get-shit-done`):

```
.github/workflows/          CI/CD, PR gating, release, stale bot
agents/                     31 gsd-*.md agent specs
bin/install.js              Multi-runtime installer (npx entry)
commands/gsd/               ~75 *.md slash-command entry files
docs/                       ARCHITECTURE, USER-GUIDE, COMMANDS, AGENTS, FEATURES, CONFIGURATION,
                            CLI-TOOLS, workflow-discuss-mode, context-monitor, manual-update,
                            localized ja-JP/ko-KR/pt-BR/zh-CN/, skills/
get-shit-done/
  bin/gsd-tools.cjs         ~19-module Node CLI (state/phase/roadmap/verify/template/init/...)
  contexts/                 dev.md, research.md, review.md (execution profiles)
  hooks/                    gsd-statusline.js, gsd-context-monitor.js, gsd-prompt-guard.js,
                            gsd-read-guard.js, gsd-workflow-guard.js, gsd-phase-boundary.sh,
                            gsd-session-state.sh, gsd-validate-commit.sh,
                            gsd-check-update{,-worker}.js
  references/               41 *.md reference files (gates, planner-antipatterns, tdd,
                            thinking-models-*, executor-examples, questioning, etc.) +
                            few-shot-examples/
  templates/                ~33 root templates + codebase/ (7 files) + research-project/ (5 files)
  workflows/                71 *.md workflow implementations (one per command + shared flows)
scripts/                    build-hooks.js, run-tests.cjs
sdk/                        headless query SDK (gsd-sdk query)
hooks/                      install-time hook shims
tests/                      vitest suite (c8 coverage, threshold 70% lines)
.planning/                  GSD's own .planning/ (dogfooded)
package.json                "get-shit-done-cc" v1.36.0, MIT, Node >=22
```

Authored artifacts (inside consuming projects) always land under `.planning/` at the repo root — see §7.

## 4. Complete command/skill catalog

Source: `commands/gsd/*.md` (full listing captured); groupings align with `docs/COMMANDS.md`.

### 4.1 Setup & project lifecycle
- **`/gsd-new-project`** — Deep context gathering → `PROJECT.md`, optional ecosystem research, `REQUIREMENTS.md`, `ROADMAP.md`, `config.json`, `STATE.md`.
- **`/gsd-new-milestone`** — Starts next version cycle, re-runs requirements + roadmap for fresh scope.
- **`/gsd-new-workspace`** / **`/gsd-list-workspaces`** / **`/gsd-remove-workspace`** — Git-worktree-based isolated workspaces with their own `.planning/`.
- **`/gsd-map-codebase`** — Parallel "mapper" agents for brownfield ingest (fills `.planning/codebase/`).
- **`/gsd-scan`** — Lightweight single-focus codebase assessment.
- **`/gsd-intel`** — Query/inspect/refresh queryable codebase intelligence JSON in `.planning/intel/`.
- **`/gsd-from-gsd2`** — Reverse-migrate a GSD-2 project (`.gsd/`) back to v1 (`.planning/`).
- **`/gsd-settings`**, **`/gsd-set-profile`** — Workflow toggles and model profile switching.
- **`/gsd-update`**, **`/gsd-reapply-patches`** — GSD self-update + restore local overrides.
- **`/gsd-profile-user`** — 8-dimension behavioral profile of the developer → `USER-PROFILE.md`.
- **`/gsd-join-discord`**, **`/gsd-help`** — Community / help surface.

### 4.2 Phase shaping
- **`/gsd-add-phase`** / **`/gsd-insert-phase`** (decimal numbering) / **`/gsd-remove-phase`** — Roadmap edits.
- **`/gsd-add-backlog`** (999.x numbering) / **`/gsd-review-backlog`** — Parking-lot items.
- **`/gsd-plant-seed`** — Capture forward-looking ideas with trigger conditions that auto-surface at the right milestone.
- **`/gsd-plan-milestone-gaps`** — Auto-generate phases to close milestone-audit gaps.
- **`/gsd-analyze-dependencies`** — Suggest `Depends on:` edges.
- **`/gsd-list-phase-assumptions`** — Preview Claude's intended approach before planning.

### 4.3 Planning
- **`/gsd-discuss-phase`** (modes: default interview, `--all`, `--auto`, `--chain`, `--power`) — CONTEXT.md.
- **`/gsd-ui-phase`** — UI design contract (`XX-UI-SPEC.md`, 6 pillars).
- **`/gsd-ai-integration-phase`** — AI framework selection + `AI-SPEC.md` for LLM/RAG/agent work.
- **`/gsd-research-phase`** — Standalone research; normally runs inside `/gsd-plan-phase`.
- **`/gsd-plan-phase`** — Orchestrates researcher → pattern-mapper → planner → plan-checker (revision loop, max 3 iter) → optional `--bounce` external refinement → requirements coverage gate.
- **`/gsd-review`** — Cross-AI peer review of plans (Claude, Codex, Gemini, Cursor, Qwen CLIs).
- **`/gsd-import`** — Ingest external plan with conflict detection.

### 4.4 Execution
- **`/gsd-execute-phase`** (flags `--wave N`, `--gaps-only`, `--cross-ai`, `--interactive`) — Wave-parallel execution with worktree isolation, `--no-verify` commits, post-wave regression gate, schema-push gate, code-review gate, verifier agent, then ROADMAP + PROJECT evolution.
- **`/gsd-autonomous`** — Runs all remaining phases (discuss→plan→execute) with built-in pauses for auth-required checkpoints.
- **`/gsd-quick`** — Ad-hoc task but with GSD guarantees (plan+execute+verify).
- **`/gsd-fast`** — Trivial inline execution, no subagents, no planning.
- **`/gsd-do`** — Freeform-text intent router → picks the correct `/gsd-*` command.
- **`/gsd-manager`** — Interactive command-center TUI for multiple phases at once.
- **`/gsd-workstreams`** (list/create/status/switch/progress/complete/resume) — Concurrent parallel work.
- **`/gsd-undo`** — Safe git revert using the phase manifest with dependency checks.
- **`/gsd-pause-work`** / **`/gsd-resume-work`** — Session-handoff `.continue-here.md` mechanics.
- **`/gsd-thread`** — Persistent cross-session lightweight context.
- **`/gsd-graphify`** — Build/query the project knowledge graph in `.planning/graphs/` (v1.36 feature).

### 4.5 Review, verification, hardening
- **`/gsd-verify-work`** — Conversational UAT with parallel debug-agent diagnosis on failures and `gsd-planner` gap-closure; auto-advance when clean.
- **`/gsd-add-tests`** — Generate tests for a completed phase from UAT criteria.
- **`/gsd-validate-phase`** — Retroactively fill Nyquist validation gaps.
- **`/gsd-code-review`** + **`/gsd-code-review-fix`** — Severity-classified review with atomic fix commits.
- **`/gsd-ui-review`** — 6-pillar retrospective visual audit.
- **`/gsd-secure-phase`** — Retroactive threat-mitigation verification (OWASP ASVS L1-3).
- **`/gsd-eval-review`** — Retroactive AI-phase eval coverage audit; scores each dimension COVERED/PARTIAL/MISSING.
- **`/gsd-audit-uat`** — Cross-phase UAT/verification audit.
- **`/gsd-audit-milestone`** — Verify milestone hit its definition of done before archiving.
- **`/gsd-audit-fix`** — Autonomous audit → classify → fix → test → commit pipeline.
- **`/gsd-verify` / `state validate` / `state sync`** — Drift detection between `STATE.md` and filesystem.
- **`/gsd-extract-learnings`** — Harvest decisions/patterns/surprises into learnings files (feeds global knowledge store when enabled).

### 4.6 Debugging, forensics, meta
- **`/gsd-debug`** — Systematic debugging with persistent state across `/clear` and context resets (`.planning/debug/*.md`).
- **`/gsd-forensics`** — Post-mortem investigation of failed workflows using git history + artifacts + state.
- **`/gsd-health`** — `.planning/` integrity check (with `--forensic` mode, 6-check audit, added 2026-04-15).
- **`/gsd-cleanup`** — Archive phase directories from completed milestones.
- **`/gsd-stats`** / **`/gsd-progress`** / **`/gsd-session-report`** / **`/gsd-milestone-summary`** — Reporting.
- **`/gsd-next`** — Intent-router; deterministically picks the next step in the phase state machine (see §10).
- **`/gsd-add-todo`** / **`/gsd-check-todos`** / **`/gsd-note`** — Zero-friction idea capture.
- **`/gsd-docs-update`** — Codebase-verified doc generation (spawns doc-writer + doc-verifier).
- **`/gsd-ship`** — PR creation with auto-generated body, post-ship review hook.
- **`/gsd-pr-branch`** — Create a clean PR branch filtering out `.planning/` commits for review.
- **`/gsd-explore`** — Socratic ideation & routing before committing to plans.
- **`/gsd-inbox`** — Captures items for later triage (workflow file exists).

Count: ~75 commands live in `commands/gsd/`. There are also community hooks (`gsd-validate-commit.sh`, `gsd-phase-boundary.sh`, `gsd-session-state.sh`) that are opt-in via the installer.

## 5. Agent catalog

31 agent spec files live in `agents/` (sourced from `docs/AGENTS.md`, which enumerates 21 primary ones plus additional specialists). Roles summarized:

| Agent | Role | Primary inputs | Primary outputs | Invoked by |
|---|---|---|---|---|
| `gsd-project-researcher` | Ecosystem scouting (spawned 4× in parallel for stack/features/architecture/pitfalls) | Domain focus | `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` in `.planning/research/` | `/gsd-new-project`, `/gsd-new-milestone` |
| `gsd-domain-researcher` | Domain/market/benchmark lookups | Project domain | Research fragments | `/gsd-new-project` |
| `gsd-phase-researcher` | Implementation-pattern research for a single phase | `CONTEXT.md`, phase scope, `REQUIREMENTS.md`, `STATE.md` | `XX-RESEARCH.md` (with Nyquist Validation Architecture section when enabled) | `/gsd-plan-phase` |
| `gsd-ai-researcher` | AI/LLM framework landscape | AI-phase context | Framework candidates | `/gsd-ai-integration-phase` |
| `gsd-ui-researcher` | Design-system scouting, Tailwind/shadcn config awareness | Existing UI state | `XX-UI-SPEC.md` | `/gsd-ui-phase` |
| `gsd-advisor-researcher` | Gray-area decision research | Single decision topic | 5-column comparison (Option/Pros/Cons/Complexity/Rec) | `/gsd-discuss-phase` advisor mode |
| `gsd-assumptions-analyzer` | Evidence-based assumptions with confidence tiers | `ROADMAP.md` + codebase | Structured assumptions | `discuss-phase-assumptions` workflow |
| `gsd-pattern-mapper` | Extract file lists + code analogs for the planner | `CONTEXT.md`, `RESEARCH.md` | `PATTERNS.md` with code excerpts | `/gsd-plan-phase` step 5.8 |
| `gsd-research-synthesizer` | Consolidate parallel research | All researcher outputs | `SUMMARY.md` | `/gsd-new-project` |
| `gsd-roadmapper` | Derive phases + success criteria | Requirements, granularity | `ROADMAP.md` | `/gsd-new-project` |
| `gsd-planner` | Phase → atomic XML tasks | `PROJECT.md`, `REQUIREMENTS.md`, `RESEARCH.md`, prior CONTEXT/SUMMARY (on 1M-token models) | `XX-YY-PLAN.md` files | `/gsd-plan-phase`, `/gsd-quick`, verify-work (gap_closure) |
| `gsd-plan-checker` | 8-dimension validation (req coverage, atomicity, read_first, deps, waves, must-haves, concreteness, alignment) | All PLAN.md + CONTEXT + RESEARCH + ROADMAP + REQUIREMENTS | PASS / ISSUES FOUND | `/gsd-plan-phase` revision loop |
| `gsd-framework-selector` | Pick concrete framework after research | Candidate frameworks | Decision rationale | `/gsd-ai-integration-phase` |
| `gsd-executor` | Implement one plan with atomic commits | `XX-YY-PLAN.md` + deps | Code + git commits + `XX-YY-SUMMARY.md` | `/gsd-execute-phase`, `/gsd-quick` |
| `gsd-code-fixer` | Targeted fix agent | Review findings | Atomic fix commits | `/gsd-code-review-fix`, `/gsd-audit-fix` |
| `gsd-integration-checker` | End-to-end cross-phase flow verification | Whole milestone | Integration report | `/gsd-audit-milestone` |
| `gsd-verifier` | Phase-goal verification (not just tasks) | Implemented code + `PLAN.md` must-haves | `XX-VERIFICATION.md` (`passed`, `human_needed`, `gaps_found`) | `/gsd-execute-phase` post-wave |
| `gsd-nyquist-auditor` | Test-coverage gap generator | Phase code + test infra | Test files + updated `VALIDATION.md` | `/gsd-validate-phase` |
| `gsd-ui-checker` | UI-spec quality gate | `XX-UI-SPEC.md` | BLOCK/FLAG/PASS | `/gsd-ui-phase` |
| `gsd-ui-auditor` | Retroactive 6-pillar visual audit (copywriting, visuals, color, typography, spacing, experience) | Frontend code | `XX-UI-REVIEW.md` with 1-4 scores | `/gsd-ui-review` |
| `gsd-code-reviewer` | Severity-classified review | Phase code diff | Review doc with severity tags | `/gsd-code-review` |
| `gsd-debugger` | Hypothesis-tracking investigator | Bug description + codebase | `.planning/debug/*.md` + knowledge base updates | `/gsd-debug`, verify-work failure path |
| `gsd-debug-session-manager` | Persists debug sessions across resets | Existing sessions | Session index | `/gsd-debug` |
| `gsd-security-auditor` | Verify declared threat mitigations | `PLAN.md` threat_model | `XX-SECURITY.md` (OPEN_THREATS vs mitigations) | `/gsd-secure-phase` |
| `gsd-eval-auditor` | AI eval coverage audit | Phase AI-SPEC | `EVAL-REVIEW.md` scores | `/gsd-eval-review` |
| `gsd-eval-planner` | AI evaluation strategy design | AI phase scope | Eval design section | `/gsd-ai-integration-phase` |
| `gsd-codebase-mapper` | Brownfield extractor (parallelized) | Live codebase | 7 files: stack, architecture, structure, conventions, concerns, integrations, testing | `/gsd-map-codebase` |
| `gsd-intel-updater` | Maintain JSON intel index | Source files | `.planning/intel/*.json` | `/gsd-intel` |
| `gsd-doc-writer` | Write codebase-grounded docs | `doc_assignment` blocks | README, ADRs, API docs | `/gsd-docs-update` |
| `gsd-doc-verifier` | Fact-check docs against live code | Generated docs | JSON verification | `/gsd-docs-update` |
| `gsd-user-profiler` | Developer behavioral profiling (8 dimensions) | Session transcripts / questionnaire | `USER-PROFILE.md` with confidence levels | `/gsd-profile-user` |

Key architectural pattern from `docs/ARCHITECTURE.md`: **least privilege per agent** — checkers are read-only, executors can write code but lack web access, researchers get web. **Sequential spine**: researcher → synthesizer → planner → checker → executor → verifier. **Parallel fanout** on researchers (4×) and executors (wave-bounded).

## 6. Template catalog

### 6.1 Root templates (`get-shit-done/templates/`)
| File | Purpose | Generated by / when |
|---|---|---|
| `project.md` | `PROJECT.md` — vision, core value, key decisions table, active/validated/out-of-scope requirements | `/gsd-new-project` |
| `requirements.md` | `REQUIREMENTS.md` — scoped feature list with REQ-IDs | `/gsd-new-project` |
| `roadmap.md` | `ROADMAP.md` — phase breakdown (integer + decimal numbering), per-phase goal, Depends on, Requirements, Success Criteria, Plans list | `/gsd-new-project`, `/gsd-add-phase`, `/gsd-insert-phase` |
| `state.md` | `STATE.md` — "living memory": current position, plan ratio, progress bar, velocity metrics (avg/plan trend), recent decisions, pending todos, blockers, deferred items, session continuity pointer to `.continue-here*.md` | Every phase transition via `gsd-tools.cjs state` |
| `config.json` | `.planning/config.json` — workflow toggles + model profile + granularity + parallelization + git branching | `/gsd-new-project`, `/gsd-settings` |
| `context.md` | `XX-CONTEXT.md` per phase — domain boundary, locked decisions, canonical refs (mandatory full paths), code context (reusable assets), user preferences, deferred ideas | `/gsd-discuss-phase` |
| `discussion-log.md` | `XX-DISCUSSION-LOG.md` — audit trail for humans only (not consumed downstream) | `/gsd-discuss-phase` |
| `discovery.md` | Initial discovery doc during new-project | `/gsd-new-project` |
| `research.md` | `XX-RESEARCH.md` skeleton (approach, dependencies, Nyquist Validation Architecture) | `gsd-phase-researcher` |
| `phase-prompt.md` | `XX-YY-PLAN.md` — YAML frontmatter (wave, depends_on, files_modified, requirements list, autonomous, cross_ai) + XML tasks (`<task type="auto">`, `<read_first>`, `<action>`, `<verify>`, `<acceptance_criteria>`, `<done>`, `<must_haves>`) | `gsd-planner` |
| `planner-subagent-prompt.md` | System prompt scaffold for `gsd-planner` | Internal |
| `debug-subagent-prompt.md` | System prompt scaffold for `gsd-debugger` | Internal |
| `summary.md` / `summary-minimal.md` / `summary-standard.md` / `summary-complex.md` | `XX-YY-SUMMARY.md` — tiered sizes; executor picks by complexity | `gsd-executor` |
| `verification-report.md` | `XX-VERIFICATION.md` — goal achievement, must-have table, status (`passed` / `human_needed` / `gaps_found`) | `gsd-verifier` |
| `VALIDATION.md` | `XX-VALIDATION.md` — Nyquist validation contract (test → requirement mapping) before code is written | Research step |
| `UAT.md` | `XX-UAT.md` — conversational test results + issues | `/gsd-verify-work` |
| `UI-SPEC.md` | `XX-UI-SPEC.md` — spacing, color, typography, copywriting, registry safety, visuals | `/gsd-ui-phase` |
| `AI-SPEC.md` | `XX-AI-SPEC.md` — framework choice, eval strategy | `/gsd-ai-integration-phase` |
| `SECURITY.md` | `XX-SECURITY.md` — threat model + mitigation verification | `/gsd-secure-phase` |
| `DEBUG.md` | Debug session doc (resumable) | `/gsd-debug` |
| `milestone.md` | Current milestone header | `/gsd-new-milestone` |
| `milestone-archive.md` | Archived milestone entry in `MILESTONES.md` | `/gsd-complete-milestone` |
| `retrospective.md` | Milestone retrospective | `/gsd-complete-milestone` |
| `user-profile.md` | `USER-PROFILE.md` — 8-dimension behavioral profile | `/gsd-profile-user` |
| `user-setup.md` | First-run setup instructions | Installer |
| `continue-here.md` | `.continue-here.md` — session handoff (`severity: blocking` entries require acknowledgement before `/gsd-next` advances) | `/gsd-pause-work`, workflow-guard |
| `claude-md.md` | Per-project `CLAUDE.md` injection | Installer (Claude runtime) |
| `copilot-instructions.md` | Per-project `.github/copilot-instructions.md` | Installer (Copilot runtime) |
| `dev-preferences.md` | Global dev preferences capture | `/gsd-profile-user` |

Excerpt from `roadmap.md` template showing the schema contract:

```
### Phase 1: [Name]
**Goal**: [What this phase delivers]
**Depends on**: Nothing (first phase)
**Requirements**: [REQ-01, REQ-02, REQ-03]
**Success Criteria** (what must be TRUE):
  1. [Observable behavior from user perspective]
**Plans**: [Number of plans]

Plans:
- [ ] 01-01: [Brief description]
```

Excerpt from `state.md` template (the file the orchestrator reads first every session):

```
Phase: [X] of [Y] ([Phase name])
Plan: [A] of [B] in current phase
Status: [Ready to plan / Planning / Ready to execute / In progress / Phase complete]
Last activity: [YYYY-MM-DD] — [What happened]
Progress: [░░░░░░░░░░] 0%
```

### 6.2 Codebase mapping templates (`templates/codebase/`)
`architecture.md`, `concerns.md`, `conventions.md`, `integrations.md`, `stack.md`, `structure.md`, `testing.md` — these seven files are populated by `gsd-codebase-mapper` agents during `/gsd-map-codebase` and sit in `.planning/codebase/`.

### 6.3 Research-project templates (`templates/research-project/`)
`ARCHITECTURE.md`, `FEATURES.md`, `PITFALLS.md`, `STACK.md`, `SUMMARY.md` — populated by the 4 parallel `gsd-project-researcher` spawns during `/gsd-new-project` and stored in `.planning/research/`.

## 7. `.planning/` directory schema and file lifecycle

```
.planning/
├── PROJECT.md              # Vision (always loaded, evolves as requirements move Active → Validated)
├── REQUIREMENTS.md         # Scoped feature list with REQ-IDs
├── ROADMAP.md              # Phase breakdown + status (updated after every phase completion)
├── STATE.md                # Living memory: decisions, blockers, session pointer, metrics
├── MILESTONES.md           # Completed versions archive
├── config.json             # Workflow toggles + model profile + parallelization + git strategy
├── .continue-here*.md      # Session handoff (severity: blocking entries gate /gsd-next)
├── research/               # STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md, SUMMARY.md
├── codebase/               # (brownfield) stack, architecture, structure, conventions, concerns,
│                           #   integrations, testing
├── intel/                  # (v1.34+) Queryable codebase JSON index
├── graphs/                 # (v1.36+) Knowledge-graph artifacts for /gsd-graphify
├── phases/
│   └── XX-phase-name/      # XX zero-padded, slug from roadmap
│       ├── XX-CONTEXT.md           # Locked decisions
│       ├── XX-DISCUSSION-LOG.md    # Human audit trail
│       ├── XX-DISCUSS-CHECKPOINT.json  # Resumable discuss state
│       ├── XX-RESEARCH.md          # Technical approach + Nyquist
│       ├── XX-PATTERNS.md          # Pattern-mapper excerpts
│       ├── XX-VALIDATION.md        # Test ↔ requirement map
│       ├── XX-UI-SPEC.md           # (optional) Design contract
│       ├── XX-AI-SPEC.md           # (optional) AI framework contract
│       ├── XX-YY-PLAN.md           # N atomic plans, YY zero-padded
│       ├── XX-YY-PLAN.pre-bounce.md # (ephemeral) backup during plan-bounce
│       ├── XX-YY-SUMMARY.md        # Executor output per plan
│       ├── XX-VERIFICATION.md      # Verifier goal-check
│       ├── XX-HUMAN-UAT.md         # Human-test items persisted for verify-work
│       ├── XX-UAT.md               # Conversational UAT transcript
│       ├── XX-UI-REVIEW.md         # (optional) 6-pillar audit
│       ├── XX-SECURITY.md          # (optional) Threat model verification
│       ├── XX-EVAL-REVIEW.md       # (optional) AI eval coverage
│       └── LEARNINGS.md            # Extracted for global knowledge store
├── quick/                  # /gsd-quick artifacts
├── todos/{pending,done}/   # /gsd-add-todo items
├── threads/                # /gsd-thread persistent contexts
├── seeds/                  # /gsd-plant-seed forward-looking ideas
├── debug/{active,resolved}/ # /gsd-debug sessions
└── workstreams/            # /gsd-new-workspace isolated state snapshots
```

**Lifecycle mechanics:**
- Files are written **before** they are read. The orchestrator only reads off disk — no hidden state in agent context.
- Every phase completion triggers: update `ROADMAP.md` (check plans + phase), append `STATE.md` metrics row, move any validated `REQUIREMENTS.md` entries to `PROJECT.md` "Validated" section.
- `state validate` / `state sync` detect drift between `STATE.md` and the filesystem.
- **Phase directories are archived** by `/gsd-cleanup` when a milestone completes (moves to `.planning/milestones/vX/`).
- `config.planning.commit_docs` controls whether `.planning/` is committed to git; auto-disabled if already in `.gitignore`.

## 8. Phase state machine (states, transitions, gates, artifacts required)

**Canonical sequence** (from `docs/ARCHITECTURE.md`):

```
discuss-phase → ui-phase → plan-phase → execute-phase → verify-work → ui-review
```

State is persisted in `STATE.md` via `gsd-tools.cjs state update/patch/advance-plan`.

**State values** (from `state.md` template):
- `Ready to discuss`
- `Discussing` (incremental checkpoints in `XX-DISCUSS-CHECKPOINT.json`)
- `Ready to plan`
- `Planning`
- `Ready to execute`
- `In progress` (wave-level granularity)
- `Phase complete` / `gaps_found` / `human_needed`

**Transition gates (from `references/gates.md`):**
GSD has four canonical gate types (added v1.34):

| Type | Behavior | Recovery |
|---|---|---|
| **Pre-flight** | Validates preconditions before work begins; blocks entry if unmet; no partial work created | Fix precondition and retry |
| **Revision** | Evaluates output, routes back to producer with feedback; bounded by iteration cap (typically 3); includes stall detection | Producer addresses feedback; re-evaluate |
| **Escalation** | Surfaces unresolvable issues to human, pauses workflow, presents options | Human chooses path; workflow resumes |
| **Abort** | Terminates to prevent damage/waste; preserves state, reports reason | Investigate root cause; restart from checkpoint |

**Specific gates encountered in the workflow:**
1. **Brownfield detection** (pre-flight at `/gsd-new-project`) — recommends `/gsd-map-codebase` first if existing code present.
2. **Requirements approval** (escalation) — user confirms scope before roadmap.
3. **Roadmap approval** (revision, loop back to `gsd-roadmapper`).
4. **Anti-pattern blocking** (pre-flight at `/gsd-execute-phase`) — `.continue-here.md` with `severity: blocking` requires 3-question acknowledgement.
5. **AI-SPEC detection** (escalation, non-blocking) — keyword scan for `agent|llm|rag|embedding|…`.
6. **UI design contract gate** (pre-flight) — frontend keywords without `UI-SPEC.md` triggers `/gsd-ui-phase` or `--skip-ui`.
7. **Security threat model gate** (pre-flight, non-blocking by default) — each PLAN must include `<threat_model>` when `security_enforcement: true`.
8. **Schema push gate** (pre-flight, blocking) — detects ORM schema files and injects `[BLOCKING]` push task to prevent false-positive verification. ORM table: Prisma → `npx prisma db push`, Drizzle → `npx drizzle-kit push`, Supabase → `supabase db push`.
9. **Plan-checker revision loop** (revision, max 3 iterations) — 8 dimensions: requirement coverage, atomicity, read_first presence, deps/waves, concreteness, must-haves alignment. Stall detection: if issue count fails to decrease, user prompted "Proceed anyway / Adjust approach".
10. **Requirements coverage gate** (escalation) — after planning, orphaned REQ-IDs surface for re-plan / defer / proceed choice.
11. **Plan bounce** (optional revision with external script) — `BOUNCE_SCRIPT PLAN_FILE BOUNCE_PASSES`, default 2 passes; invalid YAML → restore backup.
12. **Intra-wave file-overlap check** (pre-flight) — if two plans share `files_modified`, forces sequential.
13. **Worktree base-correction check** (pre-flight) — executor resets to `EXPECTED_BASE` if drift detected.
14. **Post-wave regression gate** — `npm test`/`cargo test`/`go test`/`pytest` after merge.
15. **Code review gate** — non-blocking; invokes `/gsd-code-review`.
16. **Schema drift gate** — blocks verification if ORM schema changed without corresponding push command evidence (overrideable via `GSD_SKIP_SCHEMA_CHECK=true`).
17. **Verifier gate** — goal-level check. Outputs `passed`, `human_needed` (creates `HUMAN-UAT.md`), or `gaps_found` (offers `/gsd-plan-phase N --gaps`).
18. **Security verification gate** (`/gsd-secure-phase`) — blocks on severity `security_block_on` (default `high`).

**Artifacts required per transition:**
- To enter `plan-phase`: `CONTEXT.md` (or `--prd` shortcut, or `--skip-discuss`).
- To enter `execute-phase`: at least one `PLAN.md` with valid frontmatter; `plan-checker` PASSED or user override.
- To enter `verify-work`: every non-skipped plan has a `SUMMARY.md`; verifier emitted.
- To close a phase: `VERIFICATION.md` with `passed` status (or user override on `human_needed`).

## 9. Hooks, triggers, and orchestration glue

Hook files under `get-shit-done/hooks/`:

| Hook | Runtime event | Behavior |
|---|---|---|
| `gsd-statusline.js` | `statusLine` | Displays model, task, context-usage bar (note: issue #2292 and #2219 — assumes 200K even on 1M models) |
| `gsd-context-monitor.js` | `PostToolUse` / `AfterTool` | Injects WARNING at ≤35% remaining, CRITICAL at ≤25%; debounced to prevent alert fatigue |
| `gsd-prompt-guard.js` | `PreToolUse` | Security guard — **cannot be disabled** per `CONFIGURATION.md` |
| `gsd-read-guard.js` | `PreToolUse` | Protective checks on read operations |
| `gsd-workflow-guard.js` | `PreToolUse` | Enforces workflow ordering (e.g., blocks `/gsd-execute-phase` without plans) |
| `gsd-phase-boundary.sh` | Phase transition | Stamps and validates phase handoff |
| `gsd-session-state.sh` | Session start/end | Persists session state |
| `gsd-validate-commit.sh` | Pre-commit (opt-in) | Commit message + artifact sanity |
| `gsd-check-update.js` + `gsd-check-update-worker.js` | `SessionStart` | Background version check |

**Install-time translation:** `bin/install.js` maps the Claude-Code markdown format to each runtime's native idiom — tool name mapping (`Bash → execute`), frontmatter transformation, hook event name translation, TOML for Codex agents, JSONC for OpenCode, `.clinerules` for Cline, `.github/copilot-instructions.md` for Copilot. WSL detection prevents path-resolution failures.

**Orchestration glue:** `get-shit-done/bin/gsd-tools.cjs` is the single CLI that every workflow calls. It exposes ~19 domain modules (state, phase, roadmap, config, verify, template, frontmatter, init, milestone, commands, model-profiles, UAT/verification, …). Pattern:

```bash
INIT=$(node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" init plan-phase "$PHASE")
```

Returns one JSON blob with model selections, feature flags, file paths, phase metadata, language preference — so agents downstream never re-read config. This is the mechanism that keeps the orchestrator "thin."

**Execution profiles** (`contexts/{dev,research,review}.md`) are three packaged "context execution profiles" that bundle different tool/model allowances per stage (v1.34 feature).

## 10. Intent routing / how GSD decides "what's next"

`/gsd-next` is the deterministic router. Data sources:

1. `gsd-tools.cjs state` JSON
2. `.planning/STATE.md`
3. `.planning/ROADMAP.md`

**Safety gates (hard stops):**
- `.planning/.continue-here.md` exists → resume handoff before advancing
- `STATE.md` `status: error` or `status: failed`
- Current phase `VERIFICATION.md` has unresolved `FAIL` items
- "Prior-phase completeness scan" — unfinished plans in earlier phases → user chooses defer-to-backlog or stop

`--force` bypasses all gates.

**Routing rules (8, evaluated in order):**
1. No phase directories → discuss first phase
2. Phase exists, no CONTEXT.md/RESEARCH.md → discuss current phase
3. Has context, no PLAN.md files → plan current phase
4. Plans exist, incomplete summaries → execute current phase
5. All summaries complete → verify and complete
6. Current phase done, next exists → discuss next phase
7. All phases complete → complete milestone
8. Project paused → resume work

`/gsd-do` is the **freeform** router — parses natural language and picks the right `/gsd-*` command. `/gsd-autonomous` is the **full-throttle** router — runs discuss→plan→execute per phase until either the milestone is done or an auth-required checkpoint fires.

## 11. Integration points

**Multi-runtime installation** (`bin/install.js`): flags `--claude`, `--codex`, `--copilot`, `--all`; global mode writes to `~/.claude/`, `~/.config/opencode/`, etc.; local mode writes to `.claude/`, `.github/`, `.cline/`, `.codex/`, etc.

**Agent-skill injection** (per `docs/CONFIGURATION.md`):
```json
"agent_skills": {
  "gsd-executor": ["skills/testing-standards"],
  "gsd-planner":  ["skills/architecture-rules"]
}
```
Custom `SKILL.md` files are injected per agent type, letting teams overlay project rules onto stock agents.

**Cross-AI delegation** (`workflow.cross_ai_execution = true`): plans with `cross_ai: true` frontmatter are piped to an external AI CLI (Codex, Gemini, Cursor, Qwen). Task prompt is constructed from plan OBJECTIVE+TASKS and piped over stdin — no shell interpolation. Successful completions marked to skip in the normal executor. Failure offers retry/skip/abort.

**Cross-AI peer review** (`/gsd-review`): configurable set of external CLIs that review plans before execution.

**SDK** (`sdk/`, v1.36): `gsd-sdk query` — registry-based queryable CLI with classified errors; headless integration path for CI or other tools.

**Knowledge-graph integration** (`/gsd-graphify`, v1.36): `.planning/graphs/` feeds planning agents richer context links.

**Global learnings store** (`~/.gsd/knowledge/`, feature flag `features.global_learnings`): cross-project pattern reuse. `gsd-extract-learnings` harvests; planner consumes on future projects.

**Community hooks** (opt-in): `gsd-validate-commit.sh`, `gsd-phase-boundary.sh`, `gsd-session-state.sh` — reinforce workflow safety at the git level.

No explicit mention of OMC, Claude Agent Skills SDK, or Copilot plugin schema integration — GSD's own runtime-translation layer covers Copilot via `.github/copilot-instructions.md` injection, not the official plugin manifest.

## 12. Notable strengths

- **Everything on disk.** No hidden agent state; `.planning/` is fully human-readable and git-diffable. `state validate` / `state sync` mean the orchestrator can always rebuild from ground truth.
- **Artifact chain is rigorous.** Each step's output is the next step's input, enforced by `gsd-tools.cjs init <workflow>`. No re-reading config, no drift.
- **Agent catalog is deep and specialized.** 30+ agents with explicit role/input/output contracts and read-only vs write-authorized tiers.
- **XML task schema is battle-tested.** `<read_first>` + `<action>` (concrete values, never "align X with Y") + `<acceptance_criteria>` (grep-verifiable) + `<must_haves>` (goal-backward) forces specificity.
- **Wave-based parallelism with worktree isolation.** Sequential Task dispatch + `.git/config.lock` avoidance + pre-merge snapshot + post-wave regression gate is a serious attempt at safe parallel execution.
- **Revision loops are bounded.** Plan-checker max 3 iterations with stall detection; prevents infinite back-and-forth.
- **Gate taxonomy is clean.** Pre-flight / Revision / Escalation / Abort give a consistent vocabulary.
- **Gaps are first-class.** `gaps_found` status + `/gsd-execute-phase --gaps-only` + `/gsd-plan-milestone-gaps` recognize that phases rarely land in one shot.
- **Anti-pattern blocking.** `.continue-here.md` `severity: blocking` forces 3-question acknowledgement before advance — codified learning-from-failure.
- **Nyquist validation architecture.** Map tests → requirements before code is written (the "feedback contract") is unusually disciplined.
- **Multi-runtime with single author source.** Claude, OpenCode, Gemini, Kilo, Codex, Copilot, Cursor, Windsurf, Antigravity, Augment, Trae, Qwen, CodeBuddy, Cline — 14 runtimes. Cross-AI execution means you can even mix CLIs per plan.
- **Dogfooded.** The repo has its own `.planning/` — they ship using GSD.
- **Observable.** Statusline, context monitor (35%/25% thresholds), `/gsd-progress`, `/gsd-stats`, `/gsd-session-report`, `/gsd-health --forensic`.
- **Safe undo.** `/gsd-undo` uses the phase manifest with dependency checks — not a naked `git revert`.
- **Worktree-based workspaces.** `/gsd-new-workspace` gives parallel feature isolation without branch confusion.
- **Backlog + seeds** (999.x numbering and trigger-based auto-surfacing) are elegant solutions to "good ideas at the wrong time."
- **Thinking partner & thinking-model references** (`references/thinking-models-{planning,execution,verification,research,debug}.md`) expose explicit reasoning strategies per stage.

## 13. Notable weaknesses / friction / known gaps

From open issues + docs:

- **Statusline context bar overreports on 1M-window models** (#2292, #2219) — hardcoded 200K assumption; claims 99% used when actually 20%.
- **`is_next_to_discuss` blocks parallel discuss/plan** (#2268) — only one phase can be in "Ready to discuss" at a time, preventing real concurrent prep.
- **`audit-uat` parser misses HUMAN-UAT items with bracketed result values** (#2273) — UAT format regex brittleness.
- **`gsd-quick` doesn't interactively confirm phases before proceeding** (#2180) — fires without user buy-in.
- **Windows MCP stdio deadlocks** (Claude Code #28126, documented in `plan-phase.md`): "MCP stdio deadlocks common on Windows. If frozen during agent spawning: force-kill terminal, `taskkill /F /IM node.exe`, `rmdir /S %USERPROFILE%\.claude\tasks\`, retry with `--skip-research`."
- **No production dependencies** (per `package.json`) — entire runtime relies on host runtime's Node built-ins + shell. Portability is a feature but also means limited leverage for heavy lifting.
- **Heavy disk footprint in `.planning/`.** Per-phase artifact count is 8–15 files; for long-running projects this grows substantially, which is why `/gsd-cleanup` exists but is opt-in.
- **Opinionated state machine.** The six-stage phase lifecycle is fixed; teams that don't do UI or don't want "discuss" as a hard step must use flags every time.
- **Plan-checker ceiling.** 3-iteration cap + stall detection is pragmatic but in hard cases pushes unresolved issues onto the user as "Proceed anyway / Abandon."
- **Parallel execution safety requires `--no-verify` commits.** Post-wave gate is the compensating control; pre-commit hooks are bypassed during waves.
- **No Copilot plugin manifest integration.** GSD installs to `.github/copilot-instructions.md`, not via the official Copilot CLI plugin schema — for Copilot users, GSD is instruction injection, not a first-class plugin.
- **`.planning/` is not always committed by default.** `config.planning.commit_docs` autodisables if `.planning/` is in `.gitignore`; team handoffs then require out-of-band sharing.
- **Prompt-injection exposure.** Issue #2201 ("Read-time prompt injection scanner") is explicitly requested — current read-guard is advisory.
- **Prior-phase completeness scan** can aggressively defer items to a backlog phase — risk of silently shelving work without user awareness if flag usage isn't conservative.
- **`gsd-prompt-guard.js` is non-disableable** per `CONFIGURATION.md` — users who want full control must patch source.
- **Planner source-audit false positives.** `## ⚠ Source Audit: Unplanned Items Found` surfaces REQUIREMENTS/RESEARCH/CONTEXT items not covered; anecdotally (based on `planner-antipatterns.md`) this noise is real.
- **Installer drift.** Commit 2026-04-14 #2233 "restore detect-custom-files and backup_custom_files lost in release drift" suggests recent release hygiene issues.

## 14. Recent direction (last 60 days)

From `CHANGELOG.md` and `commits/main`:

**v1.34.0 (2026-04-06)** — The four-gate taxonomy (pre-flight/revision/escalation/abort). Post-merge hunk verification (detects silently dropped hunks). Three context execution profiles (`dev`, `research`, `review`). Critical packaging fix: shell hooks were missing from npm.

**v1.35.0 (2026-04-10)** — First-class **Cline** runtime support (`.clinerules`). **CodeBuddy** and **Qwen Code** runtime support. Reverse migration `/gsd-from-gsd2`. AI framework selection wizard `/gsd-ai-integration-phase`. Retroactive AI eval coverage audit `/gsd-eval-review`. Per-CLI model selection for `/gsd-review`. Statusline surfaces GSD milestone/phase/status when no `in_progress` todo is active. Qwen and Cursor CLI peer reviewers. Worktree safety — prevents `git clean` in worktree context, pre-merge deletion verification.

**v1.36.0 (2026-04-14)** — **Knowledge graph** (`/gsd-graphify`) for planning agents. **Pattern analysis agent**. **SDK query** (registry-based `gsd-sdk query` with classified errors). **TDD pipeline mode** (`--tdd`). **Stale/orphan worktree detection** (W017). **Automatic prompt size reduction** for sub-200K models. **Cross-AI execution hook** in phase execution. External code review hook in ship. Architectural-responsibility mapping in phase-researcher. `state prune` command (prune unbounded STATE.md growth). Context-cost sizing replaces time-based reasoning in planner. Auto-delete branch cleanup on merge with weekly sweep. Agent spec standardization across all specifications.

**Post-release commits (2026-04-15):**
- `feat(progress): add --forensic flag for 6-check integrity audit after standard report` (#2231)
- `feat(discuss-phase): add --all flag to skip area selection and discuss everything` (#2230)
- `feat(handoffs): include project identity in all Next Up blocks` (#1948 / #2287)
- `fix(add-backlog): write ROADMAP entry before directory creation to prevent false duplicate detection` (#2286)
- `fix(settings): route /gsd-settings reads/writes through workstream-aware config path` (#2285)
- `fix: normalize Windows paths in update scope detection` (#2278)
- `fix: embed model_overrides in Codex TOML and OpenCode agent files` (#2279)
- `fix(installer): restore detect-custom-files and backup_custom_files lost in release drift` (#2233)
- `fix(hooks): complete stale-hooks false-positive fix — stamp .sh version headers + fix detector regex` (#2224)

**Trend summary:**
- Aggressive **runtime breadth** expansion (Cline, CodeBuddy, Qwen, Kimi requested in #2249).
- **Forensics tooling** maturing (`--forensic` health audit, `/gsd-forensics`, `state prune`).
- **SDK headless path** being built out (Phase 1 of query SDK, registry-classified errors).
- **Knowledge graph** and **global learnings** pointing toward cross-project intelligence.
- **Worktree safety** continuing to harden.
- Active bug fixing around **Windows paths**, **installer drift**, **stale hooks**, **release hygiene**.

## 15. Open questions

1. **How does GSD avoid drift between `commands/gsd/*.md` and `get-shit-done/workflows/*.md`?** There are ~75 commands and ~71 workflows — the mapping looks 1:1 but isn't documented. Is `commands/gsd/*` just a thin shim that delegates to `workflows/*`? Worth inspecting one pair directly.
2. **`gsd-tools.cjs` source.** Commands call `node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" init plan-phase "$PHASE"` — the actual domain-module behavior isn't fully mapped. A direct inspection of the file would confirm the init contract, the state schema, and the template injector.
3. **Agent skill-injection contract.** `agent_skills` is documented but the injection format (how the extra `SKILL.md` files are appended to the agent prompt) isn't clear from docs alone.
4. **Knowledge-graph data model** (`.planning/graphs/`). The v1.36 feature is announced but the shape of the graph (nodes/edges/querying) is not documented in public docs.
5. **Does the plan-bounce external script contract exist as a spec?** `BOUNCE_SCRIPT PLAN_FILE BOUNCE_PASSES` is the invocation but expected stdout contract and failure semantics are under-specified in public docs.
6. **Cross-AI-execution prompt format.** The orchestrator constructs "a task prompt from plan OBJECTIVE and TASKS" and pipes via stdin — the exact format is opaque to downstream AI CLIs.
7. **Copilot installation details.** Does the installer only write `.github/copilot-instructions.md`, or does it also register Copilot CLI plugins when available? For our copilot-omni plugin, this matters: is GSD a potential co-existence scenario, or a direct alternative?
8. **Milestone archival format.** `milestone-archive.md` template exists but the archival path (`.planning/milestones/vX/`?) and retention policy aren't documented.
9. **Workstream internals.** `/gsd-workstreams` creates isolated `.planning/` state via worktrees, but the merge-back story (how partial milestone completions reconcile) is unclear.
10. **Anti-self-healing.** `/gsd-undo` is documented but its relationship to the Nyquist validation contract (does undo also roll back test additions?) is worth confirming.
11. **`docs/skills/` subdirectory.** We did not enumerate it — may contain a "skills" abstraction competing with agent-skills injection.
12. **`.omc` vs `.planning` coexistence.** For our plugin's purposes, a key open question: could GSD's `.planning/` and our `.omc/` coexist, and what would a migration/bridge look like?

---

**Sources cited inline.** Key URLs:
- Repo: https://github.com/gsd-build/get-shit-done
- Commands dir: https://github.com/gsd-build/get-shit-done/tree/main/commands/gsd
- Agents dir: https://github.com/gsd-build/get-shit-done/tree/main/agents
- Docs: https://github.com/gsd-build/get-shit-done/tree/main/docs (ARCHITECTURE.md, USER-GUIDE.md, COMMANDS.md, AGENTS.md, FEATURES.md, CONFIGURATION.md, CLI-TOOLS.md, workflow-discuss-mode.md)
- Templates: https://github.com/gsd-build/get-shit-done/tree/main/get-shit-done/templates (+ `codebase/`, `research-project/`)
- Workflows: https://github.com/gsd-build/get-shit-done/tree/main/get-shit-done/workflows
- References: https://github.com/gsd-build/get-shit-done/tree/main/get-shit-done/references
- Hooks: https://github.com/gsd-build/get-shit-done/tree/main/get-shit-done/hooks
- CHANGELOG: https://raw.githubusercontent.com/gsd-build/get-shit-done/main/CHANGELOG.md
- Open issues: https://github.com/gsd-build/get-shit-done/issues
- Installer: https://raw.githubusercontent.com/gsd-build/get-shit-done/main/bin/install.js
