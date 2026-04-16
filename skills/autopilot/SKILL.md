---
name: autopilot
description: Full autonomous execution from idea to working code
argument-hint: "<product idea or task description>"
level: 4
---

<Purpose>
Autopilot takes a brief product idea and autonomously handles the full lifecycle:
requirements analysis, technical design, planning, parallel implementation, QA cycling,
and multi-perspective validation. It produces working, verified code from a 2-3 line
description.
</Purpose>

<Use_When>
- User wants end-to-end autonomous execution from an idea to working code
- User says "autopilot", "auto pilot", "autonomous", "build me", "create me", "make me", "full auto", "handle it all", or "I want a/an..."
- Task requires multiple phases: planning, coding, testing, and validation
- User wants hands-off execution and is willing to let the system run to completion
</Use_When>

<Do_Not_Use_When>
- User wants to explore options or brainstorm -- use `plan` skill instead
- User says "just explain", "draft only", or "what would you suggest" -- respond conversationally
- User wants a single focused code change -- use `ralph` or delegate to an executor agent
- User wants to review or critique an existing plan -- use `plan --review`
- Task is a quick fix or small bug -- use direct executor delegation
</Do_Not_Use_When>

<Why_This_Exists>
Most non-trivial software tasks require coordinated phases: understanding requirements,
designing a solution, implementing in parallel, testing, and validating quality.
Autopilot orchestrates all of these phases automatically so the user can describe what
they want and receive working code without managing each step.
</Why_This_Exists>

# Router preamble
1. Read MCP state: `python3 scripts/router_state.py --read --session-id "$OMNI_SESSION_ID" --json`
2. If `decision.redirect == "deep-interview"`, defer to `/copilot-omni:deep-interview` and exit.
3. Otherwise, proceed with `decision.skill == autopilot`.

<Execution_Policy>
- Each phase must complete before the next begins
- Parallel execution is used within phases where possible (Phase 3 and Phase 5)
- QA cycles repeat up to 5 times; if the same error persists 3 times, stop and report the fundamental issue
- Validation requires approval from all reviewers; rejected items get fixed and re-validated
- Cancel by writing `.omni/runs/<run-id>/cancel.signal` at any time; progress is preserved for resume
- Per ADR-0006: all inner skill calls are subprocess-only via `scripts/subagent.py`
</Execution_Policy>

## Step 0 — Initialise run

```bash
# Generate a stable run-id for this autopilot session.
# If OMNI_SESSION_ID is set, derive the run-id from it; otherwise generate a new one.
OMNI_SESSION_ID="${OMNI_SESSION_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
AUTOPILOT_RUN_ID="autopilot-${OMNI_SESSION_ID}"
RUN_DIR=".omni/runs/${AUTOPILOT_RUN_ID}"
mkdir -p "${RUN_DIR}"

# Check for existing state to support resume.
python3 scripts/router_state.py --read --mode autopilot --session-id "$OMNI_SESSION_ID" --json \
  > "${RUN_DIR}/resume-state.json" 2>/dev/null || echo '{}' > "${RUN_DIR}/resume-state.json"

LAST_PHASE=$(python3 -c "
import json, sys
try:
    d = json.load(open('${RUN_DIR}/resume-state.json'))
    print(d.get('phase', 0))
except Exception:
    print(0)
")
echo "autopilot: run_id=${AUTOPILOT_RUN_ID}, last_completed_phase=${LAST_PHASE}"
```

**Skip logic:**
- If `LAST_PHASE >= 1`: skip Phase 1 (Expand), resume from Phase 2.
- If `LAST_PHASE >= 2`: skip Phases 1–2, resume from Phase 3.
- Continue pattern for all 5 phases.
- If a ralplan consensus plan already exists at `.omni/plans/ralplan-*.md` or
  `.omni/plans/consensus-*.md`, set `LAST_PHASE=2` and skip Phases 1–2.

---

## Step 1 — Phase 1: Expand

**Purpose:** Turn the user's idea into a detailed requirements spec.

**Skip if:** `LAST_PHASE >= 1`, OR a deep-interview spec exists at
`.omni/specs/deep-interview-*.md`, OR a ralplan consensus plan already exists.

