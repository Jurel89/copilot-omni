---
name: ralplan
description: Consensus-loop planner — Planner → Architect → Critic convergence loop before execution
argument-hint: "[--mode autopilot.ralplan] <task description or spec>"
level: 4
---

<Purpose>
Ralplan drives a three-agent consensus loop (Planner → Architect → Critic) until the
Critic returns APPROVE, or until 3 cycles elapse without approval. It produces a
`consensus.md` plan artifact that downstream execution modes (ralph, autopilot, team)
can consume as a stable, peer-reviewed specification.

It is also the pre-execution gate that intercepts underspecified requests to ralph,
autopilot, and team and redirects them through planning before execution begins.
</Purpose>

<Use_When>
- User wants structured consensus planning before execution
- User says "ralplan", "plan first", "consensus plan", "plan then execute"
- An upstream caller (autopilot Phase 2) invokes ralplan as a nested subprocess
- Request to ralph/autopilot/team is vague (no file paths, symbols, or acceptance criteria)
</Use_When>

<Do_Not_Use_When>
- User has a specific file path, function name, or concrete acceptance criteria — execute directly
- User prefixes with `force:` or `!` — bypass the gate and execute immediately
- User wants to explore options only without a plan artifact — use `plan` skill instead
</Do_Not_Use_When>

<Why_This_Exists>
Execution modes waste cycles on scope discovery when launched on vague requests. Ralplan
forces explicit scope, testable acceptance criteria, and Planner/Architect/Critic consensus
before any code is written. The turn-based design (no blocking, no AskUserQuestion) lets
the skill exit cleanly mid-flow and resume on the next user turn.
</Why_This_Exists>

# Router preamble
1. Read MCP state: `python3 scripts/router_state.py --read --session-id "$OMNI_SESSION_ID" --json`
2. If `decision.redirect == "deep-interview"`, defer to `/copilot-omni:deep-interview` and exit.
3. Otherwise, proceed with `decision.skill == ralplan`.

<Execution_Policy>
- Per ADR-0006: all agent calls are subprocess-only via `scripts/subagent.py`
- Turn-based: if user input is needed mid-flow, persist question and exit cleanly with state="awaiting-input"
- NO AskUserQuestion anywhere in this skill
- Cancel by writing `.omni/runs/ralplan-<id>/cancel.signal` at any time
- Maximum 3 consensus cycles; unconverged after 3 → state="unconverged", exit 1
- REJECT verdict is terminal (allowed once): state="rejected", exit 1
</Execution_Policy>

---

## Step 0 — Initialise run

```bash
# Generate stable run-id for this ralplan session.
export OMNI_SESSION_ID="${OMNI_SESSION_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
export RALPLAN_RUN_ID="ralplan-${OMNI_SESSION_ID}"
export RUN_DIR=".omni/runs/${RALPLAN_RUN_ID}"
mkdir -p "${RUN_DIR}"

# Write spec.md from user prompt (or upstream caller's spec)
cat > "${RUN_DIR}/spec.md" <<'SPECEOF'
<spec>
{{PROMPT}}
</spec>
SPECEOF

# Determine mode — autopilot sets RALPLAN_MODE=autopilot.ralplan before invoking
export RALPLAN_MODE="${RALPLAN_MODE:-ralplan}"

# Write initial status.json only if not already present (preserve awaiting-input state)
python3 - <<'PYEOF'
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
mode = os.environ.get("RALPLAN_MODE", "ralplan")
session_id = os.environ.get("OMNI_SESSION_ID", "")

status_path = run_dir / "status.json"
if status_path.exists():
    try:
        existing = json.loads(status_path.read_text())
        existing_state = existing.get("state", "")
        # Preserve awaiting-input state for resume; update mode if needed
        if existing_state == "awaiting-input":
            existing["mode"] = mode
            tmp = status_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, indent=2))
            os.replace(str(tmp), str(status_path))
            print(f"ralplan: run_id={run_dir.name}, mode={mode}, state=awaiting-input (resuming)")
        else:
            print(f"ralplan: run_id={run_dir.name}, mode={mode}, state={existing_state} (existing)")
    except Exception:
        pass
else:
    status = {
        "run_id": run_dir.name,
        "mode": mode,
        "session_id": session_id,
        "state": "initializing",
        "current_cycle": 0,
        "max_cycles": 3,
        "last_verdict": None,
    }
    tmp = status_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2))
    os.replace(str(tmp), str(status_path))
    print(f"ralplan: run_id={run_dir.name}, mode={mode}, state=initializing")
PYEOF
```

---

## Step 1 — Resume gate

