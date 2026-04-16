# Phase-C Backlog

Items explicitly deferred from Phase B. Each entry notes the WS/commit that spawned it.

---

## Hardening

| Item | Source |
|------|--------|
| Router intent classification — full 16-class skill chooser (Critic P8) | wave-2.x-patch-report / B4 |
| Windows native back-pressure + background-detach (`CREATE_NEW_PROCESS_GROUP`) | wave-2.x-patch-report / Critic P9 |
| Falling exemption-cap schedule (25 → 22 → 18 → 12) | wave-2.x-patch-report / Critic P7 |
| Audit log directory permissions — `.omni/audit/` created `0700` not `0755` | wave-3-WS7-report / audit finding 10.4 |
| Unicode NFC/NFD path normalisation in protected-path matching | wave-2-WS8-report / audit finding 2.3 |
| MCP connection pool — reuse connections across tool calls (currently one-per-call) | wave-2-WS8-report / audit finding 11.2 |
| MCP context manager consistency — standardise `_Conn` usage across all handlers | wave-2-WS8-report / audit finding 11.3 |
| Per-subagent memory policing (cap concurrency AND memory) | phase-b-master-plan / ADR-0010 |
| Pipeline e2e test guards → explicit asserts (currently vacuous `if X.exists()`) | wave-2.x-patch-report / code-reviewer test theatre |
| `ralplan` heredoc → sentinel-file refactor (eliminate shell-if heredoc pattern) | wave-2.x-patch-report / Critic P10 |

## Portability

| Item | Source |
|------|--------|
| Full Windows CI lane for `subagent_pool` + background-detach | wave-3-WS10-report / WS10 gaps |
| Windows native tmux team mode (remove `OMNI_EXPERIMENTAL_TEAM=1` gate) | phase-b-master-plan / ADR-0004 |
| Cross-OS portability audit — full Windows path coverage (Wave 3.5 scope) | wave-2.x-patch-report / Architect §7 |
| `deep-interview` on Copilot CLI `-p` — verify turn-based UX works end-to-end | phase-b-master-plan / ADR-0011 |

## Features

| Item | Source |
|------|--------|
| `configure-notifications` skill — restore from `.omni/deferred/` | wave-1-WS2-report / WS2 triage |
| `deep-interview` redesign — challenge-agent pruning, ambiguity-scoring rework | phase-b-master-plan / locked decision 8 |
| Wiki / memory ingestion hooks, knowledge-graph features | phase-b-master-plan / explicit non-goal |
| LSP tools, ast-grep tools (Phase C knowledge layer) | phase-b-master-plan / explicit non-goal |
| Four-gate taxonomy (GSD-style phase state machine) | phase-b-master-plan / P2-3 |
| Artifact-first lifecycle | phase-b-master-plan / P2-4 |
| i18n / multi-language `SKILL.md` variants | phase-b-master-plan / non-goal |
| `omni_migrate_v1_to_v2.py --rollback` path documented as last-resort | phase-b-master-plan / ADR-0008 |
| `remove artifact_write` and `run_status` if still UNUSED-OUTSIDE-TESTS at Phase C gate | wave-2-WS8-report / TODO Phase C |
| Re-introduce `memory_prune` and `notepad_prune` with TTL-based cleanup | wave-2-WS8-report / TODO Phase C |
| Router: enforce `<router-decision>` at the transport layer (currently advisory) | wave-2-WS3-report |
| OOM back-pressure — memory-level limiting for subagents | wave-2-WS3-report / Critic §6 #3 |
| Trigger priority / disambiguation — declare primary skill when multiple triggers match | wave-3-WS7-report / audit finding 5.1 |

## Tests

| Item | Source |
|------|--------|
| Real-Copilot nightly CI job (requires Copilot subscription in CI) | wave-3-WS10-report / WS10 gaps |
| Mutation testing on coverage-gated modules | wave-3-WS10-report / WS10 gaps |
| MCP multi-process migration race — dedicated stress test | wave-3-WS10-report / WS10 gaps |
| `ralplan` heredoc bash path — real-bash (non-FAKE) regression test | wave-3-WS10-report / WS10 gaps |
| Test artifact lifetime GC — `.omni/runs/<run-id>/` auto-cleanup | phase-b-master-plan / Critic §6 #5 |
| Structured cancel reasons + partial-cancel (one branch of a team) | wave-3-WS6-report |
