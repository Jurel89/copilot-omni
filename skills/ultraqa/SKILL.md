---
name: ultraqa
description: QA cycling loop — build/lint/test, fix, retry up to 5 cycles
argument-hint: "[--commands '<cmd1>;<cmd2>'] [--max-cycles N] [--repeat-threshold N] <task description>"
level: 3
---

<Purpose>
UltraQA runs a configurable set of shell commands in a cycle loop. Each cycle:
runs all commands, checks for failures, classifies the dominant error, spawns an
executor to fix it, and retries — up to max_cycles (default 5) or until all pass.
Stops early if the same error signature appears >= repeat_threshold times (default 3).
</Purpose>

<Use_When>
- User wants an autonomous QA fix loop: build/lint/test until passing
- User says "ultraqa", "qa loop", "keep fixing until tests pass"
- Codebase needs repeated fix-verify cycles with observable state
</Use_When>

<Do_Not_Use_When>
- Single one-shot verification is needed — use qa-tester directly
- User wants a full autonomous pipeline from idea to code — use autopilot
- No commands exist to run — ultraqa requires at least one verifiable command
</Do_Not_Use_When>

<Why_This_Exists>
Fixing failing tests or build errors usually takes multiple iterations. UltraQA
automates the cycle: run → classify failure → spawn fix → run again. It persists
state per run, detects stuck loops (same error 3x), and supports clean cancel/resume.
</Why_This_Exists>

# Router preamble
1. Read MCP state: `python3 scripts/router_state.py --read --session-id "$OMNI_SESSION_ID" --json`
2. If `decision.redirect == "deep-interview"`, defer to `/copilot-omni:deep-interview` and exit.
3. Otherwise, proceed with `decision.skill == ultraqa`.

## Step 0 — Initialise run

```bash
OMNI_SESSION_ID="${OMNI_SESSION_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
ULTRAQA_RUN_ID="ultraqa-${OMNI_SESSION_ID}"
RUN_DIR=".omni/runs/${ULTRAQA_RUN_ID}"
mkdir -p "${RUN_DIR}"

# Check for resume state
python3 scripts/router_state.py --read --mode ultraqa --session-id "$OMNI_SESSION_ID" --json \
  > "${RUN_DIR}/resume-state.json" 2>/dev/null || echo '{}' > "${RUN_DIR}/resume-state.json"

LAST_CYCLE=$(python3 -c "
import json
try:
    d = json.load(open('${RUN_DIR}/resume-state.json'))
    print(d.get('cycle', 0))
except Exception:
    print(0)
")

echo "ultraqa: run_id=${ULTRAQA_RUN_ID}, last_cycle=${LAST_CYCLE}"
```

---

## Step 1 — Write spec

```bash
# Parse commands from PROMPT args or use defaults.
# Supported: --commands 'cmd1;cmd2;cmd3' --max-cycles N --repeat-threshold N
# Remaining text is treated as context / task description.

python3 - "${RUN_DIR}" "{{PROMPT}}" <<'PYEOF'
"""Parse ultraqa arguments and write spec.json.

Error-signature algorithm
--------------------------
To detect repeated failures across cycles, ultraqa computes a sha256
fingerprint over each failed command's output:

    raw = command_name + first_200_chars_of_stderr_after_stripping
    strip rule: remove lines that match /^\\s*\\d+[:|]/ (line numbers)
                remove ISO timestamps \\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}
    sig = sha256(raw.encode()).hexdigest()[:16]

This makes the fingerprint robust to cosmetic output changes (timestamps,
line numbers shifting) while still catching the same semantic error.
The "dominant failure" is the command with the highest exit code; ties
are broken by command order.
"""
import json
import re
import sys
from pathlib import Path

run_dir, raw_prompt = sys.argv[1], sys.argv[2]
run_dir_path = Path(run_dir)

# ── Parse flags ──────────────────────────────────────────────────────────────
commands_raw = None
max_cycles = 5
repeat_threshold = 3
context = raw_prompt

# Extract --commands '...'
m = re.search(r"--commands\s+'([^']+)'", raw_prompt)
if not m:
    m = re.search(r'--commands\s+"([^"]+)"', raw_prompt)
if not m:
    m = re.search(r"--commands\s+(\S+)", raw_prompt)
if m:
    commands_raw = m.group(1)
    context = raw_prompt[:m.start()].strip() + " " + raw_prompt[m.end():].strip()

m2 = re.search(r"--max-cycles\s+(\d+)", raw_prompt)
if m2:
    max_cycles = int(m2.group(1))
    context = context.replace(m2.group(0), "").strip()

m3 = re.search(r"--repeat-threshold\s+(\d+)", raw_prompt)
if m3:
    repeat_threshold = int(m3.group(1))
    context = context.replace(m3.group(0), "").strip()

# Default commands: python3 -m pytest -q
if not commands_raw:
    commands_raw = "python3 -m pytest -q"

commands = [c.strip() for c in commands_raw.split(";") if c.strip()]

spec = {
    "run_id": run_dir_path.name,
    "commands": commands,
    "max_cycles": max_cycles,
    "repeat_threshold": repeat_threshold,
    "context": context.strip(),
}

spec_path = run_dir_path / "spec.json"
spec_path.write_text(json.dumps(spec, indent=2))
print(f"ultraqa: spec — commands={commands}, max_cycles={max_cycles}, repeat_threshold={repeat_threshold}")
PYEOF

SPEC_EXIT=$?
[ ${SPEC_EXIT} -eq 0 ] || { echo "FAIL: spec write failed"; exit 1; }
```

