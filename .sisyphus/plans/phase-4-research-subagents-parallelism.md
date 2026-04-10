# Phase 4 Plan — Research, Subagents, and Parallel Workflows

## 1. Summary
Phase 4 introduces bounded parallelism and research workflows without giving up determinism or auditability. It combines repository evidence, prior memory, and external research into cited reports, then adds subtask decomposition, isolated workspaces for write-capable subtasks, and a deterministic merge/review pipeline.

## 2. Dependencies
- Phase 1 artifacts, Phase 2 guarded execution, and Phase 3 memory retrieval are complete and reliable.
- Sidecar already owns authoritative run state, policy, and memory.
- Wrapper can already invoke bounded Copilot sessions and resume from artifacts.
- Existing profiles can express task, tool, and path restrictions that the router must obey.

## 3. Implementation Waves

### Wave 1 — Research contract and routing primitives
Parallel tasks: research report schema, intent router, provenance model.

### Wave 2 — Subtask scheduling and isolated workspace management
Parallel tasks: subtask manifest, scheduler, workspace manager, lineage records.

### Wave 3 — Merge/review pipeline and wrapper/plugin UX
Parallel tasks: merge coordinator, review gates, wrapper research/subtask commands, plugin skill/agent updates.

### Wave 4 — Parallel correctness, isolation, and benchmark validation
Parallel tasks: conflict tests, workspace discard tests, provenance checks, planning-time benchmarks.

## 4. Task Specifications

### Task 1.1 — Define research report and subtask contracts
- **File paths**:
  - `sidecar/internal/research/report.go`
  - `sidecar/internal/research/schema.go`
  - `sidecar/internal/subtask/manifest.go`
  - `sidecar/internal/subtask/lineage.go`
  - `sidecar/schemas/research-report.schema.json`
  - `sidecar/schemas/subtask-manifest.schema.json`
- **What to implement**:
  - Research report schema that separates external findings, repository evidence, prior-memory evidence, inferences, and open questions.
  - Subtask manifest schema with scope, inputs, output contract, verification requirements, and workspace mode.
  - Parent-child lineage records to link subtasks back to their originating task and merged result.
- **Success criteria**:
  - Reports and subtasks validate through schema tests.
  - Every subtask manifest encodes whether it is read-only or write-capable.
- **Constraints**:
  - Do not mix facts and inferences in one undifferentiated section.
  - Do not allow ambiguous ownership of filesystem scope.

### Task 1.2 — Build intent and capability router
- **File paths**:
  - `sidecar/internal/router/router.go`
  - `sidecar/internal/router/capabilities.go`
  - `sidecar/internal/router/profile_filters.go`
  - `sidecar/internal/router/router_test.go`
  - `plugin/plugin.json`
- **What to implement**:
  - Router that chooses among skills, agents, sidecar MCP tools, and built-in Copilot features based on task class and profile restrictions.
  - Minimal-tool loading policy to reduce context pollution.
  - Explicit refusal paths when a requested capability is not allowed by profile or current phase.
- **Success criteria**:
  - Routing decisions are deterministic for the same input and profile.
  - Tests show disallowed tools are not surfaced through the router.
- **Constraints**:
  - Do not turn routing into a hidden autonomous planner with no artifacts.
  - Do not depend on cloud-only features to complete the local workflow.

### Task 2.1 — Implement subtask scheduler and workspace isolation manager
- **File paths**:
  - `sidecar/internal/subtask/scheduler.go`
  - `sidecar/internal/subtask/workspaces.go`
  - `sidecar/internal/subtask/isolation.go`
  - `sidecar/internal/subtask/scheduler_test.go`
  - `wrapper/internal/workflow/subtasks.go`
- **What to implement**:
  - Scheduler that decomposes eligible work into bounded subtasks with explicit scope and verification.
  - Read-only subtasks that can use the main worktree and write-capable subtasks that must use isolated directories or git worktrees.
  - Workspace metadata records stored under `.omni/` for lifecycle and cleanup.
- **Success criteria**:
  - Write-capable subtasks never modify the main worktree directly.
  - Failed subtasks can be discarded independently without corrupting siblings.
- **Constraints**:
  - Do not introduce unrestricted swarm behavior.
  - Do not leave workspace cleanup unspecified.

### Task 2.2 — Add research aggregation pipeline
- **File paths**:
  - `sidecar/internal/research/aggregate.go`
  - `sidecar/internal/research/provenance.go`
  - `sidecar/internal/research/memory_inputs.go`
  - `sidecar/internal/research/repo_inputs.go`
  - `wrapper/internal/workflow/research.go`
- **What to implement**:
  - Research workflow that merges repository exploration, local memory results, and external research outputs into one report format.
  - Provenance tags for each citation block and a clear distinction between evidence and synthesized recommendations.
  - Wrapper flow for `omni research` or equivalent entry point.
- **Success criteria**:
  - Generated reports cite each evidence source class explicitly.
  - Open questions remain visible rather than being flattened into false certainty.
- **Constraints**:
  - Do not let external research silently override repository evidence.
  - Do not omit provenance metadata to save tokens.

### Task 3.1 — Build merge coordinator and review pipeline
- **File paths**:
  - `sidecar/internal/subtask/merge.go`
  - `sidecar/internal/subtask/conflicts.go`
  - `sidecar/internal/subtask/review.go`
  - `sidecar/internal/subtask/merge_test.go`
  - `plugin/agents/omni-reviewer.agent.md`
  - `plugin/agents/omni-verifier.agent.md`
