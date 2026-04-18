# Architecture

## Overview

Copilot Omni is a **Copilot CLI plugin** — a directory with a manifest. Copilot discovers the manifest, reads the skill/agent/command definitions, spawns the MCP server as a stdio subprocess, and invokes the hook scripts at lifecycle events.

```
┌────────────────────┐
│ GitHub Copilot CLI │
└────────┬───────────┘
         │
         │ reads plugin.json (at plugin root)
         ▼
┌─────────────────────────────────────────────────────────┐
│ copilot-omni plugin                                      │
│                                                          │
│  skills/       28 SKILL.md files (LLM instructions)      │
│  agents/       19 agent prompts                          │
│                                                          │
│  hooks.json ──▶ hooks/session_start.py (sessionStart)    │
│             ──▶ hooks/pre_tool_use.py  (preToolUse)      │
│  .mcp.json  ──▶ python mcp/server.py (stdio JSON-RPC)    │
│                                                          │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
                  SQLite: $OMNI_HOME/omni.db
                  (memory, wiki, notepad, state, runs, artifacts,
                   shared_memory, trace, sessions)
```

## Runtime components

### `mcp/server.py`

Single-file stdio MCP 2024-11-05 server. Registers 30 tools across 9 families. Persists to a SQLite database opened in WAL mode. The state table uses a composite `PRIMARY KEY(mode, session_id)` so two sessions can hold rows for the same mode without colliding. Every `tools/call` is schema-validated. No imports outside the Python standard library.

Protocol transport is newline-delimited JSON (one JSON-RPC message per line on stdin → one response per line on stdout). That's what Copilot CLI sends by default.

### `hooks/*.py`

Two lifecycle hooks ship:

- `session_start.py` — emits an informational banner + recent project/subagent memory context; warns on policy files with overly permissive modes.
- `pre_tool_use.py` — shlex-safe shell parse + deny-commands + protected-path enforcement using the active policy profile in `policies/`.

Each accepts its event payload on stdin and returns JSON on stdout. Budget: < 500 ms on Windows (no large imports, minimal file I/O). Both fail open — any unhandled exception emits `{}` and exits 0 so the plugin can never block a session. If a Copilot CLI version stops emitting one of these events, the corresponding hook simply never runs.

`postToolUse`, `userPromptSubmitted`, `errorOccurred`, and `sessionEnd` are allowed events, but no handler ships. Policy enforcement for tool calls lives in `pre_tool_use.py`; the MCP `policy_check` tool is available for skills that want to pre-flight a command.

The doc at `docs/HOOK_CONTRACT.md` carries the full event-shape reference; `tests/test_hook_contract_alignment.py` keeps the config and doc in sync.

### `scripts/omni.py`

User-facing CLI. Subcommands: `version`, `doctor`, `init`, `status`, `plugin-install`, `mcp`, `list`, `memory`, `execute`, `verify`. Pure stdlib, no subprocess outside of optionally invoking `copilot` itself for `plugin-install` and `mcp`. The `memory` subcommand provides `search`, `list`, `capture`, `prune`, and `export` operations against the SQLite memory store.

### `scripts/subagent.py`

Dispatches specialist work to sub-invocations of Copilot CLI. Known skills are routed via the
`/copilot-omni:<name>` plugin skill invocation; named agents via `--agent <name>`. A file-lock
semaphore caps the number of concurrent children at `min(8, cpu_count())` by default, configurable
in `.omni/config.json` (ADR-0010). The wrapper blocks rather than fails when the cap is hit.

```python
run_agent("executor", "implement plan in .omni/plans/run-001.md", allow_all=True)
```

runs `copilot -p "…" --agent executor --allow-all`.

### `scripts/category_resolver.py`

Passthrough script — model selection is owned by the Copilot CLI host via `/model`. Agent frontmatter has no `category`, `level`, or `disallowedTools` fields.

## Data model (SQLite)

| Table | Purpose |
|-------|---------|
| `memory` | Long-lived project knowledge (scope, key, content, tags) |
| `artifacts` | Run artifacts (specs, plans, decisions, summaries) |
| `runs` | Run lifecycle rows (phase, status, metadata) |
| `state` | Mode state (autopilot, ralph, ultrawork, team, ralplan) |
| `wiki` | Persistent markdown KB by slug |
| `notepad` | Session scratch memory by kind |
| `shared_memory` | Cross-agent handoff |
| `trace` | Causal-tracing entries (observation, hypothesis, evidence, verdict) |
| `sessions` | Session summaries (internal table, no MCP tool surface) |

Schema is migrated on every server start via `_migrate()`.

## Policy model

The MCP `policy_check` tool looks up policies in this order:
1. `$OMNI_POLICY_FILE` (explicit override)
2. `<cwd>/.omni/policy-<profile>.json` (per-project)
3. `<plugin>/policies/<profile>.json` (plugin default)

Active profile is `$OMNI_POLICY_PROFILE` (default `standard`).

Shipped profiles:
- `permissive` — only blocks `:(){ :|:& };:` and `rm -rf /`.
- `standard` — also blocks `sudo`, `mkfs`, `dd if=/dev/zero`.
- `strict` — additionally protects key repo files and blocks shell pipes to `sh`.

## Why no third-party dependencies

Corporate environments often restrict `pip install` and mirror only a vetted subset of PyPI. Shipping a plugin that needs `pip install foo` means one more ticket for every corporate user. Shipping zero dependencies means the plugin works on day one with whatever Python the admin blessed.

`tests/test_discovery.py::test_no_third_party_imports` enforces the rule on every CI run.
