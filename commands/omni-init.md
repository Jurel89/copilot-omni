---
name: omni-init
description: Scaffold .omni/ directory with config, runs/, specs/, plans/, decisions/ for Copilot Omni workflows.
---

# /omni-init

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/omni.py" init` to create the `.omni/` tree in the current project. If `.omni/config.json` already exists, pass `--force` to overwrite.

After initialization, you can run `/omni-plan`, `/autopilot`, `/ralph`, or any other skill — they all write artifacts into `.omni/runs/<run-id>/`.
