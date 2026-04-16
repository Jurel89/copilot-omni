# External Repository Research: oh-my-claudecode, oh-my-openagent, get-shit-done

Research date: 2026-04-16
Scope: repository-level comparison for Copilot Omni phase A
Method: local source inspection of fresh clones plus upstream Git history sampling for the last 60 days.

## Executive Summary

These three upstream projects overlap in one obvious way: all three are trying to turn a single interactive coding agent into an orchestrated system. The overlap ends there. `oh-my-claudecode` is a Claude-first orchestration layer with aggressive hook usage, mode wrappers, and a large skill library. `oh-my-openagent` is the most explicit multi-model orchestration system of the three: categories, background agents, model matching, runtime fallback, and OpenCode-native hooks are first-class concepts rather than side effects. `get-shit-done` is less a “plugin that helps coding” and more a full project operating system: phase discussion, phase planning, execution, verification, shipping, milestone closure, backlog, workspaces, threads, and specialized auditors.

For Copilot Omni specifically, the most useful takeaway is that each upstream has a different primary abstraction:

- OMC optimizes around **modes + hooks + skills**.
- OMOA optimizes around **agents + categories + hooks + background execution**.
- GSD optimizes around **artifacts + workflow stages + specialist agents + explicit state**.

That abstraction choice drives almost every downstream design decision: where intent is routed, how persistent state is stored, what the “front door” feels like, how many moving parts exist, and what kind of failures become common.

## 1. oh-my-claudecode

Repository: `Yeachan-Heo/oh-my-claudecode`
Primary sources: `README.md`, `docs/REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/HOOKS.md`, `docs/shared/mode-hierarchy.md`, `docs/GETTING-STARTED.md`, `CHANGELOG.md`.
URLs:
- https://github.com/Yeachan-Heo/oh-my-claudecode
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/README.md
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/REFERENCE.md
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/ARCHITECTURE.md
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/HOOKS.md
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/shared/mode-hierarchy.md
- https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/CHANGELOG.md

### Positioning

OMC positions itself as an “intelligent multi-agent orchestration” layer for Claude Code. The README’s orchestration table presents multiple strategies, from “Team (recommended)” through `ccg`, `Autopilot`, `Ultrawork`, and `Ralph` (`README.md`, “Orchestration Modes”). The architecture doc frames the system as a combination of agent lanes, skills, hooks, and persistent state (`docs/ARCHITECTURE.md`). A short but revealing line from `CLAUDE.md` is that the project is about “Intelligent Multi-Agent Orchestration,” not a single prompt template.

In practice, OMC is trying to make Claude Code feel like a programmable workflow substrate. It does that by leaning heavily on hooks, a skill registry, tiered agents, and a collection of execution “modes” that can be composed or wrapped.

### Skill catalog

There is a documentation mismatch worth noting up front.

- `docs/REFERENCE.md` says “Skills (32 Total)” and explicitly says this includes “31 canonical skills + 1 deprecated alias.”
- The repository tree currently contains **37 skill directories** under `skills/`.

The directory catalog on 2026-04-16 is:

- `ai-slop-cleaner`
- `ask`
- `autopilot`
- `cancel`
- `ccg`
- `configure-notifications`
- `debug`
- `deep-dive`
- `deep-interview`
- `deepinit`
- `external-context`
- `hud`
- `learner`
- `mcp-setup`
- `omc-doctor`
- `omc-reference`
- `omc-setup`
- `omc-teams`
- `plan`
- `project-session-manager`
- `ralph`
- `ralplan`
- `release`
- `remember`
- `sciomc`
- `self-improve`
- `setup`
- `skill`
- `skillify`
- `team`
- `trace`
- `ultraqa`
- `ultrawork`
- `verify`
- `visual-verdict`
- `wiki`
- `writer-memory`

The doc-backed skill list in `docs/REFERENCE.md` overlaps strongly with the directory scan but is clearly lagging or intentionally curated. That is already one of OMC’s recurring patterns: powerful surface area, but some drift between runtime and documentation.

What those skills do at a high level:

- Core orchestration: `autopilot`, `ralph`, `ultrawork`, `team`, `ralplan`, `trace`, `ultraqa`, `ccg`.
- Setup / operations: `setup`, `omc-setup`, `omc-doctor`, `mcp-setup`, `configure-notifications`, `hud`, `release`.
- Knowledge / analysis: `ask`, `deep-interview`, `deep-dive`, `external-context`, `sciomc`, `wiki`, `remember`, `omc-reference`.
- Project workflow utilities: `project-session-manager`, `skill`, `skillify`, `learner`, `verify`, `debug`, `deepinit`, `visual-verdict`, `writer-memory`, `self-improve`.

The most important conceptual skill split is between:

- **wrapper or standalone modes** like `autopilot`, `ralph`, `team`
- **component modes** like `ultrawork` and `ultraqa`
- **support skills** like `trace`, `ask`, `verify`, `project-session-manager`

