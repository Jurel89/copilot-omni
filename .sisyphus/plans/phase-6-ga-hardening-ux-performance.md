# Phase 6 Plan — GA Hardening, UX, and Performance

## 1. Summary
Phase 6 is the production-grade finish pass: migrations, performance budgets, benchmark gates, support tooling, and UX polish. It should not create new capability families; it should make every prior phase faster, more diagnosable, safer to upgrade, and easier for both end users and operators to trust.

## 2. Dependencies
- Phases 1-5 are feature-complete and their artifact/memory/policy schemas are stable enough to version.
- Release bundling and enterprise diagnostics already exist from Phase 5.
- Verification and adversarial suites from earlier phases already cover core correctness.
- Wrapper, sidecar, and plugin all expose coherent versions and diagnostics.

## 3. Implementation Waves

### Wave 1 — Schema/version registry and migration engine
Parallel tasks: schema registry, migration manifest, rollback rules.

### Wave 2 — Benchmark harness and performance instrumentation
Parallel tasks: startup instrumentation, retrieval/policy timing, benchmark corpus, CI gates.

### Wave 3 — Support bundle and UX polish
Parallel tasks: support bundle generator, dry-run/summary mode, status/progress/error improvements, help/docs refresh.

### Wave 4 — GA regression, red-team, and upgrade/rollback validation
Parallel tasks: upgrade matrix, downgrade tests, benchmark regression gate, final docs/release checklist.

## 4. Task Specifications

### Task 1.1 — Implement schema registry and migration engine
- **File paths**:
  - `sidecar/internal/migrate/registry.go`
  - `sidecar/internal/migrate/engine.go`
  - `sidecar/internal/migrate/artifacts.go`
  - `sidecar/internal/migrate/memory.go`
  - `sidecar/internal/migrate/config.go`
  - `sidecar/internal/migrate/engine_test.go`
  - `sidecar/internal/schema/version.go`
- **What to implement**:
  - Version registry for config, artifact schemas, and memory schemas.
  - Forward and backward migration plumbing within the supported version window.
  - Migration manifests and dry-run reporting before any upgrade mutates local state.
- **Success criteria**:
  - Upgrade and rollback scenarios succeed on supported pre-GA versions.
  - Dry-run migrations show exactly what would change before execution.
- **Constraints**:
  - Do not perform destructive in-place migrations without backup or rollback metadata.
  - Do not hardcode one-off upgrade logic into unrelated packages.

### Task 1.2 — Add version-aware wrapper startup checks
- **File paths**:
  - `wrapper/internal/workflow/startup.go`
  - `wrapper/cmd/omni/main.go`
  - `wrapper/internal/sidecar/manager.go`
  - `plugin/skills/omni-doctor/SKILL.md`
- **What to implement**:
  - Startup validation that detects schema version mismatches and prompts the user toward dry-run migration, real migration, or rollback.
  - Clear UX for supported versus unsupported version windows.
  - Integration with doctor output so operators can diagnose upgrade state.
- **Success criteria**:
  - Wrapper refuses ambiguous unsupported upgrades with actionable reason codes.
  - Users can inspect upgrade state without mutating anything.
- **Constraints**:
  - Do not silently auto-migrate on every startup.
  - Do not hide downgrade limitations.

### Task 2.1 — Build benchmark harness and performance instrumentation
- **File paths**:
  - `sidecar/internal/metrics/timers.go`
  - `sidecar/internal/metrics/reports.go`
  - `wrapper/internal/metrics/startup.go`
  - `test/benchmarks/benchmark-matrix.sh`
  - `test/benchmarks/corpus/`
  - `.github/workflows/benchmarks.yml`
- **What to implement**:
  - Measurement for cold start, sidecar health, memory retrieval, policy checks, artifact hydration, planning overhead, and verification orchestration.
  - Benchmark corpus spanning small, medium, and large repositories.
  - CI regression gate that fails on critical budget regressions.
- **Success criteria**:
  - Cold-start p95 and memory-search p95 can be measured repeatably.
  - Benchmark reports are published in a stable machine-readable schema.
- **Constraints**:
  - Do not benchmark only idealized tiny repositories.
  - Do not ship performance claims without repeatable harness data.

### Task 2.2 — Add benchmark and support report schemas
- **File paths**:
  - `sidecar/schemas/benchmark-report.schema.json`
  - `sidecar/schemas/support-bundle.schema.json`
  - `sidecar/internal/support/manifest.go`
  - `sidecar/internal/metrics/schema.go`
- **What to implement**:
  - Stable report formats for benchmark runs and support bundle inventories.
  - Artifact paths and version metadata that allow cross-release comparison.
- **Success criteria**:
  - Benchmark artifacts validate and can be compared across builds.
  - Support bundle manifests are deterministic.
- **Constraints**:
  - Do not bury report structure in free-form markdown only.
  - Do not omit version/build metadata needed for triage.

### Task 3.1 — Implement support bundle generator with redaction
- **File paths**:
  - `sidecar/internal/support/bundle.go`
  - `sidecar/internal/support/redaction.go`
  - `sidecar/internal/mcp/tools.go`
  - `sidecar/internal/mcp/tool_support_bundle.go`
  - `wrapper/internal/workflow/support.go`
  - `plugin/skills/omni-support/SKILL.md`
- **What to implement**:
  - Support bundle generation covering config, resolved profile, doctor output, recent runs, verification reports, audit exports, environment summary, and benchmark summaries.
  - Secret redaction on by default with explicit operator override semantics.
  - Wrapper and skill entry points for support collection.
