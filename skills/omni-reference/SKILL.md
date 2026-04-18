---
name: omni-reference
description: copilot-omni agent catalog, available tools, team pipeline routing, commit protocol, and skills registry. Auto-loads when delegating to agents, using copilot-omni tools, orchestrating teams, making commits, or invoking skills.
user-invocable: false
---

# copilot-omni Reference

Use this built-in reference when you need detailed copilot-omni catalog information that does not need to live in the always-loaded session instructions.

## Agent Catalog

Prefix: `copilot-omni:`. See `agents/*.md` for full prompts.

- `explore` — fast codebase search and mapping
- `analyst` — requirements clarity and hidden constraints
- `planner` — sequencing and execution plans
- `architect` — system design, boundaries, and long-horizon tradeoffs
- `debugger` — root-cause analysis and failure diagnosis
- `executor` — implementation and refactoring
- `verifier` — completion evidence and validation
- `tracer` — trace gathering and evidence capture
- `security-reviewer` — trust boundaries and vulnerabilities
- `code-reviewer` — comprehensive code review
- `test-engineer` — testing strategy and regression coverage
- `designer` — UX and interaction design
- `writer` — documentation and concise content work
- `qa-tester` — runtime/manual validation
- `scientist` — data analysis and statistical reasoning
- `document-specialist` — SDK/API/framework documentation lookup
- `git-master` — commit strategy and history hygiene
- `code-simplifier` — behavior-preserving simplification
- `critic` — plan/design challenge and review

## Execution Routing

- quick category — lightweight inspection and narrow docs work
- standard implementation lanes — implementation, debugging, and review
- deep/consensus lanes — architecture, deep analysis, and high-risk planning

## Tools Reference

### External AI / orchestration
- `/team N:executor "task"`

### copilot-omni state
- `state_read`, `state_write`, `state_clear`
- CLI: `omni state list`, `omni state show <mode>`

### Team runtime (Copilot CLI — via scripts/subagent.py or omni_team.py)
- `python3 scripts/subagent.py <agent> "<prompt>"` — spawn a single agent
- `python3 scripts/omni_team.py` — team lifecycle for native Copilot team skill

### Notepad
- `notepad_read`, `notepad_write`, `notepad_prune`
- CLI: `omni notepad list`, `omni notepad show <id>`

### Project memory
- `memory_capture`, `memory_search`, `memory_prune`, `memory_export`
- CLI: `omni memory search "query"`, `omni memory list`, `omni memory capture "text"`, `omni memory prune`, `omni memory export`

### Wiki
- `wiki_write`, `wiki_read`, `wiki_query`, `wiki_list`, `wiki_ingest`, `wiki_graph`
- CLI: `omni wiki list`, `omni wiki show <slug>`, `omni wiki search "query"`, `omni wiki graph`, `omni wiki validate`

### Codebase graph
- `codebase_graph`, `codebase_impact`
- CLI: `omni codebase graph`, `omni codebase impact <path>`
- Use this for repository-level file/import/reference relationships and immediate refactor impact; use wiki graph only for stored wiki-page links

### Shared memory
- `shared_memory_read`, `shared_memory_write`
- CLI: `omni shared-memory list`, `omni shared-memory show <key>`

### Trace
- `trace_summary`, `trace_timeline`
- CLI: `omni trace list`, `omni trace show <id>`, `omni trace timeline`

### Code intelligence
- LSP: `lsp_hover`, `lsp_goto_definition`, `lsp_find_references`
- AST: `ast_grep_search`, `ast_grep_replace`

## Skills Registry

Invoke built-in workflows via `/copilot-omni:<name>`.

### Workflow skills
- `autopilot` — full autonomous execution from idea to working code
- `ralph` — persistence loop until completion with verification
- `ultrawork` — high-throughput parallel execution
- `team` — coordinated team orchestration
- `ultraqa` — QA cycle: test, verify, fix, repeat
- `omni-plan` — planning workflow and `/plan`-safe alias
- `ralplan` — consensus planning workflow
- `external-context` — external docs/research workflow
- `deepinit` — hierarchical AGENTS.md generation
- `deep-interview` — Socratic ambiguity-gated requirements workflow
- `ai-slop-cleaner` — regression-safe cleanup workflow

### Utility skills
- `cancel`, `remember`, `omni-setup`, `mcp-setup`, `omni-doctor`, `omni-reference`, `trace`, `release`, `skill`

### Keyword triggers kept compact in the always-loaded session instructions
- `"autopilot"→autopilot`
- `"ralph"→ralph`
- `"ulw"→ultrawork`
- `"ralplan"→ralplan`
- `"deep interview"→deep-interview`
- `"deslop" / "anti-slop"→ai-slop-cleaner`
- `"deep-analyze"→analysis mode`
- `"tdd"→TDD mode`
- `"deepsearch"→codebase search`
- `"ultrathink"→deep reasoning`
- `"cancelomc"→cancel`
- Team orchestration is explicit via `/team`.

## Team Pipeline

Stages: `team-plan` → `team-prd` → `team-exec` → `team-verify` → `team-fix` (loop).

- Use `team-fix` for bounded remediation loops.
- `team ralph` links the team pipeline with Ralph-style sequential verification.
- Prefer team mode when independent parallel lanes justify the coordination overhead.

## Commit Protocol

Use git trailers to preserve decision context in every commit message.

### Format
- Intent line first: why the change was made
- Optional body with context and rationale
- Structured trailers when applicable

### Common trailers
- `Constraint:` active constraint shaping the decision
- `Rejected:` alternative considered | reason for rejection
- `Directive:` forward-looking warning or instruction
- `Confidence:` `high` | `medium` | `low`
- `Scope-risk:` `narrow` | `moderate` | `broad`
- `Not-tested:` known verification gap

### Example
```text
feat(docs): reduce always-loaded copilot-omni instruction footprint

Move reference-only orchestration content into a native copilot-omni skill so
session-start guidance stays small while detailed copilot-omni reference remains available.

Constraint: Preserve the lightweight always-loaded instruction footprint
Rejected: Sync all built-in skills in legacy install | broader behavior change than issue requires
Confidence: high
Scope-risk: narrow
Not-tested: End-to-end plugin marketplace install in a fresh Copilot CLI profile
```
