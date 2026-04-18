# Phase 4: Completion

## Show Welcome Message

```
copilot-omni Setup Complete!

You don't need to learn any commands. Intelligent behaviors activate automatically.

WHAT HAPPENS AUTOMATICALLY:
- Complex tasks -> parallelize and delegate to specialists
- "plan this" -> start a planning interview
- "don't stop until done" -> persist until verified complete
- "stop" or "cancel" -> intelligently stop current operation

MAGIC KEYWORDS (optional power-user shortcuts):
Just include these words naturally in your request:

| Keyword | Effect | Example |
|---------|--------|---------|
| ralph | Persistence mode | "ralph: fix the auth bug" |
| ralplan | Iterative planning | "ralplan this feature" |
| ulw | Max parallelism | "ulw refactor the API" |
| plan | Planning interview | "plan the new endpoints" |
| team | Coordinated agents | "/copilot-omni:team 3:executor fix errors" |

**ralph includes ultrawork:** When you activate ralph mode, it automatically includes ultrawork's parallel execution. No need to combine keywords.

TEAMS:
Spawn coordinated agents with shared task lists:
- /copilot-omni:team 3:executor "fix all TypeScript errors"
- /copilot-omni:team 5:debugger "fix build errors in src/"
Teams use `python3 scripts/subagent.py` for agent invocation.

MCP SERVERS:
Run /copilot-omni:mcp-setup to verify the 28 built-in MCP tools.

CLI HELPERS (if installed):
- Session summaries are written to `.omni/sessions/*.json`

That's it! Just use Copilot CLI normally.
```

## Optional Rule Templates

copilot-omni includes rule templates you can copy to your project for automatic context injection:

| Template | Purpose |
|----------|---------|
| `coding-style.md` | Code style, immutability, file organization |
| `testing.md` | TDD workflow, 80% coverage target |
| `security.md` | Secret management, input validation |
| `performance.md` | Model selection, context management |
| `git-workflow.md` | Commit conventions, PR workflow |
| `karpathy-guidelines.md` | Coding discipline -- think before coding, simplicity, surgical changes |

Copy with:
```bash
mkdir -p .copilot/rules
cp "${OMNI_PLUGIN_ROOT}/templates/rules/"*.md .copilot/rules/
```

See `templates/rules/README.md` for details.

## Ask About Starring Repository

First, check if `gh` CLI is available and authenticated:

```bash
gh auth status &>/dev/null
```

### If gh is available and authenticated:

**Before prompting, check if the repository is already starred:**

```bash
gh api user/starred/Jurel89/copilot-omni &>/dev/null
```

**If already starred (exit code 0):**
- Skip the prompt entirely
- Continue to completion silently

**If NOT starred (exit code non-zero):**

Emit as plain chat and wait for the user's reply:

**Question:** "If you're enjoying copilot-omni, would you like to support the project by starring it on GitHub?"

**Options:**
1. **Yes, star it!** - Star the repository
2. **No thanks** - Skip without further prompts
3. **Maybe later** - Skip without further prompts

If user chooses "Yes, star it!":

```bash
gh api -X PUT /user/starred/Jurel89/copilot-omni 2>/dev/null && echo "Thanks for starring!" || true
```

**Note:** Fail silently if the API call doesn't work - never block setup completion.

### If gh is NOT available or not authenticated:

```bash
echo ""
echo "If you enjoy copilot-omni, consider starring the repo:"
echo "  https://github.com/Jurel89/copilot-omni"
echo ""
```

## Mark Completion

Get the current copilot-omni version and mark setup complete:

```bash
# Get current copilot-omni version from plugin.json
OMC_VERSION=""
if [ -f "plugin.json" ]; then
  OMC_VERSION=$(python3 -c "import json; print(json.load(open('plugin.json')).get('version', 'unknown'))" 2>/dev/null || true)
fi
if [ -z "$OMC_VERSION" ]; then
  OMC_VERSION="unknown"
fi

bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" complete "$OMC_VERSION"
```
