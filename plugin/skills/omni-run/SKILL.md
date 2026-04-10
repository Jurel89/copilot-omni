---
name: omni-run
description: Executes the full Copilot Omni workflow from health checks through artifact-backed verification.
allowed-tools:
  - bash
  - edit
  - view
  - omni_health
  - omni_artifact_write
  - omni_artifact_read
  - omni_config_resolve
user-invocable: true
---

# omni-run

Run the complete Copilot Omni workflow. Verify health, resolve configuration, load existing artifacts, update the active workflow state, and drive the repository through execution and verification.

Treat artifacts as the system of record so interrupted or delegated work can resume without losing context.
