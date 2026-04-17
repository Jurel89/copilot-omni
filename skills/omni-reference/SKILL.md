---
name: omni-reference
description: copilot-omni agent catalog, available tools, team pipeline routing, commit protocol, and skills registry. Auto-loads when delegating to agents, using copilot-omni tools, orchestrating teams, making commits, or invoking skills.
user-invocable: false
---

# copilot-omni Reference

Use this built-in reference when you need detailed copilot-omni catalog information that does not need to live in every `CLAUDE.md` session.

## Agent Catalog

Prefix: `copilot-omni:`. See `agents/*.md` for full prompts.

- `explore` (haiku) — fast codebase search and mapping
- `analyst` (opus) — requirements clarity and hidden constraints
- `planner` (opus) — sequencing and execution plans
- `architect` (opus) — system design, boundaries, and long-horizon tradeoffs
- `debugger` (sonnet) — root-cause analysis and failure diagnosis
- `executor` (sonnet) — implementation and refactoring
- `verifier` (sonnet) — completion evidence and validation
- `tracer` (sonnet) — trace gathering and evidence capture
- `security-reviewer` (sonnet) — trust boundaries and vulnerabilities
- `code-reviewer` (opus) — comprehensive code review
- `test-engineer` (sonnet) — testing strategy and regression coverage
- `designer` (sonnet) — UX and interaction design
- `writer` (haiku) — documentation and concise content work
- `qa-tester` (sonnet) — runtime/manual validation
- `scientist` (sonnet) — data analysis and statistical reasoning
- `document-specialist` (sonnet) — SDK/API/framework documentation lookup
- `git-master` (sonnet) — commit strategy and history hygiene
- `code-simplifier` (opus) — behavior-preserving simplification
- `critic` (opus) — plan/design challenge and review

## Model Routing

- `haiku` — quick lookups, lightweight inspection, narrow docs work
- `sonnet` — standard implementation, debugging, and review
- `opus` — architecture, deep analysis, consensus planning, and high-risk review

## Tools Reference

### External AI / orchestration
- `/team N:executor "task"`

### copilot-omni state
- `state_read`, `state_write`, `state_clear`

### Team runtime (Copilot CLI — via scripts/subagent.py or omni_team.py)
- `python3 scripts/subagent.py <agent> "<prompt>"` — spawn a single agent
- `python3 scripts/omni_team.py` — team lifecycle for native Copilot team skill

### Notepad
- `notepad_read`, `notepad_write`, `notepad_prune`

### Project memory
- `memory_capture`, `memory_search`, `memory_prune`, `memory_export`
- CLI: `omni memory search "query"`, `omni memory list`, `omni memory capture "text"`, `omni memory prune`, `omni memory export`

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

### Keyword triggers kept compact in CLAUDE.md
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

Move reference-only orchestration content into a native Claude skill so
session-start guidance stays small while detailed copilot-omni reference remains available.

Constraint: Preserve CLAUDE.md marker-based installation flow
Rejected: Sync all built-in skills in legacy install | broader behavior change than issue requires
Confidence: high
Scope-risk: narrow
Not-tested: End-to-end plugin marketplace install in a fresh Claude profile
```
