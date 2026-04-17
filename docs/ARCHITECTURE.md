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
│  skills/       27 SKILL.md files (LLM instructions)      │
│  agents/       19 agent prompts                          │
│                                                          │
│  hooks.json ──▶ hooks/session_start.py (sessionStart)    │
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

Single-file stdio MCP 2024-11-05 server. Registers 28 tools across 9 families. Persists to a SQLite database opened in WAL mode with `UNIQUE(mode, session_id)` constraint on the state table. Every `tools/call` is schema-validated. No imports outside the Python standard library.

Protocol transport is newline-delimited JSON (one JSON-RPC message per line on stdin → one response per line on stdout). That's what Copilot CLI sends by default.

### `hooks/*.py`

- `session_start.py` — returns an informational banner to the session.

`pre_tool_use.py`, `post_tool_use.py`, and `user_prompt_submit.py` were removed in v2.1.0 — these lifecycle events are not emitted by GitHub Copilot CLI. Policy enforcement is via the MCP `policy_check` tool.

The hook accepts its event payload on stdin and returns JSON on stdout. Budget: < 500 ms on Windows (no large imports, minimal file I/O).

### `scripts/omni.py`

User-facing CLI. Subcommands: `version`, `doctor`, `init`, `status`, `plugin-install`, `mcp`, `list`. Pure stdlib, no subprocess outside of optionally invoking `copilot` itself for `plugin-install` and `mcp`.

### `scripts/subagent.py`

Dispatches specialist work to sub-invocations of Copilot CLI. Known skills are routed via the
`/copilot-omni:<name>` slash-command namespace; named agents via `--agent <name>`. A file-lock
semaphore caps the number of concurrent children at `min(8, cpu_count())` by default, configurable
in `.omni/config.json` (ADR-0010). The wrapper blocks rather than fails when the cap is hit.

```python
run_agent("executor", "implement plan in .omni/plans/run-001.md", allow_all=True)
```

runs `copilot -p "…" --agent executor --allow-all`.

### `scripts/router.py`

Front-door intent router (ADR-0005). Scores prompt concreteness on a rubric of anchors, verbs, and
constraints; prompts scoring below the threshold (default 0.4) are redirected to `deep-interview`
before any skill fires. Bypass explicitly with `--skip-interview`.

### `scripts/category_resolver.py`

Resolves semantic model categories (`quick`, `deep`, `ultrabrain`) to the best concrete model in the
current Copilot subscription (ADR-0003). Agent frontmatter uses the category; `.omni/config.json`
overrides allow per-project pinning.

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
