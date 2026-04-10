---
name: omni-plan
description: Generates an implementation plan from a specification without executing. Produces spec and plan artifacts only.
allowed-tools:
  - view
  - bash
  - omni_artifact_read
  - omni_artifact_write
  - omni_run_status
user-invocable: true
---

# omni-plan

Run the planning workflow only: discuss, spec, plan, review. No execution. Use this when you want to review the plan before committing to implementation.

## Workflow

1. **Initialize** — Resolve config, create a new run.
2. **Discuss** — Clarify requirements from the user's prompt.
3. **Spec** — Write the specification artifact.
4. **Plan** — Write the implementation plan artifact.
5. **Review** — Check plan alignment with spec, write decisions artifact.

## Plan Format

The plan must be valid JSON:
```json
{
  "run_id": "<run-id>",
  "version": "1",
  "tasks": [
    {
      "id": "task-1",
      "title": "...",
      "description": "...",
      "dependencies": [],
      "file_targets": ["..."],
      "verification_cmd": "...",
      "rollback_note": "..."
    }
  ]
}
```

After completion, the run will be in `plan_ready` status. Run `omni-run` or `omni-resume` to proceed with execution.
