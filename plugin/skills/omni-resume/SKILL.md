---
name: omni-resume
description: Resumes an interrupted Copilot Omni workflow from recorded artifacts and repository state.
allowed-tools:
  - bash
  - edit
  - view
  - omni_artifact_read
  - omni_artifact_write
  - omni_config_resolve
user-invocable: true
---

# omni-resume

Resume an interrupted or partially completed Copilot Omni run. Reconstruct state from repository configuration and workflow artifacts, identify the last safe checkpoint, and continue execution from there.

Avoid restarting completed phases unless the recorded artifacts or current repository state show they are no longer trustworthy.
