---
name: omni-init
description: Bootstraps repository configuration for Copilot Omni workflows.
allowed-tools:
  - bash
  - edit
  - view
  - omni_health
  - omni_config_resolve
user-invocable: true
---

# omni-init

Initialize Copilot Omni for the current repository. Confirm health first, resolve repository configuration, then create or update the minimum workflow configuration needed for future runs.

Prefer safe, repeatable setup steps so the skill can be run again without damaging existing project state.