```bash
PHASE_DIR="${RUN_DIR}/phase-1"
mkdir -p "${PHASE_DIR}"

# Write spec for analyst
cat > "${PHASE_DIR}/spec.md" <<'SPECEOF'
<user-prompt>
{{PROMPT}}
</user-prompt>

Extract detailed requirements from the above idea. Produce a structured spec with:
1. Problem statement (1-2 sentences)
2. Functional requirements (bulleted)
3. Non-functional requirements (performance, security, reliability)
4. Technical constraints (languages, frameworks, deployment target)
5. Acceptance criteria (testable, specific)
6. Out-of-scope items

Output to: stdout (this will be captured as the expand spec).
SPECEOF

# Spawn analyst agent (category=deep) for requirements extraction
python3 scripts/subagent.py analyst "$(cat ${PHASE_DIR}/spec.md)" \
  --category deep \
  --session-id "$OMNI_SESSION_ID" \
  --run-id "${AUTOPILOT_RUN_ID}" \
  > "${PHASE_DIR}/output.md" 2>"${PHASE_DIR}/stderr.log"
EXIT_CODE=$?

# Write phase status
python3 -c "
import json, datetime
state = 'done' if ${EXIT_CODE} == 0 else 'failed'
d = {
    'phase': 1,
    'name': 'expand',
    'state': state,
    'exit_code': ${EXIT_CODE},
    'artifact_paths': ['${PHASE_DIR}/output.md'],
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}
open('${PHASE_DIR}/status.json', 'w').write(json.dumps(d, indent=2))
"

# Update MCP state
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot', {
    'phase': 1,
    'status': 'done' if ${EXIT_CODE} == 0 else 'failed',
    'artifact_paths': ['${PHASE_DIR}/output.md'],
    'run_id': '${AUTOPILOT_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

[ ${EXIT_CODE} -eq 0 ] || { echo "FAIL: Phase 1 (Expand) failed"; exit 1; }
EXPAND_SPEC=$(cat "${PHASE_DIR}/output.md")
```

---

## Step 2 — Phase 2: Plan

**Purpose:** Produce a validated implementation plan via ralplan subprocess.

**Skip if:** `LAST_PHASE >= 2`, OR a ralplan consensus plan already exists.

```bash
PHASE_DIR="${RUN_DIR}/phase-2"
mkdir -p "${PHASE_DIR}"

# Spawn ralplan as subprocess (per ADR-0006: subprocess-only composition)
# ralplan writes its own run-dir artifacts and MCP state under mode="autopilot.ralplan"
export RALPLAN_MODE=autopilot.ralplan
python3 scripts/subagent.py ralplan "${EXPAND_SPEC}" \
  --category deep \
  --session-id "$OMNI_SESSION_ID" \
  --run-id "${AUTOPILOT_RUN_ID}" \
  --parent-run-id "${AUTOPILOT_RUN_ID}" \
  --background \
  > "${PHASE_DIR}/ralplan-job.json" 2>/dev/null

RALPLAN_JOB_ID=$(python3 -c "import json; d=json.load(open('${PHASE_DIR}/ralplan-job.json')); print(d.get('job_id',''))")

# Wait for ralplan to complete (polls status.json, respects cancel.signal)
python3 scripts/wait_for_jobs.py \
  ".omni/runs/${AUTOPILOT_RUN_ID}/${RALPLAN_JOB_ID}/status.json" \
  --timeout 1800 \
  > "${PHASE_DIR}/wait-output.jsonl"
WAIT_EXIT=$?

# Check cancel signal
if [ -f "${RUN_DIR}/cancel.signal" ]; then
  echo "autopilot: cancel.signal detected after Phase 2, exiting"
  python3 -c "
import json, datetime
open('${PHASE_DIR}/status.json', 'w').write(json.dumps({
    'phase': 2, 'name': 'plan', 'state': 'cancelled',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"
  exit 1
fi

# Write phase status
python3 -c "
import json, datetime
state = 'done' if ${WAIT_EXIT} == 0 else 'failed'
d = {
    'phase': 2,
    'name': 'plan',
    'state': state,
    'ralplan_job_id': '${RALPLAN_JOB_ID}',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}
open('${PHASE_DIR}/status.json', 'w').write(json.dumps(d, indent=2))
"

# Update MCP state (nested key: autopilot.ralplan per ADR-0006)
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot.ralplan', {
    'phase': 2,
    'status': 'done' if ${WAIT_EXIT} == 0 else 'failed',
    'run_id': '${AUTOPILOT_RUN_ID}',
    'ralplan_job_id': '${RALPLAN_JOB_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

# Also update top-level autopilot state
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot', {
    'phase': 2,
    'status': 'done' if ${WAIT_EXIT} == 0 else 'failed',
    'run_id': '${AUTOPILOT_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

[ ${WAIT_EXIT} -eq 0 ] || { echo "FAIL: Phase 2 (Plan) failed"; exit 1; }

# Read the produced plan for use in Phase 3
PLAN_FILE=$(find ".omni/plans/" -name "ralplan-*.md" -newer "${PHASE_DIR}/ralplan-job.json" \
            -o -name "consensus-*.md" -newer "${PHASE_DIR}/ralplan-job.json" \
            2>/dev/null | sort | tail -1)
[ -n "${PLAN_FILE}" ] || PLAN_FILE="${PHASE_DIR}/plan-fallback.md"
```

