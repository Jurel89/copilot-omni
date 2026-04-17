<!-- omni:managed:start -->
## Omni Workflow Instructions

When working with Omni workflows:
1. Read existing artifacts in `.omni/runs/<run-id>/` before creating new ones.
2. Use the `health` MCP tool to verify the `copilot-omni` server is reachable.
3. Use `config_resolve` to inspect project configuration.
4. Write artifacts directly into `.omni/runs/<run-id>/` — the filesystem is canonical. (Phase-C C23 removed the legacy SQLite-mirror tools `artifact_write` / `run_status`; use `state_write` for mode state and regular file I/O for `spec.md` / `plan.md` / `decision.md` / `summary.md`.)
5. Never skip the verification phase. Use the `verify` skill or `verifier` agent.
<!-- omni:managed:end -->
