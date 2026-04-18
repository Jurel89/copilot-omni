---
name: omni-setup
description: Install or refresh copilot-omni for plugin and local-dev setups from the canonical setup flow
level: 2
---

# copilot-omni Setup

This is the **only command you need to learn**. After running this, everything else is automatic.

**When this skill is invoked, immediately execute the workflow below. Do not only restate or summarize these instructions back to the user.**

## Best-Fit Use

Choose this setup flow when the user wants to **install, refresh, or repair copilot-omni itself**.

- Marketplace/plugin install users should land here after `copilot plugin install copilot-omni@copilot-omni`
- Local-dev and worktree users should land here after updating the checked-out repo and rerunning setup

## Flag Parsing

Check for flags in the user's invocation:
- `--help` → Show Help Text (below) and stop
- `--local` → Phase 1 only (target=local), then stop
- `--force` → Skip Pre-Setup Check, run full setup (Phase 1 → 2 → 3)
- No flags → Run Pre-Setup Check, then full setup if needed

## Help Text

When user runs with `--help`, display this and stop:

```
copilot-omni Setup - Configure copilot-omni

USAGE:
  /copilot-omni:omni-setup           Run initial setup wizard (or update if already configured)
  /copilot-omni:omni-setup --local   Configure local project (.omni/ directory)
  /copilot-omni:omni-setup --force   Force full setup wizard even if already configured
  /copilot-omni:omni-setup --help    Show this help

MODES:
  Initial Setup (no flags)
    - Interactive wizard for first-time setup
    - Initializes .omni/ state directory
    - Checks for updates
    - Offers MCP configuration
    - If already configured, offers quick update option

  Local Configuration (--local)
    - Ensures .omni/ directory exists
    - Project-specific settings
    - Use this to update project config after copilot-omni upgrades

  Force Full Setup (--force)
    - Bypasses the "already configured" check
    - Runs the complete setup wizard from scratch
    - Use when you want to reconfigure preferences

EXAMPLES:
  /copilot-omni:omni-setup           # First time setup (or update if configured)
  /copilot-omni:omni-setup --local   # Update this project
  /copilot-omni:omni-setup --force   # Re-run full setup wizard
```

## Pre-Setup Check: Already Configured?

**CRITICAL**: Before doing anything else, check if setup has already been completed. This prevents users from having to re-run the full setup wizard after every update.

```bash
# Check if .omni/config.json exists
if [ -f ".omni/config.json" ]; then
  echo "copilot-omni setup was already completed."
  ALREADY_CONFIGURED="true"
else
  ALREADY_CONFIGURED="false"
fi
```

### If Already Configured (and no --force flag)

If `ALREADY_CONFIGURED` is true AND the user did NOT pass `--force` or `--local` flags:

Emit as plain chat and wait for the user's reply:

**Question:** "copilot-omni is already configured. What would you like to do?"

**Options:**
1. **Quick update** - Refresh .omni/ config without re-running full setup
2. **Run full setup again** - Go through the complete setup wizard
3. **Cancel** - Exit without changes

**If user chooses "Quick update":**
- Ensure `.omni/` directory and subdirectories exist
- Report success and exit

**If user chooses "Run full setup again":**
- Continue with Resume Detection below

**If user chooses "Cancel":**
- Exit without any changes

### Force Flag Override

If user passes `--force` flag, skip this check and proceed directly to setup.

## Resume Detection

Before starting any phase, check for existing state:

```bash
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" resume
```

If state exists (output is not "fresh"), emit as plain chat and wait for the user's reply:

**Question:** "Found a previous setup session. Would you like to resume or start fresh?"

**Options:**
1. **Resume from step $LAST_STEP** - Continue where you left off
2. **Start fresh** - Begin from the beginning (clears saved state)

If user chooses "Start fresh":
```bash
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" clear
```

## Phase Execution

### For `--local` flag:
Read the file at `${OMNI_PLUGIN_ROOT}/skills/omni-setup/phases/01-install.md` and follow its instructions.
(The phase file handles early exit for flag mode.)

### For full setup (default or --force):
Execute phases sequentially. For each phase, read the corresponding file and follow its instructions:

1. **Phase 1 - Initialize Project**: Read `${OMNI_PLUGIN_ROOT}/skills/omni-setup/phases/01-install.md` and follow its instructions.

2. **Phase 2 - Environment Configuration**: Read `${OMNI_PLUGIN_ROOT}/skills/omni-setup/phases/02-configure.md` and follow its instructions.

3. **Phase 3 - Integration Setup**: Read `${OMNI_PLUGIN_ROOT}/skills/omni-setup/phases/03-integrations.md` and follow its instructions.

## Graceful Interrupt Handling

**IMPORTANT**: This setup process saves progress after each phase via `${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh`. If interrupted (Ctrl+C or connection loss), the setup can resume from where it left off.

## Keeping Up to Date

After installing copilot-omni updates (via plugin update):

**Automatic**: Just run `/copilot-omni:omni-setup` - it will detect you've already configured and offer a quick update option that skips the full wizard.

**Manual options**:
- `/copilot-omni:omni-setup --local` to update project config only
- `/copilot-omni:omni-setup --force` to re-run the full wizard (reconfigure preferences)

This ensures you have the newest features and agent configurations without repeating the full setup.
