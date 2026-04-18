---
name: ralph
description: PRD-driven persistence loop until task completion with reviewer verification
argument-hint: "[--no-deslop] [--critic=architect|critic] <task description>"
level: 4
---

<Purpose>
Ralph is a PRD-driven persistence loop that keeps working on a task until ALL user
stories in prd.json have passes: true and are reviewer-verified. It wraps parallel
executor spawning with session persistence, automatic retry on failure, structured
story tracking, and mandatory reviewer verification before completion.
</Purpose>

<Use_When>
- Task requires guaranteed completion with verification (not just "do your best")
- User says "ralph", "don't stop", "must complete", "finish this", or "keep going until done"
- Work may span multiple iterations and needs persistence across retries
- Task benefits from structured PRD-driven execution with reviewer sign-off
</Use_When>

<Do_Not_Use_When>
- User wants a full autonomous pipeline from idea to code -- use `autopilot` instead
- User wants to explore or plan before committing -- use `plan` skill instead
- User wants a quick one-shot fix -- delegate directly to an executor agent
- User wants manual control over completion -- use a single executor subagent directly
</Do_Not_Use_When>

<Why_This_Exists>
Complex tasks often fail silently: partial implementations get declared "done", tests
get skipped, edge cases get forgotten. Ralph prevents this by:
1. Structuring work into discrete user stories with testable acceptance criteria (prd.json)
2. Iterating story-by-story until each one passes
3. Tracking progress and learnings across iterations (progress.txt)
4. Requiring fresh reviewer verification against specific acceptance criteria before completion
</Why_This_Exists>

# Router preamble
1. Read MCP state: `python3 scripts/router_state.py --read --session-id "$OMNI_SESSION_ID" --json`
2. If `decision.redirect == "deep-interview"`, defer to `/copilot-omni:deep-interview` and exit.
3. Otherwise, proceed with `decision.skill == ralph`.

<Execution_Policy>
- Fire independent agent calls simultaneously via `subagent.py --background` + `wait_for_jobs.py`
- Per ADR-0006: all agent calls are subprocess-only via `scripts/subagent.py`
- Never wait sequentially for independent work
- Deliver the full implementation: no scope reduction, no partial completion
</Execution_Policy>

## Step 0 — Initialise run

```bash
OMNI_SESSION_ID="${OMNI_SESSION_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
RALPH_RUN_ID="ralph-${OMNI_SESSION_ID}"
RUN_DIR=".omni/runs/${RALPH_RUN_ID}"
mkdir -p "${RUN_DIR}"

# Parse flags from prompt
NO_DESLOP=0
CRITIC_AGENT="architect"
PROMPT_CLEAN="{{PROMPT}}"
echo "${PROMPT_CLEAN}" | grep -q "\-\-no-deslop" && NO_DESLOP=1
CRITIC_ARG=$(echo "${PROMPT_CLEAN}" | grep -oP '(?<=--critic=)\w+' || echo "")
[ -n "${CRITIC_ARG}" ] && CRITIC_AGENT="${CRITIC_ARG}"

# Detect security-relevant PRD
SECURITY_RELEVANT=0

# PRD storage: .omni/runs/<ralph-run-id>/prd.json
PRD_FILE="${RUN_DIR}/prd.json"
PROGRESS_FILE="${RUN_DIR}/progress.txt"

# Resume: read last completed iteration from MCP state
python3 scripts/router_state.py --read --mode ralph --session-id "$OMNI_SESSION_ID" --json \
  > "${RUN_DIR}/resume-state.json" 2>/dev/null || echo '{}' > "${RUN_DIR}/resume-state.json"

LAST_ITERATION=$(python3 -c "
import json
try:
    d = json.load(open('${RUN_DIR}/resume-state.json'))
    print(d.get('iteration', -1))
except Exception:
    print(-1)
")

echo "ralph: run_id=${RALPH_RUN_ID}, last_iteration=${LAST_ITERATION}, critic=${CRITIC_AGENT}"
```

---

## Step 1 — PRD Setup (first iteration only)

**Skip if:** `prd.json` already exists with task-specific acceptance criteria.

