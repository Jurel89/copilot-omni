# Research, Subagents, and Parallel Workflows — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-4
- Status: Draft
- Depends on: phase-0, phase-1, phase-2, phase-3
- Type: Product requirements document

## Objective
Introduce bounded parallelism and deeper research without losing determinism. This phase captures the strongest orchestration ideas from Sisyphus and Oh My OpenAgent, but adapts them to Copilot CLI's real operating constraints.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Add a research workflow that can combine repo exploration, web research, and artifact memory.
- Use subagents and `/fleet`-style decomposition for bounded parallel work.
- Allow parallel read-only research in the main worktree and isolated write-capable subtasks in separate work directories or worktrees.
- Add merge, review, and conflict-detection stages for subtask outputs.
- Implement an intent and capability router that chooses between skills, agents, sidecar tools, and built-in Copilot features.

## Non-goals
- No dependency on `/delegate` or Copilot cloud agent to complete the local product workflow.
- No unrestricted swarm behavior with ambiguous ownership of the filesystem.
- No permanent background execution service.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A developer runs `omni research` and receives a structured report that blends web findings, repository evidence, and prior project decisions.
- A large refactor is split into bounded subtasks, each executed in isolation, then merged and reviewed against the spec.
- A planner uses parallel exploration to map impact across multiple subsystems before finalizing the plan.

## Scope
### In scope
- Research workflow and report format
- Subtask scheduler
- Isolated workspace strategy
- Merge and review pipeline
- Intent and capability router

### Out of scope
- No dependency on `/delegate` or Copilot cloud agent to complete the local product workflow.
- No unrestricted swarm behavior with ambiguous ownership of the filesystem.
- No permanent background execution service.

## Functional requirements
- **PHASE-4-FR-001** — The product shall support a research mode that can invoke built-in research-capable Copilot behavior and merge that output with local artifact and memory findings.
- **PHASE-4-FR-002** — The orchestrator shall decompose eligible work into subtasks with explicit scopes, inputs, output contracts, and verification requirements.
- **PHASE-4-FR-003** — Read-only subtasks may run in parallel against the main repository; write-capable subtasks must run in isolated workspaces.
- **PHASE-4-FR-004** — The product shall merge subtask outputs through a deterministic review pipeline that checks spec compliance first and code-quality second.
- **PHASE-4-FR-005** — The router shall load only the minimal required skills and tools for a task class to reduce context pollution.
- **PHASE-4-FR-006** — The run journal shall preserve lineage from parent task to subtask to merged result.

## Non-functional requirements
- **PHASE-4-NFR-001** — Parallel orchestration must not create hidden writes in the main working tree.
- **PHASE-4-NFR-002** — Subtask failure must not corrupt sibling task outputs.
- **PHASE-4-NFR-003** — Research reporting must clearly separate facts, inferences, and open questions.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Planning time reduction on large benchmark tasks: >= 25%
- Conflict-free subtask merge rate on targeted task classes: >= 80%
- Research report citation/source completeness: >= 95%

## Deliverables
- Research workflow and report format
- Subtask scheduler
- Isolated workspace strategy
- Merge and review pipeline
- Intent and capability router

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
- Parallelism can create attractive but unreliable demos if isolation and merge logic are weak.
- Web research can contaminate local engineering decisions if provenance is unclear.
- Subtask coordination overhead can erase the performance gains for smaller tasks.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- Parallel read-only research runs complete without modifying the main worktree.
- Write-capable subtasks run in isolated workspaces and can be discarded independently on failure.
- Merged outputs retain parent-child lineage and pass the same review and verification gates as serial tasks.
- Research reports explicitly tag external findings, repository evidence, prior-memory evidence, and open questions.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
