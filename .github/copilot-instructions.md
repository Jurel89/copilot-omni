<!-- omni:managed:start -->
## Copilot Omni Integration

This repository is augmented by the [copilot-omni](https://github.com/Jurel89/copilot-omni) plugin. It provides 37 skills, 19 agents, 8 slash commands, and 30 MCP tools to structure Copilot CLI sessions.

### Workflow
1. **Discuss / Spec** — use the `plan` or `deep-interview` skill to crystallize requirements.
2. **Plan** — produce `.omni/plans/<run-id>.md` before touching code.
3. **Execute** — delegate implementation to the `executor` agent; independent work runs in parallel.
4. **Verify** — run the `verify` skill or the `verifier` agent with fresh evidence.

### Key principles
- Every phase produces a durable artifact in `.omni/runs/<run-id>/`.
- Plans are read before execution. Verification evidence gates completion.
- Protected paths listed in `policies/*.json` cannot be modified unless explicitly requested.

### Configuration
See `.omni/config.json` for project settings. Run `python3 scripts/omni.py doctor` to verify the environment.
<!-- omni:managed:end -->
