# oh-my-claudecode (Yeachan-Heo) — Deep Research

Research date: 2026-04-16. All data drawn from the upstream `main` branch at https://github.com/Yeachan-Heo/oh-my-claudecode (package version 4.11.6 per `.claude-plugin/marketplace.json` and `package.json`). Complementary npm package is published as `oh-my-claude-sisyphus`. No local copilot-omni code was consulted for this report.

---

## 1. Project identity & positioning

- **Repo:** https://github.com/Yeachan-Heo/oh-my-claudecode
- **Name / branding:** "oh-my-claudecode" (OMC). npm alias: `oh-my-claude-sisyphus`. CLI binaries: `oh-my-claudecode`, `omc`, `omc-cli`.
- **Tagline (README):** *"Don't learn Claude Code. Just use OMC."*
- **Self-description (`.claude-plugin/marketplace.json`):** "Claude Code native multi-agent orchestration — intelligent model routing, 28 agents, 32 skills." (Note: the actual on-disk `agents/` count is 19 Markdown files plus product-lane variants referenced in AGENTS.md such as `dependency-expert`, `api-reviewer`, `performance-reviewer`, `product-manager`, etc., so the "28 agents" figure counts tier variants and product-lane roles, not files.)
- **Target harness:** Claude Code first (via Anthropic plugin marketplace). Secondary terminal UX through `omc` CLI.
- **License:** MIT. Author: Yeachan Heo (hurrc04@gmail.com).
- **Version:** 4.11.6 (synchronized across `package.json`, `marketplace.json`, `plugin.json`).
- **Install flow:**
  - Primary: `/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode` → `/plugin install oh-my-claudecode` → `/setup`.
  - Alt: `npm i -g oh-my-claude-sisyphus@latest && omc setup`.
- **Positioning highlights:** multi-agent orchestration with intelligent model routing (haiku/sonnet/opus), zero-config natural language entrypoints, persistent execution with verify/fix loops, HUD statusline, skill extraction, multi-provider (Claude/Codex/Gemini) tri-model orchestration, rate-limit auto-resume.

---

## 2. Repository layout

Top-level (from `GET /contents/`):

| Path | Purpose |
|------|---------|
| `.claude-plugin/` | Claude Code plugin manifest (`plugin.json`, `marketplace.json`) |
| `.clawhip/` | Additional plugin/config staging |
| `.codex` | Codex-specific config marker |
| `.mcp.json` | MCP server registration (single server `t` pointing at `bridge/mcp-server.cjs`) |
| `.github/` | CI and PR workflows |
| `agents/` | 19 agent Markdown definitions |
| `skills/` | 37 bundled skill subdirectories, each with `SKILL.md` |
| `hooks/` | Single `hooks.json` registering ~20 hook scripts across 10 events |
| `scripts/` | Node.js hook runtimes, build scripts, setup utilities (50+ files plus `lib/`, `qa-tests/`) |
| `bridge/` | MCP server, team bridge, runtime CLI, Python bridge (`gyoshu_bridge.py`), `mcp-server.cjs` bundle |
| `src/` | TypeScript source: agents, autoresearch, cli, commands, config, features, hooks, hud, installer, interop, lib, mcp, notifications, openclaw, planning, platform, providers, ralphthon, shared, skills, team, tools, types, utils, verification, __tests__ (27 subdirs) |
| `dist/` | Compiled output consumed by bundled scripts |
| `missions/` | Pre-defined task templates (autoresearch missions) |
| `templates/` | Project and code templates |
| `examples/` | Example projects |
| `benchmark/`, `benchmarks/` | Performance tests |
| `research/` | Research notes (upstream’s own) |
| `seminar/` | Training materials |
| `shellmark/` | Session recording state |
| `assets/` | Brand resources |
| `tests/` | Integration fixtures |
| `AGENTS.md`, `CLAUDE.md` | Master agent / user instruction files |
| `README.md` + 11 translated variants | Primary docs (de/es/fr/it/ja/ko/pt/ru/tr/vi/zh) |
| `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` | Standard project docs |
| `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.js`, `vitest.config.ts`, `typos.toml` | Tooling |

`.claude-plugin/plugin.json` (507 bytes) and `marketplace.json` (944 bytes) are the canonical plugin manifests. `marketplace.json` lists one plugin (oh-my-claudecode v4.11.6, category "productivity", tags: multi-agent, orchestration, delegation, todo-management, ultrawork).

---

## 3. Skills catalog

Enumerated from `GET /contents/skills` (37 directories + `AGENTS.md`). Each directory contains a `SKILL.md` with YAML frontmatter (name, description, triggers). Trigger keywords are pulled from the `skill-injector.mjs` / `keyword-detector.mjs` hooks and from individual SKILL.md files.

### Tier-0 orchestration flagships

