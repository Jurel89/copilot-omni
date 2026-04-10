# GA Hardening, Performance, UX Polish, and v1 Launch — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-6
- Status: Draft
- Depends on: phase-0, phase-1, phase-2, phase-3, phase-4, phase-5
- Type: Product requirements document

## Objective
Stabilize everything into a production-grade v1. This phase is not for new feature families; it is for latency, migrations, benchmarks, supportability, observability, and user confidence.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Set and hit performance budgets for startup, planning, retrieval, execution overhead, and verification orchestration.
- Finalize migrations, backward compatibility, and failure recovery across releases.
- Polish the UX for status, progress, errors, dry-run, interactive approval, and summary output.
- Build benchmark suites and red-team suites that guard against regressions.
- Prepare support docs, operator guides, and GA release criteria.

## Non-goals
- No new major capability families unless a GA blocker is discovered.
- No scope creep into SaaS control-plane features.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A new user can install, initialize, plan, execute, verify, inspect artifacts, and recover from failure without reading source code.
- An operator can diagnose configuration, policy, memory, or packaging issues quickly from one support bundle.
- A team can upgrade from earlier pre-GA builds with explicit migrations and rollback paths.

## Scope
### In scope
- Performance budgets and benchmark harness
- Migration engine and rollback tooling
- Support bundle generator
- Polished UX and help surfaces
- GA release checklist and operator docs

### Out of scope
- No new major capability families unless a GA blocker is discovered.
- No scope creep into SaaS control-plane features.

## Functional requirements
- **PHASE-6-FR-001** — The product shall implement versioned migrations for config, artifact schemas, and memory schemas.
- **PHASE-6-FR-002** — The product shall provide dry-run and summary modes that explain planned actions without performing them.
- **PHASE-6-FR-003** — The product shall expose support-bundle generation for diagnostics with redaction controls.
- **PHASE-6-FR-004** — The product shall publish benchmark results and maintain a regression gate in CI.
- **PHASE-6-FR-005** — The product shall offer UX affordances for current phase, active policy profile, run health, pending blockers, and next recommended command.

## Non-functional requirements
- **PHASE-6-NFR-001** — Cold start p95 for wrapper plus sidecar health must stay within the agreed product budget.
- **PHASE-6-NFR-002** — Memory retrieval, policy checks, and artifact hydration must not dominate the perceived latency of normal runs.
- **PHASE-6-NFR-003** — Upgrade and downgrade paths must be reversible within the supported version window.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Cold start p95: <= 1.5 s on target dev hardware
- Memory search warm p95: <= 150 ms
- Regression escape rate from benchmark suite: 0 critical regressions
- Support bundle usefulness in seeded incidents: >= 90% issue triage success

## Deliverables
- Performance budgets and benchmark harness
- Migration engine and rollback tooling
- Support bundle generator
- Polished UX and help surfaces
- GA release checklist and operator docs

## Test strategy
- Unit tests for schema validation, config resolution, path handling, and policy evaluation.
- Integration tests that invoke the wrapper and Copilot programmatic flow against seeded fixture repositories.
- Cross-platform packaging and install tests on clean VM or container images where applicable.
- Adversarial tests for prompt injection, protected-path bypass, invalid config, and crash recovery.
- Human evaluation sessions on representative repositories before the phase is declared complete.

## Rollout strategy
- Dogfood internally behind a feature flag or profile toggle.
- Run the phase on at least one small, one medium, and one large repository before promotion.
- Freeze scope after acceptance criteria are met and only fix blockers before starting the next phase.

## Risks and mitigations
- Late performance work can reveal architectural bottlenecks that should have been fixed earlier.
- Migration bugs can silently damage local state if schema boundaries are weak.
- Benchmark coverage can be misleading if the repo corpus is too friendly.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- All prior phase exit criteria continue to pass under the GA test matrix.
- Performance budgets are met on representative repositories and developer machines.
- Upgrade and rollback scenarios succeed on supported pre-GA versions.
- Red-team and adversarial suites pass with no unresolved critical findings.
- User-facing docs and operator docs are complete and version-matched.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
