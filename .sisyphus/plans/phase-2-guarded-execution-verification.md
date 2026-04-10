# Phase 2 Plan — Guarded Execution and Verification

## 1. Summary
Phase 2 makes plans executable without giving up control of the repository. It adds the sidecar-owned task executor, guarded MCP tools, deny-first hook enforcement, verification reporting, and rollback guidance so code changes happen only within approved plan scope and always leave auditable evidence behind.

## 2. Dependencies
- Phase 1 run state, artifact schemas, and resume flow are complete and stable.
- Approved plans already contain atomic tasks, dependencies, file targets, verification commands, and rollback notes.
- Existing profile resolution in `sidecar/internal/config/` and `profiles/` remains the base for policy enforcement.
- Wrapper orchestration already consults the sidecar before phase transitions.

## 3. Implementation Waves

### Wave 1 — Policy engine and plan-scope executor core
Parallel tasks: task selection/dependency checks, policy model, prompt-injection scanning.

### Wave 2 — Guarded MCP tools and hook enforcement
Parallel tasks: guarded patch tool, repo map tool, verification runner, preToolUse policy integration.

### Wave 3 — Execution journal, reviewer/verifier gates, rollback metadata
Parallel tasks: task journal, verification report schema, rollback recommender, wrapper execute UX.

### Wave 4 — Adversarial and crash-resume test matrix
Parallel tasks: deny-precedence tests, protected-path bypass tests, injected-plan tests, interrupted execution tests.

## 4. Task Specifications

### Task 1.1 — Implement task executor and dependency gate
- **File paths**:
  - `sidecar/internal/execution/executor.go`
  - `sidecar/internal/execution/task_selector.go`
  - `sidecar/internal/execution/dependencies.go`
  - `sidecar/internal/execution/executor_test.go`
  - `sidecar/internal/run/model.go`
- **What to implement**:
  - Approved-plan task selection that only schedules tasks whose dependencies are satisfied.
  - Run-state transitions into `executing`, `verifying`, `done`, and `blocked`.
  - Fail-closed behavior for missing tasks, cyclic dependencies, or incomplete prerequisite evidence.
- **Success criteria**:
  - Tasks outside the approved plan cannot be selected for execution.
  - Failed dependencies stop execution before any write-capable step.
- **Constraints**:
  - Do not allow whole-run autopilot without task boundaries.
  - Do not treat missing verification metadata as a warning.

### Task 1.2 — Build policy engine and injection scanning
- **File paths**:
  - `sidecar/internal/policy/engine.go`
  - `sidecar/internal/policy/paths.go`
  - `sidecar/internal/policy/commands.go`
  - `sidecar/internal/policy/injection.go`
  - `sidecar/internal/policy/reason_codes.go`
  - `sidecar/internal/policy/engine_test.go`
- **What to implement**:
  - Deny-first evaluation for prohibited shell commands, protected paths, unsafe plan mutations, and unplanned writes.
  - Prompt-injection scanning for planning artifacts and task inputs before reuse.
  - Stable reason codes and remediation text for every denial path.
- **Success criteria**:
  - Deny rules override allow rules in all tested scenarios.
  - Injected planning artifacts are blocked or sanitized before execution proceeds.
- **Constraints**:
  - Do not rely on Copilot enterprise policy to enforce local safety.
  - Do not make injection scanning optional in strict profile.

### Task 2.1 — Add guarded execution MCP tools
- **File paths**:
  - `sidecar/internal/mcp/tools.go`
  - `sidecar/internal/mcp/tool_guarded_patch.go`
  - `sidecar/internal/mcp/tool_verification_run.go`
  - `sidecar/internal/mcp/tool_repo_map.go`
  - `sidecar/internal/mcp/tool_policy_check.go`
  - `sidecar/internal/mcp/tools_test.go`