| Skill | Purpose | Trigger keywords | Dependencies / state files |
|-------|---------|------------------|----------------------------|
| **autopilot** | Five-phase end-to-end: expansion → planning → execution → QA → validation → cleanup. Skips redundant phases when consensus plans or interview specs already exist. | `autopilot`, `auto-pilot`, `build me an app`, `create me`, `autonomous`, `handle it all` | Reads `.omc/plans/ralplan-*.md`, `.omc/plans/consensus-*.md`, `.omc/specs/deep-interview-*.md`. Writes `.omc/autopilot-state.json`. Layers over `ralph` + `ultrawork`. Uses `architect`, `critic`, `security-reviewer`, `code-reviewer` in validation. |
| **ralph** | Self-referential PRD-driven persistence loop: keeps cycling until every user story in `prd.json` has `passes: true`. Fires parallel work, enforces reviewer sign-off, mandatory deslop pass (ai-slop-cleaner), regression check. | `ralph`, `don't stop` | PRD at `prd.json`; reviewer tiers `--critic=architect|critic|codex`; Stop hook (`persistent-mode.cjs`) keeps session alive via reinforcement count. |
| **ultrawork** | Stateless parallel execution engine. "Fire all independent agent calls simultaneously — never serialize independent work." Tier selection haiku/sonnet/opus, uses `run_in_background: true` for >30s ops. | `ultrawork`, `ulw`, `uw` | No persistence. Composable component that `ralph` and `autopilot` layer on top of. |
| **team** | Native Claude Code team orchestration. Five-stage pipeline `team-plan → team-prd → team-exec → team-verify → team-fix` (fix loop). Uses `TaskCreate`, `TaskUpdate`, `SendMessage`, `TeamCreate`, `TeamDelete`. Tasks live in `~/.claude/tasks/{team_name}/`. Handoffs at `.omc/handoffs/{stage-name}.md`. | Explicit-only via `/team N:agent-type` (keyword no longer auto-triggers) | Feature flags `OMC_RUNTIME_V2=1`, `OMC_TEAM_SCALING_ENABLED=1`. Graceful shutdown via `shutdown_request` + `shutdown_response` (15-30s). Watchdog: re-assigns tasks stuck >5–10 min. |
| **ralplan** | Consensus planning entrypoint. Gates vague ralph/autopilot/team requests. Runs Planner → Architect → Critic with RALPLAN-DR structured deliberation (Principles, Decision Drivers, Viable Options). Bypass via `force:` or `!` prefix. | `ralplan`, `/ralplan`, `consensus plan` | Writes `.omc/plans/*.md`. `state_write(mode="ralplan", active=true)`. Never `state_clear` before exec (30s cancel window disables stop-hook enforcement). Flags `--interactive`, `--deliberate`, `--architect codex`, `--critic codex`. |
| **deep-interview** | Socratic requirements gathering with mathematical ambiguity scoring. Refuses to proceed until ambiguity ≤ 0.2. Challenge agents (Contrarian r4+, Simplifier r6+, Ontologist r8+). Soft limit round 10, hard cap 20. | `deep-interview`, `ouroboros`, `ask me everything`, `don't assume` | Writes `.omc/specs/deep-interview-*.md`. State in `.omc/state/` (mode=deep-interview). Bridges to autopilot/ralph/team/omc-plan. |
| **deep-dive** | 2-stage pipeline: `/trace` (investigation) → `deep-interview` (requirements) with "3-point injection" (initial idea context, codebase context, question seeding from trace unknowns). | `deep dive`, `investigate deeply`, `trace and interview` | Uses `mode="deep-interview"` + `source="deep-dive"` discriminator; stores `trace_path`, `spec_path` for resume. |
| **ccg** | Claude-Codex-Gemini tri-model orchestration via `omc ask codex` + `omc ask gemini`, then Claude synthesizes. Explicit constraint: "Skill nesting (invoking a skill from within an active skill) is not supported in Claude Code." | `ccg`, `claude-codex-gemini` | Reads `.omc/artifacts/ask/`. Graceful fallback if a provider unavailable. |

### Quality / reviewer / QA

| Skill | Purpose | Triggers | Notes |
|-------|---------|----------|-------|
| **verify** | Four-tier verification ladder: existing tests → typecheck/build → targeted direct commands → manual steps. "It should work is not verification." | explicit | Outputs: what was tested, tools ran, outcomes, gaps. |
| **ai-slop-cleaner** | Regression-safe, deletion-first cleanup of AI-generated slop. Five smell categories (duplication, dead code, needless abstraction, boundary violation, missing test coverage). `--review` flag = reviewer-only mode. Runs as mandatory post-approval pass in ralph step 7.5. | `deslop`, `anti-slop`, cleanup phrases | Preserves behavior unless user asks for changes. |
| **ultraqa** | Autonomous QA cycle (max 5 iterations): run → diagnose via architect → fix via executor → repeat. Early termination after 3 identical failures. `--tests`, `--build`, `--lint`, `--typecheck`, `--custom`. `--interactive` = spawns qa-tester subagent. | explicit | `.omc/ultraqa-state.json`. |
| **trace** | Evidence-driven causal investigation with competing hypotheses, evidence for/against, critical unknown, discriminating probe. Default three lanes: code-path, config/env, measurement/assumption. | explicit | Uses `tracer` agent. |
| **debug** | Diagnose OMC session or repo state using logs, traces, state, focused reproduction. Outputs observed failure → root cause → evidence → smallest next step. | explicit | |
| **visual-verdict** | Structured visual QA verdict for screenshot-to-reference comparisons (JSON output). | explicit | |

### Planning / research / knowledge

| Skill | Purpose | Triggers | Notes |
|-------|---------|----------|-------|
| **plan** | `omc-plan` with four modes: interview, direct, consensus, review. Auto-detects specificity. Plans saved to `.omc/plans/` with testable criteria, file references, risk mitigations. | "plan this" | Quality bars: 80% claims cite file/line, 90% criteria testable. |
| **sciomc** | Parallel scientist-agent research orchestrator: decompose → execute → verify → synthesize. `AUTO:` prefix for autonomous. | explicit | `.omc/research/{session-id}/`. |
| **wiki** | Markdown knowledge base in `.omc/wiki/*.md` (Karpathy LLM Wiki model). No vector embeddings — keyword + tag. `[[page-name]]` wiki links. YAML frontmatter with category (architecture/decision/pattern/debugging/environment/session-log). `wiki_lint()` detects orphans / stale / broken refs. Auto-capture at session end. | `wiki` | MCP tools: `wiki_add`, `wiki_query`, `wiki_lint`, `wiki_ingest`, `wiki_delete`, `wiki_list`, `wiki_read`. Log: `.omc/wiki/log.md`. Index: `index.md`. |
| **remember** | Classify knowledge into project-memory, notepad-priority, notepad-working, or durable docs. | explicit | MCP tools: `notepad_write_priority`, `notepad_write_working`, `notepad_write_manual`, `project_memory_*`. |
| **learner** | "Level 7 self-improving" extraction of non-Googleable, codebase-specific insights into `.omc/skills/`. Rejects generic patterns. YAML frontmatter required. | explicit | |
| **skillify** | Convert ad-hoc successful workflows into reusable OMC skills. Writes to `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/omc-learned/<name>.md` or `.omc/skills/`. | explicit | |
| **skill** | Meta-skill CLI: `list`, `add`, `remove`, `edit`, `search`, `info`, `sync`, `setup`, `scan`. Three scopes: bundled / user (`~/.claude/skills/omc-learned/`) / project (`.omc/skills/`). | explicit | |
| **deepinit** | Generate hierarchical `AGENTS.md` documentation across a codebase, preserving manual annotations. | explicit | MCP tool `deepinit_manifest`. |
| **external-context** | Parallel document-specialist agents (up to 5) for external web/docs lookup. Facet decomposition 2-5 angles, URL citations required. | explicit — no keyword trigger | |
| **release** | Generic repo-aware release assistant. Caches rules in `.omc/RELEASE_RULE.md` (rewritten in v4.11.6). Detects version files, dist targets, changelog conventions. `--refresh` re-analyzes. | explicit | |

### Environment / infra / integrations

