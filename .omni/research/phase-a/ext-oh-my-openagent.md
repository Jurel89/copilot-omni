# oh-my-openagent (code-yeongyu) — Deep Research

> Research date: 2026-04-16
> Source repo: https://github.com/code-yeongyu/oh-my-openagent
> Default branch: `dev` (not `main` — all GitHub raw URLs must use `/dev/`)
> Homepage: https://ohmyopenagent.com/
> Latest release inspected: v3.17.3 (2026-04-15)
> Stars ~51.9k · Forks ~4.2k · 536 open issues · License SUL-1.0
> Primary language: TypeScript (~95.6%), ~1,600 source files, Bun runtime
> Renamed in v3.11.0 (2026-03-07). Was previously "oh-my-opencode" — the published npm package and CLI binary are still `oh-my-opencode`.

This report is based on direct reads of the upstream repo: `README.md`, `AGENTS.md`, `src/AGENTS.md`, `package.json`, `postinstall.mjs`, `src/index.ts`, `src/plugin-config.ts`, `src/plugin-interface.ts`, `src/create-hooks.ts`, `src/create-managers.ts`, `src/create-tools.ts`, `src/agents/builtin-agents.ts`, `src/hooks/index.ts`, `src/mcp/index.ts`, `src/openclaw/index.ts`, `.opencode/command/omomomo.md`, `.opencode/background-tasks.json`, `docs/guide/overview.md`, `docs/guide/orchestration.md`, `docs/guide/installation.md`, `docs/manifesto.md`, `docs/reference/features.md`, `docs/reference/configuration.md`, plus the open-issues and commit listings from the GitHub API.

---

## 1. Project identity & positioning

**Name & branding.** The repo is `code-yeongyu/oh-my-openagent`, marketed as **"omo" / "Oh My OpenAgent" / "OmO"** (previously "Oh My OpenCode"). The rename landed in **v3.11.0** (2026-03-07). Key identity points:

- GitHub description: *"omo; the best agent harness - previously oh-my-opencode"*
- README tagline (direct quote): *"Install OmO. Type `ultrawork`. Done."*
- Topics on GitHub: `ai, ai-agents, amp, anthropic, chatgpt, claude, claude-code, claude-skills, cursor, gemini, ide, openai, opencode, orchestration, tui, typescript`
- Self-positioning vs Claude Code (from README):
  > "Claude Code's a nice prison, but it's still a prison. We don't do lock-in here. We ride every model. Claude / Kimi / GLM for orchestration. GPT for reasoning. Minimax for speed. Gemini for creativity. … The future isn't picking one winner—it's orchestrating them all."
- README also claims: *"Anthropic blocked OpenCode because of us."*

**Not a Claude Code plugin.** Although it advertises *"Claude Code Compatible — your hooks, commands, skills, MCPs, and plugins all work here unchanged"*, it does **not** install into Claude Code. It is shipped and registered as an **OpenCode** plugin via the `@opencode-ai/plugin` and `@opencode-ai/sdk` packages, and the whole install flow targets the `opencode` binary (via `bunx oh-my-opencode install`). The Claude Code compatibility is an inbound loader: it reads `.mcp.json`, `.claude/skills/*/SKILL.md`, `.claude/rules/`, `.claude/commands/*.md`, etc., and folds them into OpenCode. There is no Claude Code plugin manifest in this repo.