---

## Step 3 — Phase 3: Execute

**Purpose:** Implement each task in the plan. Simple tasks spawn executor agents in
parallel; large/complex tasks spawn ralph as a subprocess (per ADR-0006).

**Skip if:** `LAST_PHASE >= 3`.

```bash
PHASE_DIR="${RUN_DIR}/phase-3"
mkdir -p "${PHASE_DIR}"

# Check cancel signal before starting execution
if [ -f "${RUN_DIR}/cancel.signal" ]; then
  echo "autopilot: cancel.signal detected before Phase 3, exiting"
  exit 1
fi

# Parse tasks from plan file. Each line starting with "- [ ]" or "## Task" is a task.
# For this recipe, we demonstrate spawning 3 executor jobs in parallel as background
# subagents (real runs read tasks from ${PLAN_FILE}).
STATUS_PATHS=""
JOB_IDX=0

python3 - "${PLAN_FILE:-}" "${PHASE_DIR}" "${AUTOPILOT_RUN_ID}" "${OMNI_SESSION_ID}" <<'PYEOF'
import sys, json, subprocess, os
from pathlib import Path

plan_file, phase_dir, run_id, session_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
phase_dir = Path(phase_dir)

# Read tasks from plan, or use a placeholder for the whole plan
tasks = []
if plan_file and Path(plan_file).exists():
    lines = Path(plan_file).read_text().splitlines()
    for line in lines:
        l = line.strip()
        if l.startswith('- [ ]') or l.startswith('## Task'):
            task = l.lstrip('- [ ]').lstrip('## Task').strip()
            if task:
                tasks.append(task)

if not tasks:
    tasks = [f"Implement the full plan from {plan_file or 'the specification'}"]

status_paths = []
for idx, task in enumerate(tasks):
    job_dir = phase_dir / f"job-{idx}"
    job_dir.mkdir(parents=True, exist_ok=True)

    # Determine if task is large (heuristic: mention of "ralph" or >200 chars)
    use_ralph = "ralph" in task.lower() or len(task) > 200

    agent = "ralph" if use_ralph else "executor"
    category = "deep"

    # T1: set nested mode key for ralph inner invocations (ADR-0006 §3)
    child_env = dict(os.environ)
    if agent == "ralph":
        child_env["RALPH_MODE"] = "autopilot.ralph"

    result = subprocess.run(
        [
            sys.executable, "scripts/subagent.py", agent, task,
            "--category", category,
            "--session-id", session_id,
            "--run-id", run_id,
            "--background",
        ],
        capture_output=True, text=True,
        env=child_env,
    )
    if result.returncode == 0:
        try:
            job_info = json.loads(result.stdout.strip().splitlines()[-1])
            job_id = job_info.get("job_id", "")
            sp = f".omni/runs/{run_id}/{job_id}/status.json"
            status_paths.append(sp)
            (job_dir / "job-info.json").write_text(json.dumps(job_info, indent=2))
        except Exception as e:
            print(f"warn: could not parse job info for task {idx}: {e}", file=sys.stderr)
    else:
        print(f"warn: spawn failed for task {idx}: {result.stderr[:200]}", file=sys.stderr)

(phase_dir / "status-paths.txt").write_text("\n".join(status_paths))
print(f"phase-3: spawned {len(status_paths)} jobs")
PYEOF

# Wait for all executor/ralph jobs
if [ -f "${PHASE_DIR}/status-paths.txt" ] && [ -s "${PHASE_DIR}/status-paths.txt" ]; then
  mapfile -t STATUS_ARRAY < "${PHASE_DIR}/status-paths.txt"
  python3 scripts/wait_for_jobs.py "${STATUS_ARRAY[@]}" --timeout 3600 \
    > "${PHASE_DIR}/wait-output.jsonl"
  WAIT_EXIT=$?
else
  echo "warn: no status paths for phase-3; proceeding"
  WAIT_EXIT=0
fi

# Check cancel signal
if [ -f "${RUN_DIR}/cancel.signal" ]; then
  echo "autopilot: cancel.signal detected after Phase 3"
  python3 -c "
import json, datetime
open('${PHASE_DIR}/status.json', 'w').write(json.dumps({
    'phase': 3, 'name': 'execute', 'state': 'cancelled',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"
  exit 1
fi

# Write phase status
python3 -c "
import json, datetime
state = 'done' if ${WAIT_EXIT} == 0 else 'failed'
d = {
    'phase': 3,
    'name': 'execute',
    'state': state,
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}
open('${PHASE_DIR}/status.json', 'w').write(json.dumps(d, indent=2))
"

python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot', {
    'phase': 3, 'status': 'done' if ${WAIT_EXIT} == 0 else 'failed',
    'run_id': '${AUTOPILOT_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

[ ${WAIT_EXIT} -eq 0 ] || { echo "FAIL: Phase 3 (Execute) failed"; exit 1; }
```

