# Copilot Omni

**Copilot-CLI-native multi-agent orchestration — v2.0.0.**
Pure Python stdlib + Markdown. Zero compiled binaries. Zero pip dependencies.

[![CI](https://github.com/Jurel89/copilot-omni/actions/workflows/ci.yml/badge.svg)](https://github.com/Jurel89/copilot-omni/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![python](https://img.shields.io/badge/python-%3E%3D3.9-3776AB.svg)
![platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg)
![license](https://img.shields.io/badge/license-MIT-green.svg)

## What's new in v2.0.0

- **Front-door intent router** — every prompt is scored for concreteness; vague prompts auto-redirect to `deep-interview` before any skill fires. Bypass with `--skip-interview`.
- **Semantic model categories** — `quick`, `deep`, `ultrabrain` resolve to your Copilot subscription's best available model. No hardcoded model names in skill code.
- **Autonomous pipeline modes** — `autopilot`, `ralph`, `ultrawork`, `ultraqa`, `ralplan` compose via a typed mode-key registry with full cancel-cascade semantics (ADR-0006).
- **Team orchestration** — real tmux + git-worktree parallelism (`omni team`). Subprocess fallback for non-tmux environments. MCP-backed state machine tracks every worker.
- **MCP-backed state** — 22 tools over stdio JSON-RPC 2.0. Schema-validated on every `tools/call`. WAL-mode SQLite with UNIQUE(mode, session_id).
- **17-check contract validator** — `scripts/verify_plugin_contract.py --all` is the merge gate. Checks rename hygiene, Claude-primitive absence, mode-key registry, cancel-signal pairing, worktree hygiene, and more.
- **Subagent back-pressure** — file-lock semaphore caps parallel subagents at `min(8, cpu_count())`. Configurable in `.omni/config.json`. Blocks instead of fails.
- **Hook hardening** — atomic audit logging, 5 kill-switch env vars, per-hook switches, deprecated `OMC_*` aliases with v3.0.0 removal warning, session-start banner, policy permission checks.
- **v1 → v2 migration script** — `scripts/omni_migrate_v1_to_v2.py` renames `.omc/` to `.omni/`, prints env-var guidance. Idempotent. Dry-run by default.
- **~520 tests** across unit, integration, MCP-smoke, discovery-smoke, and coverage gates.

## What it ships

- **29 skills** — autopilot, ralph, ultrawork, ultraqa, ralplan, team, plan, deep-interview, deep-dive, verify, debug, trace, remember, wiki, external-context, ask, ai-slop-cleaner, skill, skillify, setup, omni-setup, omni-doctor, omni-reference, omni-teams, mcp-setup, release, cancel, deepinit, hud. (`omni list skills` for the full list.)
- **19 agents** — analyst, architect, planner, critic, executor, explore, debugger, tracer, verifier, qa-tester, test-engineer, code-reviewer, security-reviewer, code-simplifier, document-specialist, writer, git-master, designer, scientist.
- **10 slash commands** — `/omni-init`, `/omni-doctor`, `/omni-status`, `/omni-list`, `/omni-plan`, `/omni-ship`, `/omni-verify`, `/omni-memory`, `/omni-team`, `/omni-cancel`.
- **22 MCP tools** via one stdio Python server — memory, wiki, notepad, state, shared-memory, trace, session, policy, health, doctor, config, support-bundle.
- **4 lifecycle hooks** (sessionStart, preToolUse, postToolUse, userPromptSubmit) with atomic audit logging and kill-switch matrix.

## Install

```bash
# Requires: GitHub Copilot CLI on PATH + Python >= 3.9

# Option 1: Copilot CLI plugin install
npm install -g @github/copilot-cli          # install Copilot CLI if needed
copilot plugin install Jurel89/copilot-omni

# Option 2: clone and install locally
git clone https://github.com/Jurel89/copilot-omni.git
copilot plugin install ./copilot-omni

# Option 3: trial without installing (no side effects)
copilot --plugin-dir ./copilot-omni -p "list all skills" --allow-all
```

No `go build`. No `pip install`. You need only Python ≥3.9 and the `copilot` CLI on PATH.

## Quick start

```bash
# Sanity-check your environment
python3 scripts/omni.py doctor

# Scaffold .omni/ state directory in your project
python3 scripts/omni.py init

# Let the router decide what to do (may redirect to deep-interview for vague prompts)
copilot -p "autopilot build a habit tracker CLI with streaks" --allow-all

# Skip deep-interview gate if you know exactly what you want
copilot -p "autopilot refactor scripts/router.py to use dataclasses --skip-interview" --allow-all

# Run the team orchestrator (tmux required; subprocess fallback on Windows)
copilot -p "team run wave-3 plan" --allow-all
```

## Migrating from v1.x

If you used v1.x, run the migration script first:

```bash
python3 scripts/omni_migrate_v1_to_v2.py --dry-run   # preview changes
python3 scripts/omni_migrate_v1_to_v2.py --apply     # execute
```

See [docs/MIGRATION.md](docs/MIGRATION.md) for the full v1 → v2 guide.

## Architecture

```
GitHub Copilot CLI
 ├─ reads .claude-plugin/plugin.json
 ├─ discovers skills/ (29), agents/ (19), commands/ (10)
 ├─ wires hooks/hooks.json  -> python3 hooks/*.py
 │    ├─ session_start.py   (banner, policy checks, metrics)
 │    ├─ pre_tool_use.py    (policy guard, shlex-safe parse)
 │    ├─ post_tool_use.py   (audit logging, metrics)
 │    └─ user_prompt_submit.py  (router decision, skill triggers)
 └─ wires .mcp.json         -> python3 mcp/server.py
                                 └─ SQLite store at $OMNI_HOME/omni.db
                                     schema-validated, WAL mode, UNIQUE(mode,session_id)

scripts/router.py
 └─ scores prompt concreteness (ADR-0005)
     ├─ score >= 0.4  → proceed to skill
     ├─ score <  0.4  → redirect to deep-interview
     └─ --skip-interview → bypass regardless

scripts/category_resolver.py
 └─ resolves quick|deep|ultrabrain → concrete model name
     └─ reads .omni/config.json models overrides
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for internals, [docs/ROUTER.md](docs/ROUTER.md) for the scoring rubric, and [docs/MODELS.md](docs/MODELS.md) for model categories.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — corporate install paths (RHEL, macOS, Windows, air-gapped)
- [docs/MIGRATION.md](docs/MIGRATION.md) — v1 → v2 migration guide
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — plugin internals
- [docs/ROUTER.md](docs/ROUTER.md) — front-door intent router
- [docs/MODELS.md](docs/MODELS.md) — semantic model categories
- [docs/TEAM.md](docs/TEAM.md) — team orchestration (tmux + worktrees)
- [docs/HOOK_CONTRACT.md](docs/HOOK_CONTRACT.md) — hook event shapes, kill switches, audit schema
- [docs/STATE_MODES.md](docs/STATE_MODES.md) — MCP state mode registry
- [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) — test architecture and coverage gates
- [docs/ADR/](docs/ADR/) — Architecture Decision Records (ADR-0000 – ADR-0010)
- [AGENTS.md](AGENTS.md) — agent contract and routing cheatsheet

## Why this exists

<!-- omni-rename-allow: upstream-reference -->
GitHub Copilot CLI is powerful but unopinionated. Teams that want spec-driven, auditable, resumable workflows need orchestration around it. The excellent [`oh-my-claudecode`](https://github.com/Yeachan-Heo/oh-my-claudecode) does that for Claude Code. Copilot Omni is that orchestration layer rebuilt for Copilot CLI — no Claude Code required, no compiled binaries, no npm beyond the CLI itself.

**Runtime footprint:**

- All runtime code is Python 3.9 stdlib. No third-party imports (enforced by CI).
- The MCP server is one Python file, stdio JSON-RPC 2.0.
- Hooks are tiny Python scripts.
- Everything else is Markdown.

`file mcp/server.py` → `ASCII text`. Corporate EDRs have nothing to flag.

## License

MIT. See [LICENSE](LICENSE).
