# Phase 3 Plan — Local Memory and Deep Resumability

## 1. Summary
Phase 3 adds a local-first memory spine that stores artifact-derived facts, decisions, failures, and curated summaries in SQLite, then uses that store to improve retrieval and resumption. The purpose is not autonomous novelty; it is dependable recall with explicit source attribution, privacy controls, and offline operation.

## 2. Dependencies
- Phase 1 artifacts and run journals are stable enough to ingest.
- Phase 2 verification reports, policy decisions, and execution journals exist in machine-readable form.
- Sidecar remains the owner of persistent product state and local storage.
- Profile resolution can already distinguish strict, standard, and permissive behavior.

## 3. Implementation Waves

### Wave 1 — SQLite schema, config, and migration-free initial memory engine
Parallel tasks: DB schema, config extension, repositories, record model.

### Wave 2 — Ingestion boundaries and resume hydrator
Parallel tasks: artifact ingestion, summary ingestion, deep resume bundle construction.

### Wave 3 — Search, capture, privacy controls, and wrapper/plugin UX
Parallel tasks: lexical search ranking, memory commands, export/delete/wipe flows.

### Wave 4 — Performance and compliance validation
Parallel tasks: latency tests, seeded recall corpus, wipe/export verification, offline checks.

## 4. Task Specifications

### Task 1.1 — Add SQLite-backed memory store
- **File paths**:
  - `sidecar/internal/memory/store.go`
  - `sidecar/internal/memory/schema.go`
  - `sidecar/internal/memory/records.go`
  - `sidecar/internal/memory/sqlite.go`
  - `sidecar/internal/memory/store_test.go`
  - `sidecar/go.mod`
- **What to implement**:
  - Project-local memory database under `.omni/` plus optional user-global database under `~/.copilot-omni/`.
  - Record schema with `type`, `source`, `scope`, `timestamp`, `run_id`, `repository_fingerprint`, `trust_level`, and `sensitivity` fields.
  - Repository abstraction so later migration/version work in Phase 6 has a clean seam.
- **Success criteria**:
  - Memory store initializes offline and persists records across wrapper invocations.
  - Tests verify correct separation of project-local versus user-global records.
- **Constraints**:
  - Do not depend on cloud memory or embeddings.
  - Do not ingest raw transcripts wholesale in this phase.

### Task 1.2 — Extend config and profiles for memory controls
- **File paths**:
  - `sidecar/internal/config/config.go`
  - `sidecar/internal/config/resolver.go`
  - `profiles/strict/config.json`
  - `profiles/standard/config.json`
  - `profiles/permissive/config.json`
  - `templates/config.json.tmpl`
- **What to implement**:
  - Config fields for project memory path, optional global memory enablement, retention limits, export path, and privacy defaults.
  - Profile defaults that keep strict local-first and conservative on retention/export.
  - Resolver support for relocatable DB paths and retention values.
- **Success criteria**:
  - Resolved config exposes memory policy in a stable machine-readable form.
  - Profile tests confirm expected defaults for strict versus permissive behavior.
- **Constraints**:
  - Do not let permissive profile silently disable source attribution.
  - Do not add network-dependent configuration.

### Task 2.1 — Build ingestion pipeline for artifacts and summaries
- **File paths**:
  - `sidecar/internal/memory/ingest_artifacts.go`
  - `sidecar/internal/memory/ingest_summaries.go`
  - `sidecar/internal/memory/redaction.go`
  - `sidecar/internal/memory/ingest_test.go`
  - `sidecar/internal/run/summary.go`
- **What to implement**:
  - Ingestion of specs, plans, decisions, verification reports, task journals, and selected run summaries.
  - Trust-level tagging to distinguish user-authored notes from system-generated summaries.
  - Sensitivity tagging and lightweight redaction for obvious secrets before persistence.
- **Success criteria**:
  - Each ingested memory record keeps source artifact path and originating run ID.
  - Tests confirm sensitive fields are tagged or redacted according to policy.
- **Constraints**:
  - Do not ingest every token from every transcript.
  - Do not drop source attribution for compactness.

### Task 2.2 — Implement deep resume hydrator
- **File paths**:
  - `sidecar/internal/memory/resume.go`
  - `sidecar/internal/run/resume.go`
  - `wrapper/internal/workflow/resume.go`
  - `sidecar/internal/mcp/tool_resume_context.go`
  - `test/fixtures/phase3/week-old-run/`
- **What to implement**:
  - Resume bundle builder that combines artifacts, memory search hits, and recent verification failures into a bounded context payload.
  - Preference ordering for authoritative artifacts first, then memory records, then transcript summaries.
  - Wrapper UX that tells the user exactly which evidence sources were loaded.
- **Success criteria**:
  - A week-old interrupted run resumes without manually opening old transcripts.
  - Resume payloads explicitly cite artifacts and memory record IDs.
- **Constraints**:
  - Do not let memory override current canonical artifacts.
  - Do not depend on experimental `/chronicle` support.

### Task 3.1 — Add search, capture, and privacy control APIs
- **File paths**:
  - `sidecar/internal/memory/search.go`
  - `sidecar/internal/memory/rank.go`
  - `sidecar/internal/memory/capture.go`
  - `sidecar/internal/memory/privacy.go`
  - `sidecar/internal/memory/export.go`
  - `sidecar/internal/memory/search_test.go`
- **What to implement**:
  - Lexical plus metadata plus recency ranking with deterministic tie-breaking.
  - Explicit note capture for user-authored memories and system-generated summaries.
  - Project wipe, selective delete, and export operations.
