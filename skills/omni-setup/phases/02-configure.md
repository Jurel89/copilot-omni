# Phase 2: Environment Configuration

**Skip condition**: If resuming and `lastCompletedStep >= 4`, skip this entire phase.

## Step 2.1: Clear Stale Plugin Cache

```bash
# Clear stale cache if multiple versions exist
CACHE_DIR=".omni/cache"
if [ -d "$CACHE_DIR" ]; then
  echo "Cache directory exists: $CACHE_DIR"
  # Cache cleanup logic can be added here if versioned caching is implemented
else
  echo "No cache directory found (normal for new installs)"
fi
```

## Step 2.2: Check for Updates

Notify user if a newer version is available:

```bash
# Detect installed version from plugin manifest
if [ -f "plugin.json" ]; then
  INSTALLED_VERSION=$(python3 -c "import json; print(json.load(open('plugin.json')).get('version', 'unknown'))" 2>/dev/null || echo "unknown")
else
  INSTALLED_VERSION="unknown"
fi

echo "Installed version: $INSTALLED_VERSION"

# For marketplace installs, the Copilot CLI handles plugin updates
# Users should run: copilot plugin update copilot-omni@copilot-omni
echo ""
echo "To update: copilot plugin update copilot-omni@copilot-omni"
```

## Step 2.3: Set Default Execution Mode

Emit as plain chat and wait for the user's reply:

**Question:** "Which parallel execution mode should be your default when you say 'fast' or 'parallel'?"

**Options:**
1. **ultrawork (maximum capability)** - Uses all agent tiers for complex tasks. Best for challenging work where quality matters most. (Recommended)

Store the preference in `.omni/config.json`:

```bash
CONFIG_FILE=".omni/config.json"

if [ -f "$CONFIG_FILE" ]; then
  EXISTING=$(cat "$CONFIG_FILE")
else
  EXISTING='{}'
fi

# Set defaultExecutionMode (replace USER_CHOICE with "ultrawork" or "")
echo "$EXISTING" | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['defaultExecutionMode'] = 'ultrawork'
d['configuredAt'] = __import__('datetime').datetime.now().isoformat()
json.dump(d, sys.stdout, indent=2)
" > "$CONFIG_FILE"
echo "Default execution mode set to: ultrawork"
```

**Note**: This preference ONLY affects generic keywords ("fast", "parallel"). Explicit keywords ("ulw") always override this preference.

## Step 2.4: Select Task Management Tool

Emit as plain chat and wait for the user's reply:

**Question:** "How would you like task tracking to work?"

**Options:**
1. **Built-in tracking (default)** - Uses session-scoped state and todo lists. Tasks are session-only.

Store the preference:

```bash
CONFIG_FILE=".omni/config.json"

if [ -f "$CONFIG_FILE" ]; then
  EXISTING=$(cat "$CONFIG_FILE")
else
  EXISTING='{}'
fi

echo "$EXISTING" | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['taskTool'] = 'builtin'
d['taskToolConfig'] = {'injectInstructions': True, 'useMcp': False}
json.dump(d, sys.stdout, indent=2)
" > "$CONFIG_FILE"
echo "Task tool set to: builtin"
```

## Save Progress

```bash
CONFIG_TYPE=$(python3 -c "import json; print(json.load(open('.omni/config.json')).get('configType', 'unknown'))" 2>/dev/null || echo "unknown")
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" save 4 "$CONFIG_TYPE"
```