---

## Step 4 — Phase 4: QA

**Purpose:** Cycle build/test/fix up to 5 times; stop early if same error repeats 3x.

**Skip if:** `LAST_PHASE >= 4`.

```bash
PHASE_DIR="${RUN_DIR}/phase-4"
mkdir -p "${PHASE_DIR}"

QA_MAX_CYCLES=5
QA_SAME_ERROR_LIMIT=3
LAST_ERROR=""
SAME_ERROR_COUNT=0

for QA_CYCLE in $(seq 1 ${QA_MAX_CYCLES}); do
  # Check cancel signal each cycle
  if [ -f "${RUN_DIR}/cancel.signal" ]; then
    echo "autopilot: cancel.signal detected during Phase 4 QA"
    break
  fi

  CYCLE_DIR="${PHASE_DIR}/cycle-${QA_CYCLE}"
  mkdir -p "${CYCLE_DIR}"

  # Spawn qa-tester (category=deep)
  python3 scripts/subagent.py qa-tester \
    "Run all tests, lint, and build checks. Report any failures with file:line references. Session: ${OMNI_SESSION_ID}" \
    --category deep \
    --session-id "$OMNI_SESSION_ID" \
    --run-id "${AUTOPILOT_RUN_ID}" \
    > "${CYCLE_DIR}/qa-output.md" 2>"${CYCLE_DIR}/stderr.log"
  QA_EXIT=$?

  # Detect if QA passed
  if [ ${QA_EXIT} -eq 0 ]; then
    grep -qi "all.*pass\|0 error\|no failure\|success" "${CYCLE_DIR}/qa-output.md" && {
      echo "QA cycle ${QA_CYCLE}: PASS"
      break
    }
  fi

  # Extract error fingerprint for same-error detection
  CURRENT_ERROR=$(grep -i "error\|fail" "${CYCLE_DIR}/qa-output.md" | head -1 | cut -c1-100)
  if [ "${CURRENT_ERROR}" = "${LAST_ERROR}" ] && [ -n "${CURRENT_ERROR}" ]; then
    SAME_ERROR_COUNT=$((SAME_ERROR_COUNT + 1))
    if [ ${SAME_ERROR_COUNT} -ge ${QA_SAME_ERROR_LIMIT} ]; then
      echo "STOP: same error repeated ${SAME_ERROR_COUNT} times in QA — fundamental issue requires human input"
      python3 -c "
import json, datetime
open('${PHASE_DIR}/status.json', 'w').write(json.dumps({
    'phase': 4, 'name': 'qa', 'state': 'blocked',
    'reason': 'same_error_repeated',
    'cycles': ${QA_CYCLE},
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"
      exit 2
    fi
  else
    SAME_ERROR_COUNT=0
    LAST_ERROR="${CURRENT_ERROR}"
  fi

  # Feed failures back to executor for fixing
  python3 scripts/subagent.py executor \
    "Fix the following QA failures:\n$(cat ${CYCLE_DIR}/qa-output.md)" \
    --category deep \
    --session-id "$OMNI_SESSION_ID" \
    --run-id "${AUTOPILOT_RUN_ID}" \
    > "${CYCLE_DIR}/fix-output.md" 2>/dev/null

  echo "QA cycle ${QA_CYCLE}: failures found, applied fixes"
done

# Write phase status
python3 -c "
import json, datetime
open('${PHASE_DIR}/status.json', 'w').write(json.dumps({
    'phase': 4, 'name': 'qa', 'state': 'done',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"

python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot', {
    'phase': 4, 'status': 'done',
    'run_id': '${AUTOPILOT_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true
```

