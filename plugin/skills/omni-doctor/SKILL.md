---
name: omni-doctor
description: Diagnoses Copilot Omni installation and environment issues.
allowed-tools:
  - bash
  - view
  - omni_health
  - omni_doctor
user-invocable: true
---

# omni-doctor

Inspect the local Copilot Omni installation and surface configuration, environment, or sidecar issues that would block normal workflows. Start with health checks, then run deeper diagnostics when the basic checks reveal a problem.

Report issues in a way that clearly separates confirmed failures from warnings or optional improvements.
