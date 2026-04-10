# Research, Subagents, and Parallel Workflows — Architecture

## Document control
- Product: Copilot Omni
- Phase ID: phase-4
- Status: Draft
- Depends on: phase-0, phase-1, phase-2, phase-3
- Type: Architecture document

## Architecture summary
This phase implements one slice of the overall hybrid architecture: Copilot-native UX on the surface, sidecar-owned state and policy underneath. The phase is designed so that its outputs remain valid inputs for later phases without rework.

## Architectural decisions carried into this phase
- The plugin remains the user-facing integration layer.
- The sidecar remains the authority for product-owned state, policy, memory, and guarded tools.
- Artifacts remain the canonical source of truth.
- Namespacing is mandatory to avoid plugin precedence collisions.
- The wrapper binary exists because it can control process-level Copilot flags and environment more reliably than in-session slash commands alone.

## Components in this phase
- Research report generator
- Subtask scheduler
- Workspace isolation manager
- Merge coordinator
- Intent and capability router

## Integration with Copilot CLI
- Repository-wide instructions via `.github/copilot-instructions.md`.
- Path-specific instructions via `.github/instructions/**/*.instructions.md`.
- Agent-specific instructions via `AGENTS.md`.
- Plugin-provided commands, agents, skills, hooks, and MCP server definitions.
- Wrapper-driven programmatic Copilot sessions for stronger control of permissions and phase boundaries.

## Data contracts and storage
- Subtask manifest schema
- Workspace metadata records
- Merge decision records
- Research report schema with provenance sections

## Execution flow
1. The user enters the phase through the relevant `omni` or `/omni-*` entry point.
2. The wrapper or plugin resolves active config, profile, repository fingerprint, and phase eligibility.
3. The sidecar validates artifacts and phase preconditions before any model work or write-capable step proceeds.
4. Copilot is invoked in a bounded context with only the tools, artifacts, and instructions required for the current step.
5. Outputs are normalized into artifacts, indexed as appropriate, and checked against phase policy.
6. The phase either advances state, blocks with actionable findings, or records a deterministic failure that can be resumed.

## Trust boundaries
- User-authored prompts and files are untrusted input.
- Planning artifacts are semi-trusted only after validation and injection scanning.
- Sidecar policy decisions are authoritative for product-owned operations.
- Copilot responses are treated as proposals until artifacts validate and policy allows progression.

## Security model
- Parallel write tasks isolated by workspace.
- External research provenance always preserved.
- Router respects profile-based tool restrictions.

## Performance considerations
- Keep the phase composable with later phases by avoiding hidden background processes.
- Prefer local file and SQLite operations to network dependencies.
- Bound Copilot context aggressively so later latency tuning remains possible.

## Failure handling
- Missing or shadowed plugin component due to precedence collision.
- Sidecar not found or wrong architecture binary selected.
- Schema validation failure for config or artifacts.
- Interrupted programmatic Copilot session leaving partial output.
- Policy denial or guardrail violation blocking progression.
- Verification or review failure forcing rollback or manual intervention.

## Observability
- Every phase action writes structured events to a run journal.
- Human-readable artifacts and machine-readable JSON outputs are both required.
- Errors must carry stable reason codes for future support tooling.

## Implementation work packages
- Research flow design
- Subtask schema and scheduler
- Workspace isolation implementation
- Merge/review pipeline
- Performance and correctness benchmarking

## Handoff to next phase
Phase 4 provides the orchestration advantage. Phase 5 turns that capability into something enterprises can actually deploy and govern.