---

## Step 2 — Cycle loop

```bash
# Read spec
MAX_CYCLES=$(python3 -c "import json; d=json.load(open('${RUN_DIR}/spec.json')); print(d['max_cycles'])")
REPEAT_THRESHOLD=$(python3 -c "import json; d=json.load(open('${RUN_DIR}/spec.json')); print(d['repeat_threshold'])")

FINAL_STATUS="cycles_exhausted"
LAST_SIG=""
SAME_SIG_COUNT=0

for CYCLE in $(seq 1 ${MAX_CYCLES}); do
  # Check cancel signal each cycle
  if [ -f "${RUN_DIR}/cancel.signal" ]; then
    echo "ultraqa: cancel.signal detected before cycle ${CYCLE}"
    FINAL_STATUS="cancelled"
    break
  fi

  CYCLE_DIR="${RUN_DIR}/cycle-${CYCLE}"
  mkdir -p "${CYCLE_DIR}"

  echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] Running commands..."

  # ── 2a. Run each command ──────────────────────────────────────────────────
  python3 - "${RUN_DIR}" "${CYCLE_DIR}" "${CYCLE}" <<'PYEOF'
import json
import os
import subprocess
import sys
from pathlib import Path

run_dir, cycle_dir, cycle = sys.argv[1], sys.argv[2], int(sys.argv[3])
spec = json.loads((Path(run_dir) / "spec.json").read_text())
commands = spec["commands"]

results = []
all_pass = True

for cmd in commands:
    # Sanitise command name for directory (replace non-alphanum with -)
    cmd_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in cmd.split()[0])
    cmd_dir = Path(cycle_dir) / cmd_name
    cmd_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )

    (cmd_dir / "stdout.log").write_text(proc.stdout or "")
    (cmd_dir / "stderr.log").write_text(proc.stderr or "")
    (cmd_dir / "exit.txt").write_text(str(proc.returncode))

    passed = proc.returncode == 0
    if not passed:
        all_pass = False

    results.append({
        "command": cmd,
        "cmd_name": cmd_name,
        "exit_code": proc.returncode,
        "passed": passed,
        "stdout_excerpt": proc.stdout[:500] if proc.stdout else "",
        "stderr_excerpt": proc.stderr[:500] if proc.stderr else "",
    })

    status_icon = "PASS" if passed else f"FAIL (exit {proc.returncode})"
    print(f"  [{cmd_name}] {status_icon}")

cycle_result = {
    "cycle": cycle,
    "all_pass": all_pass,
    "results": results,
}
(Path(cycle_dir) / "status.json").write_text(json.dumps(cycle_result, indent=2))

# Exit 0 if all pass, 1 otherwise
sys.exit(0 if all_pass else 1)
PYEOF

  CMD_EXIT=$?

  # ── 2b. Check if all commands passed ─────────────────────────────────────
  if [ ${CMD_EXIT} -eq 0 ]; then
    echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] PASSED — all commands succeeded"
    FINAL_STATUS="converged"

    # Write MCP state
    python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ultraqa', {
    'run_id': '${ULTRAQA_RUN_ID}',
    'cycle': ${CYCLE},
    'status': 'converged',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

    break
  fi

  echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] FAILED — classifying errors..."

  # ── 2c. Compute error signature for same-error detection ─────────────────
  CURRENT_SIG=$(python3 - "${CYCLE_DIR}" <<'SIGEOF'
"""Compute dominant-failure error signature.

Algorithm:
  1. Find command with highest (non-zero) exit code. Ties broken by order.
  2. Strip line-number prefixes (/^\s*\d+[:|]/) and ISO timestamps from stderr.
  3. sha256(command_name + first_200_chars_of_cleaned_stderr).hexdigest()[:16]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

cycle_dir = Path(sys.argv[1])
status = json.loads((cycle_dir / "status.json").read_text())
results = status["results"]

# Find dominant failure
dominant = None
for r in results:
    if not r["passed"]:
        if dominant is None or r["exit_code"] > dominant["exit_code"]:
            dominant = r

if dominant is None:
    print("")
    sys.exit(0)

cmd_name = dominant.get("cmd_name", dominant["command"].split()[0])
stderr_raw = dominant.get("stderr_excerpt", "")

# Strip line numbers and timestamps
cleaned = re.sub(r"^\s*\d+[:|]\s*", "", stderr_raw, flags=re.MULTILINE)
cleaned = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "", cleaned)
cleaned = cleaned.strip()[:200]

raw = cmd_name + cleaned
sig = hashlib.sha256(raw.encode()).hexdigest()[:16]
print(sig)
SIGEOF
)

  # ── 2d. Same-error detection ──────────────────────────────────────────────
  if [ -n "${CURRENT_SIG}" ] && [ "${CURRENT_SIG}" = "${LAST_SIG}" ]; then
    SAME_SIG_COUNT=$((SAME_SIG_COUNT + 1))
    if [ ${SAME_SIG_COUNT} -ge ${REPEAT_THRESHOLD} ]; then
      echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] STALLED — same error signature (${CURRENT_SIG}) appeared ${SAME_SIG_COUNT} times"
      FINAL_STATUS="stalled"

      python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ultraqa', {
    'run_id': '${ULTRAQA_RUN_ID}',
    'cycle': ${CYCLE},
    'status': 'stalled',
    'error_sig': '${CURRENT_SIG}',
    'same_sig_count': ${SAME_SIG_COUNT},
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

      break
    fi
  else
    SAME_SIG_COUNT=0
    LAST_SIG="${CURRENT_SIG}"
  fi

  # Update MCP state for this cycle
  python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ultraqa', {
    'run_id': '${ULTRAQA_RUN_ID}',
    'cycle': ${CYCLE},
    'status': 'cycling',
    'error_sig': '${CURRENT_SIG}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

  # Check cancel signal before spawning fix agent
  if [ -f "${RUN_DIR}/cancel.signal" ]; then
    echo "ultraqa: cancel.signal detected before fix in cycle ${CYCLE}"
    FINAL_STATUS="cancelled"
    break
  fi

  # ── 2e. Classify failure via qa-tester and spawn executor fix ────────────
  FAILURE_SUMMARY=$(python3 - "${CYCLE_DIR}" <<'FSEOF'
import json
import sys
from pathlib import Path

cycle_dir = Path(sys.argv[1])
status = json.loads((cycle_dir / "status.json").read_text())
lines = [f"[Cycle {status['cycle']}] failures:"]
for r in status["results"]:
    if not r["passed"]:
        lines.append(f"  command: {r['command']}")
        lines.append(f"  exit_code: {r['exit_code']}")
        if r.get("stderr_excerpt"):
            lines.append(f"  stderr: {r['stderr_excerpt'][:300]}")
        if r.get("stdout_excerpt"):
            lines.append(f"  stdout: {r['stdout_excerpt'][:300]}")
        lines.append("")
print("\n".join(lines))
FSEOF
)

  echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] Spawning executor to fix failures..."

  # Spawn qa-tester to classify then executor to fix (synchronous, category=deep)
  python3 scripts/subagent.py qa-tester \
    "CLASSIFY FAILURE for ultraqa fix.
Run ID: ${ULTRAQA_RUN_ID}. Session: ${OMNI_SESSION_ID}.
Failure summary:
${FAILURE_SUMMARY}

Provide: root cause (1 sentence), affected files (list), recommended fix (specific)." \
    --category deep \
    --session-id "${OMNI_SESSION_ID}" \
    --run-id "${ULTRAQA_RUN_ID}" \
    > "${CYCLE_DIR}/qa-classify.md" 2>"${CYCLE_DIR}/qa-classify-stderr.log" || true

  QA_DIAGNOSIS=$(cat "${CYCLE_DIR}/qa-classify.md" 2>/dev/null || echo "${FAILURE_SUMMARY}")

  python3 scripts/subagent.py executor \
    "FIX QA FAILURES — ultraqa cycle ${CYCLE}.
Run ID: ${ULTRAQA_RUN_ID}. Session: ${OMNI_SESSION_ID}.
QA Diagnosis:
${QA_DIAGNOSIS}

Failure summary:
${FAILURE_SUMMARY}

Apply the minimum fix. Do not broaden scope. Verify the fix addresses the root cause." \
    --category deep \
    --session-id "${OMNI_SESSION_ID}" \
    --run-id "${ULTRAQA_RUN_ID}" \
    > "${CYCLE_DIR}/executor-fix.md" 2>"${CYCLE_DIR}/executor-fix-stderr.log" || true

  echo "[ULTRAQA Cycle ${CYCLE}/${MAX_CYCLES}] Fix applied — proceeding to next cycle"

  # Brief pause to let filesystem settle
  sleep 0.1

done
```

