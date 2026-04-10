# Copilot Omni v1 Phase Roadmap

## Why this format
The product needs to be implemented as a release program, not as a single monolithic build. The architecture has hard external constraints from GitHub Copilot CLI, plus product-specific requirements around offline deployment, memory, security, and UX. Phase-gated delivery reduces risk by forcing each layer to become independently testable before the next layer depends on it.

## Master objective
Ship a production-ready v1 of Copilot Omni: a Copilot CLI plugin and bundled sidecar that delivers spec-driven workflows, guarded execution, local-first memory, bounded orchestration, and enterprise-safe distribution with minimal install burden.

## Global completion criteria for v1
- All phase exit gates pass on the supported operating-system matrix.
- The product installs without npm, PyPI, or Docker dependencies at install time.
- The product can plan, execute, verify, resume, remember, and audit a task end-to-end with artifacts as the source of truth.
- Strict-profile operation is supportable in corporate environments with limited registry access and constrained policies.
- Performance, migration, and support tooling meet the GA targets.

## Phase summary
### phase-0 — Foundation, Packaging, and Bootstrap
**Objective**: Create the installable substrate: plugin manifest, namespaced file layout, sidecar skeleton, config layering, bootstrap generation, and diagnostics. This phase proves that the product can be installed and operated inside locked-down corporate environments before any intelligence-heavy features are added.
**Depends on**: None
**Primary outputs**: Plugin repository skeleton, Sidecar bootstrap binary skeleton, Config schema and profile schema, Init/bootstrap generator, Doctor diagnostics engine, Compatibility matrix and install docs
**Promotion condition**: Plugin installs successfully from `copilot plugin install ./PATH/TO/PLUGIN` on macOS, Linux, and Windows test environments.

### phase-1 — Spec-Driven Workflow Core
**Objective**: Implement the first real product loop: discuss, spec, plan, and prepare execution as an artifact-backed state machine. This phase establishes the product's discipline and makes all later autonomy answerable to explicit artifacts.
**Depends on**: phase-0
**Primary outputs**: Run state machine, Spec and plan schemas, Conductor/planner/reviewer/verifier agents, Phase transcript export and summary generation, CLI entry points for run, plan, and resume
**Promotion condition**: A feature prompt produces a complete spec, plan, and decisions artifact set with stable IDs and machine-readable status.

### phase-2 — Guarded Execution and Verification Engine
**Objective**: Turn plans into safe code changes. This phase adds the execution machinery, the guardrails, the verification pipelines, and the fail-closed behavior that make the product usable on real repositories.
**Depends on**: phase-0, phase-1
**Primary outputs**: Guarded execution engine, MCP tools for patching, verification, and repo map, Hooks-based policy layer, Execution journal and rollback metadata, Reviewer/verifier gating
**Promotion condition**: Attempted writes outside the current plan are blocked in strict and standard profiles.

### phase-3 — Local Memory, Retrieval, and Deep Resumability
**Objective**: Add a local-first memory layer that remembers decisions, plans, failures, and repository-specific facts without depending on preview enterprise features. The goal is not novelty; it is reliable recall.
**Depends on**: phase-0, phase-1, phase-2
**Primary outputs**: Memory schema and storage engine, Artifact and summary ingestion pipeline, Memory search and capture commands, Retention and privacy controls, Deep resume context hydrator
**Promotion condition**: A previous decision can be retrieved with explicit source references to the originating run and artifact.

### phase-4 — Research, Subagents, and Parallel Workflows
**Objective**: Introduce bounded parallelism and deeper research without losing determinism. This phase captures the strongest orchestration ideas from Sisyphus and Oh My OpenAgent, but adapts them to Copilot CLI's real operating constraints.
**Depends on**: phase-0, phase-1, phase-2, phase-3
**Primary outputs**: Research workflow and report format, Subtask scheduler, Isolated workspace strategy, Merge and review pipeline, Intent and capability router
**Promotion condition**: Parallel read-only research runs complete without modifying the main worktree.

