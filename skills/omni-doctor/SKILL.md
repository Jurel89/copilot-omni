---
name: omni-doctor
description: Diagnose and fix copilot-omni installation issues
level: 3
---

# Doctor Skill

Note: All `~/.claude/...` paths in this guide respect `CLAUDE_CONFIG_DIR` when that environment variable is set.

## Task: Run Installation Diagnostics

You are the copilot-omni Doctor - diagnose and fix installation issues.

### Step 1: Check Plugin Version

```bash
# Get installed and latest versions (cross-platform)
node -e "const p=require('path'),f=require('fs'),h=require('os').homedir(),d=process.env.CLAUDE_CONFIG_DIR||p.join(h,'.claude'),b=p.join(d,'plugins','cache','omc','copilot-omni');try{const v=f.readdirSync(b).filter(x=>/^\d/.test(x)).sort((a,c)=>a.localeCompare(c,void 0,{numeric:true}));console.log('Installed:',v.length?v[v.length-1]:'(none)')}catch{console.log('Installed: (none)')}"
npm view copilot-omni version 2>/dev/null || echo "Latest: (unavailable)"
```

**Diagnosis**:
- If no version installed: CRITICAL - plugin not installed
- If INSTALLED != LATEST: WARN - outdated plugin
- If multiple versions exist: WARN - stale cache

### Step 2: Check for Legacy Hooks in settings.json

Read both `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` (profile-level) and `./.claude/settings.json` (project-level) and check if there's a `"hooks"` key with entries like:
- `bash ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/keyword-detector.sh`
- `bash ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/persistent-mode.sh`
- `bash ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/session-start.sh`

**Diagnosis**:
- If found: CRITICAL - legacy hooks causing duplicates

### Step 3: Check for Legacy Bash Hook Scripts

```bash
ls -la "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/*.sh 2>/dev/null
```

**Diagnosis**:
- If `keyword-detector.sh`, `persistent-mode.sh`, `session-start.sh`, or `stop-continuation.sh` exist: WARN - legacy scripts (can cause confusion)

### Step 4: Check CLAUDE.md

```bash
# Check if CLAUDE.md exists
ls -la "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/CLAUDE.md 2>/dev/null

# Check for copilot-omni markers (<!-- copilot-omni:START --> is the canonical marker)
grep -q "<!-- copilot-omni:START -->" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null && echo "Has copilot-omni config" || echo "Missing copilot-omni config in CLAUDE.md"

# Check CLAUDE.md (or deterministic companion) version marker and compare with latest installed plugin cache version
node -e "const p=require('path'),f=require('fs'),h=require('os').homedir(),d=process.env.CLAUDE_CONFIG_DIR||p.join(h,'.claude');const base=p.join(d,'CLAUDE.md');let baseContent='';try{baseContent=f.readFileSync(base,'utf8')}catch{};let candidates=[base];let referenced='';const importMatch=baseContent.match(/CLAUDE-[^ )]*\\.md/);if(importMatch){referenced=p.join(d,importMatch[0]);candidates.push(referenced)}else{const defaultCompanion=p.join(d,'CLAUDE-omc.md');if(f.existsSync(defaultCompanion))candidates.push(defaultCompanion);try{const others=f.readdirSync(d).filter(n=>/^CLAUDE-.*\\.md$/i.test(n)).sort().map(n=>p.join(d,n));for(const o of others){if(candidates.includes(o)===false)candidates.push(o)}}catch{}};let claudeV='(missing)';let claudeSource='(none)';for(const file of candidates){try{const c=f.readFileSync(file,'utf8');const m=c.match(/<!--\\s*copilot-omni:VERSION:([^\\s]+)\\s*-->/i);if(m){claudeV=m[1];claudeSource=file;break}}catch{}};if(claudeV==='(missing)'&&candidates.length>0){claudeV='(missing marker)';claudeSource='scanned deterministic CLAUDE sources';};let pluginV='(none)';try{const b=p.join(d,'plugins','cache','omc','copilot-omni');const v=f.readdirSync(b).filter(x=>/^\\d/.test(x)).sort((a,c)=>a.localeCompare(c,void 0,{numeric:true}));pluginV=v.length?v[v.length-1]:'(none)';}catch{};console.log('CLAUDE.md copilot-omni version:',claudeV);console.log('copilot-omni version source:',claudeSource);console.log('Latest cached plugin version:',pluginV);if(claudeV==='(missing)'||claudeV==='(missing marker)'||pluginV==='(none)'){console.log('VERSION CHECK SKIPPED: missing CLAUDE marker or plugin cache')}else if(claudeV===pluginV){console.log('VERSION MATCH: CLAUDE and plugin cache are aligned')}else{console.log('VERSION DRIFT: CLAUDE.md and plugin versions differ')}"

# Check companion files for file-split pattern (e.g. CLAUDE-omc.md)
find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" -maxdepth 1 -type f -name 'CLAUDE-*.md' -print 2>/dev/null
while IFS= read -r f; do
  grep -q "<!-- copilot-omni:START -->" "$f" 2>/dev/null && echo "Has copilot-omni config in companion: $f"
done < <(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" -maxdepth 1 -type f -name 'CLAUDE-*.md' -print 2>/dev/null)

# Check if CLAUDE.md references a companion file
grep -o "CLAUDE-[^ )]*\.md" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" 2>/dev/null
```