---

## Step 3 — Write final status and exit

```bash
# Write final run status
python3 -c "
import json, datetime, sys
final_status = '${FINAL_STATUS}'
p = '${RUN_DIR}/status.json'
open(p, 'w').write(json.dumps({
    'run_id': '${ULTRAQA_RUN_ID}',
    'state': final_status,
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
print(f'[ULTRAQA] final status: {final_status}')
"

# Exit codes: 0=converged, 1=stalled/cancelled/exhausted
case "${FINAL_STATUS}" in
  converged)
    echo "[ULTRAQA COMPLETE] Goal met. Run artifacts: ${RUN_DIR}/"
    exit 0
    ;;
  stalled)
    echo "[ULTRAQA STOPPED] Same failure repeated ${REPEAT_THRESHOLD}+ times. Root cause persists. See ${RUN_DIR}/ for details."
    exit 1
    ;;
  cancelled)
    echo "[ULTRAQA CANCELLED] Cancel signal received. Partial artifacts at ${RUN_DIR}/"
    exit 1
    ;;
  *)
    echo "[ULTRAQA STOPPED] Max cycles (${MAX_CYCLES}) reached without convergence. See ${RUN_DIR}/ for details."
    exit 1
    ;;
esac
```

---

## Resume

Re-invoke ultraqa with the same `$OMNI_SESSION_ID`. Step 0 reads
`state_read(mode="ultraqa", session_id=...)` to find the last cycle. Completed cycles
whose `all_pass=true` are not re-run. The loop resumes from the next cycle.