**Commercial context.** The README also advertises "Sisyphus Labs" (https://sisyphuslabs.ai) — *"We're building a fully productized version of Sisyphus to define the future of frontier agents."* So OmO is simultaneously OSS-marketing surface and R&D testbed for a paid agent product.

**License.** SUL-1.0 ("Standard Use License") — NOT OSI-approved (GitHub reports license as "Other / NOASSERTION"). See `LICENSE.md`. This is materially different from MIT/Apache and has contributor-assignment implications (the repo has a CLA bot and tracks signatures in commit history).

## 2. Target agent runtime(s)

**Primary runtime: OpenCode (https://opencode.ai/).** Evidence:

- `package.json` dependencies: `@opencode-ai/plugin: ^1.4.0` and `@opencode-ai/sdk: ^1.4.0`.
- `postinstall.mjs` enforces `MIN_OPENCODE_VERSION = "1.4.0"` and runs `opencode --version` to warn on version drift.
- Install flow (`docs/guide/installation.md`, Step 1) checks `command -v opencode`.
- Verification step: `cat ~/.config/opencode/opencode.json  # Should contain "oh-my-openagent" in plugin array`.
- Plugin entry in `src/index.ts`: the default export is an `OhMyOpenCodePlugin: Plugin` whose returned object uses OpenCode-native hook names (`chat.params`, `chat.headers`, `chat.message`, `experimental.chat.messages.transform`, `experimental.chat.system.transform`, `config`, `event`, `tool.execute.before`, `tool.execute.after`, `experimental.session.compacting`, `command.execute.before`).
- Config directory: `~/.config/opencode/`. User config basenames: `oh-my-openagent.json[c]` (preferred), `oh-my-opencode.json[c]` (legacy, still recognized during transition).

**Secondary/adjacent runtimes referenced but NOT targeted:**

- Claude Code — only via *inbound* compatibility loaders (`src/features/claude-code-plugin-loader`, `claude-code-command-loader`, `claude-code-agent-loader`, `claude-code-mcp-loader`, `claude-code-session-state`). Claude Code prompts in the install README literally say "Install oh-my-opencode using this URL" — i.e. Claude Code is used as a conversational *installer* for OpenCode, not a target.
- AmpCode, Cursor, Codex CLI, ChatGPT: mentioned in the "For Humans" install section as acceptable *driver* LLM agents that can paste the install prompt, again not as target runtimes.
- `src/openclaw/` — an external integration subsystem (see §6) — dispatches OpenCode sessions via Discord/Telegram/webhook/command.

**Model provider abstraction.** OmO routes across Claude Opus 4.6 / Sonnet 4.6 / Haiku 4.5, GPT-5.4 / 5.4 Mini / 5.3-codex / 5-nano, Kimi K2.5 / k2p5, GLM 5 / Big Pickle (GLM 4.6), Gemini 3.1 Pro / 3 Flash, MiniMax M2.7 / M2.7-highspeed, Grok Code Fast 1. Providers supported by the installer: `anthropic`, `openai`, `google`, `github-copilot`, `opencode`, `opencode-go` (subscription), `opencode-zen` (`opencode/` models), `zai-coding-plan` (Z.ai GLM), `kimi-for-coding`, `moonshotai`, `moonshotai-cn`, `firmware`, `ollama-cloud`, `aihubmix`, `xai`, `venice`, `vercel-ai-gateway`.

## 3. Repository layout

From `gh api .../contents` at `dev` HEAD:

```
oh-my-openagent/
├── .github/                 CI/CD (ci.yml, publish.yml, publish-platform.yml,
│                            sisyphus-agent.yml, refresh-model-capabilities.yml,
│                            cla.yml, lint-workflows.yml)
├── .opencode/               Project-level OpenCode config
│   ├── background-tasks.json   Persisted list of bg agent sessions (sample data in repo)
│   ├── command/                Project-scope slash commands (4 .md files)
│   └── skills/                 Project-scope skills (github-triage, pre-publish-review,
│                               work-with-pr, work-with-pr-workspace)
├── .sisyphus/               AI agent workspace (rules/, plans/, tasks/, notepads/)
├── assets/                  (dir)
├── bin/                     oh-my-opencode.js + platform.js dispatch shim
├── docs/
│   ├── manifesto.md
│   ├── model-capabilities-maintenance.md
│   ├── guide/   installation.md, overview.md, orchestration.md, agent-model-matching.md
│   ├── reference/  cli.md, configuration.md, features.md
│   ├── examples/, legal/, superpowers/, troubleshooting/
├── packages/                11 platform-specific compiled-binary subpackages
│                            (darwin-arm64, darwin-x64[+baseline], linux-arm64[+musl],
│                             linux-x64[+baseline, +musl, +musl-baseline], windows-x64[+baseline])
├── script/                  build-binaries.ts, build-schema.ts,
│                            build-model-capabilities.ts, run-ci-tests.ts
├── signatures/              (presumably CLA / build signatures)
├── src/                     See below
├── tests/                   Integration tests (hashline/ moved from benchmarks/)
├── AGENTS.md                Root agent contract (~11 KB)
├── CLA.md, CONTRIBUTING.md, LICENSE.md (SUL-1.0)
├── README.md + README.ja.md + README.ko.md + README.ru.md + README.zh-cn.md
├── bun.lock, bunfig.toml, bun-test.d.ts, test-setup.ts, tsconfig.json
├── package.json             name="oh-my-opencode", v3.17.3, "type": "module"
└── postinstall.mjs          Version check + platform binary resolution
```

### `src/` layout (from `gh api contents`)

```
src/
├── index.ts                   Plugin entry, 156 lines — 5-step init
├── plugin-config.ts           JSONC parse → user/project merge → Zod v4 validate → migrate
├── plugin-interface.ts        Wires 10 OpenCode hook handlers
├── plugin-dispose.ts          Graceful shutdown
├── plugin-state.ts            Model-cache state
├── create-hooks.ts            3-tier composition (Core + Continuation + Skill)
├── create-managers.ts         TmuxSessionManager, BackgroundManager, SkillMcpManager, ConfigHandler
├── create-tools.ts            ToolRegistry composition
├── create-tools.ts, create-runtime-tmux-config.ts
├── AGENTS.md                  Per-dir agent context (self-documenting pattern)
├── agents/                    11 agents (see §5)
├── cli/                       CLI: install, run, doctor, mcp-oauth (Commander)
├── config/                    Zod v4 schema system (32 files)
├── features/                  19 feature modules (see §10)
├── generated/                 Build-time generated code
├── hooks/                     52+ lifecycle hooks across dedicated dirs (see §6)
├── mcp/                       3 built-in remote MCPs: websearch, context7, grep_app
├── openclaw/                  Bidirectional Discord/Telegram/webhook bridge
├── plugin/                    10 OpenCode hook handlers + tool-registry + ultrawork
├── plugin-handlers/           6-phase config loading pipeline
├── shared/                    170+ utility files, barrel-exported
├── testing/                   Test infra
└── tools/                     26 tools across 16 directories (see §4)
```

## 4. Skills / commands / prompt assets (full catalog)

### 4.1 Slash-commands (built-in, from `docs/reference/features.md`)

| Command | Purpose |
|---|---|
| `/init-deep` | Generate hierarchical `AGENTS.md` at every directory |
| `/ralph-loop` | Self-referential loop until `<promise>DONE</promise>` (max 100 iters default, configurable) |
| `/ulw-loop` | Same as ralph-loop but runs in `ultrawork` mode |
| `/cancel-ralph` | Cancel active Ralph loop |
| `/refactor` | LSP + AST-grep + architecture analysis + TDD verification |
| `/start-work` | Resume Prometheus plan → activate Atlas |
| `/stop-continuation` | Halts ralph loop, todo continuation, boulder state |
| `/handoff` | Emit a structured context summary for a new session |
| `/git-master` | Commit/rebase/archaeology workflow (skill-routed) |
| `/playwright` | Browser automation handoff |

Custom commands load from (in order): `.opencode/command/*.md`, `~/.config/opencode/command/*.md`, `.claude/commands/*.md`, `~/.config/opencode/commands/*.md`.

Project-scope commands in this repo (for maintainer workflows, `.opencode/command/`):

- `get-unpublished-changes.md` (4.1 KB)
- `omomomo.md` (1.2 KB — **easter egg**; tells agent to render ASCII marketing for OmO. Full content read verbatim.)
- `publish.md` (13.5 KB — release orchestration)
- `remove-deadcode.md` (7.3 KB)

### 4.2 Skills (built-in, `docs/reference/features.md`)

| Skill | Trigger | Capability |
|---|---|---|
| `git-master` | commit, rebase, squash, "who wrote", "when was X added" | Three specializations: Commit Architect, Rebase Surgeon, History Archaeologist. Enforces atomic-commit rules (e.g. "5+ files → MUST be 3+ commits"), auto-detects last-30-commit style |
| `playwright` | Browser tasks, testing, screenshots | Playwright MCP (`npx @playwright/mcp@latest`) |
| `agent-browser` | Agent-browser CLI sessions | Vercel's `agent-browser` for navigation, snapshots, screenshots |
| `dev-browser` | Stateful browser scripting | Persistent page state for iterative / authenticated workflows |
| `frontend-ui-ux` | UI/UX, styling | Designer-turned-dev persona; bold aesthetic direction, distinctive typography |
| `review-work` | "review work", "review my work", "QA my work" | Launches 5 parallel bg sub-agents: goal verification, code quality, security, hands-on QA, context mining. All must pass |
| `ai-slop-remover` | "remove AI slop", "de-AI", "humanize" | Strips verbose comments, over-engineering, generic AI phrasing |

Skill load locations (priority order, highest first):
1. `.opencode/skills/*/SKILL.md` (project, OpenCode native)
2. `~/.config/opencode/skills/*/SKILL.md` (user, OpenCode native)
3. `.claude/skills/*/SKILL.md` (project, Claude Code compat)
4. `.agents/skills/*/SKILL.md` (project, Agents convention)
5. `~/.agents/skills/*/SKILL.md` (user, Agents convention)

**Skill-embedded MCPs.** Skills can carry their own MCP servers (stdio + HTTP) via SKILL.md YAML frontmatter; managed by `src/features/skill-mcp-manager/`. This is tier 3 of the three-tier MCP system.

Project-scope skills shipped in this repo (`.opencode/skills/`):

- `work-with-pr/SKILL.md` (11.6 KB)
- `work-with-pr-workspace/`
- `github-triage/SKILL.md` (17.1 KB) + `scripts/`
- `pre-publish-review/`

Built-in skills implementation directory:

```
src/features/builtin-skills/
├── skills.ts                 1.1 KB registry
├── types.ts
├── index.ts
├── agent-browser/
├── dev-browser/
├── frontend-ui-ux/
├── git-master/
└── skills/                   (additional)
```

### 4.3 MCP servers

Three-tier MCP system documented in `AGENTS.md`:

| Tier | Source | Mechanism |
|---|---|---|
| 1. Built-in | `src/mcp/` | 3 remote HTTP MCPs: `websearch` (Exa/Tavily), `context7` (official docs), `grep_app` (GitHub code search) |
| 2. Claude Code | `.mcp.json` | `${VAR}` env expansion via `claude-code-mcp-loader` |
| 3. Skill-embedded | SKILL.md YAML | `SkillMcpManager` (stdio + HTTP, per-session) |

`src/mcp/index.ts` (read verbatim) wires `createBuiltinMcps(disabledMcps, config)` with the three entries, all keyed as `{ type: "remote", url, enabled }`.

## 5. Agent catalog

From `docs/reference/features.md` and `src/agents/builtin-agents.ts`:

**11 built-in agents** (`BuiltinAgentName`): `sisyphus`, `hephaestus`, `prometheus`, `oracle`, `librarian`, `explore`, `multimodal-looker`, `metis`, `atlas`, `momus`, `sisyphus-junior`.

| Agent | Role | Default model | Key restrictions |
|---|---|---|---|
| **Sisyphus** (the namesake) | Main orchestrator, "discipline agent" that rolls the boulder | `claude-opus-4-6` (max), fallbacks to kimi-k2.5, k2p5, gpt-5.4, glm-5, big-pickle | Primary agent, respects UI model selection |
| **Hephaestus** ("Legitimate Craftsman") | Autonomous deep worker | **`gpt-5.4 (medium)` only — no fallback** (requires GPT access) | Built for Codex-style autonomy; README jokes this is *"the legitimate craftsman"* because Anthropic blocked OpenCode |
| **Prometheus** | Strategic planner, interview-driven | `claude-opus-4-6` (max) → gpt-5.4 (high) → glm-5 → gemini-3.1-pro. Dual-prompt: auto-switches between Claude and GPT variants via `isGptModel()`. GPT prompt is XML-tagged, principle-driven (~300 lines) vs Claude prompt (~1,100 lines across 7 files) | Can only create/modify markdown inside `.sisyphus/` directory (enforced by `prometheus-md-only` hook) |
| **Atlas** | Conductor / todo orchestrator; executes Prometheus plans | `claude-sonnet-4-6` → kimi-k2.5 → gpt-5.4 (medium) → minimax-m2.7 | Cannot delegate (blocked: task, call_omo_agent) |
| **Sisyphus-Junior** | Category-spawned executor (the actual code-writer) | Category-dependent; general fallback `claude-sonnet-4-6` → kimi-k2.5 → gpt-5.4 (medium) → minimax-m2.7 → big-pickle | Cannot re-delegate, obsessive todo tracking, must pass `lsp_diagnostics`, cannot modify plans |
| **Oracle** | Architecture / code review / debugging | `gpt-5.4` (high) → gemini-3.1-pro (high) → claude-opus-4-6 (max) → glm-5 | Read-only (blocked: write, edit, task, call_omo_agent) |
| **Librarian** | Docs / OSS code search | `minimax-m2.7` → minimax-m2.7-highspeed → claude-haiku-4-5 → gpt-5-nano | Read-only (blocked: write, edit, task, call_omo_agent) |
| **Explore** | Fast codebase grep | `grok-code-fast-1` → minimax-m2.7-highspeed → minimax-m2.7 → claude-haiku-4-5 → gpt-5-nano | Read-only (blocked: write, edit, task, call_omo_agent) |
| **Multimodal-Looker** | PDFs / images / diagrams | `gpt-5.4` (medium) → kimi-k2.5 → glm-4.6v → gpt-5-nano | Allowlist: `read` only |
| **Metis** | Pre-planning gap analyzer, consulted by Prometheus | `claude-opus-4-6` (max) → gpt-5.4 (high) → glm-5 → k2p5 | Catches "hidden intentions," ambiguities, AI-slop |
| **Momus** | Ruthless plan reviewer (for high-accuracy mode) | `gpt-5.4` (xhigh) → claude-opus-4-6 (max) → gemini-3.1-pro (high) → glm-5 | Can only say OKAY when 100% file refs verified, ≥80% tasks have clear refs, ≥90% have concrete acceptance criteria. Blocked: write, edit, task |

**Categories (semantic delegation layer).** When delegating, Sisyphus picks a *category*, not a model. 8 built-in categories:

| Category | Default | Use case |
|---|---|---|
| `visual-engineering` | `google/gemini-3.1-pro` (high) | Frontend, UI/UX, design, styling, animation |
| `ultrabrain` | `openai/gpt-5.4` (xhigh) | Deep logical reasoning, architecture |
| `deep` | `openai/gpt-5.4` (medium) | Autonomous problem-solving, thorough research |
| `artistry` | `google/gemini-3.1-pro` (high) | Highly creative tasks |
| `quick` | `openai/gpt-5.4-mini` | Trivial tasks, typos, single-file changes |
| `unspecified-low` | `anthropic/claude-sonnet-4-6` | General / low effort |
| `unspecified-high` | `anthropic/claude-opus-4-6` (max) | General / high effort |
| `writing` | `google/gemini-3-flash` | Documentation, prose |

Categories land in `src/tools/delegate-task/constants.ts` (`DEFAULT_CATEGORIES` + `CATEGORY_MODEL_REQUIREMENTS`). Users can override or add custom categories with `description`, `model`, `variant`, `temperature`, `top_p`, `prompt_append`, `thinking`, `reasoningEffort`, `textVerbosity`, `tools` (disable map), `maxTokens`, `is_unstable_agent` (forces background mode).

**Custom / dynamic agents.** Recent commits (see §14) added `agent_definitions` schema, a JSON agent loader, and wiring of `opencode.json` agents into the precedence chain (PR #2299, merged 2026-04-15). Custom agents discovered via config precedence: `agent_definitions` file paths → `opencode.json` `agents` map → built-ins.

**Deterministic Tab ordering.** Core agents receive an injected runtime `order` field: Sisyphus = 1, Hephaestus = 2, Prometheus = 3, Atlas = 4 (not user-configurable — documented explicitly in `docs/reference/features.md`).

## 6. Hooks, triggers, lifecycle integration

**52 hooks total**, composed across 3 tiers in `src/create-hooks.ts`:

```
createHooks()
  ├─ createCoreHooks()           # 43 hooks
  │   ├─ createSessionHooks()    # 24
  │   ├─ createToolGuardHooks()  # 14
  │   └─ createTransformHooks()  # 5
  ├─ createContinuationHooks()   # 7
  └─ createSkillHooks()          # 2
```

**OpenCode hook handlers wired by `src/plugin-interface.ts`** (verbatim names):

- `chat.params` (Anthropic effort, think mode, runtime fallback override)
- `chat.headers` (Copilot `x-initiator` header injection)
- `chat.message` (first-message variant, session setup, keyword detection for `ultrawork` / `search` / `analyze`)
- `command.execute.before`
- `config` (6-phase: provider → plugin-components → agents → tools → MCPs → commands)
- `event` (session.created / idle / deleted / error; openclaw dispatch; runtime fallback)
- `tool.execute.before` (file guard, label truncator, rules injector, prometheus md-only)
- `tool.execute.after` (output truncation, comment checker, hashline read enhancer)
- `experimental.chat.messages.transform` (context injection, thinking block validation, tool pair validation)
- `experimental.chat.system.transform`
- `experimental.session.compacting` (ctx + todo preservation) — also runs compaction-context-injector + compaction-todo-preserver + claude-code-hooks passthrough

**Named hooks exported by `src/hooks/index.ts`** (read verbatim, 59 lines). All of these are instantiable and composable:

`todo-continuation-enforcer`, `context-window-monitor`, `session-notification`, `session-notification-sender`, `session-notification-formatting`, `session-todo-status`, `idle-notification-scheduler`, `session-recovery`, `comment-checker`, `tool-output-truncator`, `directory-agents-injector`, `directory-readme-injector`, `empty-task-response-detector`, `anthropic-context-window-limit-recovery`, `think-mode`, `model-fallback`, `claude-code-hooks`, `rules-injector`, `background-notification`, `auto-update-checker`, `agent-usage-reminder`, `keyword-detector`, `non-interactive-env`, `interactive-bash-session`, `thinking-block-validator`, `tool-pair-validator`, `category-skill-reminder`, `ralph-loop`, `no-sisyphus-gpt`, `no-hephaestus-non-gpt`, `auto-slash-command`, `edit-error-recovery`, `prometheus-md-only`, `sisyphus-junior-notepad`, `task-resume-info`, `start-work`, `atlas`, `delegate-task-retry`, `question-label-truncator`, `stop-continuation-guard`, `compaction-context-injector`, `compaction-todo-preserver`, `unstable-agent-babysitter`, `preemptive-compaction`, `tasks-todowrite-disabler`, `runtime-fallback`, `write-existing-file-guard`, `bash-file-read-guard`, `hashline-read-enhancer`, `json-error-recovery`, `read-image-resizer`, `todo-description-override`, `webfetch-redirect-guard`, `legacy-plugin-toast`.

**Two distinct fallback systems** (documented in `AGENTS.md`):
- `model-fallback` — proactive, triggered in `chat.params`
- `runtime-fallback` — reactive, triggered in `session.error` (retryable 429/503/529, missing API keys, auto-retry signals)

**IntentGate classifier.** Documented in README as "IntentGate → analyzes true user intent before classifying or acting." Classifies into: research, implementation, investigation, evaluation, fix — before routing. Lives in the session-hook tier of `createCoreHooks`.

**Hashline edit (core harness bet).** Not a "hook" per se but a cross-cutting read/edit pipeline: every `read` output gets tagged `LINE#ID` content hashes; `hashline-read-enhancer` (PostToolUse) inserts them; `hashline-edit-diff-enhancer` validates on edit. README claim: *"Grok Code Fast 1: 6.7% → 68.3% success rate. Just from changing the edit tool."* Inspired by `oh-my-pi` / "The Harness Problem" (Can Bölük blog).

**OpenClaw (external bidirectional bridge).** `src/openclaw/` — ~22 files. From `src/openclaw/index.ts` (read verbatim):

- `initializeOpenClaw(config)` — starts a reply listener if `config.replyListener.discordBotToken` or `telegramBotToken` present
- `wakeOpenClaw(config, event, context)` — resolves a gateway (`command` or HTTP), interpolates an instruction template with variables (`sessionId`, `projectPath`, `tmuxSession`, `prompt`, `contextSummary`, `reasoning`, `question`, `tmuxTail`, `event`, `timestamp`, `replyChannel`, `replyTarget`, `replyThread`), and fires the webhook. On `stop` / `session-end` events inside tmux, it captures the last 15 lines of the tmux pane as `tmuxTail`.
- Reply listeners: Discord (`reply-listener-discord.ts`), Telegram (`reply-listener-telegram.ts`), injection module (`reply-listener-injection.ts`), spawn, process, startup, state, logs, paths. Session registry ties OpenCode sessions to Discord/Telegram reply channels.
- Debug: `OMO_OPENCLAW_DEBUG=1` / `OMX_OPENCLAW_DEBUG=1`.

**Tmux integration** is first-class. `src/features/tmux-subagent/` plus `src/openclaw/tmux.ts`. Background agents can spawn in tmux panes; `tmux.enabled: true` + `tmux.layout: "main-vertical"` lets you watch parallel agents live. `bunfig.toml` preloads `test-setup.ts` and `src/hooks/interactive-bash-session/` handles the Tmux-based `interactive_bash` tool (for REPLs, vim, htop, pudb).

## 7. Orchestration patterns

OmO cleanly separates three layers (from `docs/guide/orchestration.md`):

```
Planning (human + Prometheus + Metis + Momus)
   ↓ writes .sisyphus/plans/{name}.md
Execution (Atlas as conductor; does not write code itself)
   ↓ delegates via task() / call_omo_agent()
Workers (Sisyphus-Junior + Oracle + Explore + Librarian + category agents)
```

**`ultrawork` / `ulw` keyword.** README tagline: *"Install OmO. Type `ultrawork`. Done."* Activated via keyword-detector hook; `src/plugin/ultrawork-model-override.ts`, `src/plugin/ultrawork-db-model-override.ts`, `src/plugin/ultrawork-variant-availability.ts` handle per-agent model swaps when the keyword fires. Agents can have an `ultrawork: {...}` override block in config (e.g., swap Sisyphus to opus-4-6 max only when ultrawork triggers).

**Prometheus planning loop** (from `orchestration.md` mermaid diagram):

1. User describes work (via Tab→Prometheus or `@plan "…"` in Sisyphus)
2. Interview + codebase research (launches explore/librarian agents)
3. Clearance check — must have: core objective, scope boundaries, no critical ambiguities, technical approach, test strategy
4. Mandatory Metis gap analysis
5. Write plan to `.sisyphus/plans/{name}.md`
6. If user wants "high accuracy" → Momus review loop (OKAY / REJECT, no max retries)

**Atlas conductor mindset** (from `orchestration.md`): "Like an orchestra conductor: doesn't play instruments, ensures perfect harmony." Atlas CAN: read files, run commands, `lsp_diagnostics`, grep/glob/ast-grep. Atlas MUST delegate: writing, editing, bug fixes, tests, git commits.

**Wisdom accumulation.** After each task, Atlas extracts learnings into `.sisyphus/notepads/{plan-name}/`:
- `learnings.md` — patterns, conventions, successful approaches
- `decisions.md` — architectural choices + rationales
- `issues.md` — problems, blockers, gotchas
- `verification.md` — test results
- `problems.md` — unresolved / tech debt

All subsequent subagents receive accumulated wisdom, preventing repeat mistakes.

**Boulder state (session continuity).** `.sisyphus/boulder.json` tracks: `active_plan`, `session_ids[]`, `started_at`, `plan_name`. When you `/start-work` in a new session, the hook reads boulder.json and injects a continuation prompt with remaining tasks. This is the "Sisyphus rolling the boulder" metaphor made concrete.

**Todo continuation enforcer.** The "discipline" mechanism (from `orchestration.md`): when an agent goes idle with incomplete todos, the hook injects a `[SYSTEM REMINDER - TODO CONTINUATION]` block listing unchecked items, forcing continuation. Known trouble area (see issue #3446: runaway loop on un-markable blocked tasks).

**Background agents.** `src/features/background-agent/`. Fire 5+ specialists in parallel via `task(..., run_in_background=true)`; poll with `background_output(task_id=...)`. Concurrency is per-provider and per-model (`background_task.providerConcurrency` + `modelConcurrency`). Sample `.opencode/background-tasks.json` in repo shows 2 tracked bg sessions.

**Ralph Loop / `/ulw-loop`.** Named after Anthropic's Ralph Wiggum plugin. Self-referential: detects `<promise>DONE</promise>` sentinel, auto-continues if agent stops without completion, max 100 iterations default, cancelable via `/cancel-ralph` or `/stop-continuation`.

**Task system (experimental).** Gated by `experimental.task_system: true`. File-based tasks in `.sisyphus/tasks/` with `blockedBy` dependencies and automatic parallel execution. From `features.md`: follows Claude Code's internal Task tool signatures (TaskCreate/Update/List/Get) *"based on observed Claude Code behavior and internal specifications"* — i.e. reverse-engineered, not officially documented.

## 8. Intent routing / front-door logic

The "front door" is a layered pipeline — not a single classifier. In order:

1. **Keyword detector** (`createKeywordDetectorHook`, runs in `chat.message`). Detects `ultrawork` / `ulw` (max performance mode), `search` / `find` (parallel exploration), `analyze` / `investigate` (deep analysis). Activates mode flags that downstream hooks and the model override stack consume.
2. **IntentGate** (README + AGENTS.md): classifies research / implementation / investigation / evaluation / fix. Used to adapt Prometheus interview style (refactoring → safety; build from scratch → discovery; architecture → strategic).
3. **Auto-slash-command** (`createAutoSlashCommandHook`): parses inline slash commands from prompts and executes them.
4. **Ultrawork model override** (`src/plugin/ultrawork-model-override.ts` + DB variant + variant availability): swaps agent model when ultrawork is active, respecting user's per-agent `ultrawork: {...}` overrides.
5. **Model selection priority** (6 steps, from `docs/reference/configuration.md`):
   1. UI-selected model (for primary agents)
   2. User override in config
   3. Category default
   4. User `fallback_models` chain
   5. Built-in provider fallback chain (hardcoded in `src/shared/model-requirements.ts`)
   6. OpenCode system default

**Dual-prompt agents auto-detect model family.** Prometheus and Atlas detect model family at runtime via `isGptModel()` and switch between Claude-optimized (detailed checklists) and GPT-optimized (XML-tagged, principle-driven) prompts. Priority for these: Claude > GPT > Claude-like (Kimi/GLM).

**Hard-coded agent/model guards** (hooks):
- `no-sisyphus-gpt` — blocks Sisyphus from running on GPT models (old GPT models were a poor fit; GPT-5.4 now has its own path)
- `no-hephaestus-non-gpt` — blocks Hephaestus from running on anything but GPT

**Session lifecycle routing via event handler** (`src/plugin/event.ts`, 28 KB). Handles `session.created` / `idle` / `deleted` / `error` — fires openclaw dispatch, runtime fallback, notifications, and background-agent lifecycle callbacks.

## 9. State & persistence

| Location | Purpose |
|---|---|
| `.sisyphus/plans/*.md` | Prometheus-generated plans |
| `.sisyphus/boulder.json` | Active plan + session continuity |
| `.sisyphus/notepads/{plan}/*.md` | learnings / decisions / issues / verification / problems (wisdom accumulation) |
| `.sisyphus/tasks/*.json` | Experimental task system persistence |
| `.sisyphus/rules/` | Agent behavior rules (e.g., `modular-code-enforcement.md`) |
| `.opencode/background-tasks.json` | Persisted bg agent session registry |
| `/tmp/oh-my-opencode.log` | Logger output — **hardcoded**, significant for debugging (per `AGENTS.md`: *"Logger writes to `/tmp/oh-my-opencode.log` — check there for debugging"*) |
| `~/.config/opencode/` (user) | Plugin config, credential cache |
| `/tmp/` and OS-appropriate cache | Model capabilities cache (refreshed weekly by `refresh-model-capabilities.yml`) |
| `ModelCacheState` (`src/plugin-state.ts`) | In-process cache for model resolution across hook invocations |

Config migration is **idempotent via `_migrations` tracking** — creates timestamped backups before atomic writes (`migrateConfigFile`).

Session recovery (`createSessionRecoveryHook`) is transparent — handles missing tool results, thinking-block violations, empty messages, context-window overruns, JSON parse errors without user intervention.

## 10. Configuration & extension points

**Config loading** (from `src/plugin-config.ts`, read verbatim 314 lines):

1. Detect user file: `~/.config/opencode/oh-my-openagent.json[c]` preferred, legacy `oh-my-opencode.json[c]` fallback
2. Detect project file: `.opencode/oh-my-openagent.json[c]` or legacy
3. If legacy basename detected alongside canonical, log warning. If legacy only, attempt migration copy to canonical.
4. Parse JSONC (`jsonc-parser`) → `OhMyOpenCodeConfigSchema.safeParse` (Zod v4)
5. On full-schema failure, fall back to *section-by-section* partial parse (`parseConfigPartially`) — invalid sections are dropped, not fatal
6. `mergeConfigs(user, project)`: `deepMerge` for `agents`, `categories`, `claude_code`; `Set` union for all `disabled_*` arrays and `mcp_env_allowlist`; replace for other fields
7. `git_master` overrides get a separate layered merge (default → user → project)

**Schema coverage** (19 feature-specific config blocks; full list from `AGENTS.md` + `docs/reference/configuration.md`):

- `agents` (14 overridable, 21 fields each: `model`, `fallback_models` [string or mixed array of strings+objects], `temperature`, `top_p`, `prompt` [supports `file://`], `prompt_append` [supports `file://`], `tools`, `disable`, `mode`, `color`, `permission`, `category`, `variant`, `maxTokens`, `thinking`, `reasoningEffort`, `textVerbosity`, `providerOptions`)
- `categories` (built-in + custom, 13 options including `is_unstable_agent`)
- `disabled_*` arrays: `agents`, `hooks`, `mcps`, `skills`, `commands`, `tools`, `categories`
- `background_task`: `defaultConcurrency`, `staleTimeoutMs`, `providerConcurrency`, `modelConcurrency`
- `sisyphus_agent`: `disabled`, `planner_enabled`, `replace_plan`
- `tmux`: `enabled`, `layout`
- `browser_automation_engine`: `provider: "playwright" | "agent-browser"`
- `git_master`, `comment_checker`, `notification`, `mcp_env_allowlist`, `claude_code`
- `openclaw`: gateways, reply listener (Discord/Telegram bot tokens), instruction templates
- `experimental`: `aggressive_truncation`, `task_system`, `safe_hook_creation`, `auto_resume`
- `ralph_loop`: `enabled`, `default_max_iterations`
- `hashline`: edit-tool config
- `runtime_fallback`: per-model cooldown, retry logic
- `websearch`: provider selection (Exa / Tavily / …)
- `agent_definitions`: paths to external agent JSON files (added April 2026 via PR #2299)

**Permission model** (per-agent):

```jsonc
{
  "agents": {
    "explore": {
      "permission": {
        "edit": "deny",
        "bash": { "git": "allow", "rm": "deny" },
        "webfetch": "allow",
        "doom_loop": "deny",
        "external_directory": "ask"
      }
    }
  }
}
```

**File-URI prompts.** `prompt` and `prompt_append` (agent *and* category) accept `file://` URIs with absolute (`file:///abs`), relative (`file://./rel`), or home (`file://~/home`) paths. Missing-file failures are non-fatal: OmO inserts a warning placeholder rather than crashing.

**Model capability normalization.** Instead of hard-erroring on unsupported settings, OmO *downgrades*: `variant` normalized to closest supported, `reasoningEffort` downgraded/removed, `temperature`/`top_p` removed if unsupported, `maxTokens` capped to model limit, `thinking` stripped if unsupported. Capability data from (in order): provider runtime metadata → bundled models.dev data → local models.dev cache → heuristic family detection + alias rules.

**Doctor command.** `bunx oh-my-opencode doctor` runs health checks: plugin registration, config, models, environment, legacy-package warnings, compatibility-fallback diagnostics. `doctor --verbose` shows effective model resolution.

**CLI surface** (`src/cli/`): `install` (interactive + non-interactive via `--no-tui` + `--claude=…/--openai=…/…` subscription flags), `run` (non-interactive session), `doctor`, `mcp-oauth`. Built on Commander.js. CLI ships as a standalone binary via Bun-compiled platform packages (Bun 1.3.11 in CI). Windows is built on `windows-latest` (not cross-compiled) to avoid Bun segfaults.

## 11. Notable strengths

- **Honest multi-model orchestration.** Each agent has its *own* provider fallback chain (not a single global priority). Chains are documented by source file (`src/shared/model-requirements.ts`) and automatically adapted to installed subscriptions.
- **Category abstraction.** Decoupling intent (`visual-engineering`, `ultrabrain`, `quick`) from model choice is a legitimately nice pattern — protects prompts from model self-identification bias and lets users remap without editing subagent prompts.
- **Hashline edit tool.** The `LINE#ID` content-hash validation solves a real harness problem. Inspired by `oh-my-pi`, explicitly references Can Bölük's "Harness Problem" post. 10x improvement claimed for Grok Code Fast 1.
- **Dual-prompt agents.** Prometheus and Atlas auto-detect Claude vs GPT family and swap prompt style (XML-tagged principles vs detailed checklists). ~300 vs ~1,100 lines — real engineering effort.
- **Session continuity.** `.sisyphus/boulder.json` + notepad system survives crashes and multi-day work. Atlas resumes from where it left off without losing context.
- **Claude Code compatibility layers.** `.claude/skills/`, `.claude/commands/`, `.claude/rules/`, `.mcp.json` all load cleanly — reduces migration friction *into* OmO.
- **Deep observability.** Hardcoded `/tmp/oh-my-opencode.log`, PostHog telemetry (opt-out), `doctor` command, trace/session tools, comprehensive AGENTS.md at every directory level.
- **Solid engineering hygiene.** Bun-only, strict TS (no `as any` / `@ts-ignore` / path aliases), factory pattern, 200-LOC soft file limit, co-located tests, given/when/then test style, `mock.module()`-using tests auto-isolated in CI, CI auto-commits regenerated schemas.
- **Self-hosting dogfood.** README: *"99% of this project was built with OpenCode"* and the `.sisyphus/` directory at repo root contains actual plans/notepads — the tool is used to build the tool.
- **Platform-binary publishing.** 11 optional deps for darwin-arm64/x64[+baseline], linux-arm64[+musl], linux-x64[+baseline, +musl, +musl-baseline], windows-x64[+baseline]. `postinstall.mjs` + `bin/platform.js` detect AVX2 + libc family at runtime.
- **Well-staffed community.** ~52k stars, 4.2k forks, ~198 subscribers, active Discord ("#building-in-public"), CLA bot, rapid fix turnaround (multiple PR merges per day on 2026-04-14/15).
- **World-class tools integrated, not duct-taped** (README claim): LSP (rename, goto-def, find-refs, diagnostics, prepare-rename, workspace/document symbols, code actions, hover), AST-grep (25 languages, pattern search + replace), tmux (interactive bash sessions), 3 built-in MCPs.

## 12. Notable weaknesses / gaps

- **License is SUL-1.0, not OSI.** Legally distinct from MIT/Apache. Forks and downstream reuse carry material risk; any upstream adoption in a "neutral" project needs legal review.
- **Not a Claude Code plugin despite the compatibility veneer.** The runtime target is OpenCode + Bun. If a downstream project is truly Claude-Code-first, reusing this code requires porting. The "Claude Code Compatible" claim refers to *inbound* asset loading (skills/commands/MCP/rules), not outbound plugin-manifest compatibility.
- **Rename is messy and not finished.** Package name is still `oh-my-opencode`, binary is still `oh-my-opencode`, plugin id prefers `oh-my-openagent` but legacy `oh-my-opencode` still loads with a warning, config files recognize both basenames, and `detectPluginConfigFile` legacy-first logic means if *both* exist the legacy file wins — confusing for users (issue reports reflect this).
- **536 open issues** (as of 2026-04-16). Sampling: infinite-loop in Atlas orchestrator (#3446), installer generating invalid Anthropic model IDs (#3459), Windows proxy installation silently failing (#3303), maxOutputTokens validation errors (#3247, #3410), Anthropic-blocked-OpenCode content-filter regressions (#3435, #3454), resolveActualContextLimit falling back to 200k (#3450). Pattern: model/provider edge cases and Windows.
- **Heavy hook/tool count is a maintenance tax.** 52 hooks, 26 tools, 19 feature modules, 32 Zod config files, ~1,600 source files. README and AGENTS.md admit this complexity; the `run-ci-tests.ts` split for `mock.module()` tests exists because test pollution is a real problem.
- **Bun-only runtime.** *"Bun only (1.3.11 in CI) — never use npm/yarn"* (from `AGENTS.md`). Restricts contributor pool.
- **Hardcoded logger path `/tmp/oh-my-opencode.log`.** Does not work on Windows without emulation; also leaks across multi-user systems. No rotation.
- **`.sisyphus/` workspace pollutes target repos.** Every project where OmO runs gets a `.sisyphus/` directory with plans, notepads, boulder.json, tasks. Not opt-in per-project. Pushing these to git is easy to do accidentally.
- **GPT-centric for deep work.** Hephaestus *requires* GPT-5.4 with no fallback; Momus prefers GPT-5.4 xhigh; Oracle defaults to GPT-5.4. Users without OpenAI / Copilot are downgraded to "Sisyphus + Kimi" and the README itself warns: *"WHEN USER SAID THEY DON'T HAVE CLAUDE SUBSCRIPTION, SISYPHUS AGENT MIGHT NOT WORK IDEALLY."*
- **Prompt/category sprawl.** Default Sisyphus prompt is ~1,100 lines across 7 files. Categories + skills + agents + hooks + auto-slash + keyword-detector interact in non-obvious ways. Onboarding a contributor takes real effort.
- **Telemetry on by default** (opt-out via `OMO_SEND_ANONYMOUS_TELEMETRY=0` or `OMO_DISABLE_POSTHOG=1`). Corporate-safe deployments need to remember this.
- **Reverse-engineered Task tool contract.** README/features doc explicitly says Task system follows "observed Claude Code behavior and internal specifications" since Anthropic hasn't published docs. Fragile.
- **Marketing tone everywhere.** README is a sales pitch first, tech doc second. Content like *"Other harnesses promise multi-model orchestration. We ship it"* and the "oMoMoMoMo" easter egg (`.opencode/command/omomomo.md`) set a particular taste bar that may not match a conservative enterprise harness.
- **CLA bot is mandatory.** Every PR needs a CLA signature commit.

## 13. Conceptual comparison to oh-my-claudecode (OMC)

**No direct cross-references were found in the public repo.** Searching commit messages, README, AGENTS.md, docs, and issues in `oh-my-openagent` surfaces zero mentions of "oh-my-claudecode" or "OMC." There is no upstream/downstream relationship evidence: the project describes itself as following *"Heavy influence from AmpCode and Claude Code. Features ported, often improved."* The AmpCode influence is called out explicitly (Oracle and Hephaestus are inspired by AmpCode's design); the Claude Code influence is architectural ideas and asset-format compatibility.

**Conceptual parallels** (inferred from OMC's user-global instructions in this thread):

| Concept | oh-my-openagent | oh-my-claudecode (per OMC instructions) |
|---|---|---|
| **Primary runtime** | OpenCode plugin (Bun, TypeScript) | Claude Code harness |
| **Delegation contract** | `task({category, load_skills, prompt, run_in_background})` + `call_omo_agent({subagent_type})` | "Delegate specialized work to the most appropriate agent"; `executor` / `planner` / `architect` / `explore` / `designer` / `writer` agents |
| **Orchestration entry** | `ultrawork` keyword + `/start-work` for Prometheus plans | `autopilot`, `ultrawork`, `ralph`, `team`, `ralplan` tier-0 skills |
| **Keyword triggers** | `ultrawork`/`ulw`, `search`/`find`, `analyze`/`investigate`, `ultrathink` (→ think-mode hook) | `"ulw"→ultrawork`, `"ccg"→ccg`, `"ralplan"→ralplan`, `"ultrathink"→deep reasoning`, `"tdd"→TDD mode`, `"deepsearch"→codebase search`, `"cancelomc"→cancel`, `"deslop"`→ai-slop-cleaner |
| **Planning loop** | Prometheus (planner) → Metis (gap analyzer) → Momus (reviewer) → Atlas (conductor) → Sisyphus-Junior (worker) | `explore` → `planner`; separate `code-reviewer` / `verifier` agents for approval pass |
| **Self-referential loops** | Ralph Loop / `/ulw-loop` | `ralph` skill |
| **Parallel teams** | Background agents via `run_in_background`; tmux panes | `team` skill uses Claude Code native teams |
| **Persistent memory** | `.sisyphus/notepads/*`, `boulder.json` | `.omc/notepad.md`, `.omc/project-memory.json`, `.omc/plans/`, `.omc/research/`, `.omc/logs/`, `<remember>` / `<remember priority>` tags, Context Hub / `chub`, Wiki skill |
| **Model routing** | Semantic categories (`ultrabrain`, `visual-engineering`, `quick`, `deep`, `artistry`, `writing`, `unspecified-low`, `unspecified-high`) → per-model provider chains | `haiku` / `sonnet` / `opus` routing; `model=opus` for complex work |
| **Verification posture** | Momus reviewer; todo-continuation-enforcer; stop-continuation-guard | Separate `code-reviewer` / `verifier` pass: *"Never self-approve in the same active context"* |
| **Skill catalog** | 7 built-in skills + `.opencode/skills/*/SKILL.md` | Rich skill catalog: `omc-doctor`, `mcp-setup`, `cancel`, `hud`, `verify`, `autopilot`, `ralph`, `team`, `ralplan`, `ccg`, `ai-slop-cleaner`, `deep-interview`, `deep-dive`, `deepinit`, `learner`, `self-improve`, `ultraqa`, `sciomc`, `skillify`, `remember`, `ask`, `trace`, `writer-memory`, `wiki`, `configure-notifications`, `external-context`, `setup`, `release`, `plan`, `project-session-manager`, `debug`, `visual-verdict` |
| **Hook/trigger surface** | OpenCode's 10 hook handler points (`chat.*`, `tool.execute.*`, `event`, `experimental.chat.*`, `experimental.session.compacting`, `command.execute.before`) | Claude Code `<system-reminder>` tags with pattern-matching; `DISABLE_OMC`, `OMC_SKIP_HOOKS` kill switches |
| **Intent gate** | IntentGate classifier (research/impl/investigation/evaluation/fix) | Ralplan auto-gates vague requests via consensus planning |
| **External bridges** | OpenClaw (Discord/Telegram/webhook bidirectional) | `configure-notifications` (Telegram, Discord, Slack) |
| **Context dumping / init** | `/init-deep` → hierarchical AGENTS.md per dir | `deepinit` skill + hierarchical AGENTS.md |
| **Shared philosophy** | *"Human intervention is a failure signal"* (manifesto); *"Predictable, Continuous, Delegatable"*; *"The agent should be invisible"* | *"Prefer evidence over assumptions"*, *"Delegate for multi-file changes, refactors, debugging…"*, *"Verify before claiming completion"* |

The naming convention (`oh-my-<runtime>`, Sisyphus/Hephaestus/etc. mythic discipline agents, "ultrawork" terminology, ralph loop, `ulw` keyword, hierarchical AGENTS.md, `.omc/` vs `.sisyphus/` state dirs, todo-continuation discipline) suggests **strong conceptual cross-pollination but no code sharing**. The pattern library overlaps substantially — planner/executor separation, semantic categories, discipline enforcement, keyword triggers, background agents, Ralph loop, self-referential execution — while the implementations are independent (oh-my-openagent is TypeScript/Bun/OpenCode; OMC appears to be Claude-Code-native with skills as prompts + hook settings).

## 14. Recent direction (last ~60 days)

**Release cadence:** Very active. From `gh api releases`, last 10 tags:

| Tag | Date | Focus |
|---|---|---|
| v3.17.3 | 2026-04-15 | PostHog fix: disable exception autocapture to stay in free tier |
| v3.17.2 | 2026-04-13 | Minor compatibility + stability |
| v3.17.0 | 2026-04-11 | Minor compatibility + stability |
| v3.16.0 | 2026-04-08 | Minor compatibility + stability |
| v3.15.3 / .2 / .1 | 2026-04-05/06 | Minor compatibility + stability |
| v3.14.0 | 2026-03-26 | Publish-CI mock-heavy test isolation |
| v3.13.1 / .0 | 2026-03-25 | Writable data-path fallback; GitHub rename (repo) |
| v3.12.3 → .0 | 2026-03-17/18 | Todo-continuation diag, ralph-loop abort-stale-Oracle fix |
| v3.11.2 → .0 | 2026-03-07/08 | **First release as oh-my-openagent** ("we have changed our name to make it less confused; OmO and Sisyphus is about the whole architecture") |

**Key themes in last 60 days of commits:**

1. **Dual-package migration.** `oh-my-opencode` → `oh-my-openagent` transition work threading through config detection, publish CI, repo URLs, legacy package-name warnings in `doctor`, plugin ID preference in `opencode.json`.
2. **Custom agent support (PR #2299, merged 2026-04-15).** Major feature: `agent_definitions` schema, eager path resolution, JSON agent loader, wired into `opencode.json` agent precedence chain. Included security hardening (null-prototype accumulator against `__proto__` pollution, `Object.hasOwn()` instead of `in`). Adds the dynamic-custom-agent-support machinery to compete with runtime-definable agents.
3. **Bug-batch fixes (merged 2026-04-15).** `fix: numeric skill names`, `ultrawork missing run_in_background`, `ZWSP agent lookups`, `isPlanFamily regression tests`, `code-review -> review-work` rename, three bugs from issues #3366/#3272/#3222. Plus `hide native plan agent when replace_plan is true (#3443)`.
4. **Telemetry hardening.** PostHog init failures guarded, exception autocapture disabled to stay in free tier.
5. **CLI reliability.** `treat missing session status as idle in run completion`, `use getAgentRuntimeName for agent resolution in run command`, provider model-id transforms isolated from shared mocks.
6. **Test infrastructure.** Mock-heavy tests isolated in separate processes to prevent cross-file pollution, `mock.module` replaced with `spyOn` in several places.
7. **Docs refresh sprint (2026-04-13).** `docs/configuration`, `docs/features`, `docs/installation`, `docs/cli`, `docs/readme-*`, `docs/orchestration`, `docs/overview`, `docs/agent-model-matching`, `docs/contributing`, `docs/ollama` all updated in a single day — implies automated or AI-assisted doc regeneration to match v3.17.
8. **Model capability refresh.** `refresh-model-capabilities.yml` runs weekly to sync with models.dev API.
9. **CI hardening.** actionlint + shellcheck on workflows; mock-heavy isolated test split in publish CI.
10. **Platform dual-publish.** `feat: dual-publish platform binaries for oh-my-openagent` (v3.11.2) — both packages publish the 11 platform binaries.

**Trajectory reading.** The project is in stabilization + transition mode. Big architectural moves seem complete; current energy is fighting issue backlog (536 open), finishing the rename compatibility story, polishing telemetry, and broadening the custom-agent surface to let users plug in their own named agents without editing built-ins.

## 15. Open questions

1. **Claude Code plugin port.** Is a true Claude-Code-plugin build of OmO planned, or will the runtime remain OpenCode-only? Several issues (#3190 about Superpowers plugin compatibility; the whole "Claude Code Compatible" marketing) suggest demand, but no code points to a port.
2. **License intent.** What does SUL-1.0 actually permit for commercial forks and internal enterprise use? The LICENSE.md wasn't read in detail here — a corporate-safe adopter needs to read all 3,973 bytes before reusing patterns verbatim.
3. **Relationship to oh-my-claudecode.** Is there any direct lineage (shared author, shared prompts, shared skills)? No public evidence in the repo; worth checking OMC's own repo for any `oh-my-openagent` / Sisyphus / "ultrawork" references to confirm direction of influence.
4. **Productization vs open source.** With Sisyphus Labs (sisyphuslabs.ai) actively building a "productized version of Sisyphus," how will OSS features evolve? Will advanced features (team orchestration, IntentGate tuning) split off?
5. **`.sisyphus/` in target repos.** Is there an official `.gitignore` guidance for consumers, or is checking in boulder.json / plans / notepads encouraged? Docs don't address this clearly — and plans frequently contain user intent that's sensitive.
6. **Hashline edit reliability outside Grok.** The 6.7%→68.3% Grok Code Fast 1 result is hero-quoted. Are there similar before/after numbers for Claude Sonnet 4.6 and GPT-5.4? The "Harness Problem" improvement seems to matter most for models that struggle to reproduce content.
7. **Experimental task system stability.** Since it's reverse-engineered from "observed Claude Code behavior," how brittle is it to Claude Code internals drift? Recent issue #3452 (`CLI opencode run exits prematurely when background tasks are active but no todos exist`) suggests cross-over bugs.
8. **Runtime-fallback vs model-fallback overlap.** Two systems for similar problems exist (`AGENTS.md` explicitly notes this). Is there a plan to consolidate, or is the split intentional (proactive vs reactive)?
9. **Windows reliability.** Windows-specific bugs appear in the open-issues list (#3303 silent install failure behind proxy; #3321 grep CRLF + drive letter — recently merged). How production-ready is the Windows platform binary?
10. **OpenClaw security surface.** The bridge accepts inbound Discord/Telegram messages that can inject prompts into sessions. What is the threat model, and where is authentication / rate-limit / prompt-injection defense documented? `gateway-url-validation.ts` exists but wasn't read here.
11. **Upstream `oh-my-pi` / AmpCode credits.** The harness problem Hashline is credited to Can Bölük / oh-my-pi; Oracle/Hephaestus to AmpCode. Is there code copied, or only patterns? Important for any downstream licensing review.
12. **Corporate-safe mode.** Is there a single environment variable or flag that disables telemetry + easter-egg output (`oMoMoMoMo`, emoji, marketing strings in prompts) at once? The discovered env-var surface covers telemetry but not output sanitization.

---

**Research file written to:** `/home/joseibanez/develop/projects/copilot-omni/.omc/research/phase-a/ext-oh-my-openagent.md`
