# Foundation, Packaging, and Bootstrap — PRD

## Document control
- Product: Copilot Omni
- Phase ID: phase-0
- Status: Draft
- Depends on: None
- Type: Product requirements document

## Objective
Create the installable substrate: plugin manifest, namespaced file layout, sidecar skeleton, config layering, bootstrap generation, and diagnostics. This phase proves that the product can be installed and operated inside locked-down corporate environments before any intelligence-heavy features are added.

## Problem statement
Copilot CLI provides a strong native foundation for plugins, agents, skills, hooks, and MCP integration, but it does not by itself give us a complete, enterprise-safe, artifact-driven development system. This phase exists to close a specific part of that gap in a way that is independently shippable and testable.

## Goals
- Ship a working plugin package with manifest, command directories, agent directories, skill directories, hooks, and MCP wiring.
- Ship prebuilt static sidecar binaries for the primary operating systems and architectures.
- Define the configuration model, precedence, profile system, and repo-local `.omni/` layout.
- Provide bootstrap commands that generate repository-wide instructions, path-specific instructions, AGENTS.md, and product config files.
- Provide a high-signal `doctor` experience that validates installation, binaries, permissions, config resolution, and platform support.

## Non-goals
- No persistent memory retrieval yet.
- No autonomous multi-phase execution yet.
- No parallel orchestration yet.
- No cloud dependency beyond the user's existing Copilot CLI service access.

## Primary users
- Platform engineers who need a packageable, supportable system.
- Product engineers who want one coherent command flow instead of a stack of partially compatible plugins.
- Security and operations stakeholders who need deterministic guardrails, logs, and recovery paths.

## User journeys
- A platform engineer installs the plugin from a local path or internal Git repository and validates it with `omni doctor`.
- A repository maintainer runs `omni init` to generate `.github/copilot-instructions.md`, `.github/instructions/`, `AGENTS.md`, and `.omni/config.json`.
- A developer opens `copilot`, sees `/omni-doctor` and `/omni-init`, and can confirm that the plugin is wired correctly without reading internal documentation.

## Scope
### In scope
- Plugin repository skeleton
- Sidecar bootstrap binary skeleton
- Config schema and profile schema
- Init/bootstrap generator
- Doctor diagnostics engine
- Compatibility matrix and install docs

### Out of scope
- No persistent memory retrieval yet.
- No autonomous multi-phase execution yet.
- No parallel orchestration yet.
- No cloud dependency beyond the user's existing Copilot CLI service access.

## Functional requirements
- **PHASE-0-FR-001** — The product shall expose a working plugin manifest with namespaced commands, agents, skills, hooks, and MCP server definitions.
- **PHASE-0-FR-002** — The product shall ship a wrapper binary named `omni` that can locate the plugin assets and the correct platform sidecar binary.
- **PHASE-0-FR-003** — The product shall support installation from local path, internal Git URL, and internal marketplace structures without requiring npm or PyPI at install time.
- **PHASE-0-FR-004** — The product shall generate repo-local bootstrap artifacts idempotently and preserve user edits outside marked managed sections.
- **PHASE-0-FR-005** — The product shall resolve config from built-in defaults, profile packs, global user config, repo config, environment variables, and CLI flags, in that order.
- **PHASE-0-FR-006** — The product shall include `omni doctor` checks for plugin manifest validity, sidecar presence, executable permissions, MCP startup, hooks presence, and supported Copilot CLI version.

## Non-functional requirements
- **PHASE-0-NFR-001** — Cold-start diagnosis must complete in under 2 seconds on a typical developer workstation with warm disk cache.
- **PHASE-0-NFR-002** — Bootstrap generation must be deterministic and idempotent.
- **PHASE-0-NFR-003** — The packaged plugin must have no runtime dependency on package managers or interpreters not already present in the OS.
- **PHASE-0-NFR-004** — Failure messages must name the failing component, probable cause, and exact remediation command.

## UX expectations
- The user must always know the current phase, the last completed action, the next safe action, and where the artifacts were written.
- Every blocking error must be paired with a remediation message and an artifact or log reference.
- The default path should remain terse for simple tasks, while preserving deeper artifacts for reviewers and operators.

## Configuration and artifacts
- All product-owned repo-local state for this phase lives under `.omni/`.
- User-global product settings live under `~/.copilot-omni/` unless an override path is provided.
- Generated instructions must use explicit managed regions where appropriate to preserve user ownership outside those regions.

## Success metrics
- Installation success rate in clean test VMs: >= 95%
- Doctor false-positive rate: < 2%
- Bootstrap re-run drift: zero unmanaged file corruption across 50 re-runs

## Deliverables
- Plugin repository skeleton
- Sidecar bootstrap binary skeleton
- Config schema and profile schema
- Init/bootstrap generator
- Doctor diagnostics engine
- Compatibility matrix and install docs

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
- Cross-platform binary packaging and path handling are easy to get almost right and still fail in enterprise images.
- Plugin precedence conflicts can silently shadow plugin agents or skills if names are too generic.
- Bootstrap generation can damage user-authored instructions if managed regions are not explicit.

## Exit gate
The phase is complete only when every acceptance criterion below passes on the target test matrix and all blocking defects are closed or formally deferred with a documented owner and rationale.

- Plugin installs successfully from `copilot plugin install ./PATH/TO/PLUGIN` on macOS, Linux, and Windows test environments.
- The sidecar starts through the plugin MCP definition and returns a successful health response.
- `omni init` creates the expected instruction and config files and preserves manual edits outside managed blocks on repeat runs.
- `omni doctor` catches all intentionally injected packaging faults in the test harness.

## Open questions
- Which items in this phase require strict-profile defaults versus standard-profile defaults?
- Which artifacts should be committed by default, and which should remain local-only?
- Which validation checks are phase blockers versus warnings?
