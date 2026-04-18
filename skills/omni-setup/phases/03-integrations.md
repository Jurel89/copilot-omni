# Phase 3: Integration Setup

**Skip condition**: If resuming and `lastCompletedStep >= 6`, skip this entire phase.

## Step 3.1: Verify Plugin Installation

```bash
# Check if copilot-omni plugin is installed
copilot plugin list 2>/dev/null | grep -q "copilot-omni" && echo "Plugin verified" || echo "Plugin NOT found - run: copilot plugin install copilot-omni@copilot-omni"
```

## Step 3.2: Offer MCP Server Configuration

MCP servers extend Copilot CLI with additional tools (web search, GitHub, etc.).

copilot-omni provides 28 built-in MCP tools via `mcp/server.py`. No additional configuration is required for the built-in tools.

Emit as plain chat and wait for the user's reply: "Would you like to verify the built-in MCP tools are working?"

If yes, invoke the mcp-setup skill:
```
/copilot-omni:mcp-setup
```

If no, skip to next step.

## Step 3.3: Configure Team Defaults (Optional)

The `team` skill spawns coordinated agents using `scripts/subagent.py` with tmux on POSIX and subprocess fallback elsewhere.

Emit as plain chat and wait for the user's reply:

**Question:** "Would you like to configure team defaults? Teams let you spawn coordinated agents (e.g., `/copilot-omni:team 3:executor 'fix all errors'`)."

**Options:**
1. **Yes, configure teams** - Set default team size and agent type
2. **No, skip** - Use defaults (can configure later)

### If User Chooses YES:

Emit the following questions as plain chat, one at a time, waiting for the user's reply after each:

**Question 1:** "How many agents should teams spawn by default?"

**Options:**
1. **3 agents (Recommended)** - Good balance of speed and resource usage
2. **5 agents (maximum)** - Maximum parallelism for large tasks
3. **2 agents** - Conservative, for smaller projects

**Question 2:** "Which agent type should teammates use by default?"

**Options:**
1. **executor (Recommended)** - General-purpose code implementation agent
2. **debugger** - Specialized for build/type error fixing and debugging
3. **designer** - Specialized for UI/frontend work

Store the team configuration in `.omni/config.json`:

```bash
CONFIG_FILE=".omni/config.json"

if [ -f "$CONFIG_FILE" ]; then
  EXISTING=$(cat "$CONFIG_FILE")
else
  EXISTING='{}'
fi

# Replace MAX_AGENTS, AGENT_TYPE with user choices
echo "$EXISTING" | python3 -c "
import json, sys
d = json.load(sys.stdin)
# MAX_AGENTS and AGENT_TYPE are injected by the skill executor
d['team'] = {
  'maxAgents': MAX_AGENTS,
  'defaultAgentType': 'AGENT_TYPE',
  'monitorIntervalMs': 30000,
  'shutdownTimeoutMs': 15000
}
json.dump(d, sys.stdout, indent=2)
" > "$CONFIG_FILE"

echo "Team configuration saved:"
echo "  Max agents: MAX_AGENTS"
echo "  Default agent: AGENT_TYPE"
```

**Note:** Teammates are spawned via `scripts/subagent.py` as independent processes. Each teammate inherits the session model from the Copilot CLI host.

## Save Progress

```bash
CONFIG_TYPE=$(python3 -c "import json; print(json.load(open('.omni/config.json')).get('configType', 'unknown'))" 2>/dev/null || echo "unknown")
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" save 6 "$CONFIG_TYPE"
```