- **What to implement**:
  - MCP tools for controlled patch application, repository mapping, verification execution, and explicit policy evaluation.
  - Plan-scope checking for every file mutation request.
  - Structured outputs that the wrapper and plugin can feed into journals and reports.
- **Success criteria**:
  - File writes outside the current task scope are denied in strict and standard profiles.
  - Verification reports include command, exit code, artifact path, and timestamps.
- **Constraints**:
  - Do not expose a raw unrestricted file-write MCP tool.
  - Do not let repo mapping become a backdoor for arbitrary file reads outside the repo root.

### Task 2.2 — Replace simplistic hook shell logic with generated policy hook contract
- **File paths**:
  - `plugin/hooks.json`
  - `templates/hooks.json.tmpl`
  - `wrapper/internal/workflow/hooks.go`
  - `sidecar/internal/policy/hook_payload.go`
  - `test/fixtures/phase2/hooks/`
- **What to implement**:
  - Hook payload generation that delegates path/command decisions to sidecar-derived policy logic rather than hard-coded shell regexes alone.
  - `preToolUse` enforcement for shell commands, protected-path edits, and planning-artifact mutations.
  - Template support so `omni init` can install/update the generated hook configuration.
- **Success criteria**:
  - Hook decisions align with active profile and task scope.
  - Tests show blocked tools receive human-readable reasons plus machine-readable deny responses.
- **Constraints**:
  - Do not try to mutate prompts via hooks; only deny or allow.
  - Do not keep policy duplicated in multiple regex-only locations.

### Task 3.1 — Add execution journal and rollback recommendation pipeline
- **File paths**:
  - `sidecar/internal/execution/journal.go`
  - `sidecar/internal/execution/report.go`
  - `sidecar/internal/execution/rollback.go`
  - `sidecar/internal/schema/verification.go`
  - `sidecar/schemas/verification-report.schema.json`
  - `sidecar/internal/execution/journal_test.go`
- **What to implement**:
  - Per-task journal entries with before/after file sets, executed commands, policy decisions, verification results, and reviewer findings.
  - Verification report schema and rollback recommendation metadata.
  - Deterministic failure recording to support resume after crashes.
- **Success criteria**:
  - Each task has a machine-readable record of what ran and why it passed or failed.
  - Failed runs preserve enough context to recommend rollback steps.
- **Constraints**:
  - Do not mark a task complete without verification evidence.
  - Do not auto-rollback repository state in this phase.

### Task 3.2 — Extend wrapper and plugin for explicit execute/verify flow
- **File paths**:
  - `wrapper/cmd/omni/main.go`
  - `wrapper/internal/workflow/execute.go`
  - `wrapper/internal/workflow/verify.go`
  - `plugin/skills/omni-run/SKILL.md`
  - `plugin/skills/omni-plan/SKILL.md`
  - `plugin/agents/omni-verifier.agent.md`
  - `plugin/agents/omni-reviewer.agent.md`
- **What to implement**:
  - Wrapper entry points for guarded execution and verification, whether as `omni execute` or as a second-stage `omni run` mode.
  - UX that prints task identity, current allowed scope, failing command, and remediation.
  - Reviewer/verifier prompts that consume sidecar-produced reports instead of ad hoc summaries.
- **Success criteria**:
  - Executing a task always shows the approved task ID and next safe action.
  - Review and verification outputs can block run completion deterministically.
- **Constraints**:
  - Do not widen the CLI surface unless the command semantics remain coherent with the existing wrapper.
  - Do not let plugin agents perform writes outside the guarded MCP path.

### Task 4.1 — Add adversarial, integration, and interruption coverage
- **File paths**:
  - `test/adversarial/phase2/deny-precedence.sh`
  - `test/adversarial/phase2/protected-path-bypass.sh`
  - `test/adversarial/phase2/prompt-injection.txt`
  - `test/fixtures/phase2/repo-map/`
  - `test/fixtures/phase2/interrupted-execution/`
  - `test/integration-phase2.sh`