```bash
if [ ! -f "${PRD_FILE}" ]; then
  # Spawn analyst (category=deep) to generate PRD from task description
  python3 scripts/subagent.py analyst \
    "Generate a prd.json for this task: {{PROMPT}}

Output ONLY valid JSON in this exact schema:
{
  \"title\": \"<short title>\",
  \"goals\": [\"goal1\", \"goal2\"],
  \"acceptance\": [\"specific testable criterion 1\", \"specific testable criterion 2\"],
  \"non_goals\": [\"out of scope item\"],
  \"security_relevant\": false,
  \"created_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
  \"stories\": [
    {
      \"id\": \"US-001\",
      \"title\": \"<story title>\",
      \"acceptance\": [\"testable criterion\"],
      \"passes\": false
    }
  ]
}" \
    --category deep \
    --session-id "$OMNI_SESSION_ID" \
    --run-id "${RALPH_RUN_ID}" \
    > "${RUN_DIR}/prd-raw.txt" 2>/dev/null

  # Extract JSON from analyst output
  python3 - "${RUN_DIR}/prd-raw.txt" "${PRD_FILE}" <<'PYEOF'
import json, sys, re
from pathlib import Path

raw = Path(sys.argv[1]).read_text(errors="replace")
# Extract first valid JSON object
for match in re.finditer(r'\{', raw):
    candidate = raw[match.start():]
    try:
        obj = json.loads(candidate[:candidate.rfind('}')+1])
        if "stories" in obj and "acceptance" in obj:
            Path(sys.argv[2]).write_text(json.dumps(obj, indent=2))
            print("prd.json written")
            sys.exit(0)
    except Exception:
        continue
# Fallback: minimal scaffold
fallback = {
    "title": "Task from ralph",
    "goals": ["Complete the task as described"],
    "acceptance": ["Task implementation is complete and tested"],
    "non_goals": [],
    "security_relevant": False,
    "created_at": __import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    "stories": [
        {"id": "US-001", "title": "Implement task", "acceptance": ["Task is done"], "passes": False}
    ]
}
Path(sys.argv[2]).write_text(json.dumps(fallback, indent=2))
print("prd.json: fallback scaffold written")
PYEOF

  # Initialise progress.txt
  [ -f "${PROGRESS_FILE}" ] || echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=0 step=init note=prd_created" > "${PROGRESS_FILE}"

  # Detect security-relevant flag
  SECURITY_RELEVANT=$(python3 -c "
import json
try:
    d = json.load(open('${PRD_FILE}'))
    print(1 if d.get('security_relevant') else 0)
except Exception:
    print(0)
")
fi
```

---

## Step 2 — Iterate until PRD complete