---

## Step 5 — Phase 5: Validate

**Purpose:** Multi-perspective parallel review. All three reviewers must approve.

**Skip if:** `LAST_PHASE >= 5`.

```bash
PHASE_DIR="${RUN_DIR}/phase-5"
mkdir -p "${PHASE_DIR}"

VALIDATION_PROMPT="Review the implementation for correctness, quality, and security.
Verify ALL acceptance criteria from the original spec are met.
Reply with APPROVED or REJECTED followed by specific findings.
Run ID: ${AUTOPILOT_RUN_ID}. Session: ${OMNI_SESSION_ID}."

# Spawn architect + critic + security-reviewer in parallel (all category=ultrabrain)
python3 scripts/subagent.py architect "${VALIDATION_PROMPT}" \
  --category ultrabrain \
  --session-id "$OMNI_SESSION_ID" \
  --run-id "${AUTOPILOT_RUN_ID}" \
  --background \
  > "${PHASE_DIR}/architect-job.json" 2>/dev/null &

python3 scripts/subagent.py critic "${VALIDATION_PROMPT}" \
  --category ultrabrain \
  --session-id "$OMNI_SESSION_ID" \
  --run-id "${AUTOPILOT_RUN_ID}" \
  --background \
  > "${PHASE_DIR}/critic-job.json" 2>/dev/null &

python3 scripts/subagent.py security-reviewer "${VALIDATION_PROMPT}" \
  --category ultrabrain \
  --session-id "$OMNI_SESSION_ID" \
  --run-id "${AUTOPILOT_RUN_ID}" \
  --background \
  > "${PHASE_DIR}/security-job.json" 2>/dev/null &

wait

# Collect status paths
STATUS_PATHS=""
for JOB_FILE in architect-job critic-job security-job; do
  JOB_ID=$(python3 -c "import json; d=json.load(open('${PHASE_DIR}/${JOB_FILE}.json')); print(d.get('job_id',''))" 2>/dev/null)
  [ -n "${JOB_ID}" ] && STATUS_PATHS="${STATUS_PATHS} .omni/runs/${AUTOPILOT_RUN_ID}/${JOB_ID}/status.json"
done

# Wait for all three reviewers
python3 scripts/wait_for_jobs.py ${STATUS_PATHS} --timeout 1800 \
  > "${PHASE_DIR}/wait-output.jsonl"
WAIT_EXIT=$?

# Check cancel signal
if [ -f "${RUN_DIR}/cancel.signal" ]; then
  echo "autopilot: cancel.signal detected after Phase 5"
  exit 1
fi

# Parse results
python3 - "${PHASE_DIR}" <<'PYEOF'
import json, sys
from pathlib import Path

phase_dir = Path(sys.argv[1])
results = {}
for reviewer in ["architect", "critic", "security-reviewer"]:
    job_file = phase_dir / f"{reviewer.replace('-','')}-job.json" \
        if reviewer != "security-reviewer" else phase_dir / "security-job.json"
    # Try architect-job, critic-job, security-job names
    for candidate in [
        phase_dir / f"{reviewer}-job.json",
        phase_dir / f"{reviewer.split('-')[0]}-job.json",
    ]:
        if candidate.exists():
            try:
                job = json.loads(candidate.read_text())
                job_id = job.get("job_id", "")
                run_id = job.get("run_id", "")
                stdout_path = Path(f".omni/runs/{run_id}/{job_id}/stdout.log")
                if stdout_path.exists():
                    output = stdout_path.read_text()
                    results[reviewer] = "APPROVED" if "APPROVED" in output.upper() else "REJECTED"
                else:
                    results[reviewer] = "UNKNOWN"
            except Exception:
                results[reviewer] = "UNKNOWN"
            break

approved = all(v == "APPROVED" for v in results.values())
print(json.dumps({"results": results, "approved": approved}))
PYEOF > "${PHASE_DIR}/validation-result.json"

APPROVED=$(python3 -c "import json; d=json.load(open('${PHASE_DIR}/validation-result.json')); print('yes' if d.get('approved') else 'no')")

# Write phase status
python3 -c "
import json, datetime
open('${PHASE_DIR}/status.json', 'w').write(json.dumps({
    'phase': 5, 'name': 'validate',
    'state': 'done' if '${APPROVED}' == 'yes' else 'rejected',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"

python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('autopilot', {
    'phase': 5, 'status': 'done' if '${APPROVED}' == 'yes' else 'rejected',
    'run_id': '${AUTOPILOT_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

if [ "${APPROVED}" != "yes" ]; then
  echo "FAIL: validation rejected by one or more reviewers. See ${PHASE_DIR}/validation-result.json"
  echo "Fix issues, then re-run autopilot to resume from Phase 5."
  exit 1
fi

echo "autopilot: all validators approved. Run complete."
echo "Run artifacts: ${RUN_DIR}/"
```

