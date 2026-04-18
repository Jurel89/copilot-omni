---
name: omni-doctor
description: Diagnose and fix copilot-omni installation issues
level: 3
---

# Doctor Skill

Note: All `.omni/` paths are relative to the current project root unless noted otherwise.

## Task: Run Installation Diagnostics

You are the copilot-omni Doctor - diagnose and fix installation issues.

### Step 1: Check Plugin Version

```bash
# Get installed version from plugin manifest
if [ -f "plugin.json" ]; then
  python3 -c "import json; print('Installed:', json.load(open('plugin.json')).get('version', '(none)'))"
else
  echo "Installed: (none - plugin.json not found)"
fi

# Check Copilot CLI version
copilot --version 2>/dev/null || echo "Copilot CLI: (not found)"
```

**Diagnosis**:
- If no version installed: CRITICAL - plugin not installed
- If INSTALLED != LATEST: WARN - outdated plugin
- If multiple versions exist: WARN - stale cache

### Step 2: Check Plugin Manifest

Verify the plugin manifest is valid:

```bash
if [ -f "plugin.json" ]; then
  python3 -c "import json; d=json.load(open('plugin.json')); print('Name:', d.get('name')); print('Version:', d.get('version')); print('Skills:', len(d.get('skills', []))); print('Agents:', len(d.get('agents', [])))"
else
  echo "CRITICAL: plugin.json not found"
fi
```

**Diagnosis**:
- If plugin.json missing: CRITICAL - plugin manifest not found
- If skills/agents count is 0: WARN - plugin may be corrupted

### Step 3: Check for Legacy State Directories

Look for old v1.x state directories:

```bash
# Check for the legacy v1 state directory
if [ -d ".omni-legacy" ]; then
  echo "WARN: Legacy v1 state directory alias found. Run: python3 scripts/omni_migrate_v1_to_v2.py --dry-run"
elif [ -d ".omni" ] && [ -f ".omni/legacy-state.marker" ]; then
  echo "WARN: Legacy v1 state marker found. Run: python3 scripts/omni_migrate_v1_to_v2.py --dry-run"
fi

# Check for legacy state files
ls -la .omni/state/*.json 2>/dev/null | head -20
```

**Diagnosis**:
- If a legacy v1 state directory or marker exists: WARN - migration recommended
- If legacy state files exist in `.omni/state/`: INFO - old state files present

### Step 4: Check AGENTS.md and Docs

```bash
# Check if AGENTS.md exists
if [ -f "AGENTS.md" ]; then
  echo "AGENTS.md: found"
  grep -q "copilot-omni" AGENTS.md && echo "Has copilot-omni markers: yes" || echo "Has copilot-omni markers: no"
else
  echo "AGENTS.md: missing"
fi

# Check plugin version from manifest against expected
INSTALLED_VERSION=$(python3 -c "import json; print(json.load(open('plugin.json')).get('version', 'unknown'))" 2>/dev/null || echo "unknown")
echo "Plugin version: $INSTALLED_VERSION"
```

**Diagnosis**:
- If AGENTS.md missing: WARN - agent routing cheatsheet not present
- If plugin.json missing: CRITICAL - cannot determine version

### Step 5: Check .omni/ Directory Health

```bash
# Check .omni/ structure
for dir in runs plans specs decisions state sessions audit cache; do
  if [ -d ".omni/$dir" ]; then
    echo "OK: .omni/$dir/"
  else
    echo "MISSING: .omni/$dir/"
  fi
done

# Check config.json
if [ -f ".omni/config.json" ]; then
  python3 -c "import json; d=json.load(open('.omni/config.json')); print('Config schema_version:', d.get('schema_version', 'missing'))"
else
  echo "WARN: .omni/config.json not found"
fi
```

**Diagnosis**:
- If core directories missing: WARN - incomplete initialization
- If config.json missing: WARN - run setup to create default config

### Step 6: Check for Legacy Curl-Installed Content

Check for legacy agents, commands, and skills installed via curl (before plugin system).
**Important**: Only flag files whose names match actual plugin-provided names. Do NOT flag user's custom agents/commands/skills that are unrelated to copilot-omni.

```bash
# Check for legacy local skills directory
ls -la .omni/skills/ 2>/dev/null

# Check for legacy agents installed outside plugin
ls -la agents/ 2>/dev/null | head -10
```

