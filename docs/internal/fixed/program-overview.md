# Copilot Omni v1 Program

This document set replaces the idea of a single `v0.1` scope with a **phase-gated implementation program**. Each phase has its own PRD, architecture document, deliverables, test plan, acceptance criteria, and handoff conditions.

The intended working rule is simple: **finish one phase, stabilize it, test it, fix it, then advance**. No phase should depend on implicit future work.

## File map
- `roadmap/v1-phase-roadmap.md` — master sequencing and phase logic
- `roadmap/phase-gate-checklist.md` — mandatory gate checklist before promotion
- `decisions/architecture-principles.md` — cross-phase design rules
- `decisions/target-system-architecture.md` — global system architecture and canonical repo/data layout
- `decisions/source-alignment.md` — how external inspirations map into the product
- `phases/*-prd.md` — product requirements per phase
- `phases/*-architecture.md` — architecture documents per phase
- `program-manifest.json` — machine-readable phase map

## Recommended execution order
1. Phase 0 — Foundation, Packaging, and Bootstrap
2. Phase 1 — Spec-Driven Workflow Core
3. Phase 2 — Guarded Execution and Verification Engine
4. Phase 3 — Local Memory, Retrieval, and Deep Resumability
5. Phase 4 — Research, Subagents, and Parallel Workflows
6. Phase 5 — Enterprise Policy, Offline Distribution, and Operability
7. Phase 6 — GA Hardening, Performance, UX Polish, and v1 Launch

## Global rules
- Use a native GitHub Copilot CLI plugin for user-facing integration and a bundled local sidecar binary for memory, policy, orchestration state, and guarded tools.
- Every run must produce durable artifacts: spec, plan, decisions, execution log, verification report, and state metadata. Artifacts are the source of truth, not the live chat transcript.
- Run discuss, plan, execute, and verify as separate bounded contexts. Use programmatic Copilot invocations for phase transitions to reduce context drift.
- Default to local storage, local binaries, and offline-capable installation. External registries, cloud memory, and experimental features are optional accelerators, not core dependencies.
- Treat enterprise GitHub policy as advisory. Enforce policy in the sidecar and hooks, with path validation, prompt-injection scanning, command allowlists, protected paths, and audit trails.
- Use plugins, agents, skills, hooks, MCP, plan mode, /research, /fleet, and session persistence where they fit. Do not fight built-ins when composition is enough.
- Prefix agents, skills, commands, servers, and files to avoid precedence collisions with project-level or personal configurations.
- No phase advances until installability, correctness, UX, and rollback gates pass. Each phase must be independently shippable and diagnosable.
- No npm, PyPI, Docker, or system Python requirement at install time for the plugin itself. Ship static sidecar binaries and plain files.
- Prefer one coherent entry flow with predictable artifacts and diagnostics over a broad command surface that users need to memorize.

## Naming note
`Copilot Omni` is a working product name used in this planning set. It can be renamed later without changing the architecture or phase sequence.
