# Copilot Omni — Agent Contract

This repository is a **GitHub Copilot CLI plugin** written in pure Markdown + Python stdlib.
No Go, no npm beyond the CLI, no compiled binaries. Ships as a clone-and-go repo.

## What you have here

| Area | Count | Location |
|------|-------|----------|
| Skills | 30 | `skills/<name>/SKILL.md` |
| Agents | 19 | `agents/<name>.md` |
| Slash commands | 10 | `commands/<name>.md` |
| MCP tools | 20 | served by `mcp/server.py` |
| Lifecycle hooks | 4 | `hooks/*.py` |

## Operating principles

- **Delegate by capability.** Use `scripts/subagent.py <name> "<prompt>"` (or `copilot -p ... --agent <name>`) to invoke a specialist agent when the task calls for one.
- **Evidence over assumption.** Run the verifier / code-reviewer pass separately from the writer pass. Never self-approve.
- **Smallest viable change.** Don't broaden scope unless asked.
- **Front-door router.** Every user prompt is scored by `scripts/router.py`. Vague prompts redirect to `deep-interview`. Bypass with `--skip-interview` only.
- **Semantic model categories.** Agent frontmatter uses `category: quick|deep|ultrabrain`. Never hardcode a concrete model name — `scripts/category_resolver.py` resolves at runtime.
- **Corporate-safe.** Every runtime piece is interpreted Python (stdlib only) or Markdown. Never add compiled binaries. Never add third-party pip dependencies (enforced by CI).

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

## Skill catalog (29 skills)

| Skill | Purpose |
|-------|---------|
| `autopilot` | Full autonomous build loop — spec → plan → execute → verify |
| `ralph` | Iterative improvement loop with critic gating |
| `ultrawork` | Maximum parallelism pipeline with cap-sanity guard |
| `ultraqa` | Autonomous QA pipeline — test generation + coverage analysis |
| `ralplan` | Ralplan consensus: architect + planner + critic in parallel |
| `team` | Team orchestration — tmux workers + git worktrees + MCP state |
| `plan` | Lightweight planning skill — produces `.omni/plans/<slug>.md` |
| `deep-interview` | Turn-based requirements gathering (redirected from router) |
| `deep-dive` | Deep exploratory analysis of a codebase area |
| `verify` | Completion verification — runs validator + tests + checks |
| `debug` | Structured debugging loop with tracer integration |
| `trace` | Causal trace across runs / state / audit log |
| `remember` | Persist a note to `.omni/` notepad or shared memory |
| `wiki` | Read / write / query the wiki MCP store |
| `external-context` | Fetch and summarise external documentation |
| `ask` | Single-question interactive prompt |
| `ai-slop-cleaner` | Detect and remove AI-generated filler language |
| `skill` | Invoke any other skill by name |
| `skillify` | Convert a raw prompt into a skill template |
| `setup` | Project bootstrap (init + doctor + configure) |
| `omni-setup` | Plugin-level setup and configuration |
| `omni-doctor` | Diagnose plugin health and environment |
| `omni-reference` | Look up plugin internals and docs |
| `omni-teams` | Manage multi-team configurations |
| `mcp-setup` | Configure the MCP server connection |
| `release` | Prepare a release artifact and preflight |
| `cancel` | Cancel a running mode / pipeline with cascade |
| `deepinit` | Deep project initialisation with full scan |
| `configure-notifications` | Wire Telegram / Slack / Discord webhooks for run events |

## MCP tools (20 tools, schema-validated)

All tools are served by `mcp/server.py` (stdio JSON-RPC 2.0, stdlib only).
Every `tools/call` is schema-validated; invalid payloads return a structured error.