- **What to implement**:
  - End-to-end tests for out-of-plan writes, protected paths, dangerous commands, and malicious planning artifacts.
  - Resume-after-crash execution fixtures.
  - Verification attribution checks to ensure failing command and artifact are always named.
- **Success criteria**:
  - Unsafe command escape rate stays at zero in the seeded adversarial suite.
  - Interrupted runs resume with preserved logs and task status.
- **Constraints**:
  - Do not leave adversarial coverage as manual-only testing.
  - Do not allow flaky tests that hide false negatives.

## 5. Sidecar MCP Tools to Add

### `omni_guarded_patch`
- **Input schema**: `{ repo_root: string, run_id: string, task_id: string, file_path: string, patch: string, expected_hash?: string }`
- **Output format**: JSON `{ applied: boolean, file_path, before_hash, after_hash, policy: { allowed, reason_code, message }, scope_match: boolean }`
- **Behavior description**: Applies a patch only when the target file is within the approved task scope, the path is allowed by profile, and the task is currently executable.

### `omni_verification_run`
- **Input schema**: `{ repo_root: string, run_id: string, task_id?: string, commands: string[], mode: "task"|"run" }`
- **Output format**: JSON `{ status, mode, commands: [{ command, exit_code, stdout_path, stderr_path, duration_ms }], report_path }`
- **Behavior description**: Executes configured build/lint/test/custom verification commands, captures outputs to artifacts, and returns a structured report.

### `omni_repo_map`
- **Input schema**: `{ repo_root: string, include?: string[], exclude?: string[], max_files?: number, task_id?: string }`
- **Output format**: JSON `{ files: [{ path, language, size_bytes, role }], warnings: [] }`
- **Behavior description**: Produces a bounded repository map used to target edits and reviews without scanning the entire repo blindly.

### `omni_policy_check`
- **Input schema**: `{ repo_root: string, run_id?: string, task_id?: string, operation: "command"|"path"|"artifact"|"prompt", value: string, metadata?: object }`
- **Output format**: JSON `{ allowed: boolean, reason_code, message, profile, matched_rule }`
- **Behavior description**: Exposes the sidecar’s authoritative policy decision logic to the wrapper, hooks, and tests.

## 6. Plugin Components to Add
- Update `plugin/hooks.json` to drive deny-based pre-tool policy checks from sidecar-aware rule material instead of only a hard-coded shell case statement.
- Update `plugin/agents/omni-reviewer.agent.md` to require spec-compliance review before code-quality review.
- Update `plugin/agents/omni-verifier.agent.md` to consume structured verification reports and journal data.
- Update `plugin/skills/omni-run/SKILL.md` and possibly add `plugin/skills/omni-execute/SKILL.md` if execution is surfaced as a separate user command.
- Add a template-driven hooks asset if bootstrap needs to install repository-local policy files.

## 7. Verification Checklist
- `go test ./...` passes in `sidecar/` and `wrapper/` with policy and execution coverage.
- Adversarial tests prove deny rules override allow rules and protected paths cannot be edited without explicit policy.
- A task outside the approved plan is blocked before any write is attempted.
- A failed verification run produces a report naming the failing command and output artifact.
- Interrupted execution resumes with preserved journal state and deterministic rollback guidance.
- Planning artifacts containing injection markers are blocked or sanitized before execution continues.

## 8. Risks and Mitigations
- **Risk: policy becomes unusably strict.** Mitigation: keep strict/standard/permissive profiles explicit and test policy behavior per profile.
- **Risk: guarded patching is too brittle for real refactors.** Mitigation: pair patching with repo mapping, content hashes, and clear task file targets.
- **Risk: verification latency dominates the workflow.** Mitigation: support task-level versus run-level verification granularity from plan metadata and record timings for later Phase 6 budgets.
- **Risk: hooks and sidecar diverge.** Mitigation: generate hook-facing policy material from the same rule engine and verify parity in tests.
