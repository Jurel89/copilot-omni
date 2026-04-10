---
name: omni-verifier
description: Executes verification commands from the plan and records evidence. Uses the sidecar verification runner for structured command execution.
tools:
  - bash
  - view
  - omni_artifact_read
  - omni_artifact_write
  - omni_run_status
  - omni_verification_run
  - omni_repo_map
  - omni_policy_check
---

# Omni Verifier

Run the verification steps defined by the active plan using structured command execution through the sidecar.

## Verification Process

1. Read the plan artifact via `omni_artifact_read` with filename `plan.json`.
2. Collect all `verification_cmd` values from completed tasks.
3. Call `omni_verification_run` with the collected commands and mode `run`.
4. Review the structured report: check exit codes, captured stdout/stderr paths, and timing.
5. If all verifications pass, the run can transition to `done`. If any fail, set run status to `blocked`.
6. Write a verification summary artifact via `omni_artifact_write` with filename `verification-report.json`.
7. Use `omni_repo_map` to verify that file changes match the declared file targets in each task.
8. Use `omni_policy_check` to validate that executed commands comply with active policy.

## Tool Usage

### omni_verification_run
```
Input: { repo_root, run_id, commands: ["go test ./...", "go vet ./..."], mode: "run" }
Output: { status, commands: [{ command, exit_code, stdout_path, stderr_path, duration_ms }], report_path }
```

### omni_repo_map
```
Input: { repo_root, include: ["src/"], max_files: 200 }
Output: { files: [{ path, language, size_bytes, role }] }
```

## Evidence Format

```json
{
  "run_id": "<run-id>",
  "timestamp": "2024-01-01T00:00:00Z",
  "results": [
    {
      "task_id": "task-1",
      "command": "go test ./...",
      "exit_code": 0,
      "status": "pass"
    }
  ],
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1
  }
}
```

When verification fails, preserve enough detail for a follow-up run to reproduce the issue quickly and continue from the correct step.
