# Phase 1 Plan — Spec-Driven Workflow Core

## 1. Summary
Phase 1 turns the Phase 0 scaffold into the first complete artifact-backed workflow: discuss, spec, plan, review, and gated handoff into execution. The key outcome is that the sidecar becomes the source of truth for run state and artifacts, while the wrapper and plugin expose a clear `omni run|plan|resume` experience that can be interrupted and resumed without guessing from chat history.

## 2. Dependencies
- Phase 0 binaries, plugin assets, profile resolution, and bootstrap templates are accepted and released.
- The existing wrapper command surface in `wrapper/cmd/omni/main.go` remains the primary CLI entry point.
- The existing plugin agents and skills remain namespaced under `omni-*`.
- `.omni/` remains the repo-local state root and `~/.copilot-omni/` remains the user-global settings root.

## 3. Implementation Waves

### Wave 1 — Canonical run state and artifact contracts
Parallel tasks: state model, artifact store, schema validation.

### Wave 2 — Sidecar workflow and resume APIs
Parallel tasks: MCP tools, transcript ingestion/export helpers, resume hydration.

### Wave 3 — Wrapper orchestration and bounded Copilot phase runner
Parallel tasks: wrapper workflow runner, per-phase Copilot invocation contracts, CLI UX/status updates.

### Wave 4 — Plugin contract alignment
Parallel tasks: agent prompt updates, skill updates, MCP config alignment, hook adjustments for phase visibility.

### Wave 5 — Integration, crash recovery, and acceptance tests
Parallel tasks: unit tests, wrapper integration tests, resume/crash fixtures, adversarial artifact validation tests.

## 4. Task Specifications

### Task 1.1 — Define run and artifact schemas
- **File paths**:
  - `sidecar/internal/run/model.go`
  - `sidecar/internal/run/status.go`
  - `sidecar/internal/schema/run.go`
  - `sidecar/internal/schema/plan.go`
  - `sidecar/internal/schema/spec.go`
  - `sidecar/internal/schema/decision.go`
  - `sidecar/schemas/run.schema.json`
  - `sidecar/schemas/plan.schema.json`
  - `sidecar/schemas/spec.schema.json`
  - `sidecar/schemas/decision.schema.json`
- **What to implement**:
  - Stable run ID structure and allowed statuses: `draft`, `spec_ready`, `plan_ready`, `executing`, `verifying`, `done`, `blocked`, `aborted`.
  - Machine-readable schemas for `run.json`, `plan.json`, spec metadata, and decisions metadata.
  - Explicit validation rules for task dependencies, file targets, verification commands, and rollback notes.
- **Success criteria**:
  - Unit tests reject invalid state transitions and malformed plan artifacts.
  - Schema validation catches missing verification steps and missing file targets.
- **Constraints**:
  - Do not make execution legal before plan review passes.
  - Do not store state only in transcript markdown.

### Task 1.2 — Build artifact store and append-safe writes
- **File paths**:
  - `sidecar/internal/artifact/layout.go`
  - `sidecar/internal/artifact/store.go`
  - `sidecar/internal/artifact/writer.go`
  - `sidecar/internal/artifact/reader.go`
  - `sidecar/internal/artifact/transcripts.go`
  - `sidecar/internal/artifact/store_test.go`
- **What to implement**:
  - Canonical layout for `.omni/runs/<run-id>/run.json`, `.omni/specs/<run-id>.md`, `.omni/plans/<run-id>.json`, `.omni/decisions/<run-id>.md`, and `.omni/runs/<run-id>/transcripts/*.md`.
  - Atomic write strategy using temp files plus rename for crash resilience.
  - Artifact read helpers that normalize paths and reject traversal.
- **Success criteria**:
  - Tests prove partial writes do not corrupt existing artifacts.
  - Artifact paths are deterministic and match the architecture document.
- **Constraints**:
  - Do not write product-owned artifacts outside `.omni/`.
  - Do not allow arbitrary absolute-path reads or writes.

### Task 2.1 — Add Phase 1 sidecar MCP tools
- **File paths**:
  - `sidecar/internal/mcp/tools.go`
  - `sidecar/internal/mcp/tool_artifact_read.go`
  - `sidecar/internal/mcp/tool_artifact_write.go`
  - `sidecar/internal/mcp/tool_run_status.go`
  - `sidecar/internal/mcp/tool_resume_context.go`
  - `sidecar/internal/mcp/tools_test.go`