---

## Resume

Re-invoke autopilot with the same `$OMNI_SESSION_ID` to resume from the last
completed phase. Step 0 reads `state_read(mode="autopilot", session_id=...)` and sets
`LAST_PHASE` accordingly. Phases already completed are skipped.

```bash
# Resume example
OMNI_SESSION_ID=my-session-id /copilot-omni:autopilot "same task description"
```

## Cancel

Write the signal file to cleanly cancel autopilot and all in-flight inner subprocesses:

```bash
echo "" > ".omni/runs/autopilot-${OMNI_SESSION_ID}/cancel.signal"
```

Per ADR-0006: inner subprocesses (`ralplan`, `ralph`, `executor`) poll for this file
every 1 second. On detection they exit cleanly with `state="cancelled"`. Cleanup of
the run-dir is the outer skill's responsibility.

---

<Examples>
<Good>
User: "autopilot A REST API for a bookstore inventory with CRUD operations using TypeScript"
Why good: Specific domain (bookstore), clear features (CRUD), technology constraint (TypeScript). Autopilot has enough context to expand into a full spec.
</Good>

<Good>
User: "build me a CLI tool that tracks daily habits with streak counting"
Why good: Clear product concept with a specific feature. The "build me" trigger activates autopilot.
</Good>

<Bad>
User: "fix the bug in the login page"
Why bad: This is a single focused fix, not a multi-phase project. Use direct executor delegation or ralph instead.
</Bad>

<Bad>
User: "what are some good approaches for adding caching?"
Why bad: This is an exploration/brainstorming request. Respond conversationally or use the plan skill.
</Bad>
</Examples>

<Escalation_And_Stop_Conditions>
- Stop and report when the same QA error persists across 3 cycles (fundamental issue requiring human input)
- Stop and report when validation keeps failing after 3 re-validation rounds
- Stop when cancel.signal is present in the run-dir
- If requirements were too vague and expansion produces an unclear spec, offer redirect to `/deep-interview` for Socratic clarification, or pause and ask the user for clarification before proceeding
</Escalation_And_Stop_Conditions>

<Final_Checklist>
- [ ] All 5 phases completed (Expand, Plan, Execute, QA, Validate)
- [ ] All validators approved in Phase 5
- [ ] Phase status.json files written for all 5 phases with state="done"
- [ ] MCP state rows written for mode="autopilot" with session_id
- [ ] No banned Claude primitives in executed recipe (validator: no-claude-primitives)
- [ ] Cancel signal file absent (or handled cleanly)
- [ ] User informed of completion with summary of what was built
</Final_Checklist>

<Advanced>
## Configuration

Optional settings in `.omni/config.json`:

```json
{
  "autopilot": {
    "maxQaCycles": 5,
    "maxValidationRounds": 3,
    "pauseAfterExpansion": false,
    "pauseAfterPlanning": false,
    "skipQa": false,
    "skipValidation": false
  }
}
```

## Pipeline: deep-interview → ralplan → autopilot

The recommended full pipeline chains three quality gates:

```
/deep-interview "vague idea"
  → Socratic Q&A → spec (ambiguity <= 20%)
  → /ralplan --direct → consensus plan (Planner/Architect/Critic approved)
  → /autopilot → skips Phase 1+2, starts at Phase 3 (Execution)
```

When autopilot detects a ralplan consensus plan (`.omni/plans/ralplan-*.md` or
`.omni/plans/consensus-*.md`), it skips both Phase 1 and Phase 2 because the plan
has already been requirements-validated and architecture-reviewed.
</Advanced>