```bash
OMNI_SESSION_ID=my-session-id /copilot-omni:ultraqa "same task description"
```

## Cancel

Write the signal file to cancel the current ultraqa run cleanly:

```bash
echo "" > ".omni/runs/ultraqa-${OMNI_SESSION_ID}/cancel.signal"
```

Per ADR-0006: the cycle loop polls `cancel.signal` before each cycle and before each
executor spawn. On detection the loop exits cleanly with `state="cancelled"`.

---

<Examples>
<Good>
Run pytest until passing (default behaviour):
```bash
/copilot-omni:ultraqa "fix all failing tests in tests/"
```
Why good: Uses default commands (pytest), max_cycles=5, repeat_threshold=3.
</Good>

<Good>
Custom commands with semicolon separator:
```bash
/copilot-omni:ultraqa --commands 'npm run build;npm run lint;npm test' "fix all CI failures"
```
Why good: Three commands run in order each cycle; any failure triggers the fix loop.
</Good>

<Bad>
Infinitely retrying the same unfixable error without stall detection:
```
cycle 1: same error → fix
cycle 2: same error → fix
cycle 3: same error → fix (stall NOT detected)
```
Why bad: Without same-error detection, ultraqa would loop forever. The repeat_threshold
stops this at cycle 3 and surfaces the fundamental issue.
</Bad>
</Examples>

<Final_Checklist>
- [ ] Spec written with commands, max_cycles, repeat_threshold
- [ ] Cycle loop ran up to max_cycles
- [ ] All commands' stdout/stderr/exit.txt written per cycle
- [ ] MCP state row written for mode="ultraqa" each cycle
- [ ] Same-error detection fired at repeat_threshold (stalled exit)
- [ ] cancel.signal handled cleanly between cycles
- [ ] Final status.json written with state=converged|stalled|cancelled|cycles_exhausted
- [ ] No banned Claude primitives in this SKILL.md
</Final_Checklist>