Check whether this run was previously suspended waiting for user input.
If `status.json` has `state="awaiting-input"`, read `pending-question.md`, prepend
to the current turn context, clear the pending file, and set state back to `"planning"`.

```bash
python3 - <<'PYEOF'
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
status_path = run_dir / "status.json"
pending_path = run_dir / "pending-question.md"

if not status_path.exists():
    print("ralplan: no existing status — fresh run")
    exit(0)

try:
    status = json.loads(status_path.read_text())
except Exception:
    print("ralplan: could not read status.json — treating as fresh run")
    exit(0)

state = status.get("state", "")
if state != "awaiting-input":
    print(f"ralplan: state={state} — no resume needed")
    exit(0)

# Resume from awaiting-input
question = ""
if pending_path.exists():
    question = pending_path.read_text().strip()
    # Clear the pending question so it is not re-processed on next resume
    pending_path.write_text("")
    print(f"ralplan: resume — cleared pending question: {question[:80]}")

# Transition back to planning
status["state"] = "planning"
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
import os as _os
_os.replace(str(tmp), str(status_path))
print("ralplan: state → planning (resumed from awaiting-input)")
PYEOF
```

---

## Step 2 — Cancel check helper

```bash
_ralplan_check_cancel() {
  if [ -f "${RUN_DIR}/cancel.signal" ]; then
    python3 - <<'PYEOF'
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}
status["state"] = "cancelled"
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
import os as _os
_os.replace(str(tmp), str(status_path))
print("ralplan: cancel.signal detected — state=cancelled")
PYEOF
    exit 1
  fi
}
```

---

## Step 3 — Consensus loop (up to 3 cycles)