| Skill | Purpose | Triggers | Notes |
|-------|---------|----------|-------|
| **setup** | Unified setup entrypoint. Routes to wizard / doctor / mcp. | explicit | |
| **omc-setup** | Install/refresh OMC across plugin/npm/local-dev. `--local`, `--global`, `--force`. Resume via `setup-progress.sh`. Writes `~/.claude/.omc-config.json`. | explicit | Phases: install CLAUDE.md → env/HUD → integrations → welcome. |
| **omc-doctor** | Six diagnostic checks: plugin version, legacy hooks, legacy scripts, CLAUDE.md markers (`<!-- OMC:VERSION:X.X.X -->`), plugin cache, legacy content. Auto-fix option. Respects `CLAUDE_CONFIG_DIR`. | explicit | |
| **mcp-setup** | Configure popular MCP servers (Context7, Exa Web Search, Filesystem, GitHub, custom). Uses `claude mcp add`. | explicit | |
| **hud** | Statusline configuration. Presets: minimal / focused (default) / full. Stored in `~/.claude/settings.json` under `omcHud`. `agentsFormat`, `safeMode`, `contextLimitWarning`. Refresh ~300ms. | explicit | |
| **configure-notifications** | Telegram, Discord, Slack, webhooks, OpenClaw gateway, n8n. Wizard flow detects platform keyword. `~/.claude/.omc-config.json`. Requires per-session flags (`omc --telegram --discord`) or env vars. Template variables `{{sessionId}}`, `{{projectName}}`, `{{duration}}`. | explicit | |
| **omc-teams** | tmux-based CLI worker runtime (claude/codex/gemini). Each in tmux panes. Complement to native `/team`. Falls back to detached tmux if not in an active session. | explicit | |
| **ask** | Unified CLI advisor: `omc ask claude|codex|gemini "…"`. Artifacts in `.omc/artifacts/ask/`. Forbids raw CLI assembly. | explicit | |
| **self-improve** | Evolutionary improvement engine with tournament selection. Persistent `improve/{goal_slug}` branch. Research → Planning (N planners) → Review (architect + critic) → Execution (parallel worktrees) → Tournament → Recording → Cleanup. Stop conditions: user stop / target reached / plateau / max iter / circuit breaker. | explicit | `.omc/self-improve/`. Step 0 always runs worktree cleanup (idempotent, crash-safe). |
| **cancel** | Canonical exit for every mode (autopilot, ralph, ultrawork, ultraqa, swarm, ultrapilot, pipeline, team). Two-pass graceful team shutdown (15s window). `--force`, `--all`. Autopilot state preserved for resume; others cleared. | `cancelomc`, `stopomc` | Bash fallback removes files if state tools unavailable. |
| **project-session-manager** | Worktree-first dev environment. `review <ref>`, `fix <ref>`, `feature <proj> <name>`. Worktrees in `~/.psm/worktrees/`. Optional tmux sessions named `psm:project:type-id`. Lightweight `teleport` variant without tmux. | explicit | |
| **writer-memory** | Korean-centric creative writing memory: characters, world, relationships, scenes, themes. Data in `.writer-memory/memory.json`. Korean+English query. | explicit | Off-pattern vs. software-dev flow. |
| **omc-reference** | Auto-loaded reference bundle: agent catalog, tools, pipeline routing, commit protocol, skills registry. | auto when delegating / committing | |

---

## 4. Agent catalog

