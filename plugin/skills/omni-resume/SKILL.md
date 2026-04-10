---
name: omni-resume
description: Resumes an interrupted Copilot Omni workflow from recorded artifacts, run state, and memory context.
allowed-tools:
  - bash
  - edit
  - view
  - omni_artifact_read
  - omni_artifact_write
  - omni_config_resolve
  - omni_run_status
  - omni_resume_context
  - omni_memory_search
  - omni_memory_capture
  - omni_memory_ingest
user-invocable: true
---

# omni-resume

Resume an interrupted or partially completed Copilot Omni run. Uses `omni_resume_context` to reconstruct state from artifacts and determines which phases remain.

## Resume Process

1. **Hydrate** — Call `omni_resume_context` with the run ID. This returns the current status, completed artifacts, and recommended next action.
2. **Assess** — Check `omni_run_status` for blockers. If blocked, report blockers to the user.
3. **Continue** — Run only the remaining phases from where the run was interrupted. Do NOT re-run completed phases or duplicate existing artifacts.
4. **Validate** — Before continuing, verify existing artifacts are still valid (spec exists, plan is parseable, no missing fields).

## State Recovery

The resume engine derives phase from `run.json` plus artifact existence:
- `draft` → No spec exists. Start from discuss phase.
- `spec_ready` → Spec exists, no plan. Start from plan phase.
- `plan_ready` → Plan exists, not reviewed. Start from review phase.
- `blocked` → Check blockers. If resolved, retry the blocked phase.

## Deep Resume with Memory

Phase 3 adds memory-enriched context recovery:
1. **Memory Search** — Call `omni_memory_search` with the original prompt or run ID to find related past decisions, specs, and plans.
2. **Context Enrichment** — The `omni_resume_context` tool now returns memory-enriched context including recent decisions and project patterns.
3. **Artifact Ingestion** — If artifacts from the interrupted run haven't been ingested into memory, call `omni_memory_ingest` to capture them before resuming.

Avoid restarting completed phases unless artifacts are corrupted or missing.
