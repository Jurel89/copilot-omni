---
name: omni-run
description: Executes the full Copilot Omni workflow: discuss, spec, plan, review, execute, and verify phases producing artifact-backed state transitions.
allowed-tools:
  - bash
  - edit
  - view
  - omni_health
  - omni_artifact_write
  - omni_artifact_read
  - omni_config_resolve
  - omni_run_status
  - omni_resume_context
  - omni_doctor
  - omni_guarded_patch
  - omni_verification_run
  - omni_repo_map
  - omni_policy_check
user-invocable: true
---

# omni-run

Run the complete Copilot Omni workflow through all phases: discuss, spec, plan, review, execute, verify. Each phase produces a durable artifact under `.omni/`.

## Workflow

1. **Initialize** — Check `omni_health`, resolve config via `omni_config_resolve`, create a new run via `omni_artifact_write` with `artifact_type: "run"`.
2. **Discuss** — Understand the user's request. Capture requirements and constraints.
3. **Spec** — Generate a formal specification. Write to `.omni/specs/<run-id>.md` via `omni_artifact_write` with `artifact_type: "spec"`. Must include objective, requirements, and acceptance criteria.
4. **Plan** — Generate an implementation plan as JSON. Write to `.omni/plans/<run-id>.json` via `omni_artifact_write` with `artifact_type: "plan"`. Each task must have: id, title, description, dependencies, file_targets, verification_cmd, rollback_note.
5. **Review** — Check spec/plan alignment. Write findings to `.omni/decisions/<run-id>.md` via `omni_artifact_write` with `artifact_type: "decision"`. Block execution on unresolved BLOCKING findings.
6. **Execute** — Execute approved plan tasks one at a time. Each task uses `omni_guarded_patch` for file writes within approved scope. Files outside the task's `file_targets` are blocked by policy.
7. **Verify** — Run all verification commands from completed tasks via `omni_verification_run`. If all pass, transition to `done`. If any fail, block with failure details.
8. **Status** — Update run status via `omni_run_status` after each phase. Report current phase, artifact paths, and next action to the user.

## Artifacts Produced

| Artifact | Path | Format |
|---|---|---|
| Run state | `.omni/runs/<run-id>/run.json` | JSON |
| Specification | `.omni/specs/<run-id>.md` | Markdown |
| Implementation plan | `.omni/plans/<run-id>.json` | JSON |
| Review decisions | `.omni/decisions/<run-id>.md` | Markdown |
| Phase transcripts | `.omni/runs/<run-id>/transcripts/<phase>.md` | Markdown |

Treat artifacts as the system of record so interrupted or delegated work can resume without losing context.
