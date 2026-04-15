---
name: omni-doctor
description: Check Copilot Omni environment (python, copilot CLI, plugin files, MCP server).
---

# /omni-doctor

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/omni.py" doctor`.

Reports:
- Python version (must be ≥3.9)
- Copilot CLI presence on PATH
- Plugin manifest (`.claude-plugin/plugin.json`)
- MCP server file
- Number of skills, agents, and commands loaded
- Platform + `$OMNI_HOME` directory
