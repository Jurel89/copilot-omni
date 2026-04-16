# WS5d Completion Report — Ralplan Consensus Loop

**Branch:** `phase-b/wave-2/WS5d-ralplan`
**Date:** 2026-04-16

---

## 1. Consensus-Loop Shape

Ralplan drives a **Planner → Architect → Critic** consensus loop with up to 3 cycles:

```
cycle 1..3:
  a. Planner (category=deep)       → plan-v<n>.md
  b. Check clarifying question     → if found: state=awaiting-input, exit 0
  c. Architect (category=ultrabrain) → architect-review-v<n>.md
  d. Critic (category=ultrabrain)  → critic-review-v<n>.md
  e. Parse verdict via parse_critic_verdict.py
     APPROVE → consensus.md, state=converged, exit 0
     REJECT  → state=rejected, exit 1 (no further cycles)
     REVISE  → feed review back to planner, next cycle
after 3 REVISE: → divergent-points.md, state=unconverged, exit 1
```

### Verdict semantics

| Verdict | Meaning | Action |
|---------|---------|--------|
| `APPROVE` | Plan meets all quality criteria | Write `consensus.md`, exit 0 |
| `REVISE`  | Plan needs revisions (addressable) | Feed reviews back to Planner, next cycle |
| `REJECT`  | Plan is fundamentally flawed (terminal) | Write rejection state, exit 1 immediately |

---

## 2. Resume Protocol for `awaiting-input` State

When the Planner needs clarification before proceeding:

1. Planner emits `<clarifying-question>...</clarifying-question>` block in its output.
2. Ralplan detects the block, extracts the question, writes it to `pending-question.md`.
3. `status.json` is updated to `state="awaiting-input"`, script exits 0.
4. The skill emits the question as plain text to the user (no `AskUserQuestion`).
5. On the next user turn, the answer is included in the next ralplan invocation.
6. Step 0 detects existing `status.json` and preserves `state="awaiting-input"`.
7. Step 1 (resume gate) reads `pending-question.md`, clears it, sets `state="planning"`.
8. Consensus loop proceeds from cycle 1 with the answer prepended to the spec context.

**Key invariant:** `pending-question.md` is cleared (set to `""`) on resume so it is not
re-processed on a subsequent resume.

---

## 3. Critic-Verdict Parser API

**Script:** `scripts/parse_critic_verdict.py`

```
python3 scripts/parse_critic_verdict.py <path-to-critic-review.md>
# or via stdin:
cat critic-review-v2.md | python3 scripts/parse_critic_verdict.py
```

- Reads the file (path arg) or stdin.
- Finds the **last** line matching `^VERDICT: (APPROVE|REVISE|REJECT)$` (case-sensitive).
- Prints just the verdict word (`APPROVE`, `REVISE`, or `REJECT`) to stdout.
- Exits 0 on success, 1 if no valid verdict line found.

The "last line wins" rule handles review files where the Critic revises its verdict mid-text
(e.g., writes `VERDICT: REVISE` then adds `VERDICT: APPROVE` after reconsidering).

---

## 4. Test Inventory

### `tests/test_parse_critic_verdict.py` (18 tests)

| Test | Covers |
|------|--------|
| `test_approve_verdict` | Happy path: APPROVE |
| `test_revise_verdict` | Happy path: REVISE |
| `test_reject_verdict` | Happy path: REJECT |
| `test_missing_verdict_returns_none` | No verdict line |
| `test_empty_string_returns_none` | Empty input |
| `test_multiple_verdicts_last_wins` | Last verdict wins (REVISE→APPROVE) |
| `test_multiple_verdicts_last_wins_revise` | Last verdict wins (APPROVE→REVISE) |
| `test_case_sensitive_lowercase_ignored` | `verdict: approve` ignored |
| `test_case_sensitive_mixed_ignored` | `Verdict: APPROVE` ignored |
| `test_verdict_with_trailing_whitespace` | Trailing spaces OK |
| `test_verdict_embedded_in_longer_line_ignored` | Not at line start ignored |
| `test_verdict_standalone_line_only` | Leading space ignored |
| `test_long_review_with_approve_at_end` | Realistic review file |
| `test_main_reads_file` | CLI file arg |
| `test_main_missing_file_exits_1` | Missing file |
| `test_main_no_verdict_exits_1` | No verdict → exit 1 |
| `test_main_approve_prints_and_exits_0` | Output is just verdict word |
| `test_main_reject_prints_and_exits_0` | REJECT output |

