<!-- omni:managed:start -->
## Omni Workflow Instructions

When working with Omni workflows:
1. Read existing artifacts in `.omni/runs/<run-id>/` before creating new ones.
2. Use the `health` MCP tool to verify the `copilot-omni` server is reachable.
3. Use `config_resolve` to inspect project configuration.
4. Write artifacts with `artifact_write` (kinds: `spec`, `plan`, `decision`, `summary`).
5. Read artifacts with `artifact_read`.
6. Never skip the verification phase. Use the `verify` skill or `verifier` agent.
<!-- omni:managed:end -->
