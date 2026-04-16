---
name: setup
description: Use first for install/update routing — sends setup, doctor, or MCP requests to the correct copilot-omni setup flow
level: 2
---

# Setup

Use `/copilot-omni:setup` as the unified setup/configuration entrypoint.

## Usage

```bash
/copilot-omni:setup                # full setup wizard
/copilot-omni:setup doctor         # installation diagnostics
/copilot-omni:setup mcp            # MCP server configuration
/copilot-omni:setup wizard --local # explicit wizard path
```

## Routing

Process the request by the **first argument only** so install/setup questions land on the right flow immediately:

- No argument, `wizard`, `local`, `global`, or `--force` -> route to `/copilot-omni:omni-setup` with the same remaining args
- `doctor` -> route to `/copilot-omni:omni-doctor` with everything after the `doctor` token
- `mcp` -> route to `/copilot-omni:mcp-setup` with everything after the `mcp` token

Examples:

```bash
/copilot-omni:setup --local          # => /copilot-omni:omni-setup --local
/copilot-omni:setup doctor --json    # => /copilot-omni:omni-doctor --json
/copilot-omni:setup mcp github       # => /copilot-omni:mcp-setup github
```

## Notes

- `/copilot-omni:omni-setup`, `/copilot-omni:omni-doctor`, and `/copilot-omni:mcp-setup` remain valid compatibility entrypoints.
- Prefer `/copilot-omni:setup` in new documentation and user guidance.

Task: {{ARGUMENTS}}