- **What to implement**:
  - Register MCP tools for artifact IO, run-state lookup, and resume context hydration.
  - Enforce schema validation on write-capable tools.
  - Return structured JSON payloads with stable reason codes when blocked.
- **Success criteria**:
  - `tools/list` includes the new tools and each tool validates input arguments.
  - Invalid artifact writes are rejected before filesystem mutation.
- **Constraints**:
  - Do not let MCP callers mutate arbitrary repo files through artifact tools.
  - Do not return opaque free-form errors without reason codes.

### Task 2.2 — Implement run orchestrator and resume engine in sidecar
- **File paths**:
  - `sidecar/internal/run/orchestrator.go`
  - `sidecar/internal/run/transition.go`
  - `sidecar/internal/run/resume.go`
  - `sidecar/internal/run/journal.go`
  - `sidecar/internal/run/orchestrator_test.go`
- **What to implement**:
  - Transition validation between discuss, spec, plan, review, and execution-ready phases.
  - Resume hydration that reconstructs current phase, latest approved artifacts, and next safe action from `.omni/` artifacts.
  - Structured journal entries for every phase transition.
- **Success criteria**:
  - Interrupted runs resume without duplicate artifact creation.
  - Sidecar can derive the current phase from artifacts plus `run.json` alone.
- **Constraints**:
  - Do not infer state from transcript text if `run.json` disagrees.
  - Do not silently auto-approve specs in strict profile.

### Task 3.1 — Add bounded Copilot phase runner to wrapper
- **File paths**:
  - `wrapper/internal/workflow/runner.go`
  - `wrapper/internal/workflow/phases.go`
  - `wrapper/internal/workflow/resume.go`
  - `wrapper/internal/workflow/prompts.go`
  - `wrapper/internal/copilot/invoke.go`
  - `wrapper/cmd/omni/main.go`
- **What to implement**:
  - Wrapper orchestration that runs discuss, spec, plan, and review as separate `copilot -p` invocations with phase-scoped prompts and transcript targets.
  - Shared plumbing for `omni run`, `omni plan`, and `omni resume` to consult sidecar state before invoking Copilot.
  - Clear terminal summaries: current phase, artifact path, next action, and blocking reason.
- **Success criteria**:
  - `omni run "feature"` produces a full artifact set and stops in a deterministic reviewed state.
  - `omni resume <run-id>` continues from the last incomplete phase instead of restarting from scratch.
- **Constraints**:
  - Do not collapse the whole lifecycle into one unbounded Copilot session.
  - Do not bypass sidecar validation for convenience.

### Task 3.2 — Track transcript export and summary generation
- **File paths**:
  - `wrapper/internal/workflow/transcripts.go`
  - `sidecar/internal/artifact/transcripts.go`
  - `sidecar/internal/run/summary.go`
  - `test/fixtures/phase1/`
  - `test/integration-phase1.sh`
- **What to implement**:
  - Transcript naming per phase under `.omni/runs/<run-id>/transcripts/`.
  - Lightweight per-phase summaries stored with the run for resume and operator use.
  - Integration fixtures for interrupted runs and restart/resume flows.
- **Success criteria**:
  - Per-phase transcript files are created predictably.
  - Resume works even if only artifacts and transcript summaries remain available.
- **Constraints**:
  - Do not make transcript markdown the only record of state.
  - Do not store summaries without source phase attribution.

### Task 4.1 — Align plugin agents and skills to real Phase 1 behavior
- **File paths**:
  - `plugin/agents/omni-conductor.agent.md`
  - `plugin/agents/omni-planner.agent.md`
  - `plugin/agents/omni-reviewer.agent.md`
  - `plugin/agents/omni-verifier.agent.md`
  - `plugin/skills/omni-run/SKILL.md`
  - `plugin/skills/omni-plan/SKILL.md`
  - `plugin/skills/omni-resume/SKILL.md`
  - `plugin/.mcp.json`
- **What to implement**:
  - Update tool lists and prompts to rely on the newly implemented artifact and run-state MCP tools.
  - Clarify that reviewer blocks execution until plan/spec alignment and verification coverage pass.
  - Keep skills as the primary user-facing command surface.
- **Success criteria**:
  - Agent/tool references match tools actually exposed by the sidecar.
  - Skills describe the real lifecycle and artifact expectations.
- **Constraints**:
  - Do not introduce a parallel execution story in this phase.
  - Do not add non-namespaced plugin components.