**Diagnosis**:
- If CLAUDE.md missing: CRITICAL - CLAUDE.md not configured
- If `<!-- copilot-omni:START -->` found in CLAUDE.md: OK
- If `<!-- copilot-omni:START -->` found in a companion file (e.g. `CLAUDE-omc.md`): OK - file-split pattern detected
- If no copilot-omni markers in CLAUDE.md or any companion file: WARN - outdated CLAUDE.md
- If `copilot-omni:VERSION` marker is missing from deterministic CLAUDE source scan (base + referenced companion): WARN - cannot verify CLAUDE.md freshness
- If `CLAUDE.md copilot-omni version` != `Latest cached plugin version`: WARN - version drift detected (run `omc update` or `omc setup`)

### Step 5: Check for Stale Plugin Cache

```bash
# Count versions in cache (cross-platform)
node -e "const p=require('path'),f=require('fs'),h=require('os').homedir(),d=process.env.CLAUDE_CONFIG_DIR||p.join(h,'.claude'),b=p.join(d,'plugins','cache','omc','copilot-omni');try{const v=f.readdirSync(b).filter(x=>/^\d/.test(x));console.log(v.length+' version(s):',v.join(', '))}catch{console.log('0 versions')}"
```

**Diagnosis**:
- If > 1 version: WARN - multiple cached versions (cleanup recommended)

### Step 6: Check for Legacy Curl-Installed Content

Check for legacy agents, commands, and skills installed via curl (before plugin system).
**Important**: Only flag files whose names match actual plugin-provided names. Do NOT flag user's custom agents/commands/skills that are unrelated to copilot-omni.

```bash
# Check for legacy agents directory
ls -la "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/agents/ 2>/dev/null

# Check for legacy commands directory
ls -la "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands/ 2>/dev/null

# Check for legacy skills directory
ls -la "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/skills/ 2>/dev/null
```

**Diagnosis**:
- If `~/.claude/agents/` exists with files matching plugin agent names: WARN - legacy agents (now provided by plugin)
- If `~/.claude/commands/` exists with files matching plugin command names: WARN - legacy commands (now provided by plugin)
- If `~/.claude/skills/` exists with files matching plugin skill names: WARN - legacy skills (now provided by plugin)
- If custom files exist that do NOT match plugin names: OK - these are user custom content, do not flag them