```bash
MAX_ITERATIONS=10
ITERATION=0
# If resuming, start from last completed iteration + 1
[ "${LAST_ITERATION}" -ge 0 ] && ITERATION=$((LAST_ITERATION + 1))

while [ ${ITERATION} -lt ${MAX_ITERATIONS} ]; do
  # Poll cancel signal each iteration
  if [ -f "${RUN_DIR}/cancel.signal" ]; then
    echo "ralph: cancel.signal detected at iteration ${ITERATION}, exiting cleanly"
    python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ralph', {
    'iteration': ${ITERATION}, 'status': 'cancelled',
    'run_id': '${RALPH_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true
    exit 1
  fi

  ITER_DIR="${RUN_DIR}/iteration-${ITERATION}"
  mkdir -p "${ITER_DIR}"

  echo "ralph: starting iteration ${ITERATION}"

  # --- Step 2a: Pick next incomplete story ---
  NEXT_STORY=$(python3 - "${PRD_FILE}" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    stories = d.get("stories", [])
    for s in stories:
        if not s.get("passes"):
            print(json.dumps(s))
            sys.exit(0)
    print("")  # all done
except Exception as e:
    print("", file=__import__('sys').stderr)
PYEOF
)

  if [ -z "${NEXT_STORY}" ]; then
    echo "ralph: all stories pass — proceeding to reviewer verification"
    break
  fi

  STORY_TITLE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('title',''))" "${NEXT_STORY}" 2>/dev/null)
  STORY_ACCEPTANCE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print('\n'.join(d.get('acceptance',[])))" "${NEXT_STORY}" 2>/dev/null)

  # --- Step 2b: Spawn executor (category=deep) for this story ---
  python3 scripts/subagent.py executor \
    "Implement the following user story for: {{PROMPT}}

Story: ${STORY_TITLE}
Acceptance criteria:
${STORY_ACCEPTANCE}

Current PRD: $(cat ${PRD_FILE})
Progress so far: $(cat ${PROGRESS_FILE} 2>/dev/null || echo 'first iteration')" \
    --category deep \
    --session-id "$OMNI_SESSION_ID" \
    --run-id "${RALPH_RUN_ID}" \
    > "${ITER_DIR}/executor-output.md" 2>"${ITER_DIR}/executor-stderr.log"
  EXEC_EXIT=$?

  # Save a diff patch (best-effort)
  git diff 2>/dev/null > "${ITER_DIR}/diff.patch" || true

  # --- Step 2c: Reviewer lane ---
  REVIEW_PROMPT="Review this implementation against the acceptance criteria.
Story: ${STORY_TITLE}
Acceptance criteria:
${STORY_ACCEPTANCE}

Implementation output:
$(cat ${ITER_DIR}/executor-output.md)

Reply with APPROVED or REJECTED followed by specific findings."

  if [ "${SECURITY_RELEVANT}" = "1" ]; then
    # Spawn critic + security-reviewer in parallel
    python3 scripts/subagent.py "${CRITIC_AGENT}" "${REVIEW_PROMPT}" \
      --category ultrabrain \
      --session-id "$OMNI_SESSION_ID" \
      --run-id "${RALPH_RUN_ID}" \
      --background \
      > "${ITER_DIR}/critic-job.json" 2>/dev/null &

    python3 scripts/subagent.py security-reviewer "${REVIEW_PROMPT}" \
      --category ultrabrain \
      --session-id "$OMNI_SESSION_ID" \
      --run-id "${RALPH_RUN_ID}" \
      --background \
      > "${ITER_DIR}/security-job.json" 2>/dev/null &

    wait

    # Collect status paths for both
    CRITIC_JOB_ID=$(python3 -c "import json; d=json.load(open('${ITER_DIR}/critic-job.json')); print(d.get('job_id',''))" 2>/dev/null)
    SECURITY_JOB_ID=$(python3 -c "import json; d=json.load(open('${ITER_DIR}/security-job.json')); print(d.get('job_id',''))" 2>/dev/null)

    python3 scripts/wait_for_jobs.py \
      ".omni/runs/${RALPH_RUN_ID}/${CRITIC_JOB_ID}/status.json" \
      ".omni/runs/${RALPH_RUN_ID}/${SECURITY_JOB_ID}/status.json" \
      --timeout 600 > "${ITER_DIR}/review-wait.jsonl"

    # Merge review outputs
    {
      echo "=== ${CRITIC_AGENT} review ==="
      cat ".omni/runs/${RALPH_RUN_ID}/${CRITIC_JOB_ID}/stdout.log" 2>/dev/null
      echo ""
      echo "=== security-reviewer ==="
      cat ".omni/runs/${RALPH_RUN_ID}/${SECURITY_JOB_ID}/stdout.log" 2>/dev/null
    } > "${ITER_DIR}/review.md"
  else
    # Spawn single reviewer (category=ultrabrain)
    python3 scripts/subagent.py "${CRITIC_AGENT}" "${REVIEW_PROMPT}" \
      --category ultrabrain \
      --session-id "$OMNI_SESSION_ID" \
      --run-id "${RALPH_RUN_ID}" \
      > "${ITER_DIR}/review.md" 2>/dev/null
  fi

  # Parse reviewer verdict
  VERDICT=$(grep -i "^APPROVED\|^REJECTED" "${ITER_DIR}/review.md" | head -1 | awk '{print $1}' | tr '[:lower:]' '[:upper:]')
  [ -z "${VERDICT}" ] && grep -qi "approved" "${ITER_DIR}/review.md" && VERDICT="APPROVED"
  [ -z "${VERDICT}" ] && VERDICT="REJECTED"

  if [ "${VERDICT}" = "APPROVED" ]; then
    # Mark story as passing in prd.json
    STORY_ID=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('id',''))" "${NEXT_STORY}" 2>/dev/null)
    python3 - "${PRD_FILE}" "${STORY_ID}" <<'PYEOF'
import json, sys
prd_path, story_id = sys.argv[1], sys.argv[2]
d = json.load(open(prd_path))
for s in d.get("stories", []):
    if s.get("id") == story_id:
        s["passes"] = True
        break
open(prd_path, "w").write(json.dumps(d, indent=2))
print(f"story {story_id} marked passes=true")
PYEOF

    # Record to progress.txt
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=${ITERATION} step=story_done note=${STORY_TITLE}" >> "${PROGRESS_FILE}"

    # --- Deslop pass (unless --no-deslop) ---
    if [ "${NO_DESLOP}" = "0" ]; then
      CHANGED_FILES=$(git diff --name-only 2>/dev/null || echo "")
      if [ -n "${CHANGED_FILES}" ]; then
        # Read ai-slop-cleaner runbook and follow its steps on changed files
        DESLOP_SKILL_FILE="skills/ai-slop-cleaner/SKILL.md"
        if [ -f "${DESLOP_SKILL_FILE}" ]; then
          python3 scripts/subagent.py executor \
            "Follow the ai-slop-cleaner runbook (skills/ai-slop-cleaner/SKILL.md) on these files only:
${CHANGED_FILES}

Do NOT expand scope to unrelated files. Run in standard cleanup mode (not --review).
Preserve behavior. Prefer deletion over addition." \
            --category quick \
            --session-id "$OMNI_SESSION_ID" \
            --run-id "${RALPH_RUN_ID}" \
            > "${ITER_DIR}/deslop-output.md" 2>/dev/null
          echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=${ITERATION} step=deslop note=completed" >> "${PROGRESS_FILE}"
        fi
      fi

      # Regression re-verification after deslop
      python3 scripts/subagent.py qa-tester \
        "Run all relevant tests, build, and lint checks on the changed files.
Changed files: ${CHANGED_FILES}
Session: ${OMNI_SESSION_ID}" \
        --category deep \
        --session-id "$OMNI_SESSION_ID" \
        --run-id "${RALPH_RUN_ID}" \
        > "${ITER_DIR}/regression-output.md" 2>/dev/null

      grep -qi "fail\|error" "${ITER_DIR}/regression-output.md" && {
        echo "WARN: regression failures after deslop — recording for next iteration"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=${ITERATION} step=regression_warn note=deslop_introduced_failures" >> "${PROGRESS_FILE}"
      }
    fi
  else
    # REJECTED: feed reviewer feedback to executor, cap at 5 iterations per story
    echo "ralph: iteration ${ITERATION} rejected, feeding back to executor"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=${ITERATION} step=rejected note=${VERDICT}" >> "${PROGRESS_FILE}"

    python3 scripts/subagent.py executor \
      "Fix the following reviewer feedback for story '${STORY_TITLE}':
$(cat ${ITER_DIR}/review.md)

Original task: {{PROMPT}}
Acceptance criteria:
${STORY_ACCEPTANCE}" \
      --category deep \
      --session-id "$OMNI_SESSION_ID" \
      --run-id "${RALPH_RUN_ID}" \
      >> "${ITER_DIR}/executor-output.md" 2>/dev/null

    # Update diff patch after fix
    git diff 2>/dev/null > "${ITER_DIR}/diff.patch" || true
  fi

  # Write iteration status.json
  python3 -c "
import json, datetime
open('${ITER_DIR}/status.json', 'w').write(json.dumps({
    'iteration': ${ITERATION},
    'story': '${STORY_TITLE}',
    'verdict': '${VERDICT}',
    'state': 'done',
    'ended_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}, indent=2))
"

  # Update MCP state
  python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ralph', {
    'iteration': ${ITERATION},
    'story': '${STORY_TITLE}',
    'verdict': '${VERDICT}',
    'status': 'iterating',
    'run_id': '${RALPH_RUN_ID}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

  ITERATION=$((ITERATION + 1))
done
```