### phase-5 — Enterprise Policy, Offline Distribution, and Operability
**Objective**: Make the product genuinely deployable in conservative corporate environments. This phase hardens packaging, policy packs, offline installation, release signing, and auditability.
**Depends on**: phase-0, phase-1, phase-2, phase-3, phase-4
**Primary outputs**: Release bundle format, Policy packs and validator, Offline installation guides and scripts, Audit export tools, Enterprise diagnostics and compatibility matrix
**Promotion condition**: The product installs from a local marketplace root added via `copilot plugin marketplace add /PATH/TO/MARKETPLACE`.

### phase-6 — GA Hardening, Performance, UX Polish, and v1 Launch
**Objective**: Stabilize everything into a production-grade v1. This phase is not for new feature families; it is for latency, migrations, benchmarks, supportability, observability, and user confidence.
**Depends on**: phase-0, phase-1, phase-2, phase-3, phase-4, phase-5
**Primary outputs**: Performance budgets and benchmark harness, Migration engine and rollback tooling, Support bundle generator, Polished UX and help surfaces, GA release checklist and operator docs
**Promotion condition**: All prior phase exit criteria continue to pass under the GA test matrix.

## Sequencing logic
### 1. Foundation first
Packaging, namespacing, config precedence, bootstrap generation, and diagnostics are phase-0 concerns because every later phase depends on them implicitly. If these are unstable, every feature above them is expensive to debug.

### 2. Discipline before autonomy
Spec, plan, decisions, and resume come before execution because they make the system inspectable. Execution without artifacts becomes impossible to verify or govern later.

### 3. Safety before memory
Guarded execution comes before advanced memory because persistent memory of unsafe behavior is not a product advantage. The execution layer must be safe and audit-ready before the memory layer records and amplifies it.

### 4. Memory before orchestration
Parallelism and deeper orchestration benefit from knowing prior decisions, failures, and repo-specific patterns. A memory spine reduces repeated mistakes and makes orchestration more answerable.

### 5. Enterprise operability before GA
There is no point in calling the product production-ready if offline distribution, policy packs, release signing, and audit export remain unfinished.

### 6. Hardening last
GA work focuses on migrations, performance, observability, docs, and regression prevention. It should be done once the feature surface is materially complete.

## Gate policy
- No phase starts implementation until the previous phase's acceptance criteria, regression suite, and rollback notes are complete.
- If a phase misses performance or safety targets, the next phase does not absorb the problem by workaround. The phase is reopened and fixed.
- Any cross-phase change that invalidates prior acceptance must update the affected phase documents and rerun the relevant tests.

## Cross-phase architectural constants
- **Hybrid runtime** — Use a native GitHub Copilot CLI plugin for user-facing integration and a bundled local sidecar binary for memory, policy, orchestration state, and guarded tools.
- **Artifact-first execution** — Every run must produce durable artifacts: spec, plan, decisions, execution log, verification report, and state metadata. Artifacts are the source of truth, not the live chat transcript.
- **Fresh-context phases** — Run discuss, plan, execute, and verify as separate bounded contexts. Use programmatic Copilot invocations for phase transitions to reduce context drift.
- **Local-first and enterprise-safe** — Default to local storage, local binaries, and offline-capable installation. External registries, cloud memory, and experimental features are optional accelerators, not core dependencies.
- **Security as a product feature** — Treat enterprise GitHub policy as advisory. Enforce policy in the sidecar and hooks, with path validation, prompt-injection scanning, command allowlists, protected paths, and audit trails.
- **Copilot-native where possible** — Use plugins, agents, skills, hooks, MCP, plan mode, /research, /fleet, and session persistence where they fit. Do not fight built-ins when composition is enough.
- **Namespaced everything** — Prefix agents, skills, commands, servers, and files to avoid precedence collisions with project-level or personal configurations.
- **Strict phase gates** — No phase advances until installability, correctness, UX, and rollback gates pass. Each phase must be independently shippable and diagnosable.
- **Minimal install burden** — No npm, PyPI, Docker, or system Python requirement at install time for the plugin itself. Ship static sidecar binaries and plain files.
- **Stable UX over feature count** — Prefer one coherent entry flow with predictable artifacts and diagnostics over a broad command surface that users need to memorize.

## Open program-level decisions
- Final product name.
- Exact supported-version window for Copilot CLI and OS releases.
- Whether embeddings remain optional in v1 or become a post-v1 capability.
- Whether write-capable parallel execution is allowed in phase 4 or deferred if worktree isolation is not reliable enough.