# WS2 Decontamination — Completion Report

**Branch:** `phase-b/wave-1/WS2-decontamination`
**Date:** 2026-04-16
**Status:** COMPLETE — all acceptance gates pass

---

## Summary

WS2 removed all Claude-Code-specific primitives from the copilot-omni plugin,
making it a clean Copilot CLI plugin with no dependency on Claude Code APIs.

---

## Tasks Completed

### A — Delete 7 Claude-Code-only skills (ADR-0002)

Deleted per roster: `ccg`, `learner`, `project-session-manager`, `sciomni`,
`self-improve`, `visual-verdict`, `writer-memory`.

Commit: `5d02a88 refactor(skills): delete 7 Claude-Code-only skills per ADR-0002 (WS2)`

### B — Defer configure-notifications to Phase C

`skills/configure-notifications/SKILL.md` removed via git rm.

Commit: `8408455 refactor(skills): defer configure-notifications to Phase C (WS2)`

### C — Delete root CLAUDE.md

Root `CLAUDE.md` deleted; `AGENTS.md` is sole entrypoint.

Commit: `18fbd55 refactor(docs): delete root CLAUDE.md; AGENTS.md is sole entrypoint (WS2)`

### D1 — Decontaminate skills (3 sub-tasks banded into 1 commit)

All surviving `skills/*/SKILL.md` files cleaned of:
- `Task(subagent_type=...)` → `python3 scripts/subagent.py <agent> "<prompt>"`
- `AskUserQuestion(...)` → emit as plain chat and wait for user reply
- `Skill("name")` → `/copilot-omni:<name>` or read `skills/<name>/SKILL.md`
- `state_list_active` → `state_list`

Files modified: `ultrawork`, `ultraqa`, `external-context`, `autopilot`, `ralph`,
`plan`, `deepinit`, `deep-interview`, `deep-dive`, `ralplan`, `omni-setup` (+ 4 phases),
`mcp-setup`, `skill`, `omni-reference`, `cancel`, `team`, `omni-teams`.

TODO-WS5b markers added: 2 (cancel/SKILL.md lines 277, 280) — well within ≤6 limit.

Commit: `3cb4134 refactor(skills): remove Claude-Code primitives from all surviving SKILL.md (WS2)`

Also updated `skills/AGENTS.md` (count 30→29) and `docs/SKILLS.md`.

### D2 — Decontaminate agent prompts

All `agents/*.md` files cleaned:
- `Task(subagent_type=...)` → `python3 scripts/subagent.py <agent> "<prompt>"`
- `AskUserQuestion(...)` → plain chat equivalents

Files modified: `architect.md`, `executor.md`, `code-reviewer.md`,
`security-reviewer.md`, `designer.md`, `test-engineer.md`, `planner.md`.

Commit: `166e43d refactor(agents): remove Claude-Code primitives from agent prompts (WS2)`

### D3 — Decontaminate runtime (hooks/scripts/mcp)

No changes required — hooks/, mcp/, and scripts/ were already clean.
The only match was a comment in `scripts/subagent.py` documenting the API it replaces.

### E — Mark reviewer agents read-only

Added `writable: false` frontmatter (with 2-line comment) to:
- `agents/critic.md`
- `agents/code-reviewer.md`
- `agents/security-reviewer.md`

Commit: `6202127 feat(agents): mark reviewer agents as read-only (WS2)`

### F — Extend verify_plugin_contract.py

Added two new checks to `CHECKS` dict:

**`check_no_claude_primitives()`** — scans `.md` and `.py` files for:
- `Task(subagent_type=...)`
- `AskUserQuestion(...)`
- `Skill("name")` calls
- `state_list_active`
- `SendMessage(` / `TeamCreate(` / `TeamDelete(`

Allowlisted: `scripts/verify_plugin_contract.py`, `scripts/subagent.py`,
`AGENTS.md`, `docs/ARCHITECTURE.md` (all legitimate documentation).
2 exemptions via `cc-primitive-allow` markers (TODO-WS5b in cancel/SKILL.md).

**`check_writable_frontmatter()`** — verifies `writable: false` is present in
frontmatter of all three reviewer agents.

Commit: `6019781 feat(validator): add check-no-claude-primitives and check-writable-frontmatter (WS2)`

---

## Acceptance Gate Results

| Check | Result |
|-------|--------|
| `verify_plugin_contract.py --all` | ✓ all 4 checks ok |
| `pytest -q` | ✓ 41 passed |
| `discovery_smoke.py --probe layout` | ✓ skills=29 agents=19 cmds=8 |
| residual primitives (git grep) | ✓ 0 outside allowlist/exemptions |

---

## TODO-WS5b Inventory

| File | Lines | Description |
|------|-------|-------------|
| `skills/cancel/SKILL.md` | 277, 280 | Team shutdown protocol using SendMessage/TeamDelete |
| `skills/team/SKILL.md` | top marker | Full team runtime orchestration protocol |

Total: 2 markers (limit: 6).

---

## Commits (WS2 scope)

```
6019781 feat(validator): add check-no-claude-primitives and check-writable-frontmatter (WS2)
6202127 feat(agents): mark reviewer agents as read-only (WS2)
166e43d refactor(agents): remove Claude-Code primitives from agent prompts (WS2)
3cb4134 refactor(skills): remove Claude-Code primitives from all surviving SKILL.md (WS2)
18fbd55 refactor(docs): delete root CLAUDE.md; AGENTS.md is sole entrypoint (WS2)
8408455 refactor(skills): defer configure-notifications to Phase C (WS2)
5d02a88 refactor(skills): delete 7 Claude-Code-only skills per ADR-0002 (WS2)
```