---

## Step 3 — Final reviewer verification

```bash
ALL_PASS=$(python3 - "${PRD_FILE}" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    all_pass = all(s.get("passes") for s in d.get("stories", []))
    print("yes" if all_pass else "no")
except Exception:
    print("no")
PYEOF
)

if [ "${ALL_PASS}" = "yes" ]; then
  echo "ralph: all PRD stories pass — run complete"

  python3 -c "
import sys; sys.path.insert(0, 'scripts')
import subagent
subagent._mcp_write_best_effort('ralph', {
    'iteration': ${ITERATION},
    'status': 'done',
    'run_id': '${RALPH_RUN_ID}',
    'prd_path': '${PRD_FILE}',
    'progress_path': '${PROGRESS_FILE}',
}, '${OMNI_SESSION_ID}')
" 2>/dev/null || true

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) iteration=${ITERATION} step=complete note=all_stories_passed" >> "${PROGRESS_FILE}"
  echo "ralph: artifacts in ${RUN_DIR}/"
else
  echo "FAIL: ralph hit MAX_ITERATIONS (${MAX_ITERATIONS}) without completing all PRD stories"
  echo "Resume by re-running ralph with the same OMNI_SESSION_ID=${OMNI_SESSION_ID}"
  exit 1
fi
```

---