`agents/` holds 19 files, each with YAML frontmatter (`name`, `description`, `model`, `level`, optional `disallowedTools`). Models observed on `main`: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`. Tier aliases used in some places (`sonnet`/`opus`/`haiku`) are explicitly warned against for Bedrock/Vertex compatibility (see pre-tool-enforcer logic and recent PRs).

| Agent | Model | Level | Tools / restrictions | Role |
|-------|-------|-------|----------------------|------|
| **analyst** | opus-4-6 | 3 | disallow Write/Edit | Pre-planning consultant converting scope into testable acceptance criteria. Read-only. |
| **architect** | opus-4-6 | 3 | disallow Write/Edit | Strategic architecture & debugging advisor (read-only). Diagnoses, recommends, hands off. |
| **planner** | opus-4-6 | 4 | — | Interview-first strategic planner. Writes `.omc/plans/*.md` (3–6 step plans, acceptance criteria). |
| **executor** | sonnet-4-6 | 2 | — | Implementation agent. Small, correct changes. Enforces diagnostics/build/tests before completion. |
| **explore** | haiku-4-5 | 3 | disallow Write/Edit | Parallel codebase search via LSP/ast_grep/Grep/Glob. Always returns absolute paths with context. |
| **verifier** | sonnet-4-6 | 3 | — | Evidence-based completion checks; designs verification strategy; regression risk. |
| **debugger** | sonnet-4-6 | — | — | Root-cause analysis, regression isolation, build fixes. Escalates after 3 failed hypotheses. |
| **tracer** | sonnet-4-6 | 3 | — | Evidence-driven causal tracing with competing hypotheses and discriminating probe. |
| **critic** | opus-4-6 | 3 | disallow Write/Edit | Final quality gate; structured multi-perspective review. Rejects flawed work. |
| **code-reviewer** | opus-4-6 | 3 | disallow Write/Edit | Severity-rated code review; SOLID, logic defects, style, performance. |
| **security-reviewer** | opus-4-6 | 3 | disallow Write/Edit | OWASP Top 10, secrets, unsafe patterns. Prioritized by severity/exploitability/blast radius. |
| **test-engineer** | sonnet-4-6 | — | — | TDD discipline — "no production code without a failing test first". Testing pyramid 70/20/10. |
| **qa-tester** | sonnet-4-6 | 3 | — | Interactive CLI testing using tmux session orchestration. Cleanup/teardown emphasis. |
| **designer** | sonnet-4-6 | 2 | — | UI/UX designer-developer. Framework-idiomatic. Opinionated about typography, color, motion. |
| **writer** | haiku-4-5 | — | Read/Glob/Grep/Write/Edit/Bash | Technical documentation, tested examples, matches code reality. |
| **document-specialist** | sonnet-4-6 | 2 | disallow Write/Edit | External documentation & reference specialist. Requires URL/citation per claim. |
| **scientist** | sonnet-4-6 | 3 | python_repl + Read/Glob/Grep/Bash | Data analysis and research via `python_repl`. Reports to `.omc/scientist/reports/`, figures to `.omc/scientist/figures/`. |
| **git-master** | sonnet-4-6 | — | Bash/Read/Grep | Atomic commit splitting, style-matched messages, safe rebase (`--force-with-lease`). |
| **code-simplifier** | opus-4-6 | 3 | — | Clarity/consistency refactor without behavior change. Used by Stop hook opt-in. |

`AGENTS.md` also references agents beyond the 19 files (presumably variants or planned): `style-reviewer`, `api-reviewer`, `performance-reviewer`, `dependency-expert`, `quality-strategist`, `researcher`, `product-manager`, `ux-researcher`, `information-architect`, `product-analyst`, `vision`. These may be dynamically composed from tier flags or future additions — the marketplace line "28 agent variants" likely counts these.

---

## 5. Hooks & triggers

`hooks/hooks.json` registers the following. All scripts live in `scripts/` (Node.js `.mjs` / `.cjs`). Timeouts listed in seconds.

| Event | Script(s) | Timeout | Effect |
|-------|-----------|---------|--------|
| **UserPromptSubmit** | `keyword-detector.mjs` | 5 | Detects magic keywords (cancelomc/stopomc, ralph, autopilot, ultrawork, ccg, ralplan, deep-interview/ouroboros, tdd, code-review, security-review, ultrathink, deepsearch, deep-analyze, wiki, plus anti-slop patterns). Sanitizes input (strips XML/URLs/code blocks/file paths/markdown); does context analysis to avoid false positives ("explain autopilot" won't trigger). Conflict priority: cancel > ralph > autopilot > ultrawork > ccg > ralplan. Team worker guard blocks re-detection. Preferred action: inject `skills/{name}/SKILL.md` content as `additionalContext`; fallback to tool invocation `oh-my-claudecode:{name}`. |
| **UserPromptSubmit** | `skill-injector.mjs` | 3 | Trigger-based skill matching. Scans each SKILL.md YAML frontmatter, scores +10 per trigger match, sorts desc, caps at `MAX_SKILLS_PER_SESSION=5`. Session dedup via bridge cache or `.omc/state/skill-sessions-fallback.json`. Project skills prioritized over user skills. |
| **SessionStart** (universal) | `session-start.mjs` | 5 | Restores Ultrawork/Ralph state, pending todos, project memory; injects version-drift warnings, npm update nudges (24h cache), HUD setup status, notepad priority block. Cleans stale plugin cache to symlinks. Reads `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_ROOT`. |
| **SessionStart** (universal) | `project-memory-session.mjs` | 5 | Calls `registerProjectMemoryContext(sessionId, cwd)` from dist. Detects tech stack, build commands, custom notes. |
| **SessionStart** (universal) | `wiki-session-start.mjs` | 5 | Loads wiki context. |
| **SessionStart** ("init" matcher) | `setup-init.mjs` | 30 | First-run setup initialization. |
| **SessionStart** ("maintenance" matcher) | `setup-maintenance.mjs` | 60 | Periodic maintenance refresh. |
| **PreToolUse** | `pre-tool-enforcer.mjs` | 3 | Enforces: valid model routing for `Task/Agent` (denies tier aliases without `OMC_SUBAGENT_MODEL` in Bedrock/Vertex with `forceInherit`, bare Anthropic IDs, `[1m]` context suffix). Team mode gate: disallows `Task` without `team_name` when active team exists. Validates session-id and agent name regexes. Writes skill active-state markers; injects reminders (todos, parallel execution, verification); records invocations to flow traces. |
| **PermissionRequest** (Bash) | `permission-handler.mjs` | 5 | Reads JSON stdin, delegates to `processPermissionRequest()` from dist. Gatekeeper for bash permissions. Safe default on failure: `continue: true, suppressOutput: true`. Recently hardened (PRs #2594 and several follow-ups) to narrow auto-approval to single-test runs + safe repo inspection, reject ripgrep sweeps that could bypass git worktree checks. |
| **PostToolUse** | `post-tool-verifier.mjs` | 3 | Detects bash failures, write perm errors, subagent completion, context threshold warnings. Appends bash history. Processes `<remember>` tags. Distinguishes legitimate non-zero exits (e.g., `gh pr checks` pending) from real failures. |
| **PostToolUse** | `project-memory-posttool.mjs` | 3 | Auto-updates project memory after significant tool ops. |
| **PostToolUse** | `post-tool-rules-injector.mjs` | 3 | Injects applicable rule files from `.claude/rules`, `.github/instructions`, `.cursor/rules`, `~/.claude/rules`. Content-hash + realpath dedup. Worktree-safe root derivation from accessed file path. |
| **PostToolUseFailure** | `post-tool-use-failure.mjs` | 3 | Logs to `.omc/state/last-tool-error.json`. 60s retry window, resets outside. Pivot hint after 5 failures. Suppresses noise for optional startup tools. Path-traversal guard. |
| **SubagentStart** | `subagent-tracker.mjs start` | 3 | Invokes `processSubagentStart` from dist. Adds to active-subagents registry. |
| **SubagentStop** | `subagent-tracker.mjs stop` | 5 | `processSubagentStop`. |
| **SubagentStop** | `verify-deliverables.mjs` | 5 | Advisory-only deliverable checks (file existence, ≥200-byte content, required regex patterns, required sections). Loaded from `.omc/deliverables.json` or OMC defaults, filtered by current team stage. Never blocks. |
| **PreCompact** | `pre-compact.mjs` | 10 | Pre-compaction context preservation. |
| **PreCompact** | `project-memory-precompact.mjs` | 5 | Flush project memory before compaction. |
| **PreCompact** | `wiki-pre-compact.mjs` | 3 | Flush wiki before compaction. |
| **Stop** | `context-guard-stop.mjs` | 5 | Reads transcript tail for `context_window` / `input_tokens`. Blocks at ≥75%; bypasses at ≥95% to avoid deadlock. Max 2 blocks per transcript. Never blocks context-limit or user-aborted stops. |
| **Stop** | `persistent-mode.cjs` | 10 | Reads mode state files (`ralph-state.json`, `autopilot-state.json`, team/pipeline/swarm, ultrawork/ultraqa, skill-active-state) from `~/.omc/state/`. Returns `decision: "block"` with reinforcement count increment. Circuit breaker: "20 reinforcements max" for autopilot. Session-id isolation; 2-hour staleness window. Respects cancel signal and context-limit. Sends fire-and-forget notifications. |
| **Stop** | `code-simplifier.mjs` | 5 | Opt-in (`~/.omc/config.json`, `codeSimplifier.enabled`). `git diff HEAD --name-only` → filter by extension set (TS/JS/PY/GO/RS) → cap at 10 → block stop with Task message to `code-simplifier` agent. Marker file prevents re-triggering. |
| **SessionEnd** | `session-end.mjs` | 30 | Summary, state flush. |
| **SessionEnd** | `wiki-session-end.mjs` | 30 | Optional auto-capture of session to wiki. |

---

## 6. MCP server(s) and tools exposed

`.mcp.json`:

```json
{
  "mcpServers": {
    "t": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/bridge/mcp-server.cjs"]
    }
  }
}
```

A single stdio MCP server named `t`, implemented in `bridge/mcp-server.cjs` (bundled/minified with AJV). Tool prefix in Claude Code becomes `mcp__plugin_oh-my-claudecode_t__<tool>`.

Tool inventory (observed in this session's active tool surface):

**Notepad (working/priority/manual memory):**
- `notepad_read` — read notepad
- `notepad_stats` — size/section statistics
- `notepad_prune` — trim stale entries
- `notepad_write_priority` — persistent priority context (carries across turns)
- `notepad_write_working` — working/scratch notes
- `notepad_write_manual` — user-directed notes

**Project memory:**
- `project_memory_read` — read `.omc/project-memory.json`
- `project_memory_write` — replace whole memory
- `project_memory_add_note` — append note
- `project_memory_add_directive` — append directive

**Shared memory (cross-agent blackboard):**
- `shared_memory_read`, `shared_memory_write`, `shared_memory_list`, `shared_memory_delete`, `shared_memory_cleanup`

**State machine (mode lifecycle for ralph/autopilot/team/etc.):**
- `state_write`, `state_read`, `state_clear`, `state_get_status`, `state_list_active`

**Wiki:**
- `wiki_add`, `wiki_read`, `wiki_list`, `wiki_query`, `wiki_lint`, `wiki_ingest`, `wiki_delete`

**Session search / trace (orchestration observability):**
- `session_search` — search historical sessions
- `trace_summary` — summarize a flow trace
- `trace_timeline` — timeline view of a flow trace

**Code intelligence (LSP + ast-grep + Python):**
- `lsp_servers`, `lsp_hover`, `lsp_goto_definition`, `lsp_find_references`, `lsp_document_symbols`, `lsp_workspace_symbols`, `lsp_diagnostics`, `lsp_diagnostics_directory`
- `lsp_code_actions`, `lsp_code_action_resolve`
- `lsp_prepare_rename`, `lsp_rename`
- `ast_grep_search`, `ast_grep_replace`
- `python_repl`

**Skills / config:**
- `list_omc_skills`, `load_omc_skills_global`, `load_omc_skills_local`
- `deepinit_manifest`

That is ~40 MCP tools under one server. Tools are highly coupled to OMC’s internal state (notepad, project memory, wiki, state-machine), meaning skills can directly read/write persistent context without touching the filesystem from the agent.

---

## 7. Orchestration patterns

### autopilot (end-to-end)

Five phases, each bypassable when upstream artifacts already exist:

0. **Expansion** — user idea → detailed spec; skipped if consensus plan or interview spec found; redirects vague requests to `/deep-interview`.
1. **Planning** — `architect` + `critic`; bypassed if ralplan consensus plan detected.
2. **Execution** — `ralph` + `ultrawork` in parallel; tiered haiku/sonnet/opus routing.
3. **QA** — up to 5 rounds; halts on 3 identical failures.
4. **Validation** — parallel `architect` (functionality), `security-reviewer`, `code-reviewer`. All must approve.
5. **Cleanup** — removes `.omc/autopilot-state.json`, retains specs/plans.

State: `.omc/autopilot-state.json`. Resumable via `persistent-mode.cjs` Stop hook (20 reinforcements max).

### ralph (persistence loop)

Story-centric PRD loop. Key mechanics:
- Scaffold `prd.json` generated if missing; loop forces a **refinement gate** before work starts (concrete verifiable acceptance criteria required, not generic "Implementation is complete").
- Per-story verification with fresh evidence (test runs, build, lint).
- Reviewer tiers: STANDARD (Sonnet) for small changes <100 lines/<5 files; THOROUGH (Opus) for large/security; selectable `--critic=architect|critic|codex`.
- Mandatory Step 7.5 deslop pass (ai-slop-cleaner) unless `--no-deslop`.
- Step 7 approval is **not** a reporting moment — deslop + regression tests continue in the same turn.
- Anti-patterns explicitly called out: sequential independent tasks, reducing scope to pass tests.
- Completion checklist triggers `/oh-my-claudecode:cancel` for clean exit.

Stop hook reinforcement prevents Claude from ending its turn while `ralph-state.json.active=true`.

### ultrawork

Stateless parallel fan-out. Composable primitive — ralph and autopilot layer on top. Enforces "fire all independent calls simultaneously, never serialize." `run_in_background: true` for >30s ops. Lightweight verification only (build/tests/no new errors).

### team

Native Claude Code team orchestration. Five-stage pipeline with per-stage routing:

| Stage | Primary agents | Logic |
|-------|----------------|-------|
| plan | `explore`, `planner` | Add `analyst`/`architect` for complex systems |
| prd | `analyst` | Add `critic` to challenge scope |
| exec | `executor` (sonnet) | Match to subtask type: `designer` for UI, `debugger` for builds, `writer` for docs |
| verify | `verifier` (sonnet) | Add `security-reviewer` for auth changes, `code-reviewer` for >20 files |
| fix | `executor`/`debugger` | Debugger for type/build regressions; executor (opus) for complex multi-file |

User's `N:agent-type` param overrides only the exec stage. Handoffs at `.omc/handoffs/{stage-name}.md` (10-20 line summaries). Tasks in `~/.claude/tasks/{team_name}/`. Inter-agent communication via `SendMessage`. Watchdog reassigns stuck tasks after 5–10 min. Graceful shutdown via `shutdown_request`/`shutdown_response` (15–30s) then `TeamDelete`. Lead-crash recovery via `state_read(mode="team")`. Feature flags: `OMC_RUNTIME_V2=1` (event-driven), `OMC_TEAM_SCALING_ENABLED=1` (mid-session worker scaling).

Workers run a strict preamble: claim → work → complete → report → repeat. "Teammates never spawn sub-agents, never run team commands, never use tmux orchestration."

### ralplan (consensus planning)

Front-door gate for vague ralph/autopilot/team requests. Auto-passes if request contains concrete signals (file path, issue/PR #, symbol casing, test runner, numbered steps, acceptance criteria, error reference, code block). Bypass: `force: …`, `! …`. Flow: Planner → (optional user feedback) → Architect → Critic → re-review up to 5× → apply improvements → final approval → execution via team or ralph. `--deliberate` adds pre-mortem and expanded test planning.

State discipline: `state_write(mode="ralplan", active=true)` on entry, `active=false` on handoff, `state_clear` only on terminal exit — never before launching execution (30s cancel window disables stop-hook enforcement otherwise).

### deep-dive (composite)

`trace` (investigation) → `deep-interview` (requirements). The "3-point injection" enriches the interview with trace's most likely explanation, trace's codebase synthesis (skip redundant exploration), and per-lane critical unknowns as lead questions.

### self-improve (evolutionary)

Tournament-based autonomous improvement engine. Persistent improvement branch `improve/{goal_slug}`. Per-iteration: research → N-planner fan-out → architect + critic review (enforcing harness rules H001 single hypothesis / H002 diversity / H003 no repetition streaks) → parallel worktree execution + benchmarks → tournament merge of best non-regressing candidate → recording → cleanup → stop evaluation. Step 0 (worktree cleanup) runs every iteration as idempotent crash-safe preamble. State in `.omc/self-improve/`.

---

## 8. Intent routing / front-door logic

Two layers:

1. **Keyword detection (`keyword-detector.mjs`, UserPromptSubmit, 5s)**  
   Lowercases prompt, sanitizes (strips XML/URLs/code blocks/file paths/markdown), analyzes context to distinguish activation from information ("explain autopilot" ≠ trigger). Matches against a fixed keyword-to-skill map (see §3). Conflict priority: `cancel > ralph > autopilot > ultrawork > ccg > ralplan > others`. Team is explicit-only (`/team`). Writes `.omc/state/` markers for modes that persist. Prefers injecting `skills/{name}/SKILL.md` content directly; falls back to `oh-my-claudecode:{name}` tool invocation. Guards against keyword re-detection inside team workers (avoids spawn loops).

2. **Trigger-scored skill injector (`skill-injector.mjs`, UserPromptSubmit, 3s)**  
   Reads every SKILL.md frontmatter's `triggers` array. +10 points per match. Sorts desc, caps at `MAX_SKILLS_PER_SESSION=5`. Session dedup via either compiled bridge (in-memory) or file fallback `.omc/state/skill-sessions-fallback.json`. Project-level skills processed before user-level → higher priority.

3. **ralplan gate** runs on top: if keyword routing would land in ralph/autopilot/team with insufficient concreteness, it redirects into consensus planning first. Explicit `/ralplan` invocation no longer stalls before planning after v4.11.6 fix (commit `09ffccc5`, 2026-04-14).

4. **pre-tool-enforcer** at PreToolUse further gates `Task`/`Agent` spawning (model routing, team_name presence, name validation) before the agent actually runs.

---

## 9. State management

Primary state root: `.omc/` at project root. Global state: `~/.omc/` and `~/.claude/`.

| Path | Contents |
|------|----------|
| `.omc/state/` | Mode state files: `ralph-state.json`, `autopilot-state.json`, `ultrawork-*`, `ultraqa-state.json`, `team-*`, `pipeline-*`, `swarm-*`, `skill-active-state.json`, `last-tool-error.json`, `skill-sessions-fallback.json`, cancel markers |
| `.omc/state/sessions/{sessionId}/` | Per-session isolated state (referenced by `~/.claude/CLAUDE.md` in reference material) |
| `.omc/plans/` | `ralplan-*.md`, `consensus-*.md`, generic plans |
| `.omc/specs/` | `deep-interview-*.md` crystallized specs |
| `.omc/handoffs/` | Team stage handoffs (10–20 lines each) |
| `.omc/artifacts/ask/` | `omc ask` responses as `<provider>-<slug>-<timestamp>.md` |
| `.omc/scientist/reports/`, `.omc/scientist/figures/` | Scientist agent outputs |
| `.omc/research/{session-id}/` | sciomc research sessions |
| `.omc/self-improve/` | Self-improve configs, iteration history, research briefs, merge reports, progress charts |
| `.omc/wiki/*.md` + `index.md` + `log.md` | Wiki pages with YAML frontmatter |
| `.omc/notepad.md` | Priority + working notepad (used heavily by Stop/Session hooks) |
| `.omc/project-memory.json` | Project-level durable memory (tech stack, build commands, directives) |
| `.omc/logs/` | Hook logs (referenced in base CLAUDE.md) |
| `.omc/deliverables.json` | Per-project overrides for `verify-deliverables` hook |
| `.omc/RELEASE_RULE.md` | Release skill's derived rules cache |
| `.omc/ultraqa-state.json`, `.omc/autopilot-state.json` | Mode state (some also mirrored in `.omc/state/`) |
| `~/.omc/config.json` | `codeSimplifier.enabled` and other opt-ins |
| `~/.claude/.omc-config.json` | Setup completion + notification integration config |
| `~/.claude/skills/omc-learned/` | User-scope learned skills (from skillify/learner) |
| `~/.claude/tasks/{team_name}/` | Native team TaskList JSON |
| `.omc/skills/` | Project-scope skills |
| `.writer-memory/memory.json` | Writer-memory skill |
| `~/.psm/worktrees/<project>/<type>-<id>/` | PSM worktrees |
| `~/.psm/projects.json`, `~/.psm/sessions.json` | PSM metadata |

Session isolation:
- `persistent-mode.cjs` keys by `session_id`; only blocks stop when state's session matches.
- 2-hour staleness window prevents new sessions from inheriting old ralph/autopilot loops.
- Reinforcement counters per-mode with circuit breakers (autopilot 20 reinforcements).

State mutation access is centralized via MCP tools (`state_write`, `state_read`, `state_clear`, `state_get_status`, `state_list_active`) plus direct file access from hook scripts.

---

## 10. Configuration & kill-switches

**Global config files:**
- `~/.claude/settings.json` — HUD settings (`omcHud`), hook registrations when installed globally.
- `~/.claude/.omc-config.json` — setup completion marker, notification config.
- `~/.omc/config.json` — opt-in features like `codeSimplifier.enabled`.
- `.omc-config.json` — per-project overrides including wiki auto-capture toggles.

**Environment variables (observed):**
- `CLAUDE_CONFIG_DIR` — overrides default `~/.claude` path; honored by all doctor/setup paths.
- `CLAUDE_PLUGIN_ROOT` — plugin install path for module loading and notifications.
- `OMC_SUBAGENT_MODEL` — explicit provider model ID; required by pre-tool-enforcer when tier aliases are used under Bedrock/Vertex with `forceInherit`.
- `OMC_RUNTIME_V2` — event-driven team monitoring instead of done.json polling.
- `OMC_TEAM_SCALING_ENABLED` — mid-session worker scaling.
- `OMC_TELEGRAM_BOT_TOKEN` etc. — auto-enable notifications without config file.
- `DISABLE_OMC`, `OMC_SKIP_HOOKS` — global kill-switches referenced in the fork's CLAUDE.md ("Kill switches"); upstream AGENTS.md mentions the same pattern. Exact env-var name conventions appear to be inherited from this upstream.

**Per-session CLI activation flags (notifications):**
`omc --telegram`, `omc --discord`, `omc --slack`, combinable. Without flags, notifications stay silent even if config file is populated.

**CLI-level flags seen across skills:** `--force`, `--all`, `--refresh`, `--interactive`, `--deliberate`, `--architect codex`, `--critic codex`, `--no-deslop`, `--review`, `--tests`, `--build`, `--lint`, `--typecheck`, `--custom`, `AUTO:` prefix, `force:` / `!` bypass prefixes for the ralplan gate.

---

## 11. Notable strengths

1. **Depth of hook coverage.** 10 hook events wired with >20 scripts — session lifecycle, tool gating, permission narrowing, context-budget guardrails, persistent-mode reinforcement, subagent tracking, deliverable verification, auto-simplification, and knowledge-graph hydration (project memory + wiki). Very little orchestration responsibility is left to the model to remember.
2. **MCP-centric state.** The `t` MCP server exposes ~40 tools for notepad/project-memory/wiki/state/shared-memory/trace/session-search/LSP/ast-grep/python. Skills can manipulate persistent structures directly instead of threading files through the model.
3. **Intent routing is layered.** Keyword detector + trigger-scored injector + ralplan gate + pre-tool-enforcer compose into a defense-in-depth front door. "Team is explicit-only" removed a class of spurious activations.
4. **State discipline is battle-tested.** Session-id isolation, 2-hour staleness windows, reinforcement circuit breakers, cancel signal respect, context-limit bypass to prevent deadlock — all signs of iterative production hardening.
5. **Model-routing correctness focus.** Pre-tool-enforcer explicitly rejects tier aliases and `[1m]` context suffixes on Bedrock/Vertex under `forceInherit`, and the recent PR stream (PR #2647) shows ongoing migration of agent frontmatter to tier-alias usage.
6. **Authoring/reviewer separation is structural.** Read-only agents (`architect`, `analyst`, `critic`, `code-reviewer`, `security-reviewer`, `explore`, `document-specialist`) literally have `disallowedTools: Write, Edit`. Verifier is a separate pass.
7. **Composable pattern hierarchy.** `ultrawork` is the bottom primitive, `ralph` wraps it with persistence, `team` wraps it with routing, `autopilot` wraps all three, `ralplan`/`deep-interview`/`deep-dive` front-door them. Clean layering.
8. **Quality gates are mandatory, not advisory.** Ralph's step 7.5 deslop pass, verifier's evidence-based completion, context-guard at 75%, ralplan's RALPLAN-DR structure, PRD refinement gate.
9. **Knowledge compounding.** The wiki (Karpathy-style keyword+tag, no embeddings), project-memory, notepad, and learner/skillify skills form a persistence stack that turns sessions into durable assets.
10. **Multi-provider orchestration built in.** `omc ask`, `ccg`, `omc-teams` wire Codex and Gemini alongside Claude, and `omc team` can route to external CLI workers with lifecycle management.
11. **Active, rapid release cadence.** v4.11.6 release landed April 13 with 50 merged PRs; no open issues as of April 16; hardening work on Ralph approval spoofing and permission trust boundaries was resolved same day.
12. **Diagnostic surface.** `omc-doctor` with six checks + auto-fix, `setup-progress.sh` resume, `trace_summary`/`trace_timeline` MCP tools, `session_search` — reproducibility and debuggability are first-class.

---

## 12. Notable weaknesses / rough edges / known bugs

1. **Single bundled MCP server.** `bridge/mcp-server.cjs` is a minified AJV-heavy bundle — hard to audit or fork. No source-of-truth TypeScript for the MCP tool schemas is published in an obvious place (lives in `src/mcp/` but surfaces are coupled through the bundle).
2. **Documented agent count is aspirational.** `marketplace.json` advertises "28 agent variants" but only 19 are on disk; the rest are referenced by `AGENTS.md` without dedicated files. Easy to mislead new contributors.
3. **Some skills have stubs.** `setup/SKILL.md` contains `{{ARGUMENTS}}` placeholder indicating a templated slash-command skill; the rendered version isn't in the raw file, which makes it hard to read without the harness.
4. **Ralph safety had recent exploits.** The April 13 commit burst (`f6507966`, `e122fcf0`, `5481044d`, `bdf56347`, `3213d01a`) closes approval spoofing, injected-prompt self-approval, stale architect approvals, and non-bypassable PRD gate. The pattern of same-day hotfix commits across multiple gates suggests earlier versions of Ralph were vulnerable to self-approval or gate bypass.
5. **Permission handler previously over-approved.** PR #2594 and follow-ups narrowed auto-approval for "safe repo inspection" after earlier reports that ripgrep sweeps or temp-dir approvals bypassed git-worktree checks. Current state looks solid but the PR cluster indicates a previously loose trust boundary.
6. **HUD can contend with git.** Merged PR #2650 fixes HUD git polling index-lock contention — implies prior HUD runs blocked commits or rebases under heavy polling.
7. **State sprawl.** ".omc/" has many sibling top-level files (autopilot-state.json, ultraqa-state.json) alongside `.omc/state/` — the partition isn't fully consistent. Some writers go straight to `.omc/…-state.json`, others go through MCP `state_write`. Different lifecycle expectations.
8. **Stop hook reinforcement can feel adversarial.** `persistent-mode.cjs` blocking stops 20 times is by design but depends on accurate `session_id` mapping and 2-hour staleness. If a new session inherits an older session id (or a worktree's transcript path), phantom loops can occur — hence the worktree-resolution fixes in hook scripts.
9. **`code-simplifier` Stop hook is intrusive when enabled.** It runs on every stop with modified files, delegating to an Opus agent, which is expensive. Correctly opt-in by default, but teams enabling it may not realize per-stop cost.
10. **Skill nesting not supported.** `ccg/SKILL.md` explicitly says so. This is a Claude Code constraint, but it leaks into skill design: composite workflows have to use CLI bridges (`omc ask`) instead of `Skill()` calls.
11. **Bedrock/Vertex compatibility is perennial.** Recent PRs (#2647 "use tier aliases in agent frontmatter for Bedrock/Vertex compat") continue to patch routing. Agent frontmatter still contains full IDs like `claude-opus-4-6` in some places and tier aliases in others — inconsistency.
12. **Deep-interview threshold drift.** PR #2646 fixes "initial threshold cache drift" — suggesting the ambiguity-score gating was subject to cache staleness across sessions.
13. **No visible issue tracker.** GitHub Issues is empty (zero open, zero listed closed at the surface explored). Triage happens through PRs. That makes it harder to understand external bug reports or feature requests from the community.
14. **Terminology overlap is confusing.** `team` (native), `omc-teams` (tmux), `swarm` (legacy, referenced in cancel skill), `pipeline` (also legacy). Multiple "team-like" modes with subtle differences.
15. **`mcp-server.cjs` bundle swallows tool names.** When auditing, only tool names visible to a live session are discoverable — there is no separate manifest listing the MCP tool schemas.
16. **Writer-memory is off-domain.** Korean creative-writing memory embedded in a developer toolchain plugin. Genuinely useful for some users but stretches the framework's scope.

---

## 13. Recent direction (last 30–60 days of commits)

From `GET /repos/Yeachan-Heo/oh-my-claudecode/commits?per_page=50` and closed PR list:

**v4.11.6 release (2026-04-13, commit `287565314`)** — 50 merged PRs, 4 features, 30 fixes, 14 other. Highlights:
- MiniMax coding plan usage provider integration.
- HUD extra usage spend data; provider-specific usage cache splitting.
- Release skill rewritten as generic repo-aware assistant.
- Suppression of stale tmux pane alerts / noise.
- Wiki hook fixes to wrap `additionalContext` in `hookSpecificOutput`.
- Concurrent settings preservation during install.
- Duplicate hook firing fix when plugin and standalone modes coexist.
- Context bloat reduction by eliminating repeated rule/skill injection.
- stdin closure on provider spawns to prevent hanging in piped environments.
- Cleanup scoping to managed directories only.
- tmux keyword-alert hardening against review/payload noise.

**Ralph hardening blitz (2026-04-13, same-day cluster):**
- `3213d01a` Make Ralph enforce real PRD and story review gates
- `bdf56347` Make Ralph startup PRD gating non-bypassable
- `5481044d` Prevent stale architect approvals from advancing Ralph stories
- `e122fcf0` Prevent Ralph from approving its own injected prompt text
- `f6507966` Close Ralph approval spoofing in reviewer-gated progression
- `74edf7c2` Merge Ralph PRD architect gate enforcement

**Permission handler hardening (2026-04-13):**
- `f9fab905` Merge PR #2594: Reduce approval stalls for safe repo inspection
- `e2e1ebeb` Prevent runtime parity guard from auto-approving ripgrep sweeps
- `91d2cc72` Restore mergeability for runtime parity guard follow-up
- `de71458d` Guard shipped permission-handler parity at runtime entrypoint
- `a3396b5f` Ship narrowed permission trust boundary in runtime hook
- `f5a56d07` Prevent temp-dir approvals from bypassing git worktree checks
- `0e2d49ba` / `f7f86297` Keep approval/camelCase tests aligned
- `b564709e` Reduce approval stalls for safe repo inspection and single-test runs

**PR review / testing infra:**
- PR #2600 Keep PR review verification focused by default
- PR #2598 Reduce false-severe PR review noise in clean worktrees

**Operational fixes:**
- PR #2590 Suppress stale tmux pane alert replays
- PR #2588 Wrap wiki hook additionalContext in hookSpecificOutput
- PR #2650 Avoid HUD git polling index lock contention
- PR #2647 Use tier aliases in agent frontmatter for Bedrock/Vertex compat
- PR #2646 Fix deep-interview initial threshold cache drift
- PR #2639 Support z.ai weekly token limit on pro+ tiers
- PR #2635 CI upgrade test to catch warnings/errors

**Most recent commit (2026-04-14, `09ffccc5`):** Fix explicit /ralplan startup stalling before planning. First post-release hotfix — cosmetic startup bug in ralplan.

**Overall theme:** stabilization and security, not new features. Ralph approval model, permission trust boundary, Bedrock/Vertex routing, and HUD contention all got hard-fixes. The project is in mature "reliability over novelty" mode (1,611 total closed PRs, 0 open at research time).

---

## 14. Open questions / things worth testing

1. **MCP tool schemas.** Since `bridge/mcp-server.cjs` is bundled, clone and introspect the runtime server to dump each tool's JSONSchema. Verify shapes for `state_write`, `notepad_write_priority`, `wiki_query`, `trace_summary` in particular — these are the high-frequency ones.
2. **Ralph PRD refinement gate.** Run ralph on a trivially-scoped task and confirm the refinement gate blocks generic acceptance criteria. Test escape hatches and whether reviewer-gated progression still admits `critic`-approved plans when `architect` is stale.
3. **ralplan bypass semantics.** Test `force:` vs `!` prefixes, and verify that ralplan no longer stalls at startup (commit `09ffccc5`). Check whether `deliberate` mode adds true pre-mortem or just extra planning rounds.
4. **Context-guard 75%/95% thresholds.** Artificially bloat transcript to trip thresholds; verify that 95%+ really bypasses the block (no deadlock) and that max-2-blocks-per-transcript caps apply.
5. **Session isolation.** Create two concurrent sessions with mode state; verify `persistent-mode.cjs` only blocks the matching session. Test 2-hour staleness by backdating state files.
6. **Permission-handler trust boundary.** Fuzz with ripgrep sweeps from `/tmp`, symlinked worktrees, and bash command injection attempts to validate the narrowed trust model. This area had multiple same-day patches — high-regression risk.
7. **Team watchdog + shutdown.** Spawn a 3-worker team, kill one mid-task, verify watchdog re-assigns after 5–10 min; then cancel and verify graceful shutdown completes in 15–30s or falls back to force.
8. **Skill injector dedup.** Send the same trigger multiple times in one session and confirm the skill isn't re-injected. Then rotate sessions and ensure `.omc/state/skill-sessions-fallback.json` either carries correctly or is flushed as expected.
9. **pre-tool-enforcer on Bedrock.** With `forceInherit=true` and only tier aliases in agent frontmatter, confirm the enforcer rejects spawning. Then set `OMC_SUBAGENT_MODEL=…` and confirm allow.
10. **Autopilot resumability.** Start autopilot, cancel mid-Phase-2, restart — verify `.omc/autopilot-state.json` correctly resumes at Phase 2 with remaining stories intact (versus re-running expansion).
11. **Verify-deliverables severity.** Confirm that missing deliverables are advisory-only (never blocking) and that `.omc/deliverables.json` overrides default requirements.
12. **HUD vs git contention.** With PR #2650 merged, stress-test by running heavy git ops while HUD is active. Check that polling backs off.
13. **Wiki auto-capture boundary.** Enable auto-capture in `.omc-config.json`, verify what gets written and whether YAML frontmatter is reliably attached.
14. **Self-improve circuit breaker.** Intentionally regress a benchmark and verify the tournament rejects it; drive to the plateau / circuit-breaker stop condition.
15. **Notification flags.** Verify `omc` without any flags truly suppresses notifications even when config populated, vs env-var-only path that auto-activates.
16. **Documented vs shipped agent count.** Inventory `src/agents/` and `src/team/` to see whether tier-variant agents like `style-reviewer`, `api-reviewer`, `performance-reviewer` are code-backed or doc-only.
17. **Code-simplifier Stop cost.** With `codeSimplifier.enabled=true`, measure how many Opus delegations it triggers per typical day of edits — whether the "10-file cap" is enough.
18. **Cross-skill state collisions.** Start `deep-dive` (which uses `mode="deep-interview"` with `source="deep-dive"`) and simultaneously run `/deep-interview`; verify the discriminator prevents collision.
19. **Missing `setup/SKILL.md` arguments.** Establish whether the `{{ARGUMENTS}}` placeholder is a harness-rendered template or a stale stub that should be fixed.
20. **ralplan gate concreteness signals.** Test edge cases: does a single PR URL bypass? What about a multi-line quoted error trace without a file path? Signals listed in the skill are a regex-ish heuristic worth validating.

