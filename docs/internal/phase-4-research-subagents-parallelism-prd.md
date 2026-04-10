# Guarded Execution and Verification Engine — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-2
- Status: Draft
- Depends on: phase-0, phase-1
- Type: Product requirements document

## Objective
Turn plans into safe code changes. This phase adds the execution machinery, the guardrails, the verification pipelines, and the fail-closed behavior that make the product usable on real repositories.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Implement execution of atomic tasks under explicit policy and plan constraints.
- Add guarded write, guarded patch, repo-map, and verification MCP tools in the sidecar.
- Implement policy hooks for shell commands, protected paths, and planning-artifact integrity.
- Bound autopilot to task-level execution, never to the entire product lifecycle.
- Add independent review and verification before tasks and runs can be marked complete.

## Non-goals
- No broad memory search beyond current-run artifacts.
- No cross-task parallel code writing yet.
- No remote repository delegation dependency.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A developer approves a plan and runs `omni execute`, which works task by task and stops on violations or failed verification.
- A security-conscious team enables strict profile and sees prohibited shell commands, protected paths, and prompt-injected planning files blocked automatically.
- A reviewer inspects verification reports and independent review findings before merging the work.

## Scope
### In scope
- Guarded execution engine
- MCP tools for patching, verification, and repo map
- Hooks-based policy layer
- Execution journal and rollback metadata
- Reviewer/verifier gating

### Out of scope
- No broad memory search beyond current-run artifacts.
- No cross-task parallel code writing yet.
- No remote repository delegation dependency.

## Functional requirements
- **PHASE-2-FR-001** — The product shall execute only tasks that exist in an approved plan and whose dependencies are satisfied.
- **PHASE-2-FR-002** — The sidecar shall expose guarded MCP tools for patch application, repo mapping, verification runs, and policy evaluation.
- **PHASE-2-FR-003** — Pre-tool policy checks shall block prohibited shell commands, protected paths, unplanned file writes, and unsafe planning-artifact mutations.
- **PHASE-2-FR-004** — The product shall scan planning artifacts and task inputs for prompt-injection patterns before reuse.
- **PHASE-2-FR-005** — Each task shall record before/after file sets, executed commands, verification outputs, and reviewer findings.
- **PHASE-2-FR-006** — The verifier shall run configured build, lint, test, formatting, and custom checks per task or per run, based on plan metadata.
- **PHASE-2-FR-007** — A failed task shall stop the run, preserve logs, and emit a deterministic rollback recommendation.

## Non-functional requirements
- **PHASE-2-NFR-001** — Guardrail checks must add negligible overhead relative to normal command execution.
- **PHASE-2-NFR-002** — Policy failures must be explicit, reproducible, and logged with reason codes.
- **PHASE-2-NFR-003** — Execution must remain resumable after process interruption or CLI crash.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Unsafe command escape rate in adversarial tests: 0
- Verification failure attribution completeness: >= 95% of failed runs name the failing command and artifact
- Resume-after-crash success during execution: >= 90%

## Deliverables
- Guarded execution engine
- MCP tools for patching, verification, and repo map
- Hooks-based policy layer
- Execution journal and rollback metadata
- Reviewer/verifier gating

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
- Guardrails can become so restrictive that the system is unusable if policies are not profile-driven.
- Patching strategies can become brittle across large refactors unless repo mapping and file targeting are strong.
- Verification latency can dominate execution time on big repositories.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- Attempted writes outside the current plan are blocked in strict and standard profiles.
- Injected malicious text in planning artifacts is detected or sanitized before execution continues.
- Each completed task has a verification report and independent review outcome.
- Adversarial tests confirm that deny rules override allow rules and that protected paths cannot be edited without explicit policy.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