```bash
# Early cancel check before entering loop (handles cancel.signal set before Step 0 ran)
_ralplan_check_cancel

# Ensure status is set to planning before loop
python3 - <<'PYEOF'
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}

# Treat missing/empty state as "initializing" (fresh run with no prior status.json)
current_state = status.get("state") or "initializing"

if current_state not in ("planning", "initializing"):
    # Already converged/rejected/unconverged — nothing to do
    print(f"ralplan: state={current_state} — skipping loop")
    exit(0)

status["state"] = "planning"
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
import os as _os
_os.replace(str(tmp), str(status_path))
print("ralplan: state → planning")
PYEOF

VERDICT=""
export CYCLE=0

for CYCLE in 1 2 3; do
  export CYCLE
  _ralplan_check_cancel

  echo "ralplan: --- cycle ${CYCLE} ---"

  # Update status: current_cycle
  python3 - <<PYEOF
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}
status["current_cycle"] = int(os.environ.get("CYCLE", "1"))
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
import os as _os
_os.replace(str(tmp), str(status_path))
PYEOF

  export PLAN_FILE="${RUN_DIR}/plan-v${CYCLE}.md"
  export ARCH_REVIEW="${RUN_DIR}/architect-review-v${CYCLE}.md"
  export CRITIC_REVIEW="${RUN_DIR}/critic-review-v${CYCLE}.md"
  PREV_REVIEW=""
  if [ $CYCLE -gt 1 ]; then
    PREV_REVIEW="${RUN_DIR}/critic-review-v$((CYCLE - 1)).md"
  fi
  export PREV_REVIEW

  # ---- 3a: Planner ----
  _ralplan_check_cancel

  # Build planner prompt via Python to avoid bash XML-tag parsing issues
  PLANNER_PROMPT=$(python3 - <<PYEOF
import os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
cycle = int(os.environ.get("CYCLE", "1"))
spec = (run_dir / "spec.md").read_text(errors="replace") if (run_dir / "spec.md").exists() else ""
prev_review_path = run_dir / f"critic-review-v{cycle - 1}.md" if cycle > 1 else None
prev_review = ""
if prev_review_path and prev_review_path.exists():
    prev_review = f"\nPrevious critic review (address all concerns):\n{prev_review_path.read_text(errors='replace')}"

prompt = f"""You are the Planner agent in a consensus planning loop.
Produce a detailed implementation plan based on the spec below.
{spec}
{prev_review}

If you need clarification from the user before proceeding, output a single XML block:
<clarifying-question>
Your question here.
</clarifying-question>
Then stop. Do not produce a plan.

Otherwise produce the full plan in markdown. End with: PLAN COMPLETE"""
print(prompt)
PYEOF
)

  python3 scripts/subagent.py planner \
    "${PLANNER_PROMPT}" \
    --category deep \
    --session-id "${OMNI_SESSION_ID}" \
    --run-id "${RALPLAN_RUN_ID}" \
    > "${PLAN_FILE}.raw" 2>&1
  PLANNER_EXIT=$?

  # Write MCP state for planner step
  python3 - <<PYEOF
import json, os, time
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
session_id = os.environ.get("OMNI_SESSION_ID", "")
mode = os.environ.get("RALPLAN_MODE", "ralplan")
cycle = int(os.environ.get("CYCLE", "1"))
plan_path = str(run_dir / f"plan-v{cycle}.md")

try:
    import sqlite3
    from pathlib import Path as _P
    home = _P.home() / ".omni"
    db = home / "omni.db"
    if db.exists():
        body = json.dumps({
            "run_id": run_dir.name,
            "cycle": cycle,
            "plan_path": plan_path,
            "step": "planner",
        })
        with sqlite3.connect(str(db), timeout=5) as conn:
            try:
                conn.execute(
                    "INSERT INTO state(mode, body, session_id, updated_at)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, session_id=excluded.session_id,"
                    " updated_at=excluded.updated_at",
                    (mode, body, session_id, time.time()),
                )
            except Exception:
                conn.execute(
                    "INSERT INTO state(mode, body, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, updated_at=excluded.updated_at",
                    (mode, body, time.time()),
                )
except Exception as e:
    print(f"warning: MCP state write failed (non-fatal): {e}")
PYEOF

  # ---- 3b: Check for clarifying question ----
  if python3 - <<PYEOF
import re, sys
from pathlib import Path

raw = Path(os.environ.get("PLAN_FILE", "") + ".raw") if __import__("os").environ.get("PLAN_FILE") else None
import os
raw = Path(os.environ["PLAN_FILE"] + ".raw")
text = raw.read_text(errors="replace") if raw.exists() else ""
m = re.search(r"<clarifying-question>(.*?)</clarifying-question>", text, re.DOTALL)
if m:
    question = m.group(1).strip()
    run_dir = Path(os.environ["RUN_DIR"])
    (run_dir / "pending-question.md").write_text(question)

    status_path = run_dir / "status.json"
    try:
        status = __import__("json").loads(status_path.read_text())
    except Exception:
        status = {}
    status["state"] = "awaiting-input"
    tmp = status_path.with_suffix(".tmp")
    tmp.write_text(__import__("json").dumps(status, indent=2))
    os.replace(str(tmp), str(status_path))
    print(f"ralplan: planner asked a clarifying question — state=awaiting-input")
    print(f"Question: {question}")
    sys.exit(0)  # 0 = question found
else:
    sys.exit(1)  # 1 = no question, continue
PYEOF
  then
    # Clarifying question found — exit cleanly for turn-based resume
    exit 0
  fi

  # Promote raw output to plan file
  if [ -f "${PLAN_FILE}.raw" ]; then
    cp "${PLAN_FILE}.raw" "${PLAN_FILE}"
  fi

  _ralplan_check_cancel

  # ---- 3c: Architect review ----
  ARCH_PROMPT="You are the Architect agent in a consensus planning loop.
Review the plan below for structural soundness. Provide the strongest steelman
antithesis, at least one real tradeoff tension, and a synthesis where possible.
Flag any principle violations. Annotate the plan with your structural concerns.

Plan:
$(cat ${PLAN_FILE} 2>/dev/null || echo '(plan not found)')

Output your review in markdown. End with: ARCHITECT REVIEW COMPLETE"

  python3 scripts/subagent.py architect \
    "${ARCH_PROMPT}" \
    --category ultrabrain \
    --session-id "${OMNI_SESSION_ID}" \
    --run-id "${RALPLAN_RUN_ID}" \
    > "${ARCH_REVIEW}" 2>&1

  _ralplan_check_cancel

  # ---- 3d: Critic evaluation ----
  CRITIC_PROMPT="You are the Critic agent in a consensus planning loop.
Evaluate the plan against quality criteria: principle-option consistency, fair
alternatives, risk mitigation clarity, testable acceptance criteria, and concrete
verification steps.

Plan:
$(cat ${PLAN_FILE} 2>/dev/null || echo '(plan not found)')

Architect review:
$(cat ${ARCH_REVIEW} 2>/dev/null || echo '(no architect review)')

Provide your evaluation. End your response with EXACTLY one of these verdict lines:
VERDICT: APPROVE
VERDICT: REVISE
VERDICT: REJECT"

  python3 scripts/subagent.py critic \
    "${CRITIC_PROMPT}" \
    --category ultrabrain \
    --session-id "${OMNI_SESSION_ID}" \
    --run-id "${RALPLAN_RUN_ID}" \
    > "${CRITIC_REVIEW}" 2>&1

  # ---- 3e/3f/3g: Parse verdict and branch ----
  VERDICT=$(python3 scripts/parse_critic_verdict.py "${CRITIC_REVIEW}" 2>/dev/null || echo "REVISE")
  echo "ralplan: cycle ${CYCLE} verdict=${VERDICT}"

  if [ "${VERDICT}" = "APPROVE" ]; then
    # ---- 3e: Converged ----
    cat > "${RUN_DIR}/consensus.md" <<CONEOF
# Consensus Plan (cycle ${CYCLE})

> Approved by Critic after ${CYCLE} cycle(s).

$(cat ${PLAN_FILE})

---
*Architect review: see architect-review-v${CYCLE}.md*
*Critic review: see critic-review-v${CYCLE}.md*
CONEOF

    python3 - <<PYEOF
import json, os, time
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
mode = os.environ.get("RALPLAN_MODE", "ralplan")
session_id = os.environ.get("OMNI_SESSION_ID", "")
cycle = int(os.environ.get("CYCLE", "1"))

status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}
status.update({
    "state": "converged",
    "current_cycle": cycle,
    "last_verdict": "APPROVE",
})
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
os.replace(str(tmp), str(status_path))

# MCP state update
try:
    import sqlite3
    home = Path.home() / ".omni"
    db = home / "omni.db"
    if db.exists():
        body = json.dumps({
            "run_id": run_dir.name,
            "cycle": cycle,
            "status": "converged",
            "last_critic_verdict": "APPROVE",
            "spec_excerpt": (run_dir / "spec.md").read_text()[:200] if (run_dir / "spec.md").exists() else "",
            "current_version": f"plan-v{cycle}.md",
        })
        with sqlite3.connect(str(db), timeout=5) as conn:
            try:
                conn.execute(
                    "INSERT INTO state(mode, body, session_id, updated_at)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, session_id=excluded.session_id,"
                    " updated_at=excluded.updated_at",
                    (mode, body, session_id, time.time()),
                )
            except Exception:
                conn.execute(
                    "INSERT INTO state(mode, body, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, updated_at=excluded.updated_at",
                    (mode, body, time.time()),
                )
except Exception as e:
    print(f"warning: MCP state write failed (non-fatal): {e}")
print(f"ralplan: converged after {cycle} cycle(s) — consensus.md written")
PYEOF
    exit 0
  fi

  if [ "${VERDICT}" = "REJECT" ]; then
    # ---- 3f: Rejected ----
    python3 - <<PYEOF
import json, os, time
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
mode = os.environ.get("RALPLAN_MODE", "ralplan")
session_id = os.environ.get("OMNI_SESSION_ID", "")
cycle = int(os.environ.get("CYCLE", "1"))
critic_review_path = run_dir / f"critic-review-v{cycle}.md"
reject_reason = critic_review_path.read_text(errors="replace")[-500:] if critic_review_path.exists() else "(see critic review)"

status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}
status.update({
    "state": "rejected",
    "current_cycle": cycle,
    "last_verdict": "REJECT",
    "reject_reason_excerpt": reject_reason[:200],
})
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
os.replace(str(tmp), str(status_path))
print(f"ralplan: REJECT verdict in cycle {cycle} — state=rejected")
print(f"Rejection reason (excerpt): {reject_reason[:200]}")
PYEOF
    exit 1
  fi

  # REVISE — feed back and continue loop
  echo "ralplan: REVISE — feeding critic review back to planner for cycle $((CYCLE + 1))"

done

# ---- Step 5: Loop exhausted without APPROVE ----
python3 - <<'PYEOF'
import json, os, time
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
mode = os.environ.get("RALPLAN_MODE", "ralplan")
session_id = os.environ.get("OMNI_SESSION_ID", "")

# Collect divergent points from all 3 critic reviews
divergent_lines = []
for cycle in range(1, 4):
    review_path = run_dir / f"critic-review-v{cycle}.md"
    if review_path.exists():
        text = review_path.read_text(errors="replace")
        divergent_lines.append(f"## Cycle {cycle} critic concerns\n\n{text[:800]}\n")

divergent_content = "\n---\n".join(divergent_lines) if divergent_lines else "(no critic reviews found)"

divergent_path = run_dir / "divergent-points.md"
divergent_path.write_text(
    f"# Divergent Points — ralplan unconverged after 3 cycles\n\n"
    f"The Planner and Critic could not reach consensus in 3 cycles.\n"
    f"Below are the Critic's concerns from each cycle:\n\n"
    + divergent_content
)

status_path = run_dir / "status.json"
try:
    status = json.loads(status_path.read_text())
except Exception:
    status = {}
status.update({
    "state": "unconverged",
    "current_cycle": 3,
    "last_verdict": "REVISE",
})
tmp = status_path.with_suffix(".tmp")
tmp.write_text(json.dumps(status, indent=2))
os.replace(str(tmp), str(status_path))

# MCP state update
try:
    import sqlite3
    home = Path.home() / ".omni"
    db = home / "omni.db"
    if db.exists():
        body = json.dumps({
            "run_id": run_dir.name,
            "cycle": 3,
            "status": "unconverged",
            "last_critic_verdict": "REVISE",
            "spec_excerpt": (run_dir / "spec.md").read_text()[:200] if (run_dir / "spec.md").exists() else "",
            "current_version": "plan-v3.md",
        })
        with sqlite3.connect(str(db), timeout=5) as conn:
            try:
                conn.execute(
                    "INSERT INTO state(mode, body, session_id, updated_at)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, session_id=excluded.session_id,"
                    " updated_at=excluded.updated_at",
                    (mode, body, session_id, time.time()),
                )
            except Exception:
                conn.execute(
                    "INSERT INTO state(mode, body, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, updated_at=excluded.updated_at",
                    (mode, body, time.time()),
                )
except Exception as e:
    print(f"warning: MCP state write failed (non-fatal): {e}")

print("ralplan: unconverged after 3 cycles — divergent-points.md written")
print("Please review divergent-points.md and either refine the spec or resolve the Critic concerns manually.")
PYEOF
exit 1
```

