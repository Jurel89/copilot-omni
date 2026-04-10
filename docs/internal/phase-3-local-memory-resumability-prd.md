# Spec-Driven Workflow Core — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-1
- Status: Draft
- Depends on: phase-0
- Type: Product requirements document

## Objective
Implement the first real product loop: discuss, spec, plan, and prepare execution as an artifact-backed state machine. This phase establishes the product's discipline and makes all later autonomy answerable to explicit artifacts.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Define the canonical state model for runs, specs, plans, decisions, and tasks.
- Ship the conductor, planner, verifier, and reviewer agents with namespaced identities.
- Implement the `/omni`, `/omni-plan`, and `omni run|plan|resume` entry points.
- Use fresh-context Copilot invocations per phase and store transcripts and summaries as artifacts.
- Ensure no execution starts until a valid spec and plan exist.

## Non-goals
- No memory ranking beyond direct artifact lookup.
- No parallel execution yet.
- No automatic code writing without an explicit task plan.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A developer describes a feature in plain language and receives a generated spec, decisions log, and implementation plan.
- A staff engineer pauses work after plan generation, reviews the artifacts in Git, and resumes later with `omni resume`.
- A team lead uses the generated plan to split work and estimate risk before any code is changed.

## Scope
### In scope
- Run state machine
- Spec and plan schemas
- Conductor/planner/reviewer/verifier agents
- Phase transcript export and summary generation
- CLI entry points for run, plan, and resume

### Out of scope
- No memory ranking beyond direct artifact lookup.
- No parallel execution yet.
- No automatic code writing without an explicit task plan.

## Functional requirements
- **PHASE-1-FR-001** — The product shall represent each run with a stable run ID and status transitions: `draft`, `spec_ready`, `plan_ready`, `executing`, `verifying`, `done`, `blocked`, `aborted`.
- **PHASE-1-FR-002** — The product shall generate `spec.md`, `plan.json`, and `decisions.md` under `.omni/` for every user-requested run.
- **PHASE-1-FR-003** — The product shall require spec approval state before execution can begin in strict profile; standard profile may allow inline continuation with an explicit confirmation artifact.
- **PHASE-1-FR-004** — The product shall run discuss, spec, plan, and review as separate bounded Copilot sessions or bounded subagent turns and record phase transcripts.
- **PHASE-1-FR-005** — The planner shall decompose work into atomic tasks with dependencies, file targets, commands, and verification expectations.
- **PHASE-1-FR-006** — The reviewer agent shall check the plan against the spec and emit blocking findings before execution is allowed.

## Non-functional requirements
- **PHASE-1-NFR-001** — Spec generation must be reproducible enough that rerunning with the same inputs produces materially equivalent scope and acceptance criteria.
- **PHASE-1-NFR-002** — Artifact writes must be append-safe and crash-resilient.
- **PHASE-1-NFR-003** — The UX must make the current phase and next required action obvious at all times.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Plan acceptance rate by reviewers during pilot: >= 80% without manual rewrite
- Unplanned file touches during later execution: < 5% of modified files
- Resume success after interrupted planning run: >= 95%

## Deliverables
- Run state machine
- Spec and plan schemas
- Conductor/planner/reviewer/verifier agents
- Phase transcript export and summary generation
- CLI entry points for run, plan, and resume

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
- Overly rigid artifacts can slow down small tasks if profiles and shortcuts are badly designed.
- Spec quality can degrade if the discussion phase is too shallow or too verbose.
- Fresh-context orchestration can increase latency if artifact hydration is inefficient.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- A feature prompt produces a complete spec, plan, and decisions artifact set with stable IDs and machine-readable status.
- Execution is blocked if the plan lacks required verification steps or if review finds unresolved blocking issues.
- Interrupted runs can be resumed without duplicate artifact creation or lost decisions.
- Every task in the plan names intended files, expected verification commands, and a rollback note.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
