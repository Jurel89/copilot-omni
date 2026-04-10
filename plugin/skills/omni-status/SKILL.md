---
name: omni-status
description: Reports the current status, phase, and next action for a Copilot Omni run.
allowed-tools:
  - view
  - omni_run_status
  - omni_artifact_read
user-invocable: true
---

# omni-status

Check the current status of a Copilot Omni run. Reports the run ID, current phase, last completed action, blockers, and recommended next step.

## Usage

Call `omni_run_status` with the run ID (or omit to check the latest run). The response includes:

- `run_id` — The stable run identifier
- `status` — Current run status (draft, spec_ready, plan_ready, executing, verifying, done, blocked, aborted)
- `current_phase` — The active workflow phase
- `next_safe_action` — What the user should do next
- `blockers` — Any blocking issues preventing progression
- `artifact_paths` — Paths to all artifacts produced so far

This is a read-only operation. No artifacts are modified.