That split is documented in `docs/shared/mode-selection-guide.md` and `docs/shared/mode-hierarchy.md`.

### Agent catalog

OMC’s agent model is tiered. `README.md` says “19 specialized agents (with tier variants),” while `docs/REFERENCE.md` says “Agents (29 Total).” The 29 number is the more useful operational number because OMC treats tier variants as real routing targets.

The documented catalog in `docs/REFERENCE.md` includes these role families:

- Analysis: `architect-low`, `architect-medium`, `architect`
- Execution: `executor-low`, `executor`, `executor-high`
- Search: `explore`, `explore-high`
- Research: `document-specialist`
- Frontend: `designer-low`, `designer`, `designer-high`
- Docs: `writer`
- Visual: `vision`
- Planning: `planner`
- Critique: `critic`
- Pre-planning: `analyst`
- Testing: `qa-tester`
- Tracing: `tracer`
- Security: `security-reviewer-low`, `security-reviewer`
- Build/debug: `debugger`
- TDD: `test-engineer`
- Code review: `code-reviewer`
- Data science: `scientist`, `scientist-high`
- Git: `git-master`
- Simplification: `code-simplifier`

A useful OMC quote is its “smart model routing” line from the README: “Haiku for simple tasks, Opus for complex reasoning.” That is not just marketing. The tier matrix in `docs/shared/agent-tiers.md` makes the routing scheme explicit.

### Hook and trigger surface

OMC is hook-heavy. `docs/REFERENCE.md` says it “registers 20 hook scripts across 11 Claude Code lifecycle events.” `docs/HOOKS.md` breaks the model down clearly.

Lifecycle events used:

