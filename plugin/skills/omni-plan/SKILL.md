---
name: omni-plan
description: Produces an implementation plan from existing specifications and workflow artifacts.
allowed-tools:
  - view
  - bash
  - omni_artifact_read
  - omni_artifact_write
user-invocable: true
---

# omni-plan

Generate a plan-only output for the current repository context. Read the latest specifications and workflow artifacts, produce a sequenced implementation plan, and write the resulting plan artifact for later review or execution.

Keep the plan concrete enough that another agent can pick it up without re-discovering intent.