- **Success criteria**:
  - Search p95 stays below the documented warm-query target on seeded data.
  - Wipe and delete flows remove only scoped records and leave audit metadata where policy allows.
- **Constraints**:
  - Do not introduce embeddings as a requirement.
  - Do not blur project-local and user-global deletion semantics.

### Task 3.2 — Expose memory UX through MCP, wrapper, and plugin
- **File paths**:
  - `sidecar/internal/mcp/tools.go`
  - `sidecar/internal/mcp/tool_memory_search.go`
  - `sidecar/internal/mcp/tool_memory_capture.go`
  - `sidecar/internal/mcp/tool_memory_delete.go`
  - `sidecar/internal/mcp/tool_memory_export.go`
  - `wrapper/cmd/omni/main.go`
  - `wrapper/internal/workflow/memory.go`
  - `plugin/skills/omni-memory-search/SKILL.md`
  - `plugin/skills/omni-memory-capture/SKILL.md`
  - `plugin/skills/omni-memory-prune/SKILL.md`
- **What to implement**:
  - MCP tools for search, capture, delete/prune, and export.
  - Wrapper subcommands or flags for explicit memory operations.
  - Skills for interactive use in Copilot sessions when the user wants direct memory lookup or note capture.
- **Success criteria**:
  - Memory search results show source attribution and trust level.
  - Export produces a deterministic portable format for support or compliance review.
- **Constraints**:
  - Do not add a large new command surface if wrapper flags can cover it cleanly.
  - Do not expose raw SQL or DB file paths to the model layer.

### Task 4.1 — Validate recall quality, performance, and privacy guarantees
- **File paths**:
  - `test/fixtures/phase3/memory-corpus/`
  - `test/integration-phase3.sh`
  - `test/benchmarks/memory-latency.sh`
  - `test/adversarial/phase3/privacy-controls.sh`
- **What to implement**:
  - Seeded recall corpus with at least 50 runs worth of artifacts.
  - Performance checks for warm-query p95 latency and ingestion overhead.
  - Privacy/compliance tests for wipe, selective delete, and export.
- **Success criteria**:
  - Search remains under the documented latency target on the seeded corpus.
  - Project wipe fully removes project memory without touching enabled global memory.
- **Constraints**:
  - Do not rely on one tiny happy-path repository for benchmarks.
  - Do not leave export/uninstall privacy behavior unspecified.

## 5. Sidecar MCP Tools to Add

### `omni_memory_search`
- **Input schema**: `{ repo_root: string, query: string, scope?: "project"|"global"|"both", types?: string[], limit?: number }`
- **Output format**: JSON `{ results: [{ record_id, score, type, source_path, run_id, excerpt, trust_level, sensitivity, created_at }], query_meta }`
- **Behavior description**: Performs deterministic lexical and metadata search over memory records, ranks by lexical match, metadata filters, and recency, and always preserves source attribution.

### `omni_memory_capture`
- **Input schema**: `{ repo_root: string, content: string, type: "user_note"|"system_summary", run_id?: string, scope?: "project"|"global", sensitivity?: "low"|"medium"|"high" }`
- **Output format**: JSON `{ stored: true, record_id, scope, trust_level, created_at }`
- **Behavior description**: Stores an explicit user or system memory entry with trust/sensitivity metadata and source context.

### `omni_memory_delete`
- **Input schema**: `{ repo_root: string, record_ids?: string[], delete_scope?: "project"|"global", wipe_project?: boolean }`
- **Output format**: JSON `{ deleted_count, wipe_project, remaining_project_records, warnings: [] }`
- **Behavior description**: Supports selective deletion and complete project wipe while preserving global-memory boundaries.

### `omni_memory_export`
- **Input schema**: `{ repo_root: string, scope: "project"|"global"|"both", format?: "json"|"jsonl", output_path?: string }`
- **Output format**: JSON `{ exported: true, record_count, output_path, schema_version }`
- **Behavior description**: Exports memory records in a portable offline format for compliance review, backup, or migration.

## 6. Plugin Components to Add
- Add `plugin/skills/omni-memory-search/SKILL.md` for direct retrieval with attribution.
- Add `plugin/skills/omni-memory-capture/SKILL.md` for explicit note capture with trust labels.
- Add `plugin/skills/omni-memory-prune/SKILL.md` for delete/wipe/export workflows.
- Update `plugin/agents/omni-conductor.agent.md` and `plugin/skills/omni-resume/SKILL.md` so resume uses artifact-plus-memory hydration rather than transcript-only context.
- Keep plugin naming namespaced and avoid adding cloud-only dependencies.

## 7. Verification Checklist
- `go test ./...` passes with memory-store and retrieval coverage.
- Seeded recall queries return explicit source references to the originating run and artifact.
- Warm-query p95 stays within the 150 ms target on the medium seeded corpus.
- `omni resume` reconstructs task context after a long pause using artifacts plus memory, not manual transcript browsing.
- Project wipe deletes project-local memory completely while leaving user-global memory intact when enabled.
- Export works offline and produces deterministic, attributed records.

## 8. Risks and Mitigations
- **Risk: low-signal ingestion pollutes search results.** Mitigation: keep ingestion boundaries explicit and rank artifact-derived records above generic summaries.
- **Risk: recency overwhelms correctness.** Mitigation: combine recency with type/source weighting and test against curated benchmark queries.
- **Risk: sensitive content gets persisted.** Mitigation: add sensitivity tagging, redaction helpers, explicit retention controls, and privacy tests before rollout.
- **Risk: memory becomes a second inconsistent state store.** Mitigation: keep artifacts authoritative and use memory only as an indexed retrieval layer plus resume aid.