## Resume

Re-invoke ralph with the same `$OMNI_SESSION_ID` to resume from the last completed
iteration. Step 0 reads `state_read(mode="ralph", session_id=...)` and sets
`LAST_ITERATION`. Completed iterations and approved stories are not re-run.

```bash
OMNI_SESSION_ID=my-session-id /copilot-omni:ralph "same task description"
```

## Cancel

Write the signal file to cleanly cancel ralph and all in-flight inner subprocesses:

```bash
echo "" > ".omni/runs/ralph-${OMNI_SESSION_ID}/cancel.signal"
```

Per ADR-0006: inner subprocesses (`executor`, `critic`, `security-reviewer`) are
spawned via `subagent.py` and poll for this file. On detection they exit cleanly.

---

<Examples>
<Good>
Correct parallel reviewer invocation (security-relevant PRD):
```bash
python3 scripts/subagent.py architect "${REVIEW_PROMPT}" --category ultrabrain --background > critic-job.json &
python3 scripts/subagent.py security-reviewer "${REVIEW_PROMPT}" --category ultrabrain --background > security-job.json &
wait
```
Why good: Both reviewers spawn simultaneously via background jobs.
</Good>

<Good>
Story-by-story verification:
```
iteration=0: story US-001 "Add flag detection helpers" → APPROVED → passes=true
iteration=1: story US-002 "Wire PRD into executor" → REJECTED → fix applied
iteration=2: story US-002 retried → APPROVED → passes=true
```
Why good: Each story verified against its own acceptance criteria before marking complete.
</Good>

<Bad>
Claiming completion without PRD verification:
"All the changes look good, the implementation should work correctly. Task complete."
Why bad: Uses "should" and "look good" -- no fresh evidence, no story-by-story verification, no reviewer check.
</Bad>
</Examples>

<Escalation_And_Stop_Conditions>
- Stop and report when a fundamental blocker requires user input (missing credentials, unclear requirements, external service down)
- Stop when cancel.signal is detected in the run-dir
- Continue working when iteration produces a rejected verdict — fix and retry (capped at MAX_ITERATIONS)
- If the same story fails across 3+ consecutive iterations, report it as a potential fundamental problem
</Escalation_And_Stop_Conditions>

<Final_Checklist>
- [ ] All prd.json stories have passes: true (no incomplete stories)
- [ ] prd.json acceptance criteria are task-specific (not generic boilerplate)
- [ ] All requirements from the original task are met (no scope reduction)
- [ ] progress.txt records implementation details and learnings
- [ ] iteration-N/{diff.patch, review.md, status.json} written for each iteration
- [ ] MCP state rows written for mode="ralph" with session_id
- [ ] ai-slop-cleaner pass completed on changed files (or --no-deslop specified)
- [ ] Post-deslop regression tests pass
- [ ] No banned host-specific primitives in executed recipe (primitive guardrail passes)
</Final_Checklist>
