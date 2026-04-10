---
name: omni-memory
description: Search, capture, and manage project memory for context-aware development decisions and deep resumability.
allowed-tools:
  - bash
  - view
  - omni_health
  - omni_config_resolve
  - omni_memory_search
  - omni_memory_capture
  - omni_memory_wipe
  - omni_memory_export
  - omni_memory_ingest
  - omni_memory_prune
  - omni_doctor
user-invocable: true
---

# omni-memory

Search, capture, and manage local project memory. Memory stores decisions, specs, plans, verification outcomes, and user notes so that context can be reconstructed without relying on long chat transcripts.

## Commands

### Search Memory
Use `omni_memory_search` with:
- `query` (required): Search terms for lexical matching
- `type` (optional): Filter by type — "decision", "spec", "plan", "summary", "note", "verification"
- `scope` (optional): Filter by scope — "project" or "global"
- `run_id` (optional): Filter to a specific run
- `tags` (optional): Filter by tags
- `limit` (optional): Maximum results (default 10)

### Capture Memory
Use `omni_memory_capture` with:
- `repo_root` (required): Repository root path
- `title` (required): Short title for the memory entry
- `content` (required): The memory content to store
- `type` (optional): Record type (default "note")
- `source` (optional): "user" or "system" (default "user")
- `tags` (optional): Tags for categorization
- `sensitivity` (optional): "normal", "sensitive", or "secret" (default "normal")

### Ingest Run Artifacts
Use `omni_memory_ingest` with:
- `repo_root` (required): Repository root path
- `run_id` (required): Run ID whose artifacts to ingest
- `artifact_types` (optional): Array of types to ingest — "spec", "plan", "decision", "verification" (default: all)

### Wipe Memory
Use `omni_memory_wipe` with:
- `repo_root` (required): Repository root path
- `scope` (required): "project" to wipe project memory, "global" to wipe global memory

### Export Memory
Use `omni_memory_export` with:
- `repo_root` (required): Repository root path
- `scope` (optional): "project" or "global" (default "project")

### Prune Memory
Use `omni_memory_prune` with:
- `repo_root` (required): Repository root path
- `max_age_days` (optional): Delete records older than N days
- `max_records` (optional): Keep only the newest N records
- `scope` (optional): "project" or "global" (default "project")

## Memory Schema

Each memory record has:
- **type**: decision, spec, plan, summary, note, verification
- **source**: user (explicit), system (auto-generated), artifact (ingested)
- **scope**: project or global
- **trust_level**: high (user-verified), medium (system-generated), low (unverified)
- **sensitivity**: normal, sensitive (secrets redacted), secret (blocked from content)

## Privacy

- All memory is stored locally in `.omni/memory.db`
- Secret patterns are automatically redacted during ingestion
- Project memory can be wiped independently of global memory
- Memory can be exported as JSON for compliance workflows