### `tests/test_pipeline_e2e_ralplan.py` (9 tests)

| Test | Covers |
|------|--------|
| `test_ralplan_converges_first_cycle` | APPROVE cycle 1 → consensus.md, state=converged |
| `test_ralplan_converges_after_revisions` | REVISE→APPROVE → 2 cycles, consensus written |
| `test_ralplan_unconverged` | 3×REVISE → divergent-points.md, state=unconverged |
| `test_ralplan_rejected` | REJECT cycle 1 → state=rejected, no further cycles |
| `test_ralplan_clarifying_question` | Planner question → state=awaiting-input, pending-question.md |
| `test_ralplan_resume_after_clarification` | Pre-seed awaiting-input → resume → state moves forward |
| `test_ralplan_cancel_cascade` | cancel.signal → state=cancelled, no orphan jobs |
| `test_ralplan_no_banned_primitives` | 0 Task/Skill/AskUserQuestion/SendMessage hits |
| `test_ralplan_nested_under_autopilot` | RALPLAN_MODE=autopilot.ralplan → mode in status.json |

---

## 5. Validator Output

```
python3 scripts/verify_plugin_contract.py --all
```

All checks green. Exemptions within the ≤25 limit established in WS5c.

---

## 6. Test Count

| Baseline (WS5c) | New (WS5d) | Total |
|-----------------|-----------|-------|
| 246 | 27 | 273 |

- 18 verdict parser unit tests
- 9 ralplan consensus-loop e2e tests

---

## 7. Manual Smoke Evidence

```
OMNI_SUBAGENT_FAKE=1 \
OMNI_SESSION_ID=ws5d-smoke \
OMNI_SUBAGENT_FAKE_RESPONSE_FILE=tests/fixtures/ralplan-converge-cycle1.json \
python3 tests/_pipeline_runner.py ralplan 'design a CLI bookmark manager'
```

Expected output:
- Exit: 0
- `consensus.md` written to `.omni/runs/ralplan-ws5d-smoke/`
- `status.json`: `{"state": "converged", "last_verdict": "APPROVE", ...}`

---

## 8. Key Design Decisions

### Turn-based, not blocking

Per locked decision 8 + ADR-0011: ralplan never calls `AskUserQuestion`. When the Planner
needs clarification, it emits a `<clarifying-question>` XML block, ralplan persists the
question to `pending-question.md` and exits 0. The LLM surfaces the question as plain text.
Resume happens on the next user turn by re-invoking with the same `OMNI_SESSION_ID`.

### OMNI_SUBAGENT_FAKE_RESPONSE_FILE (WS5d addition to subagent.py)

Tests preload a JSON file mapping `agent_name → list_of_responses_in_order`. The fake
subagent pops the next response per agent invocation, enabling deterministic multi-cycle
testing without any real Copilot CLI. Invocation counts are tracked in a sidecar
`<file>.counts.json` using atomic writes.

### export variables for Python heredocs

All shell variables used inside Python heredoc subprocesses (`RUN_DIR`, `RALPLAN_RUN_ID`,
`RALPLAN_MODE`, `CYCLE`, `PLAN_FILE`, etc.) are `export`ed so Python's `os.environ`
can read them in the spawned subprocess.

---

## 9. Wave-2 Wrap-Up

WS5b (autopilot/ralph), WS5c (ultrawork/ultraqa), and WS5d (ralplan) together complete
the WS5 split. The autonomous pipeline is now Copilot-CLI native end-to-end:

- **Subprocess composition** (ADR-0006): all skill→agent calls via `scripts/subagent.py`
- **Cancel cascade**: `cancel.signal` file checked before every agent spawn
- **MCP state**: one row per run, updated at each phase/cycle transition
- **Turn-based interactive**: no blocking primitives, resume via persisted state
- **Pool back-pressure** (ADR-0010): `subagent_pool.py` enforced across all modes

### Handoff for WS6 (team rebuild)

WS6 can adopt the same pipeline state model:
- Run-dir layout: `.omni/runs/<skill>-<session-id>/`
- `status.json` with `state`, `mode`, `session_id` fields
- Cancel cascade via `cancel.signal`
- MCP state writes for monitoring via `omni doctor`
- `OMNI_SUBAGENT_FAKE_RESPONSE_FILE` for deterministic e2e tests
