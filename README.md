# Copilot Omni

**Enterprise-safe multi-agent orchestration for GitHub Copilot CLI.**
Pure Python stdlib + Markdown. Zero compiled binaries. Zero pip dependencies. Installs on locked-down corporate machines (CrowdStrike, SentinelOne, no admin, no npm).

[![CI](https://github.com/Jurel89/copilot-omni/actions/workflows/ci.yml/badge.svg)](https://github.com/Jurel89/copilot-omni/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![python](https://img.shields.io/badge/python-%3E%3D3.9-3776AB.svg)
![platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg)
![license](https://img.shields.io/badge/license-MIT-green.svg)

## What it ships

- **37 skills** — autopilot, ralph, ultrawork, team, plan, deep-interview, debug, trace, verify, ultraqa, wiki, remember, external-context, ask, ccg, ai-slop-cleaner, sciomc, self-improve, skill, skillify, learner, setup, omc-doctor, release, cancel, … (`omni list skills` for the full list).
- **19 agents** — analyst, architect, planner, critic, executor, explore, debugger, tracer, verifier, qa-tester, test-engineer, code-reviewer, security-reviewer, code-simplifier, document-specialist, writer, git-master, designer, scientist.
- **8 slash commands** — `/omni-init`, `/omni-doctor`, `/omni-status`, `/omni-list`, `/omni-plan`, `/omni-ship`, `/omni-verify`, `/omni-memory`.
- **30 MCP tools** via one stdio Python server (memory, wiki, notepad, state, artifacts, runs, policy, trace, …).
- **4 lifecycle hooks** (sessionStart, preToolUse, postToolUse, userPromptSubmit) enforcing policy and auditing.

## Install (corporate-friendly)

```bash
# Method 1: Copilot CLI marketplace
copilot plugin install Jurel89/copilot-omni

# Method 2: clone and install locally
git clone https://github.com/Jurel89/copilot-omni.git
copilot plugin install ./copilot-omni

# Method 3: trial via --plugin-dir, no install
copilot --plugin-dir ./copilot-omni -p "list all skills" --allow-all
```

No `go build`, no `npm install`, no `pip install`. You need only Python ≥3.9 and the `copilot` CLI on PATH.

## Quick start

```bash
python3 scripts/omni.py doctor            # Verify environment
python3 scripts/omni.py init               # Scaffold .omni/ in your project
copilot -p "autopilot build a habit tracker CLI with streaks" --allow-all
```

## Why this exists

GitHub Copilot CLI is powerful but unopinionated. Teams that want spec-driven, auditable, resumable workflows need orchestration around it. The excellent [`oh-my-claudecode`](https://github.com/Yeachan-Heo/oh-my-claudecode) does that for Claude Code — but relies on a 900 KB bundled Node runtime. Corporate environments often block unsigned Node binaries and arbitrary npm installs.

**Copilot Omni is that orchestration layer, rebuilt for Copilot CLI, with a runtime footprint corporate EDRs cannot flag:**

- All runtime code is Python 3.9 stdlib. No third-party imports (enforced by CI).
- The MCP server is one Python file, stdio JSON-RPC 2.0.
- Hooks are tiny Python scripts.
- Everything else is Markdown.

`file mcp/server.py` → `ASCII text`. No ELF, no PE, no signatures for EDR to match.

## Architecture

```
Copilot CLI
 ├─ reads .claude-plugin/plugin.json
 ├─ discovers skills/ (37), agents/ (19), commands/ (8)
 ├─ wires hooks/hooks.json  -> python3 hooks/*.py
 └─ wires .mcp.json         -> python3 mcp/server.py
                                 └─ SQLite store at $OMNI_HOME/omni.db
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for internals.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — corporate install paths (RHEL, macOS, Windows, air-gapped)
- [docs/MIGRATION.md](docs/MIGRATION.md) — upgrading from v0.1.0 Go runtime
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — plugin internals
- [docs/SKILLS.md](docs/SKILLS.md) — full skill index
- [AGENTS.md](AGENTS.md) — agent contract

## License

MIT. See [LICENSE](LICENSE).
