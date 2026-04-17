# Phase 4: Completion

## Detect Upgrade from 2.x

Check if user has existing 2.x configuration:

```bash
ls "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands/ralph-loop.md 2>/dev/null || ls "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands/ultrawork.md 2>/dev/null
```

If found, this is an upgrade from 2.x. Set `IS_UPGRADE=true`.

## Show Welcome Message

### For New Users (IS_UPGRADE is not true):

```
copilot-omni Setup Complete!

You don't need to learn any commands. I now have intelligent behaviors that activate automatically.

WHAT HAPPENS AUTOMATICALLY:
- Complex tasks -> I parallelize and delegate to specialists
- "plan this" -> I start a planning interview
- "don't stop until done" -> I persist until verified complete
- "stop" or "cancel" -> I intelligently stop current operation

MAGIC KEYWORDS (optional power-user shortcuts):
Just include these words naturally in your request:

| Keyword | Effect | Example |
|---------|--------|---------|
| ralph | Persistence mode | "ralph: fix the auth bug" |
| ralplan | Iterative planning | "ralplan this feature" |
| ulw | Max parallelism | "ulw refactor the API" |
| plan | Planning interview | "plan the new endpoints" |
| team | Coordinated agents | "/team 3:executor fix errors" |

**ralph includes ultrawork:** When you activate ralph mode, it automatically includes ultrawork's parallel execution. No need to combine keywords.

TEAMS:
Spawn coordinated agents with shared task lists and real-time messaging:
- /copilot-omni:team 3:executor "fix all TypeScript errors"
- /copilot-omni:team 5:debugger "fix build errors in src/"
Teams use `python3 scripts/subagent.py` for agent invocation (WS5b will add full team orchestration).

MCP SERVERS:
Run /copilot-omni:mcp-setup to add tools like web search, GitHub, etc.

copilot-omni CLI HELPERS (if installed):
- omc teleport    - Create an isolated git worktree
- omc team status - Inspect a running team job
- Session summaries are written to `.omni/sessions/*.json`

That's it! Just use Claude Code normally.
```

### For Users Upgrading from 2.x (IS_UPGRADE is true):

```
copilot-omni Setup Complete! (Upgraded from 2.x)

GOOD NEWS: Your existing commands still work!
- /ralph, /ultrawork, /omni-plan, etc. all still function

WHAT'S NEW in 3.0:
You no longer NEED those commands. Everything is automatic now:
- Just say "don't stop until done" instead of /ralph
- Just say "fast" or "parallel" instead of /ultrawork
- Just say "plan this" instead of /omni-plan
- Just say "stop" instead of /cancel

MAGIC KEYWORDS (power-user shortcuts):
| Keyword | Same as old... | Example |
|---------|----------------|---------|
| ralph | /ralph | "ralph: fix the bug" |
| ralplan | /ralplan | "ralplan this feature" |
| ulw | /ultrawork | "ulw refactor API" |
| omni-plan | /omni-plan | "plan the endpoints" |
| team | (new!) | "/team 3:executor fix errors" |

TEAMS (NEW!):
Spawn coordinated agents with shared task lists and real-time messaging:
- /copilot-omni:team 3:executor "fix all TypeScript errors"
- Uses `python3 scripts/subagent.py` for agent invocation (WS5b will add full team orchestration)

copilot-omni CLI HELPERS (if installed):
- omc teleport    - Create an isolated git worktree
- omc team status - Inspect a running team job
- Session summaries are written to `.omni/sessions/*.json`

Your workflow won't break - it just got easier!
```

## Optional Rule Templates

copilot-omni includes rule templates you can copy to your project's `.claude/rules/` directory for automatic context injection:

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
mkdir -p .claude/rules
cp "${CLAUDE_PLUGIN_ROOT}/templates/rules/"*.md .claude/rules/
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
gh api user/starred/Yeachan-Heo/copilot-omni &>/dev/null
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
gh api -X PUT /user/starred/Yeachan-Heo/copilot-omni 2>/dev/null && echo "Thanks for starring!" || true
```

**Note:** Fail silently if the API call doesn't work - never block setup completion.

### If gh is NOT available or not authenticated:

```bash
echo ""
echo "If you enjoy copilot-omni, consider starring the repo:"
echo "  https://github.com/Yeachan-Heo/copilot-omni"
echo ""
```

## Mark Completion

Get the current copilot-omni version and mark setup complete:

```bash
# Get current copilot-omni version from CLAUDE.md
OMC_VERSION=""
if [ -f ".claude/CLAUDE.md" ]; then
  OMC_VERSION=$(grep -m1 'copilot-omni:VERSION:' .claude/CLAUDE.md 2>/dev/null | sed -E 's/.*copilot-omni:VERSION:([^ ]+).*/\1/' || true)
elif [ -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" ]; then
  OMC_VERSION=$(grep -m1 'copilot-omni:VERSION:' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null | sed -E 's/.*copilot-omni:VERSION:([^ ]+).*/\1/' || true)
fi
if [ -z "$OMC_VERSION" ]; then
  OMC_VERSION=$(omc --version 2>/dev/null | head -1 || true)
fi
if [ -z "$OMC_VERSION" ]; then
  OMC_VERSION="unknown"
fi

bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-progress.sh" complete "$OMC_VERSION"
```