### Task 5.1 — Expand tests for lifecycle, validation, and crash recovery
- **File paths**:
  - `sidecar/internal/run/resume_test.go`
  - `sidecar/internal/schema/plan_test.go`
  - `wrapper/internal/workflow/runner_test.go`
  - `test/integration-phase1.sh`
  - `test/fixtures/phase1/interrupted-run/`
  - `test/fixtures/phase1/invalid-plan/`
- **What to implement**:
  - Unit tests for schema validation and transition rules.
  - Integration coverage for `omni run`, `omni plan`, and `omni resume`.
  - Fixture-driven crash recovery and duplicate-artifact prevention tests.
- **Success criteria**:
  - Phase 1 exit-gate scenarios are encoded in automated tests.
  - Invalid plans block execution with reproducible errors.
- **Constraints**:
  - Do not depend on manual verification for the core lifecycle.
  - Do not treat warnings as approvals in strict profile.

## 5. Sidecar MCP Tools to Add

### `omni_artifact_read`
- **Input schema**: `{ repo_root: string, artifact_type: "run"|"spec"|"plan"|"decision"|"transcript", run_id: string, path?: string }`
- **Output format**: JSON `{ artifact_type, run_id, canonical_path, content, metadata }`
- **Behavior description**: Resolves and reads only canonical Omni artifacts for a run, normalizes paths, and rejects traversal or unknown artifact types.

### `omni_artifact_write`
- **Input schema**: `{ repo_root: string, artifact_type: "run"|"spec"|"plan"|"decision"|"summary", run_id: string, content: string|object, validate_schema: boolean, expected_status?: string }`
- **Output format**: JSON `{ written: true, canonical_path, version, validation: { ok, errors: [] } }`
- **Behavior description**: Validates artifact content against schema when applicable, performs append-safe writes, and records a run-journal event.

### `omni_run_status`
- **Input schema**: `{ repo_root: string, run_id: string }`
- **Output format**: JSON `{ run_id, status, current_phase, last_completed_action, next_safe_action, blockers, artifact_paths }`
- **Behavior description**: Returns the authoritative run-state snapshot used by wrapper and plugin UX.

### `omni_resume_context`
- **Input schema**: `{ repo_root: string, run_id: string }`
- **Output format**: JSON `{ run_id, status, hydrate_from: { run, spec, plan, decisions, summaries, transcripts }, recommended_prompt, next_safe_action }`
- **Behavior description**: Builds a deterministic resume bundle from artifacts so the wrapper can restart at the correct phase with bounded context.

## 6. Plugin Components to Add
- Update `plugin/agents/omni-conductor.agent.md` to drive the full discuss→spec→plan→review progression through sidecar-backed artifacts.
- Update `plugin/agents/omni-planner.agent.md` to require atomic tasks with dependencies, file targets, verification commands, and rollback notes.
- Update `plugin/agents/omni-reviewer.agent.md` to emit blocking findings against the spec and plan.
- Update `plugin/agents/omni-verifier.agent.md` to check plan completeness before later execution phases.
- Update `plugin/skills/omni-run/SKILL.md`, `plugin/skills/omni-plan/SKILL.md`, and `plugin/skills/omni-resume/SKILL.md` to describe the real artifact-backed flow.
- Optionally add `plugin/skills/omni-status/SKILL.md` only if the wrapper exposes the same concept; otherwise keep status inside `omni resume` and CLI output.

## 7. Verification Checklist
- `go test ./...` passes in both `sidecar/` and `wrapper/`.
- A seeded run produces `run.json`, `spec.md`, `plan.json`, `decisions.md`, and per-phase transcripts in the expected locations.
- `omni run "feature"` blocks before execution when review fails or required verification metadata is missing.
- `omni resume <run-id>` reconstructs the next safe action after an interrupted planning run without duplicating artifacts.
- Invalid artifact writes fail with stable reason codes and no partial file corruption.
- Plugin agent definitions reference only implemented MCP tools.

## 8. Risks and Mitigations
- **Risk: artifact schema churn creates rework in later phases.** Mitigation: freeze canonical field names now and add version fields to every machine-readable artifact.
- **Risk: wrapper and sidecar disagree on run phase.** Mitigation: make `run.json` plus sidecar transition logic authoritative and keep wrapper logic thin.
- **Risk: transcript exports become the de facto state store.** Mitigation: require all progression-critical data to exist in validated artifacts first and treat transcript summaries as supplemental.
- **Risk: strict-profile approval rules remain ambiguous.** Mitigation: encode profile-specific approval checks in sidecar validation and test them explicitly.
