# Copilot Omni — Agent Contract

This repository is a **GitHub Copilot CLI plugin** written in pure Markdown + Python stdlib. No Go, no npm, no compiled binaries. Ships as a clone-and-go repo.

## What you have here

| Area | Count | Location |
|------|-------|----------|
| Skills | 37 | `skills/<name>/SKILL.md` |
| Agents | 19 | `agents/<name>.md` |
| Slash commands | 8 | `commands/<name>.md` |
| MCP tools | 30 | served by `mcp/server.py` |
| Lifecycle hooks | 4 | `hooks/*.py` |

## Operating principles

- **Delegate by capability.** Use `scripts/subagent.py <name> "<prompt>"` (or `copilot -p ... --agent <name>`) to invoke a specialist agent when the task calls for one.
- **Evidence over assumption.** Run the verifier / code-reviewer pass separately from the writer pass. Never self-approve.
- **Smallest viable change.** Don't broaden scope unless asked.
- **Corporate-safe.** Every runtime piece is interpreted Python (stdlib only) or Markdown. Never add compiled binaries. Never add third-party pip dependencies.

## Agent roster (routing cheatsheet)

| Need | Agent |
|------|-------|
| Requirements & gap analysis | `analyst` |
| Architecture, deep reasoning | `architect` |
| Ordered implementation plan | `planner` |
| Adversarial plan review | `critic` |
| Implement code | `executor` |
| Map a new codebase | `explore` |
| Bug diagnosis | `debugger` |
| Causal tracing | `tracer` |
| Final completion check | `verifier` |
| Runtime CLI testing | `qa-tester` |
| Write / maintain tests | `test-engineer` |
| PR-style review | `code-reviewer` |
| Vuln & secret review | `security-reviewer` |
| Code simplification | `code-simplifier` |
| External doc lookup | `document-specialist` |
| Long-form documentation | `writer` |
| Git / branch / rebase | `git-master` |
| UI / UX design | `designer` |
| Data / research workflows | `scientist` |

## MCP tools (surface area)

Memory: `memory_capture`, `memory_search`, `memory_export`, `memory_prune`.
Artifacts: `artifact_write`, `artifact_read`.
Runs: `run_status`, `resume_context`.
State: `state_write`, `state_read`, `state_clear`.
Wiki: `wiki_write`, `wiki_read`, `wiki_query`, `wiki_list`.
Notepad: `notepad_write`, `notepad_read`, `notepad_prune`.
Shared memory: `shared_memory_write`, `shared_memory_read`.
Trace: `trace_summary`, `trace_timeline`.
Session: `session_search`.
Subtask / workspace: `subtask`, `workspace`.
Policy + health: `policy_check`, `health`, `doctor`, `config_resolve`, `support_bundle`.

## How skills invoke subagents

Copilot Omni skills target Claude Code's `Task(subagent_type=...)` pattern. In Copilot CLI we translate that to:

```python
from scripts.subagent import run_agent
run_agent("executor", "implement the plan in .omni/plans/run-001.md")
```

or equivalently, as a shell command inside a skill:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/subagent.py" executor "..."
```

Either form spawns `copilot -p "..." --agent <name> --allow-all` as a subprocess and collects the output.

## Filesystem conventions (per project)

```
<project-root>/
├── AGENTS.md                  # (this file — managed by `omni init`)
├── .omni/
│   ├── config.json
│   ├── runs/<run-id>/{spec.md, plan.json, decisions.md, summary.md}
│   ├── specs/, plans/, decisions/
│   ├── audit/tool-audit.log
│   └── support/
```

Global state lives at `$OMNI_HOME/omni.db` (default `~/.omni/omni.db`).
