# Document Audit - Critical Findings

## CRITICAL: File Naming Mismatch

The filenames in `docs/internal/` are **systematically shifted by 2 positions** from their actual content. Every file's content belongs to the phase that is **2 positions earlier** than its filename suggests.

### Mapping Table

| Filename | Expected Content | ACTUAL Content Inside |
|---|---|---|
| `phase-0-foundation-bootstrap-prd.md` | Phase 0 PRD | **References** (source links) |
| `phase-0-foundation-bootstrap-architecture.md` | Phase 0 Architecture | **program-manifest.json** (all phases) |
| `phase-1-spec-driven-workflow-core-prd.md` | Phase 1 PRD | **Phase Roadmap** (v1 program overview) |
| `phase-1-spec-driven-workflow-core-architecture.md` | Phase 1 Architecture | **Phase Gate Checklist** |
| `phase-2-guarded-execution-verification-prd.md` | Phase 2 PRD | **Phase 0 PRD** (Foundation, Packaging, Bootstrap) |
| `phase-2-guarded-execution-verification-architecture.md` | Phase 2 Architecture | **Phase 0 Architecture** (Foundation, Packaging, Bootstrap) |
| `phase-3-local-memory-resumability-prd.md` | Phase 3 PRD | **Phase 1 PRD** (Spec-Driven Workflow Core) |
| `phase-3-local-memory-resumability-architecture.md` | Phase 3 Architecture | **Phase 1 Architecture** (Spec-Driven Workflow Core) |
| `phase-4-research-subagents-parallelism-prd.md` | Phase 4 PRD | **Phase 2 PRD** (Guarded Execution and Verification) |
| `phase-4-research-subagents-parallelism-architecture.md` | Phase 4 Architecture | **Phase 2 Architecture** (Guarded Execution and Verification) |
| `phase-5-enterprise-offline-distribution-prd.md` | Phase 5 PRD | **Phase 3 PRD** (Local Memory, Retrieval, Deep Resumability) |
| `phase-5-enterprise-offline-distribution-architecture.md` | Phase 5 Architecture | **Phase 3 Architecture** (Local Memory, Retrieval, Deep Resumability) |
| `phase-6-ga-hardening-ux-performance-prd.md` | Phase 6 PRD | **Phase 4 PRD** (Research, Subagents, Parallel Workflows) |
| `phase-6-ga-hardening-ux-performance-architecture.md` | Phase 6 Architecture | **Phase 4 Architecture** (Research, Subagents, Parallel Workflows) |
| `architecture-principles.md` | Architecture Principles | **Phase 5 PRD** (Enterprise Policy, Offline Distribution) |
| `source-alignment.md` | Source Alignment | **Phase 5 Architecture** (Enterprise Policy, Offline Distribution) |
| `initial-architecture-draft.md` | Initial Architecture Draft | **Phase 6 PRD** (GA Hardening, Performance, UX Polish) |
| `target-system-architecture.md` | Target System Architecture | **Phase 6 Architecture** (GA Hardening, Performance, UX Polish) |
| `phase-gate-checklist.md` | Phase Gate Checklist | **Program Overview** (file map, execution order, global rules) |

### Correct Content-to-Phase Mapping

For implementation, use this corrected mapping:

| Phase | PRD Source File | Architecture Source File |
|---|---|---|
| Program Overview | `phase-gate-checklist.md` | - |
| Manifest/References | `phase-0-foundation-bootstrap-prd.md` | `phase-0-foundation-bootstrap-architecture.md` |
| Roadmap | `phase-1-spec-driven-workflow-core-prd.md` | `phase-1-spec-driven-workflow-core-architecture.md` |
| Phase 0 - Foundation | `phase-2-guarded-execution-verification-prd.md` | `phase-2-guarded-execution-verification-architecture.md` |
| Phase 1 - Spec Workflow | `phase-3-local-memory-resumability-prd.md` | `phase-3-local-memory-resumability-architecture.md` |
| Phase 2 - Guarded Execution | `phase-4-research-subagents-parallelism-prd.md` | `phase-4-research-subagents-parallelism-architecture.md` |
| Phase 3 - Memory | `phase-5-enterprise-offline-distribution-prd.md` | `phase-5-enterprise-offline-distribution-architecture.md` |
| Phase 4 - Research/Subagents | `phase-6-ga-hardening-ux-performance-prd.md` | `phase-6-ga-hardening-ux-performance-architecture.md` |
| Phase 5 - Enterprise | `architecture-principles.md` | `source-alignment.md` |
| Phase 6 - GA | `initial-architecture-draft.md` | `target-system-architecture.md` |

### Recommended Fix

Rename all files so their names match their actual content. This should be done BEFORE any implementation to prevent confusion.

## Initial Observations

### Positive
1. **Well-structured phase program** - 7 phases with clear dependencies, exit gates, and deliverables
2. **Strong security model** - fail-closed, path validation, injection scanning, protected paths
3. **Artifact-first** - every run produces durable artifacts as source of truth
4. **Local-first** - no cloud dependencies, offline-capable
5. **Enterprise-aware** - policy packs, audit exports, air-gapped installation

### Concerns (Pending Research Validation)
1. **Copilot CLI feature assumptions** - docs reference features that may not exist yet (programmatic mode, /chronicle, /fleet, plan mode)
2. **Wrapper binary necessity** - docs say wrapper exists to "control process-level Copilot flags" - need to validate this is actually needed
3. **Sidecar + MCP architecture** - need to validate MCP server definition in plugins is real
4. **Hooks for policy** - docs assume hooks can block/modify execution - need validation
5. **No code exists yet** - this is pure greenfield, which means the docs are the only source of truth

### Missing from Docs
1. **Technology stack decisions** - what language for the sidecar? Rust? Go? TypeScript?
2. **CI/CD pipeline design**
3. **Exact plugin.json schema** (referenced but not specified)
4. **Testing framework choices**
5. **Sidecar communication protocol** - how does the plugin talk to the sidecar? stdin/stdout? HTTP? Unix socket?