**Diagnosis**:
- If legacy local skills conflict with plugin skills: WARN - naming collision
- If agents/ directory has files not in plugin manifest: INFO - custom agents detected

**Known plugin agent names** (check agents/ for these):
`analyst`, `architect`, `code-reviewer`, `code-simplifier`, `critic`, `debugger`, `designer`, `document-specialist`, `executor`, `explore`, `git-master`, `planner`, `qa-tester`, `scientist`, `security-reviewer`, `test-engineer`, `tracer`, `verifier`, `writer`

**Known plugin skill names** (check skills/ for these):
`ai-slop-cleaner`, `autopilot`, `cancel`, `configure-notifications`, `debug`, `deep-dive`, `deep-interview`, `deepinit`, `external-context`, `mcp-setup`, `omni-doctor`, `omni-reference`, `omni-setup`, `plan`, `ralph`, `ralplan`, `release`, `remember`, `setup`, `skill`, `skillify`, `team`, `trace`, `ultraqa`, `ultrawork`, `verify`, `wiki`

**Commands**: removed in v2.1.0 (the commands/ directory no longer exists).

---

## Step 7: Active Autopilot, Ralph, Ultrawork, and UltraQA Runs (WS5b/WS5c)

Read MCP state to list any currently active autopilot, ralph, ultrawork, or ultraqa runs.

```python
import json, sys, os
from pathlib import Path

# Scan .omni/runs/ for active autopilot, ralph, ultrawork, and ultraqa runs
runs_dir = Path(".omni/runs")
active_runs = []

_PREFIXES = ("autopilot-", "ralph-", "ultrawork-", "ultraqa-")

def _skill_of(run_id):
    for prefix in _PREFIXES:
        if run_id.startswith(prefix):
            return prefix.rstrip("-")
    return None

if runs_dir.exists():
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        skill = _skill_of(run_id)
        if skill is None:
            continue

        # Determine current phase/iteration/cycle and last-update timestamp
        phase_info = "unknown"
        last_update = None

        if skill == "autopilot":
            for phase_n in (5, 4, 3, 2, 1):
                sp = run_dir / f"phase-{phase_n}" / "status.json"
                if sp.exists():
                    try:
                        d = json.loads(sp.read_text())
                        state = d.get("state", "?")
                        ended_at = d.get("ended_at", "")
                        phase_info = f"phase={phase_n} state={state}"
                        last_update = ended_at
                        break
                    except Exception:
                        pass

        elif skill == "ralph":
            # ralph: find highest iteration
            iter_dirs = sorted(
                [p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("iteration-")],
                key=lambda p: int(p.name.split("-")[1]) if p.name.split("-")[1].isdigit() else -1
            )
            if iter_dirs:
                sp = iter_dirs[-1] / "status.json"
                if sp.exists():
                    try:
                        d = json.loads(sp.read_text())
                        n = d.get("iteration", "?")
                        state = d.get("state", "?")
                        ended_at = d.get("ended_at", "")
                        phase_info = f"iteration={n} state={state}"
                        last_update = ended_at
                    except Exception:
                        pass

        elif skill == "ultrawork":
            # ultrawork: read summary.json or run-level status.json
            summary_path = run_dir / "summary.json"
            run_status_path = run_dir / "status.json"
            if summary_path.exists():
                try:
                    d = json.loads(summary_path.read_text())
                    total = d.get("total", "?")
                    done = d.get("done", "?")
                    failed = d.get("failed", 0)
                    status = d.get("status", "?")
                    phase_info = f"total={total} done={done} failed={failed} status={status}"
                    last_update = d.get("by_task", {})
                    # Extract latest ended_at from by_task
                    latest = None
                    for t in d.get("by_task", {}).values():
                        ea = t.get("ended_at")
                        if ea:
                            latest = ea if latest is None else max(latest, ea)
                    last_update = latest
                except Exception:
                    pass
            elif run_status_path.exists():
                try:
                    d = json.loads(run_status_path.read_text())
                    state = d.get("state", "?")
                    ended_at = d.get("ended_at", "")
                    phase_info = f"state={state}"
                    last_update = ended_at
                except Exception:
                    pass
            # Also count spawned jobs
            job_dirs = [p for p in run_dir.iterdir()
                        if p.is_dir() and not p.name.startswith("_")]
            if job_dirs and phase_info == "unknown":
                phase_info = f"jobs={len(job_dirs)}"

        elif skill == "ultraqa":
            # ultraqa: find highest cycle
            cycle_dirs = sorted(
                [p for p in run_dir.iterdir()
                 if p.is_dir() and p.name.startswith("cycle-")],
                key=lambda p: int(p.name.split("-")[1]) if p.name.split("-")[1].isdigit() else -1
            )
            run_status_path = run_dir / "status.json"
            if run_status_path.exists():
                try:
                    d = json.loads(run_status_path.read_text())
                    state = d.get("state", "?")
                    ended_at = d.get("ended_at", "")
                    n_cycles = len(cycle_dirs)
                    phase_info = f"cycles={n_cycles} state={state}"
                    last_update = ended_at
                except Exception:
                    pass
            elif cycle_dirs:
                sp = cycle_dirs[-1] / "status.json"
                if sp.exists():
                    try:
                        d = json.loads(sp.read_text())
                        n = d.get("cycle", "?")
                        all_pass = d.get("all_pass", "?")
                        phase_info = f"cycle={n} all_pass={all_pass}"
                    except Exception:
                        pass

        cancel_signal = (run_dir / "cancel.signal").exists()
        active_runs.append({
            "run_id": run_id,
            "skill": skill,
            "phase_info": phase_info,
            "last_update": last_update or "unknown",
            "cancel_signal": cancel_signal,
        })

if not active_runs:
    print("Active runs: none")
else:
    print(f"Active runs ({len(active_runs)}):")
    for r in active_runs:
        cancel_note = " [cancel.signal present]" if r["cancel_signal"] else ""
        print(f"  {r['skill']:12s}  {r['run_id']}  {r['phase_info']}  last_update={r['last_update']}{cancel_note}")
```