- **What to implement**:
  - Deterministic merge pipeline for subtask outputs with spec-compliance review first and code-quality review second.
  - Conflict detection for overlapping file changes and contradictory subtask outputs.
  - Lineage-aware merge decision artifacts.
- **Success criteria**:
  - Merged outputs preserve parent-child lineage and pass the same review/verification gates as serial work.
  - Conflicting outputs block merge with actionable explanations.
- **Constraints**:
  - Do not auto-merge write-capable sibling outputs without review.
  - Do not drop lineage metadata after merge.

### Task 3.2 — Surface research and parallel workflows in wrapper and plugin
- **File paths**:
  - `wrapper/cmd/omni/main.go`
  - `plugin/skills/omni-research/SKILL.md`
  - `plugin/skills/omni-subtasks/SKILL.md`
  - `plugin/skills/omni-merge/SKILL.md`
  - `plugin/agents/omni-conductor.agent.md`
  - `plugin/.mcp.json`
- **What to implement**:
  - Wrapper command surface and status output for research, subtask planning, workspace preparation, and merge review.
  - New plugin skills that expose the research and subtask workflows with bounded instructions.
  - Conductor guidance for when to use serial work versus bounded parallel work.
- **Success criteria**:
  - Users can see whether a subtask is read-only or isolated-write before it runs.
  - Plugin instructions match the sidecar/router capability model.
- **Constraints**:
  - Do not overload the user with many overlapping commands.
  - Do not expose workspaces as a hidden implementation detail with no cleanup path.

### Task 4.1 — Validate parallel correctness, provenance, and performance gains
- **File paths**:
  - `test/fixtures/phase4/parallel-readonly/`
  - `test/fixtures/phase4/isolated-write/`
  - `test/fixtures/phase4/merge-conflict/`
  - `test/integration-phase4.sh`
  - `test/benchmarks/phase4-planning-time.sh`
- **What to implement**:
  - Isolation tests proving read-only research does not write the main worktree.
  - Workspace discard and sibling-failure containment tests.
  - Research provenance validation and planning-time benchmark scenarios.
- **Success criteria**:
  - Parallel read-only workflows leave the main worktree untouched.
  - Conflict-free merge rate and planning-time improvement are measurable on target task classes.
- **Constraints**:
  - Do not claim wins from toy single-file benchmarks only.
  - Do not waive provenance checks for external findings.

## 5. Sidecar MCP Tools to Add

### `omni_research_bundle`
- **Input schema**: `{ repo_root: string, query: string, include_memory?: boolean, include_repo_map?: boolean, include_external?: boolean, limit?: number }`
- **Output format**: JSON `{ report_path, sections: { external_findings, repo_evidence, memory_evidence, inferences, open_questions }, citations: [] }`
- **Behavior description**: Collects bounded research inputs from external sources, repo evidence, and local memory, then writes a structured research report with provenance.

### `omni_subtask_schedule`
- **Input schema**: `{ repo_root: string, run_id: string, task_id: string, strategy?: "serial"|"parallel", max_parallel?: number }`
- **Output format**: JSON `{ scheduled: true, subtasks: [{ subtask_id, scope, workspace_mode, dependencies, verification_requirements }], manifest_path }`
- **Behavior description**: Decomposes an eligible task into explicit subtasks with scopes, contracts, and allowed concurrency.

### `omni_workspace_prepare`
- **Input schema**: `{ repo_root: string, run_id: string, subtask_id: string, mode: "readonly"|"isolated_write" }`
- **Output format**: JSON `{ workspace_id, mode, path, cleanup_hint, main_worktree_write_allowed: false }`
- **Behavior description**: Prepares the execution workspace for a subtask, using the main tree for read-only work and an isolated directory/worktree for writes.

### `omni_merge_review`
- **Input schema**: `{ repo_root: string, run_id: string, parent_task_id: string, subtask_ids: string[] }`
- **Output format**: JSON `{ mergeable: boolean, conflicts: [], review_findings: [], merged_artifact_path?: string }`
- **Behavior description**: Evaluates subtask outputs for conflicts and review findings before merging them back into the parent task result.

## 6. Plugin Components to Add
- Add `plugin/skills/omni-research/SKILL.md` for structured research mode.
- Add `plugin/skills/omni-subtasks/SKILL.md` to initiate bounded subtask decomposition.
- Add `plugin/skills/omni-merge/SKILL.md` for merge-review workflows.
- Update `plugin/agents/omni-conductor.agent.md` to decide between serial and bounded parallel execution.
- Update `plugin/agents/omni-reviewer.agent.md` and `plugin/agents/omni-verifier.agent.md` so merged outputs go through the same gates as serial outputs.

## 7. Verification Checklist
- `go test ./...` passes with router, scheduler, workspace, and merge coverage.
- Parallel read-only research runs leave the main worktree unchanged.
- Write-capable subtasks execute only in isolated workspaces and can be discarded independently.
- Merged outputs preserve lineage from parent task to subtask to final merged result.
- Research reports explicitly separate external findings, repository evidence, memory evidence, inferences, and open questions.
- Benchmarks show the targeted planning-time reduction on large benchmark tasks without regressions in correctness.

## 8. Risks and Mitigations
- **Risk: parallelism produces flashy but unreliable demos.** Mitigation: require explicit scope contracts, isolated workspaces, and merge review gates.
- **Risk: external research contaminates engineering decisions.** Mitigation: preserve provenance and require repository/spec evidence to win when conflicts exist.
- **Risk: routing becomes opaque.** Mitigation: emit routing decisions into the run journal and keep router behavior deterministic and testable.
- **Risk: overhead outweighs gains on small tasks.** Mitigation: route only eligible tasks to subtask scheduling and keep serial execution as the default fast path.
