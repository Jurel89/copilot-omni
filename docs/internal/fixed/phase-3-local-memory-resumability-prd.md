# Local Memory, Retrieval, and Deep Resumability — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-3
- Status: Draft
- Depends on: phase-0, phase-1, phase-2
- Type: Product requirements document

## Objective
Add a local-first memory layer that remembers decisions, plans, failures, and repository-specific facts without depending on preview enterprise features. The goal is not novelty; it is reliable recall.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Create project-local and optional user-global memory stores backed by SQLite.
- Ingest specs, plans, decisions, verification outcomes, and selected session summaries into memory.
- Provide fast lexical retrieval first, with structured metadata and recency scoring.
- Implement explicit memory commands for search, capture, prune, export, and privacy controls.
- Support deep resume that reconstructs run context from artifacts and memory, not from a long chat window.

## Non-goals
- No mandatory embeddings in this phase.
- No cloud-synced memory service.
- No automatic ingestion of every token from every transcript.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A developer asks why a previous architecture choice was made and gets the original decision, linked spec, and later verification impact.
- A team member resumes a task after days or weeks and retrieves the last known plan, blockers, failed commands, and relevant decisions.
- A security team verifies that all memory remains local and can be scrubbed or exported under policy.

## Scope
### In scope
- Memory schema and storage engine
- Artifact and summary ingestion pipeline
- Memory search and capture commands
- Retention and privacy controls
- Deep resume context hydrator

### Out of scope
- No mandatory embeddings in this phase.
- No cloud-synced memory service.
- No automatic ingestion of every token from every transcript.

## Functional requirements
- **PHASE-3-FR-001** — The sidecar shall maintain a project memory database and may maintain a user-global memory database if enabled.
- **PHASE-3-FR-002** — The ingestion pipeline shall store artifact-derived memory records with type, source, scope, timestamp, run ID, repository fingerprint, and sensitivity metadata.
- **PHASE-3-FR-003** — The product shall support lexical and metadata search over memory records with deterministic ranking and explicit source attribution.
- **PHASE-3-FR-004** — Memory capture shall support explicit user-authored notes and system-generated summaries, with different trust levels.
- **PHASE-3-FR-005** — The product shall provide retention controls, project wipe, selective delete, and export capabilities.
- **PHASE-3-FR-006** — Resume shall hydrate the current task context from memory plus artifacts and shall not require experimental `/chronicle` support.

## Non-functional requirements
- **PHASE-3-NFR-001** — Memory search p95 latency must stay below 150 ms on a warm local database for medium-sized projects.
- **PHASE-3-NFR-002** — Memory ingestion must not block the main UX path for long-running executions.
- **PHASE-3-NFR-003** — All memory operations must function without internet access.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Recall precision on curated benchmark queries: >= 85%
- Incorrect source attribution: 0 tolerance
- Warm-query p95 latency: <= 150 ms

## Deliverables
- Memory schema and storage engine
- Artifact and summary ingestion pipeline
- Memory search and capture commands
- Retention and privacy controls
- Deep resume context hydrator

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
- Over-ingestion can fill the database with low-signal noise.
- Memory ranking can overfit to recency and hide older but still correct decisions.
- Sensitive data can be captured if ingestion boundaries are not explicit.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- A previous decision can be retrieved with explicit source references to the originating run and artifact.
- Project memory can be wiped completely and independently of global memory.
- Resume after a week-long pause reconstructs task context without requiring manual browsing of old transcripts.
- Memory search remains fast on seeded repositories with at least 50 runs worth of artifacts.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