---

## Pre-Execution Gate

Ralplan is also the pre-execution gate for ralph, autopilot, and team. When any of those
skills detects an underspecified request (≤15 effective words, no file paths, no symbols,
no acceptance criteria, no issue numbers), they redirect here before spawning any agents.

### Bypass signals (gate auto-passes when ANY of these is present)

| Signal | Example |
|---|---|
| File path | `src/hooks/bridge.ts` |
| Issue/PR number | `#42` |
| camelCase symbol | `processKeywordDetector` |
| PascalCase symbol | `UserModel` |
| snake_case symbol | `user_model` |
| Test target | `npm test` |
| Numbered steps | `1. Add X\n2. Test Y` |
| Acceptance criteria | `acceptance criteria: ...` |
| Error reference | `TypeError in auth` |
| Code block | `` ` `` |
| Escape prefix | `force:` or `!` |

### Gate redirect message (emit when intercepting)

```
This request looks underspecified for direct execution. Starting ralplan consensus planning
to produce a clear, testable plan before execution begins.

Use `force: <skill> <prompt>` or `! <skill> <prompt>` to bypass planning.
```

---

## Resume protocol

If ralplan exits with `state="awaiting-input"`:
1. The `pending-question.md` file in the run-dir contains the clarifying question.
2. The LLM emits the question as plain text to the user.
3. On the next user turn, the answer is prepended to the ralplan invocation prompt.
4. Ralplan re-invokes with the same `OMNI_SESSION_ID`; Step 1 (resume gate) picks up the answer.

---

## Cancel cascade

Write `.omni/runs/ralplan-<id>/cancel.signal` at any time. Every bash block in the
consensus loop calls `_ralplan_check_cancel` before spawning agents. On detection:
- `status.json` is updated to `state="cancelled"`
- The script exits 1 cleanly
- No new agent jobs are spawned after the signal is detected

---

## Run-directory layout

```
.omni/runs/ralplan-<id>/
  spec.md                    — user input / caller spec
  status.json                — {state, current_cycle, last_verdict, ...}
  plan-v1.md                 — Planner output cycle 1
  plan-v2.md                 — Planner output cycle 2 (if REVISE)
  plan-v3.md                 — Planner output cycle 3 (if REVISE×2)
  architect-review-v1.md     — Architect review cycle 1
  architect-review-v2.md     — ...
  architect-review-v3.md     — ...
  critic-review-v1.md        — Critic review cycle 1
  critic-review-v2.md        — ...
  critic-review-v3.md        — ...
  consensus.md               — Final approved plan (written on APPROVE)
  divergent-points.md        — Summary of disagreements (written on unconverged)
  pending-question.md        — Clarifying question for user (state=awaiting-input)
  cancel.signal              — Write this file to cancel mid-run
```

---

## MCP state

One row per run keyed by `mode` (e.g. `"ralplan"` standalone, `"autopilot.ralplan"` when
nested). Body fields: `run_id`, `cycle`, `status`, `last_critic_verdict`, `spec_excerpt`,
`current_version`.

When invoked by autopilot, the caller sets `RALPLAN_MODE=autopilot.ralplan` before
executing this skill. The mode value flows through to all MCP state writes and to
`status.json`.