**Memory:** `memory_capture`, `memory_search`, `memory_export`.
**Artifacts:** write to `.omni/runs/<run-id>/` directly; the canonical store is the filesystem. (The SQLite mirror `artifact_write` / `run_status` was removed in Phase-C C23 — see docs/ADR/ADR-0007-state-store-ownership.md.)
**State:** `state_write`, `state_read`, `state_clear`, `state_get_status`, `state_list_active`.
**Wiki:** `wiki_write`, `wiki_read`, `wiki_query`, `wiki_list`.
**Notepad:** `notepad_write`, `notepad_read`, `notepad_prune`.
**Shared memory:** `shared_memory_write`, `shared_memory_read`.
**Trace:** `trace_summary`, `trace_timeline`.
**Session:** `session_search`.
**Policy + health:** `policy_check`, `health`, `doctor`, `config_resolve`, `support_bundle`.

See `docs/STATE_MODES.md` for the full mode-key registry and ownership matrix (ADR-0007).

## Hook contract

Four lifecycle hooks enforce policy and produce audit evidence:

| Hook | Script | Key responsibilities |
|------|--------|---------------------|
| `sessionStart` | `hooks/session_start.py` | Banner, policy permission checks, metrics |
| `preToolUse` | `hooks/pre_tool_use.py` | Policy guard, shlex-safe argument parse |
| `postToolUse` | `hooks/post_tool_use.py` | Audit append, metrics write |
| `userPromptSubmit` | `hooks/user_prompt_submit.py` | Router decision, skill trigger hints |

Kill switches (any stops all hooks): `OMNI_SKIP_HOOKS=1`, `DISABLE_OMNI=1`.
Per-hook: `OMNI_SKIP_PRE_TOOL_USE=1`, `OMNI_SKIP_POST_TOOL_USE=1`, `OMNI_SKIP_SESSION_START=1`, `OMNI_SKIP_USER_PROMPT_SUBMIT=1`.
Deprecated aliases (removed in v3.0.0): `OMC_SKIP_HOOKS=1`, `DISABLE_OMC=1`. <!-- omni-rename-allow: OMC legacy env var names documented here -->

Full event shapes, audit schema, and metrics schema: `docs/HOOK_CONTRACT.md`.

## How skills invoke subagents

Skills use `scripts/subagent.py` to spawn subagents:

```python
from scripts.subagent import run_agent
run_agent("executor", "implement the plan in .omni/plans/run-001.md")
```

Or as a shell command inside a skill:

```bash
python3 "${COPILOT_PLUGIN_ROOT}/scripts/subagent.py" executor "..."
```

Either form spawns `copilot -p "..." --agent <name> --allow-all` as a subprocess.
Back-pressure: a file-lock semaphore caps concurrent subagents at `min(8, cpu_count())` (ADR-0010).
Overridable via `.omni/config.json > runtime.max_parallel_subagents`.

## Filesystem conventions (per project)

```
<project-root>/
├── AGENTS.md                  # this file — managed by `omni init`
├── .omni/
│   ├── config.json            # schema_version, models overrides, runtime config
│   ├── runs/<run-id>/{spec.md, plan.json, decisions.md, summary.md}
│   ├── specs/, plans/, decisions/
│   ├── audit/hooks.jsonl      # atomic, file-locked audit log
│   ├── audit/metrics.jsonl    # hook latency + router decision metrics
│   └── cache/banner.json      # session-start banner cache (keyed by manifest hash)
```

Global state: `$OMNI_HOME/omni.db` (default `~/.omni/omni.db`).

## Further reading

- [docs/ROUTER.md](docs/ROUTER.md) — front-door intent router, ADR-0005 scoring rubric
- [docs/MODELS.md](docs/MODELS.md) — semantic model categories, config overrides
- [docs/TEAM.md](docs/TEAM.md) — team orchestration internals
- [docs/HOOK_CONTRACT.md](docs/HOOK_CONTRACT.md) — hook contract, kill switches, audit schema
- [docs/STATE_MODES.md](docs/STATE_MODES.md) — mode-key registry, state ownership matrix
- [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) — test architecture, coverage gates, CI matrix
- [docs/MIGRATION.md](docs/MIGRATION.md) — v1 → v2 migration guide
- [docs/ADR/README.md](docs/ADR/README.md) — ADR index (ADR-0000 – ADR-0010)