- **Success criteria**:
  - Seeded incidents can be triaged successfully from the support bundle alone at the target success rate.
  - Bundle contents are redacted by default and listed in a manifest.
- **Constraints**:
  - Do not dump raw secrets or full memory DB contents by default.
  - Do not require network connectivity to create a bundle.

### Task 3.2 — Polish wrapper and plugin UX for status, progress, errors, and dry-run
- **File paths**:
  - `wrapper/cmd/omni/main.go`
  - `wrapper/internal/workflow/status.go`
  - `wrapper/internal/workflow/dry_run.go`
  - `wrapper/internal/workflow/output.go`
  - `plugin/skills/omni-run/SKILL.md`
  - `plugin/skills/omni-plan/SKILL.md`
  - `plugin/skills/omni-resume/SKILL.md`
  - `docs/operator/ga-runbook.md`
  - `README.md`
- **What to implement**:
  - Dry-run and summary modes that explain intended actions without mutating state.
  - Consistent terminal/status output for current phase, active profile, run health, blockers, and next recommended command.
  - Final help text and operator docs aligned to the shipped command surface.
- **Success criteria**:
  - Users can understand next safe action and failure remediation without reading code.
  - Dry-run mode produces accurate previews and never mutates artifacts.
- **Constraints**:
  - Do not expand the command surface unnecessarily.
  - Do not leave error messages without stable reason codes and remediation.

### Task 4.1 — Run GA regression, red-team, and upgrade matrix
- **File paths**:
  - `test/integration-phase6.sh`
  - `test/upgrade/upgrade-matrix.sh`
  - `test/upgrade/rollback-matrix.sh`
  - `test/redteam/final-suite.sh`
  - `.github/workflows/ga-gate.yml`
  - `docs/release/ga-checklist.md`
- **What to implement**:
  - CI and local gates that rerun all prior phase checks plus upgrade, rollback, benchmark, and red-team suites.
  - Final GA checklist documenting exit criteria, sign-off roles, and blocked-release conditions.
  - Representative repo soak runs recorded as release evidence.
- **Success criteria**:
  - All prior phase exit criteria continue to pass on the GA matrix.
  - Critical regressions fail the GA gate immediately.
- **Constraints**:
  - Do not treat benchmark regressions as informational only.
  - Do not launch with version-mismatched docs and binaries.

## 5. Sidecar MCP Tools to Add

### `omni_migrate_state`
- **Input schema**: `{ repo_root: string, dry_run?: boolean, target_version?: string, include_global_memory?: boolean }`
- **Output format**: JSON `{ current_versions, target_version, dry_run, steps: [{ component, from, to, action }], applied: boolean, rollback_hint?: string }`
- **Behavior description**: Plans or applies versioned migrations for config, artifacts, and memory schemas and returns a reversible migration summary.

### `omni_support_bundle`
- **Input schema**: `{ repo_root: string, output_path?: string, include_runs?: number, include_benchmarks?: boolean, redact?: boolean }`
- **Output format**: JSON `{ bundle_path, manifest_path, redacted: boolean, contents: [], schema_version }`
- **Behavior description**: Generates a portable support bundle with redaction and a machine-readable manifest for triage.

### `omni_benchmark_run`
- **Input schema**: `{ repo_root: string, suite?: "startup"|"memory"|"policy"|"full", iterations?: number, output_path?: string }`
- **Output format**: JSON `{ suite, iterations, budgets, measurements, report_path, passed }`
- **Behavior description**: Runs benchmark scenarios, records timings, compares them to product budgets, and writes a benchmark report artifact.

### `omni_status_summary`
- **Input schema**: `{ repo_root: string, run_id?: string, include_next_action?: boolean }`
- **Output format**: JSON `{ current_phase, active_profile, run_health, pending_blockers, next_recommended_command, artifact_paths }`
- **Behavior description**: Produces the concise state summary used by the polished wrapper UX and dry-run flows.

## 6. Plugin Components to Add
- Add `plugin/skills/omni-support/SKILL.md` for support-bundle generation.
- Update `plugin/skills/omni-run/SKILL.md`, `plugin/skills/omni-plan/SKILL.md`, and `plugin/skills/omni-resume/SKILL.md` to reflect dry-run, summary, and GA-quality status output.
- Update doctor/help-oriented plugin content so migration and benchmark diagnostics are discoverable.
- Keep agent/skill/tool naming stable to avoid precedence and upgrade confusion.

## 7. Verification Checklist
- All prior phase verification gates still pass under the GA matrix.
- Cold-start p95, memory-search p95, and other published budgets are met on representative hardware and repositories.
- Upgrade and rollback scenarios succeed across the supported pre-GA window.
- Support bundles are redacted by default and sufficient to triage seeded incidents.
- Dry-run mode never mutates state and accurately previews planned actions.
- Final red-team and adversarial suites pass with no unresolved critical findings.
- User-facing docs and operator docs are complete, accurate, and version-matched.

## 8. Risks and Mitigations
- **Risk: late performance tuning exposes architectural bottlenecks.** Mitigation: instrument hot paths first, publish budgets, and fail CI on critical regressions.
- **Risk: migration bugs damage local state.** Mitigation: require dry-run visibility, backups/rollback hints, and upgrade-matrix testing.
- **Risk: support bundles become either too sparse or too invasive.** Mitigation: define a manifest schema, redact by default, and validate with seeded incidents.
- **Risk: UX polish drifts from real behavior.** Mitigation: make status/dry-run output read from sidecar-authoritative state rather than duplicated wrapper logic.
