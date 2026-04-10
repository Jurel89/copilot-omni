# Enterprise Policy, Offline Distribution, and Operability — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-5
- Status: Draft
- Depends on: phase-0, phase-1, phase-2, phase-3, phase-4
- Type: Product requirements document

## Objective
Make the product genuinely deployable in conservative corporate environments. This phase hardens packaging, policy packs, offline installation, release signing, and auditability.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Ship signed, checksummed, versioned release bundles with sidecar binaries and plugin assets.
- Support local filesystem marketplace, internal Git, and repository auto-install patterns.
- Provide strict, standard, and permissive policy profiles with explicit defaults.
- Add audit exports, policy validation, and environment diagnostics for enterprise support teams.
- Ensure the product behaves sanely when GitHub enterprise policies, MCP allowlists, or model settings are restrictive or partially unavailable.

## Non-goals
- No hosted control plane.
- No dependency on external package registries.
- No attempt to replace GitHub's native enterprise administration interfaces.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A platform team publishes an internal bundle and installs it via a local filesystem marketplace in an offline lab.
- A repository enables the plugin through `enabledPlugins` and ships repo-scoped marketplace metadata for onboarding.
- A security team validates that strict profile disables auto-update, blocks external registries, and produces audit exports.

## Scope
### In scope
- Release bundle format
- Policy packs and validator
- Offline installation guides and scripts
- Audit export tools
- Enterprise diagnostics and compatibility matrix

### Out of scope
- No hosted control plane.
- No dependency on external package registries.
- No attempt to replace GitHub's native enterprise administration interfaces.

## Functional requirements
- **PHASE-5-FR-001** — The release process shall produce static binaries, checksums, signatures, SBOMs, and provenance metadata.
- **PHASE-5-FR-002** — The product shall support installation from local filesystem marketplace roots, internal Git URLs, and direct local paths.
- **PHASE-5-FR-003** — The product shall ship policy packs that control commands, tools, network access posture, protected paths, memory retention, and update behavior.
- **PHASE-5-FR-004** — The product shall validate active enterprise constraints and warn when GitHub settings limit available capabilities.
- **PHASE-5-FR-005** — The product shall expose audit exports for runs, policy decisions, verification outcomes, and packaging metadata.
- **PHASE-5-FR-006** — The product shall support portable operation through relocatable config and cache directories.

## Non-functional requirements
- **PHASE-5-NFR-001** — Offline installation must be documented, repeatable, and testable without internet access.
- **PHASE-5-NFR-002** — Policy pack validation must be deterministic and CI-friendly.
- **PHASE-5-NFR-003** — Release artifacts must be reproducible or close enough to support trustable provenance.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Air-gapped install success rate: >= 95%
- Policy validation false-negative rate: 0 on seeded policy test corpus
- Support time to diagnose packaging/config issues: reduced by >= 50% versus baseline

## Deliverables
- Release bundle format
- Policy packs and validator
- Offline installation guides and scripts
- Audit export tools
- Enterprise diagnostics and compatibility matrix

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
- Release engineering can become its own project if artifact formats and signing strategy are not fixed early.
- Enterprises may expect GitHub policy to enforce things it currently does not strictly enforce.
- Portable installations can create path and update edge cases.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- The product installs from a local marketplace root added via `copilot plugin marketplace add /PATH/TO/MARKETPLACE`.
- Strict profile disables or warns on features that rely on experimental or weakly enforced enterprise controls.
- Audit exports contain sufficient data to reconstruct run status, verification state, and policy decisions without exposing secrets.
- Offline install tests pass on macOS, Linux, and Windows images with no package-manager access.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