**Diagnosis**:
- If no active runs: OK — no autopilot, ralph, ultrawork, or ultraqa sessions in progress
- If runs present with recent last_update: INFO — active session running
- If run has `cancel.signal` but no `state=cancelled` status: WARN — stale cancel signal (run `python3 scripts/verify_plugin_contract.py --check-cancel-signal-pairing` to confirm)
- If run has been in the same phase/iteration/cycle for > 30 min: WARN — potentially stuck
- If ultrawork run shows failed > 0: WARN — one or more fan-out jobs failed
- If ultraqa run shows state=stalled: WARN — same error repeated, needs human input

Add to the Report Format table:
```
| Active Runs (autopilot/ralph/ultrawork/ultraqa) | OK/INFO/WARN | <n> runs, or none |
```

---

## Report Format

After running all checks, output a report:

```
## copilot-omni Doctor Report

### Summary
[HEALTHY / ISSUES FOUND]

### Checks

| Check | Status | Details |
|-------|--------|---------|
| Plugin Version | OK/WARN/CRITICAL | ... |
| Plugin Manifest | OK/WARN/CRITICAL | ... |
| .omni/ Directory | OK/WARN | ... |
| AGENTS.md | OK/WARN | ... |
| Legacy v1 State | OK/WARN | ... |
| Custom Skills | OK/WARN | ... |

### Issues Found
1. [Issue description]
2. [Issue description]

### Recommended Fixes
[List fixes based on issues]
```

---

## Auto-Fix (if user confirms)

If issues found, ask user: "Would you like me to fix these issues automatically?"

If yes, apply fixes:

### Fix: Missing .omni/ Directories

```bash
mkdir -p .omni/{runs,plans,specs,decisions,state,sessions,audit,cache}
echo "Created .omni/ directory structure"
```

### Fix: Missing Default Config

```bash
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
```

### Fix: Legacy v1.x State

If a legacy v1 state directory or marker exists, offer migration:

```bash
python3 scripts/omni_migrate_v1_to_v2.py --dry-run
```

### Fix: Git Ignore Rules

```bash
if [ -d ".git" ] && ! grep -q "copilot-omni" .git/info/exclude 2>/dev/null; then
  cat >> .git/info/exclude << 'GIT_EOF'

# copilot-omni local artifacts
.omni/runs/*
.omni/state/*
.omni/sessions/*
.omni/cache/*
GIT_EOF
  echo "Added .omni/ ignore rules to .git/info/exclude"
fi
```

---

## Post-Fix

After applying fixes, inform user:
> Fixes applied. Restart your Copilot CLI session for changes to take effect.
