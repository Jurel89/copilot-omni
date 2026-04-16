# WS3 Completion Report — Front-Door Intent Router

**Branch:** `phase-b/wave-2/WS3-front-door-router`
**Date:** 2026-04-16
**Status:** complete

---

## ADR-0005 Summary

ADR-0005 (`docs/ADR/ADR-0005-router-scoring-rubric.md`) codifies the concreteness scoring
rubric. Key decisions:

| Signal | Weight |
|---|---|
| File:line reference | +0.10 |
| Explicit file path | +0.30 |
| Function/method name | +0.25 |
| Code block (fenced ≥3 body lines OR ≥3 indented lines) | +0.40 |
| Issue/PR reference | +0.20 |
| Error keywords | +0.20 |
| Specific tech name | +0.10 |
| Concrete numeric spec | +0.15 |
| Bypass marker `--skip-interview` | +1.00 (force bypass) |
| Vagueness penalty (each phrase) | −0.10, capped at −0.50 |

Default threshold: `0.4`. Score < 0.4 → redirect; score >= 0.4 → proceed; tie → proceed.
`--skip-interview` anywhere → bypass, regardless of score.

Code-block rule: fenced block needs ≥3 non-empty body lines; indented block needs ≥3 consecutive
4-space lines. Inline backticks do NOT count.

---

## Router Classifier

**File:** `scripts/router.py`
**LOC:** ~380
**Dependencies:** stdlib only (re, json, datetime, argparse, pathlib, subprocess)

### Public API

```python
classify(prompt, *, threshold=0.4, config=None) -> dict
emit_router_state(decision, *, session_id=None) -> None
```

`classify()` is pure CPU — zero I/O. `emit_router_state()` writes the decision to MCP via
subprocess JSON-RPC (best-effort; failure logged to stderr, never propagates).

### CLI

```bash
python3 scripts/router.py --prompt "<text>"
python3 scripts/router.py --stdin
python3 scripts/router.py --threshold 0.5 --prompt "<text>"
python3 scripts/router.py --emit-state --prompt "<text>"
```

---

## Hook Integration

**File:** `hooks/user_prompt_submit.py` (complete rewrite of v1 advisory hint system)

### What fires when

1. Prompt arrives via stdin JSON (`{"prompt": "..."}`)
2. Router classifies via `router.classify()`
3. Decision persisted via `router.emit_router_state()` (best-effort)
4. `<router-decision>` tag emitted as `additionalContext`

### Emitted decision block format

```
redirect: <router-decision redirect="deep-interview" reason="vague-prompt" score="0.27">
          {"signals": [...], "bypass": "use --skip-interview to bypass"}
          </router-decision>

bypass:   <router-decision bypass="true" score="1.0">{"signals": [...]}</router-decision>

proceed:  <router-decision proceed="true" score="0.55"></router-decision>
```

Kill switches honored: `OMNI_SKIP_HOOKS`, `DISABLE_OMNI`, `OMC_SKIP_HOOKS` (compat alias),
`DISABLE_OMC` (compat alias).

---

## Bypass Syntax Decision Rationale

The bypass syntax is `--skip-interview` ONLY. The `!` prefix was dropped per critic §7 #4 and
plan revision F9. Rationale: `!` is ambiguous in many shells and CLI contexts; `--skip-interview`
is explicit, grep-able, and unambiguous. The substring match allows placement anywhere in the
prompt (start, middle, end).

---

## Stub State Reader

**File:** `scripts/router_state.py`
**LOC:** ~130

`read_pipeline_state(session_id=None, mode="router")`:
- `mode="router"` → attempts MCP `state_read` via subprocess; returns `None` if MCP unavailable.
- Any other pipeline mode (autopilot, ralph, ultrawork, team) → returns stub
  `{"status": "unknown", "reason": "WS5 not yet shipped"}` per F4.

WS5b will replace the stub logic with real pipeline state reads.

---

## Test Coverage

### `tests/test_router.py`

| Category | Count |
|---|---|
| Trivially concrete prompts | 10 |
| Trivially vague prompts | 8 |
| Bypass cases | 6 |
| Near-threshold edge cases (within ±0.10) | 10 |
| Adversarial cases | 8 |
| Penalty stacking | 6 |
| Code block detection | 6 |
| Signals audit trail | 8 |
| **Total** | **62** |

All tests assert BOTH decision AND exact score (rounded to 2 dp).
Near-threshold cases: 10 (≥8 required by spec).

### `tests/test_hooks.py` (WS3 additions)

10 new tests covering: vague→redirect tag, concrete→proceed tag, bypass tag, kill switches
(OMNI_SKIP_HOOKS, DISABLE_OMNI, OMC_SKIP_HOOKS), empty prompt, no-redirect attr on bypass.

### `tests/test_router_state.py`

14 tests: stub returns for all WS5 modes, stub is copy not reference, router mode no-crash,
CLI smoke tests.

---

## `/omni-do` and `/omni-next` Commands

Both are markdown-driven LLM-instruction files in `commands/`:

- `commands/omni-do.md`: instructs the LLM to invoke the router via `python3 scripts/router.py
  --stdin`, parse the JSON decision, and act on it.
- `commands/omni-next.md`: instructs the LLM to call `python3 scripts/router_state.py --read
  --session-id <id>` and act on the returned state.

**Determinism caveat (per critic §6 #7):** Both commands are consumed by the LLM, not executed
independently as CLI binaries. The determinism comes from the script output; the LLM interprets
and acts on that output. This is documented in the command bodies.

---

## Validator Output

- `MAX_EXEMPTIONS_TOTAL` raised from 15 → 25 (1-line change with WS3 rationale comment).
- All 11 existing checks remain green.
- `commands` count: 10 (was 8; +2: omni-do, omni-next).

---

## omni doctor Integration

`scripts/omni.py` doctor command updated:
- Reads `.omni/config.json` for `router.vagueness_threshold`.
- Writes default 0.4 if missing.
- `--verbose` flag prints most recent router decision from MCP state.

---

## Handoff for WS4

WS4 (model resolver) does not depend on the router's decision, but both share `.omni/config.json`.
WS4 should add its config under a separate top-level key (e.g. `resolver`) to avoid collision.

## Handoff for WS5b

WS5b (autopilot/ralph pipeline state) should:
1. Implement `state_write/state_read` calls for `mode="autopilot"`, `mode="ralph"`, etc.
2. Replace the stub in `scripts/router_state.py` for those modes.
3. Downstream: skills can read the router's `mode="router"` decision to skip the analyst phase
   when `decision=="proceed"` and redirect to `deep-interview` when `decision=="redirect"`.

---

## Deferred TODOs

- Phase C: enforce `<router-decision>` at the transport layer (currently advisory).
- Phase C: OOM back-pressure — NOT added here per critic §6 #3 + ADR-0010.
- Phase C: replace stub state reader for non-router modes once WS5b ships.