- `UserPromptSubmit`
- `SessionStart`
- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`
- `PreCompact`
- `Stop`
- `SessionEnd`

The most important hooks for behavior shaping are:

- `keyword-detector.mjs`: turns prompt keywords into skill activations.
- `skill-injector.mjs`: injects the resolved skill prompts.
- `persistent-mode.cjs`: keeps active modes like Ralph or Autopilot from ending early.
- `pre-tool-enforcer.mjs`: enforces tool/agent rules.
- `project-memory-*` and `pre-compact.mjs`: preserve state and context.

OMC’s trigger model is therefore two-tiered:

1. explicit slash/skill invocation, such as `/oh-my-claudecode:ralph`
2. implicit keyword routing, where typed words like `ulw`, `ralph`, or `autopilot` activate modes via `keyword-detector`

The hook docs are explicit that “autopilot, ralph, ultrawork, and ultraqa are skills … not hooks,” while the `persistent-mode` hook is what “enforces their continuation.” That distinction matters: OMC’s hooks do not define the workflow, but they strongly control when the workflow starts, how it continues, and how it survives interruption.

### Orchestration model

OMC has the richest “named mode” taxonomy of the three projects.

Primary modes documented in `README.md` and `docs/shared/mode-hierarchy.md`:

- `team`: staged, coordinated multi-agent shared-task execution
- `omc team`: tmux-backed CLI workers using real `claude` / `codex` / `gemini`
- `ccg`: Claude-Codex-Gemini advisory synthesis
- `autopilot`: autonomous end-to-end execution
- `ultrawork`: maximum parallelism engine
- `ralph`: persistence wrapper with verify/fix loop
- `pipeline`: sequential staged processing
- `ultrapilot` legacy alias

The most revealing inheritance statement in `docs/shared/mode-hierarchy.md` is:

- `autopilot` includes `ralph`, `ultrawork`, `ultraqa`, and `plan`
- `ralph` includes `ultrawork`
- `ultrawork` is a component, not a full workflow

So, in OMC, “mode” is not just a user-facing command label. It is a compositional execution grammar.

For Copilot Omni, OMC’s closest equivalents to the terms in your prompt are:

- **autopilot equivalent**: `autopilot`
- **ralph equivalent**: `ralph`
- **ultrawork equivalent**: `ultrawork`
- **ralplan equivalent**: `ralplan`
- **team equivalent**: `team` / `omc-teams`

### Intent-routing front door

OMC has multiple front doors.

- Explicit: slash skills such as `/oh-my-claudecode:autopilot`.
- Implicit: keyword-triggered routing such as `ulw`, `ralph`, `autopilot`, `search`, `analyze`.
- Setup front door: `setup` / `omc-setup` skill.

The keyword detector is the most important implicit router. `docs/HOOKS.md` says it sanitizes the prompt and matches “magic keywords.” That makes OMC relatively friendly for natural-language steering, but it also creates accidental-trigger risk, which the recent commit history shows the project repeatedly hardening against.

### State persistence

OMC’s persistent state is centered on `.omc/`. `docs/ARCHITECTURE.md` gives the most complete structure:

- `.omc/state/` for per-mode state and sessions
- `.omc/notepad.md` for compaction-resistant notes
- `.omc/project-memory.json` for project memory
- `.omc/plans/`, `.omc/notepads/`, `.omc/prompts/`, `.omc/research/`, `.omc/logs/`
- `.omc/state/interop/` for cross-tool envelopes

There is also optional centralized state via `OMC_STATE_DIR`, which relocates per-project state to a stable hashed location outside a worktree. This is a strong design point for systems that use worktrees or ephemeral checkouts.

Short snippet worth preserving: the architecture doc says OMC separates “control plane vs data plane.” That is one of the more mature state-design ideas among these projects.

### Configuration

OMC has at least two configuration stories in the docs.

- `docs/GETTING-STARTED.md` describes JSONC config files: `~/.config/claude-omc/config.jsonc` and `.claude/omc.jsonc`.
- `docs/REFERENCE.md` focuses heavily on generated `.claude/CLAUDE.md` files and environment variables.

That is not necessarily contradictory, but it is cognitively expensive. Users are expected to understand generated `CLAUDE.md`, project/global precedence, JSONC config, and env vars such as `OMC_STATE_DIR`, `OMC_PARALLEL_EXECUTION`, `OMC_SKIP_HOOKS`.

Strength of the design: plenty of knobs.
Weakness of the design: too many knobs, spread across multiple mechanisms.

### Notable strengths

- Strong composition model. OMC is unusually explicit about how `autopilot`, `ralph`, `ultrawork`, and `team` relate.
- Mature hook usage. The hooks are not incidental glue; they are a genuine runtime layer.
- Good persistence model. `.omc/` is substantial and thoughtfully split.
- Strong verification philosophy. Separate `critic`, `code-reviewer`, `verify`, `ultraqa`, and review gates recur throughout the docs.
- Interop ambition. `omc-teams` and `ccg` bridge into Codex/Gemini rather than staying Claude-only.

### Notable weaknesses

- Documentation drift. Agent counts and skill counts differ between README, REFERENCE, and filesystem.
- Very high conceptual load. Modes, hooks, skills, tiers, keywords, CLI workers, and multiple config channels make onboarding hard.
- Hook sensitivity. Recent changes are full of false-positive suppression, stale pane cleanup, trust-boundary hardening, and keyword-trigger fixes, which suggests a powerful but delicate runtime.
- Claude Code assumptions remain central even where external CLIs exist.

### Recent direction: last 60 days

The last 60 days are dominated by hardening rather than category expansion.

Evidence:

- `CHANGELOG.md` for `v4.11.6` dated **2026-04-13** reports “4 new features, 30 bug fixes, 14 other changes.”
- Recent commits from **2026-04-09 to 2026-04-14** concentrate on Ralph gate enforcement, permission trust boundaries, hook duplication, tmux noise suppression, HUD usage providers, and `OMC_STATE_DIR` state-resolution fixes.

Observed themes:

- **Ralph hardening**: “Make Ralph enforce real PRD and story review gates,” “Prevent Ralph from approving its own injected prompt text,” “Close Ralph approval spoofing…”
- **Hook/noise suppression**: repeated work on keyword false positives, stale pane replay alerts, and post-tool noise.
- **State/path correctness**: centralized `OMC_STATE_DIR` resolution and installer/settings race fixes.
- **HUD/provider visibility**: MiniMax usage provider, extra usage spend display, cache splitting.

My reading: OMC is in a stabilization and guardrail phase. It is not retreating from its complex mode-and-hook architecture; it is doubling down and trying to make that architecture less fragile.

## 2. oh-my-openagent / oh-my-opencode

Repository: `code-yeongyu/oh-my-openagent`
Primary sources: `README.md`, `docs/guide/overview.md`, `docs/guide/orchestration.md`, `docs/reference/features.md`, `docs/reference/configuration.md`, `src/features/builtin-commands/commands.ts`, `src/tools/call-omo-agent/constants.ts`, `src/tools/delegate-task/*.ts`, `src/create-hooks.ts`, `src/tools/session-manager/storage.ts`.
URLs:
- https://github.com/code-yeongyu/oh-my-openagent
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/README.md
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/guide/overview.md
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/guide/orchestration.md
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/reference/features.md
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/reference/configuration.md
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/features/builtin-commands/commands.ts
- https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/create-hooks.ts

### Positioning

OMOA’s positioning is the clearest and most opinionated of the three. `docs/guide/overview.md` says it is about “breaking free” of one-model lock-in. It explicitly frames itself as multi-model orchestration: “Claude for orchestration. GPT for deep reasoning. Gemini for frontend.” That is the project’s core identity, not a side capability.

The architecture diagram in `docs/guide/overview.md` is straightforward:

- User request
- Intent Gate
- Sisyphus as main orchestrator
- Prometheus, Atlas, Oracle, Librarian, Explore, and category-based agents under it

If OMC is “mode-first,” OMOA is “orchestrator-first.”

### Skill catalog

Unlike OMC and GSD, OMOA does not present a giant repository-level `skills/` directory as its main catalog. Instead, `docs/reference/features.md` documents **built-in skills** plus a custom SKILL.md loading system.

Built-in skills documented:

- `git-master`
- `playwright`
- `agent-browser`
- `dev-browser`
- `frontend-ui-ux`
- `review-work`
- `ai-slop-remover`

Custom skill load paths, in priority order, include:

- `.opencode/skills/*/SKILL.md`
- `~/.config/opencode/skills/*/SKILL.md`
- `.claude/skills/*/SKILL.md`
- `.agents/skills/*/SKILL.md`
- `~/.agents/skills/*/SKILL.md`

That is a major difference from OMC. OMOA’s built-in skill set is smaller, but its compatibility layer for imported skill ecosystems is broader.

### Agent catalog

`docs/reference/features.md` says OMOA provides **11 specialized AI agents**. The documented built-ins are:

Core agents:

- `Sisyphus`
- `Hephaestus`
- `Oracle`
- `Librarian`
- `Explore`
- `Multimodal-Looker`

Planning agents:

- `Prometheus`
- `Metis`
- `Momus`

Orchestration agents:

- `Atlas`
- `Sisyphus-Junior`

There is a second catalog layer via `task` categories rather than named agents:

- `visual-engineering`
- `ultrabrain`
- `deep`
- `artistry`
- `quick`
- `unspecified-low`
- `unspecified-high`
- `writing`

And there is now a third layer: **dynamic custom agents**. The current source in `src/tools/call-omo-agent/agent-resolver.ts` explicitly merges built-in allowed agents with agents discovered dynamically from the runtime registry. Recent commits on **2026-04-14** added `agent_definitions` loading and precedence rules. That is a concrete sign that OMOA is moving from a fixed cast toward an extensible agent registry.

### Hook and trigger surface

OMOA has the broadest event taxonomy of the three, at least in documentation.

`docs/reference/features.md` groups hooks by abstract event types:

- `PreToolUse`
- `PostToolUse`
- `Message`
- `Event`
- `Transform`
- `Params`

The built-in hook set is extensive. Important clusters:

- Context injection: directory AGENTS/README/rules injectors, compaction context injector, context-window monitor, preemptive compaction
- Productivity/control: keyword detector, think-mode, ralph-loop, start-work, auto-slash-command, category-skill reminder
- Quality/safety: comment-checker, thinking-block validator, edit-error recovery, write-existing-file guard, hashline helpers
- Recovery/stability: session recovery, runtime fallback, model fallback, JSON recovery
- Task management: task-resume-info, delegate-task-retry, tasks-todowrite-disabler
- Continuation: todo continuation, compaction todo preservation, unstable-agent babysitter
- Integration: Claude Code hooks bridge, Atlas orchestration, interactive bash session, non-interactive env

The runtime constructor in `src/create-hooks.ts` assembles hooks from three factories: core, continuation, and skill hooks. That separation suggests OMOA treats hooks as a modular subsystem instead of a flat bag of callbacks.

### Orchestration model

OMOA’s orchestration model has named personas rather than mode wrappers.

Main equivalents:

- **ultrawork equivalent**: `ultrawork` / `ulw`, usually driven by Sisyphus with maximum intensity
- **ralph equivalent**: `/ralph-loop`
- **planning equivalent**: Prometheus + Metis + Momus
- **execution equivalent**: Atlas + Sisyphus-Junior
- **deep autonomous worker**: Hephaestus

The most important architecture split is in `docs/guide/orchestration.md`:

- Planning = `Prometheus` + `Metis` + `Momus`
- Execution = `Atlas`
- Work is carried out by `Sisyphus-Junior` and specialists

This is cleaner than OMC’s inheritance-heavy mode system. It is also more obviously actor-based.

### Intent-routing front door

OMOA explicitly names an **Intent Gate**. `docs/guide/overview.md` says:

> “Before acting on any request, Sisyphus classifies your true intent.”

That is the cleanest statement of front-door routing among the three upstreams.

Operational front doors include:

- Natural prompt routed through Sisyphus and the Intent Gate
- Mode keyword `ultrawork` / `ulw`
- Planning trigger via Prometheus mode (`@plan` or tab according to docs)
- Slash commands such as `/init-deep`, `/ralph-loop`, `/start-work`, `/refactor`
- Direct agent invocation such as `@oracle`
- `task` delegations using categories

The key architectural point is that OMOA cleanly separates **intent classification**, **named strategic/orchestration agents**, and **category-based workers**. That three-layer model is arguably the most elegant of the set.

### State persistence

OMOA spreads persistence across several subsystems.

Documented persistence surfaces include:

- `.sisyphus/tasks/` for persistent task-system JSON files
- `.sisyphus/notepads/{plan-name}/` for accumulated wisdom (`learnings.md`, `decisions.md`, `issues.md`, `verification.md`, `problems.md`)
- session-manager storage that merges SDK-backed session storage with filesystem session storage (`src/tools/session-manager/storage.ts`)
- Claude session-state mapping in `src/features/claude-code-session-state/state.ts`
- model capability caches in `src/plugin-state.ts`

This is a capable design, but it is less visibly centralized than OMC’s `.omc/` or GSD’s `.planning/`. OMOA stores the right things, but in a more subsystem-local way.

### Configuration

Configuration is powerful and fairly coherent. `docs/reference/configuration.md` documents:

- project config: `.opencode/oh-my-openagent.json[c]` or legacy `.opencode/oh-my-opencode.json[c]`
- user config: `~/.config/opencode/oh-my-openagent.json[c]` or legacy variants
- agent overrides
- category overrides
- fallback models
- task system settings
- hook settings
- commands, browser automation, tmux, notification, MCP, LSP, hashline-edit, experimental settings

The source file `src/plugin-config.ts` is also worth noting because it implements partial config loading, migration of legacy basenames, merge behavior across arrays and nested config, and `agent_definitions` path resolution. That is a mature compatibility story.

### Notable strengths

- Cleanest multi-model thesis. OMOA is explicit about why different models should do different work.
- Strong orchestration separation: Sisyphus / Prometheus / Atlas / Junior is easier to reason about than a pile of generic modes.
- Excellent delegation substrate: categories, background tasks, dynamic custom agents, fallback chains, task system.
- Strong tooling story: hashline edit, LSP, AST-grep, visual `look_at`, interactive bash, session search.
- Compatibility ambition: OpenCode-native plus Claude-compatible skills/commands/hooks paths.

### Notable weaknesses

- Runtime complexity is extremely high. Hooks, categories, agent prompts, task system, background manager, session manager, and compatibility bridges all overlap.
- State is less centralized and therefore less inspectable at a glance than GSD or OMC.
- Rename transition (`openagent` vs `opencode`) still leaks through docs, config basenames, package name, and schema URLs.
- Heavy reliance on OpenCode/Bun/TypeScript infrastructure. This is not a lightweight or corporate-minimal system.

### Recent direction: last 60 days

OMOA appears to be moving in two directions simultaneously: **extensibility** and **runtime hardening**.

Evidence from recent commits sampled after **2026-02-15**:

- **2026-04-14**: `feat(agents): add agent_definitions schema, eager path resolution, and JSON agent loader`
- **2026-04-14**: `feat(agents): wire agent_definitions and opencode.json agents into precedence chain`
- **2026-04-14 to 2026-04-15**: multiple prototype-safety fixes in agent loader code
- **2026-04-15**: fixes for hidden native plan agents, telemetry free-tier containment, run-command agent resolution, regression tests
- **2026-03-26**: restriction fallback fix for unknown agents

The strongest directional signal is the addition of **custom agent definitions** plus the source change in `agent-resolver.ts` that merges built-ins with dynamically discovered agents. That is not a small maintenance patch; it expands the project from “a system with known cast members” toward “a platform with a built-in cast and user-defined additions.”

## 3. get-shit-done (GSD)

Repository: `gsd-build/get-shit-done`
Primary sources: `README.md`, `docs/FEATURES.md`, `docs/USER-GUIDE.md`, `docs/CONFIGURATION.md`, `docs/COMMANDS.md`, `docs/AGENTS.md`, `commands/gsd/*.md`, `get-shit-done/bin/lib/config.cjs`, `get-shit-done/bin/lib/state.cjs`.
URLs:
- https://github.com/gsd-build/get-shit-done
- https://github.com/gsd-build/get-shit-done/blob/main/README.md
- https://github.com/gsd-build/get-shit-done/blob/main/docs/FEATURES.md
- https://github.com/gsd-build/get-shit-done/blob/main/docs/USER-GUIDE.md
- https://github.com/gsd-build/get-shit-done/blob/main/docs/CONFIGURATION.md
- https://github.com/gsd-build/get-shit-done/blob/main/docs/COMMANDS.md
- https://github.com/gsd-build/get-shit-done/blob/main/docs/AGENTS.md
- https://github.com/gsd-build/get-shit-done/blob/main/CHANGELOG.md

### Positioning

GSD is the least “plugin-ish” and the most workflow-opinionated of the three. The README does not primarily sell a coding assistant; it sells a method: initialize a project, discuss a phase, plan the phase, execute it, verify it, ship it, complete the milestone, repeat. The user guide includes a full lifecycle diagram with those steps as the main spine.

The project is really a project execution OS layered on top of agent runtimes. That is why it supports so many runtimes and why it persists so many artifacts.

### Skill / command catalog

GSD’s practical “skill” surface is its command set. On disk today there are **74 command files** in `commands/gsd/`. That command count also matches the project’s recent docs sync work and tests guarding command counts.

Representative groups:

- Core workflow: `new-project`, `discuss-phase`, `ui-phase`, `plan-phase`, `execute-phase`, `verify-work`, `ship`, `complete-milestone`
- Navigation / orchestration: `next`, `progress`, `resume-work`, `manager`, `autonomous`, `quick`, `fast`, `do`
- Phase management: `add-phase`, `insert-phase`, `remove-phase`, `analyze-dependencies`, `plan-milestone-gaps`, `validate-phase`
- Brownfield / discovery: `map-codebase`, `scan`, `intel`, `explore`
- Review / security / docs: `code-review`, `code-review-fix`, `audit-fix`, `review`, `secure-phase`, `docs-update`
- Context / backlog / thread: `note`, `add-todo`, `check-todos`, `add-backlog`, `review-backlog`, `plant-seed`, `thread`
- Multi-project / workstreams: `new-workspace`, `list-workspaces`, `remove-workspace`, `workstreams`
- AI-specialized: `ai-integration-phase`, `eval-review`

GSD’s true “front door” commands are `new-project`, `next`, `do`, `autonomous`, `quick`, and `manager`. The rest fill defined lifecycle slots.

### Agent catalog

Again there is some documentation drift.

- `docs/AGENTS.md` says “All 21 specialized agents.”
- The repository currently contains **31 agent spec files** under `agents/`.

The on-disk catalog on 2026-04-16 is:

- `gsd-advisor-researcher`
- `gsd-ai-researcher`
- `gsd-assumptions-analyzer`
- `gsd-code-fixer`
- `gsd-code-reviewer`
- `gsd-codebase-mapper`
- `gsd-debug-session-manager`
- `gsd-debugger`
- `gsd-doc-verifier`
- `gsd-doc-writer`
- `gsd-domain-researcher`
- `gsd-eval-auditor`
- `gsd-eval-planner`
- `gsd-executor`
- `gsd-framework-selector`
- `gsd-integration-checker`
- `gsd-intel-updater`
- `gsd-nyquist-auditor`
- `gsd-pattern-mapper`
- `gsd-phase-researcher`
- `gsd-plan-checker`
- `gsd-planner`
- `gsd-project-researcher`
- `gsd-research-synthesizer`
- `gsd-roadmapper`
- `gsd-security-auditor`
- `gsd-ui-auditor`
- `gsd-ui-checker`
- `gsd-ui-researcher`
- `gsd-user-profiler`
- `gsd-verifier`

Conceptually these break down into:

- researchers and synthesizers
- planners and roadmappers
- executors and checkers
- verifiers and auditors
- brownfield mappers / profilers / debuggers
- AI-specialized researchers and evaluators

This is the broadest specialized agent set of the three if you count real agent specs rather than role tiers.

### Hook and trigger surface

GSD’s hook system is much narrower than OMC’s or OMOA’s, but it is more obviously operational.

Current hook files under `hooks/`:

- `gsd-check-update-worker.js`
- `gsd-check-update.js`
- `gsd-context-monitor.js`
- `gsd-phase-boundary.sh`
- `gsd-prompt-guard.js`
- `gsd-read-guard.js`
- `gsd-session-state.sh`
- `gsd-statusline.js`
- `gsd-validate-commit.sh`
- `gsd-workflow-guard.js`

`docs/FEATURES.md` describes the hook system as runtime hooks for:

- status display
- context monitoring
- update checking
- commit validation
- prompt/read guards
- workflow guardrails
- session-state capture

This is a much more conservative use of hooks than OMC. GSD uses hooks as **guardrails and observability**, not as the primary mechanism for spinning up modes.

### Orchestration model

GSD’s orchestration model is phase-based and artifact-driven.

The canonical lifecycle in `docs/USER-GUIDE.md` is:

1. `/gsd-new-project`
2. `/gsd-discuss-phase`
3. `/gsd-ui-phase` when relevant
4. `/gsd-plan-phase`
5. `/gsd-execute-phase`
6. `/gsd-verify-work`
7. `/gsd-ship` optional
8. milestone audit / completion

GSD’s equivalents to your terms:

- **autopilot/team equivalent**: `/gsd-autonomous`, which runs discuss → plan → execute across phases
- **phase-based equivalent**: the whole default model, especially `discuss-phase` → `plan-phase` → `execute-phase`
- **intent router front door**: `/gsd-do`
- **fast-path equivalent**: `/gsd-quick` and `/gsd-fast`

The important architectural point is that GSD does not mainly orchestrate by choosing “modes.” It orchestrates by **moving the project through artifact-producing lifecycle stages**.

### Intent-routing front door

GSD has two strong front doors.

- `/gsd-do`: routes freeform text to the appropriate GSD command and “never does the work itself” (`commands/gsd/do.md`).
- `/gsd-next`: examines project state and runs the next logical workflow step.

This is the cleanest command-dispatch story of the three. OMC relies more on keywords. OMOA relies more on Sisyphus + Intent Gate. GSD says, in effect: “if you do not know the correct verb, ask `/gsd-do`; if you do not know the correct next state transition, ask `/gsd-next`.”

### State persistence

GSD’s persistence model is the most explicit and artifact-heavy.

Core project state lives in `.planning/` and includes at minimum:

- `PROJECT.md`
- `REQUIREMENTS.md`
- `ROADMAP.md`
- `STATE.md`
- `config.json`
- phase directories with `CONTEXT.md`, `RESEARCH.md`, `PLAN.md`, `SUMMARY.md`, `VALIDATION.md`, `VERIFICATION.md`, `UAT.md`, etc.

The implementation in `get-shit-done/bin/lib/state.cjs` is notable because it treats `STATE.md` as a real progression engine rather than a passive note. It provides read, patch, update, sync, and validation operations with concurrency protection and atomic writes. That is closer to workflow engine behavior than to assistant memory behavior.

GSD also adds:

- workspaces
- workstreams
- backlog and seeds
- threads
- `.planning/intel/` for codebase intelligence
- optional SDK/query surfaces

Among the three, GSD is the easiest to audit from disk after the fact.

### Configuration

GSD stores project settings in `.planning/config.json` and documents a large schema in `docs/CONFIGURATION.md`. Config areas include:

- core settings (`mode`, `granularity`, `project_code`)
- workflow toggles (`research`, `plan_check`, `verifier`, `auto_advance`, `discuss_mode`, `skip_discuss`, `use_worktrees`, `code_review`, `plan_bounce`, `cross_ai_execution`)
- parallelization
- git branching strategy
- hooks
- feature flags
- model profiles
- agent skill injection
- response language
- graphify and intel

One of GSD’s strongest config ideas is the distinction between **workflow toggles** and **model profiles**. It lets users choose both *which process* should run and *how expensive/capable the agents should be*.

### Notable strengths

- Strongest end-to-end workflow framing. It is very hard to get lost about “what comes next.”
- Best artifact discipline. `.planning/` makes planning and delivery inspectable.
- Strong verification posture: plan checking, verifier, Nyquist validation, audits, review, security, docs verification.
- Broad runtime support while staying workflow-centric.
- Best command-level discoverability, especially through `/gsd-do` and `/gsd-next`.

### Notable weaknesses

- Heavy ceremony. For small tasks, the full lifecycle can feel like overkill.
- Command sprawl: 74 commands is powerful but intimidating.
- Documentation drift persists here too; docs/AGENTS count lags actual agent files.
- Because state is rich and explicit, recovery from corrupted artifacts or wrong early decisions can be expensive.
- It is better at project execution than at lightweight, opportunistic freeform collaboration.

### Recent direction: last 60 days

GSD’s recent direction is unusually easy to summarize because its `CHANGELOG.md` is detailed and current.

Key dated releases:

- **2026-04-14**: `1.36.0`
- **2026-04-10**: `1.35.0`
- **2026-04-06**: `1.34.2`, `1.34.1`, `1.34.0`
- **2026-04-05**: `1.33.0`
- **2026-04-04**: `1.32.0`
- **2026-04-01**: `1.31.0`

Dominant themes:

- **More workflow intelligence**: graphify, pattern mapper, plan bounce, extract learnings, workstream-aware SDK support.
- **More runtime breadth**: Cline, CodeBuddy, Qwen, Trae, Kilo, Augment, Codex/Copilot support hardened further.
- **More AI-specialized workflows**: AI integration phase, eval review, cross-AI execution hooks, external review hooks.
- **More safety and observability**: state consistency gates, health validation, stale/orphan worktree detection, hook versioning, artifact audit gates.

Unlike OMC, which is currently mostly hardening a stable conceptual model, and unlike OMOA, which is currently opening its agent model up, GSD is still visibly **expanding scope** while hardening.

## Cross-plugin comparison

### Structural comparison

| Capability category | oh-my-claudecode | oh-my-openagent | get-shit-done |
|---|---|---|---|
| Primary abstraction | Modes + hooks + skills | Agents + categories + hooks | Workflow stages + artifacts + specialist agents |
| Main positioning | Claude Code orchestration layer | Multi-model orchestration engine for OpenCode and compatible runtimes | Project execution operating system |
| Front door | Slash skills and magic keywords | Sisyphus + Intent Gate + slash commands + direct agent calls | `/gsd-do`, `/gsd-next`, explicit workflow commands |
| Catalog shape | Large skill library, tiered agent families | Smaller built-in skill set, strong named agents, custom agent/category system | Huge command library, large specialist agent roster |
| Orchestration style | Named modes such as `autopilot`, `ralph`, `ultrawork`, `team` | Named orchestrators/personas plus category workers | Phase pipeline: discuss → plan → execute → verify |
| Persistent state root | `.omc/` | Mixed: `.sisyphus/`, session storage, plugin caches | `.planning/` |
| Hook role | Core runtime behavior and mode continuation | Major runtime substrate for routing, recovery, editing, tasks | Guardrails, status, workflow safety |
| Config style | JSONC + CLAUDE.md + env vars | JSONC with strong schema and migration | `.planning/config.json` with workflow toggles and profiles |
| Best fit | Claude-centric orchestration with rich modes | Heterogeneous multi-model coding teams | Disciplined project delivery and auditability |
| Biggest risk | Drift and hook complexity | System complexity and rename/compat transition | Ceremony and command sprawl |

### Detailed comparison matrix

| Capability | oh-my-claudecode | oh-my-openagent | get-shit-done |
|---|---|---|---|
| Positioning | Intelligent multi-agent orchestration for Claude Code | Anti-lock-in multi-model orchestration | Full project lifecycle system |
| Skill catalog | Large local skill repo; docs say 32, tree shows 37 | 7 documented built-in skills plus custom SKILL.md loading | Command-centric rather than skill-centric; 74 commands |
| Agent catalog | Tiered families; docs say 29 total targets | 11 documented built-ins plus custom dynamic agents | 31 agent files on disk; docs lag at 21 |
| Hook surface | 20 hook scripts across 11 lifecycle events | Very broad hook taxonomy across tool, message, event, transform, params | 10 operational hooks |
| Team/parallel model | `team`, `omc-teams`, `ultrawork`, `ccg` | Background agents, tmux panes, category workers | Parallel execution by plan waves and specialist spawning |
| Persistent “don’t stop” loop | `ralph` + `persistent-mode` | `/ralph-loop` + continuation hooks | `/gsd-autonomous` and workflow re-entry, but less sloganized |
| Planning model | `plan`, `ralplan`, analyst/planner/critic | Prometheus + Metis + Momus | Discuss-phase + phase-researcher + planner + plan-checker |
| Verification model | `verify`, `ultraqa`, critic/reviewer lanes | Atlas verification, review-work, diagnostics, todo continuation | verifier, Nyquist, code review, security, docs, audit workflows |
| Intent routing | Magic keywords and explicit skill invocation | Intent Gate inside Sisyphus | `/gsd-do` and `/gsd-next` |
| State inspectability | High, but split across many `.omc` subtrees | Medium; powerful but more subsystem-scattered | Very high; `.planning` is explicit and audit-friendly |
| Config complexity | High | High | High, but more workflow-coherent |
| Docs consistency | Medium-low due count drift | Medium; better conceptual coherence, some rename complexity | Medium; detailed docs, some stale counts |
| Recent direction | Hardening hooks, gates, HUD, Ralph trust boundaries | Dynamic custom agents plus runtime hardening | Scope expansion plus hardening across workflows and runtimes |

## Takeaways for Copilot Omni

If the goal is to learn from these upstreams rather than copy them, the cleanest reusable lessons are:

1. OMC proves that **hooks can be a first-class runtime layer**, not just convenience scripts. But it also shows the maintenance cost when too much routing intelligence lives in hooks.
2. OMOA proves that **intent routing + named orchestrators + category workers** is a clean mental model. It is the best upstream reference if Copilot Omni wants multi-model delegation without phase-heavy ceremony.
3. GSD proves that **artifact-first workflows scale better than chat-only workflows** for long-running project delivery. If Copilot Omni needs auditable progression, GSD is the closest fit.

My synthesis is:

- Borrow OMOA’s separation of intent classification from execution.
- Borrow GSD’s explicit artifact/state discipline.
- Borrow OMC’s mode composition only selectively; the power is real, but the maintenance burden is also real.

The common anti-pattern across all three is surface-area inflation. Each system has become strong by adding concepts, but each also shows some combination of drift, rename baggage, count mismatch, or runtime fragility. For Copilot Omni, the biggest design opportunity is to keep the best abstractions while resisting uncontrolled expansion.

## Source appendix

### oh-my-claudecode

- Repo: https://github.com/Yeachan-Heo/oh-my-claudecode
- `README.md`
- `CLAUDE.md`
- `CHANGELOG.md`
- `docs/REFERENCE.md`
- `docs/ARCHITECTURE.md`
- `docs/HOOKS.md`
- `docs/GETTING-STARTED.md`
- `docs/shared/mode-hierarchy.md`
- `docs/shared/agent-tiers.md`

### oh-my-openagent

- Repo: https://github.com/code-yeongyu/oh-my-openagent
- `README.md`
- `AGENTS.md`
- `docs/guide/overview.md`
- `docs/guide/orchestration.md`
- `docs/reference/features.md`
- `docs/reference/configuration.md`
- `src/create-hooks.ts`
- `src/plugin-config.ts`
- `src/plugin-state.ts`
- `src/features/builtin-commands/commands.ts`
- `src/tools/call-omo-agent/constants.ts`
- `src/tools/call-omo-agent/agent-resolver.ts`
- `src/tools/session-manager/storage.ts`

### get-shit-done

- Repo: https://github.com/gsd-build/get-shit-done
- `README.md`
- `CHANGELOG.md`
- `docs/FEATURES.md`
- `docs/USER-GUIDE.md`
- `docs/CONFIGURATION.md`
- `docs/COMMANDS.md`
- `docs/AGENTS.md`
- `commands/gsd/autonomous.md`
- `commands/gsd/do.md`
- `get-shit-done/bin/lib/config.cjs`
- `get-shit-done/bin/lib/state.cjs`