**Known plugin agent names** (check agents/ for these):
`architect.md`, `document-specialist.md`, `explore.md`, `executor.md`, `debugger.md`, `planner.md`, `analyst.md`, `critic.md`, `verifier.md`, `test-engineer.md`, `designer.md`, `writer.md`, `qa-tester.md`, `scientist.md`, `security-reviewer.md`, `code-reviewer.md`, `git-master.md`, `code-simplifier.md`

**Known plugin skill names** (check skills/ for these):
`ai-slop-cleaner`, `autopilot`, `cancel`, `ccg`, `configure-notifications`, `deep-interview`, `deepinit`, `external-context`, `learner`, `mcp-setup`, `omni-doctor`, `omni-setup`, `omni-teams`, `plan`, `project-session-manager`, `ralph`, `ralplan`, `release`, `sciomni`, `setup`, `skill`, `team`, `ultraqa`, `ultrawork`, `visual-verdict`, `writer-memory`

**Known plugin command names** (check commands/ for these):
`ultrawork.md`, `deepsearch.md`

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
| Legacy Hooks (settings.json) | OK/CRITICAL | ... |
| Legacy Scripts (~/.claude/hooks/) | OK/WARN | ... |
| CLAUDE.md | OK/WARN/CRITICAL | ... |
| Plugin Cache | OK/WARN | ... |
| Legacy Agents (~/.claude/agents/) | OK/WARN | ... |
| Legacy Commands (~/.claude/commands/) | OK/WARN | ... |
| Legacy Skills (~/.claude/skills/) | OK/WARN | ... |

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

### Fix: Legacy Hooks in settings.json
Remove the `"hooks"` section from `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` (keep other settings intact)

### Fix: Legacy Bash Scripts
```bash
rm -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/keyword-detector.sh
rm -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/persistent-mode.sh
rm -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/session-start.sh
rm -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/stop-continuation.sh
```

### Fix: Outdated Plugin
```bash
# Clear plugin cache (cross-platform)
node -e "const p=require('path'),f=require('fs'),d=process.env.CLAUDE_CONFIG_DIR||p.join(require('os').homedir(),'.claude'),b=p.join(d,'plugins','cache','omc','copilot-omni');try{f.rmSync(b,{recursive:true,force:true});console.log('Plugin cache cleared. Restart Claude Code to fetch latest version.')}catch{console.log('No plugin cache found')}"
```

### Fix: Stale Cache (multiple versions)
```bash
# Keep only latest version (cross-platform)
node -e "const p=require('path'),f=require('fs'),h=require('os').homedir(),d=process.env.CLAUDE_CONFIG_DIR||p.join(h,'.claude'),b=p.join(d,'plugins','cache','omc','copilot-omni');try{const v=f.readdirSync(b).filter(x=>/^\d/.test(x)).sort((a,c)=>a.localeCompare(c,void 0,{numeric:true}));v.slice(0,-1).forEach(x=>f.rmSync(p.join(b,x),{recursive:true,force:true}));console.log('Removed',v.length-1,'old version(s)')}catch(e){console.log('No cache to clean')}"
```

### Fix: Missing/Outdated CLAUDE.md
Fetch latest from GitHub and write to `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`:
```
WebFetch(url: "https://raw.githubusercontent.com/Yeachan-Heo/copilot-omni/main/docs/CLAUDE.md", prompt: "Return the complete raw markdown content exactly as-is")
```

### Fix: Legacy Curl-Installed Content

Remove legacy agents, commands, and skills directories (now provided by plugin):

```bash
# Backup first (optional - ask user)
# mv "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/agents "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/agents.bak
# mv "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands.bak
# mv "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/skills "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/skills.bak

# Or remove directly
rm -rf "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/agents
rm -rf "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/commands
rm -rf "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/skills
```

**Note**: Only remove if these contain copilot-omni-related files. If user has custom agents/commands/skills, warn them and ask before removing.

---

## Post-Fix

After applying fixes, inform user:
> Fixes applied. **Restart Claude Code** for changes to take effect.
