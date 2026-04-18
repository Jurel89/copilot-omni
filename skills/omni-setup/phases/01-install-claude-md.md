# Phase 1: Initialize Project

## Determine Configuration Target

If `--local` flag was passed, set `CONFIG_TARGET=local`.

Otherwise (initial setup wizard), emit as plain chat and wait for the user's reply:

**Question:** "Where should I configure copilot-omni?"

**Options:**
1. **Local (this project)** - Creates `.omni/` in the current project directory. Best for project-specific configurations.

Set `CONFIG_TARGET` to `local` based on user's choice.

## Create .omni/ Directory Structure

**MANDATORY**: Always run this step. Do NOT skip.

```bash
# Create .omni/ directory structure
mkdir -p .omni/{runs,plans,specs,decisions,state,sessions,audit,cache}

# Create default config if it doesn't exist
if [ ! -f ".omni/config.json" ]; then
  cat > .omni/config.json << 'CONFIG_EOF'
{
  "schema_version": 1,
  "runtime": {
    "max_parallel_subagents": 8
  }
}
CONFIG_EOF
  echo "Created default .omni/config.json"
fi

# Seed .git/info/exclude with copilot-omni ignore rules
if [ -d ".git" ]; then
  if ! grep -q "copilot-omni" .git/info/exclude 2>/dev/null; then
    cat >> .git/info/exclude << 'GIT_EOF'

# copilot-omni local artifacts
.omni/runs/*
.omni/state/*
.omni/sessions/*
.omni/cache/*
GIT_EOF
    echo "Added .omni/ ignore rules to .git/info/exclude"
  fi
fi

echo "Project initialization complete."
```

## Report Success

```
copilot-omni Project Configuration Complete
- .omni/ directory: Initialized with runs, plans, specs, state, sessions, audit, cache
- Git excludes: Added local `.omni/*` ignore rules to `.git/info/exclude`
- Config: .omni/config.json created (if missing)
- Scope: PROJECT - applies only to this project
- Hooks: Provided by plugin (no manual installation needed)
- Agents: 19 specialist agents available
- Skills: 27 workflow skills available

Note: This configuration is project-specific and won't affect other projects.
```

## Save Progress

```bash
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" save 2 "$CONFIG_TARGET"
```

## Early Exit for Flag Mode

If `--local` flag was used, clear state and **STOP HERE**:
```bash
bash "${OMNI_PLUGIN_ROOT}/scripts/setup-progress.sh" clear
```
Do not continue to Phase 2 or other phases.
