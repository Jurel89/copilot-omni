# WS3 Front-Door Intent Router

## Overview

Every user prompt passes through the WS3 router before any skill dispatch occurs. The router
runs a lightweight, pure-CPU classifier (`scripts/router.py`) that scores the prompt for
concreteness, then decides one of three actions: **proceed** (concrete enough, execute
immediately), **redirect** (vague, gather requirements via `deep-interview`), or **bypass**
(user explicitly opted out with `--skip-interview`). The decision is persisted to MCP state
(`mode="router"`) so downstream skills can inspect it without re-running the classifier.

---

## Signal Table

Scoring follows ADR-0005 exactly. Each signal fires at most once.

| Signal | Weight | Pattern |
|---|---|---|
| File:line reference (`path/to/file.py:42`) | +0.10 | `\b\S+/\S+\.\w+:\d+` |
| Explicit file path | +0.30 | `\b\S+/\S+\.\w+\b` |
| Function or method name (`foo()`, `def foo`, `function foo`) | +0.25 | `\b[a-zA-Z_]\w*\(\)` or `\bdef / function` |
| Code block (fenced ≥3 body lines OR ≥3 indented lines) | +0.40 | Markdown fence / 4-space indent |
| Issue / PR reference (`#1234`, `PR #x`) | +0.20 | `#\d{3,}` |
| Error keywords (`Error:`, `Traceback`, `Exception`, `panic:`) | +0.20 | Case-sensitive token match |
| Specific tech name (postgres, pytest, docker, …) | +0.10 | Dictionary lookup |
| Concrete numeric spec (timeout/cap: `500ms`, `2GB`) | +0.15 | `\d+\s*(s\|ms\|MB\|GB\|%\|x)` |
| Bypass marker `--skip-interview` | +1.00 | Substring, force-passes |

**Vagueness penalties** (each −0.10, capped at −0.50 total):
"build me", "create something", "I want a", "do whatever", "you decide", "fix this"

**Score formula:**
```
score = clamp(sum_of_signals + capped_penalty, -1.0, +1.0)
```

Default threshold: **0.4** — prompts with `score < 0.4` are redirected.

---

## Worked Examples

### 1. Trivially vague → redirect

**Prompt:** `build me something useful`

| Signal | Weight | Evidence |
|---|---|---|
| vagueness_penalty | −0.10 | "build me" |

**Score:** −0.10 → **redirect** to deep-interview

---

### 2. File path only → redirect

**Prompt:** `fix scripts/server.py — it crashes`

| Signal | Weight | Evidence |
|---|---|---|
| file_path | +0.30 | `scripts/server.py` |

**Score:** 0.30 → **redirect** (below threshold 0.40)

---

### 3. File:line reference → proceed (tie)

**Prompt:** `fix hooks/pre_tool_use.py:42 — the regex is wrong`

| Signal | Weight | Evidence |
|---|---|---|
| file_line_ref | +0.10 | `hooks/pre_tool_use.py:42` |
| file_path | +0.30 | `hooks/pre_tool_use.py` |

**Score:** 0.40 → **proceed** (ties go to proceed)

---

### 4. Error traceback with function name → proceed

**Prompt:** `Traceback in validate() call stack`

| Signal | Weight | Evidence |
|---|---|---|
| error_keyword | +0.20 | `Traceback` |
| func_name | +0.25 | `validate()` |

**Score:** 0.45 → **proceed**

---

### 5. Explicit bypass → bypass

**Prompt:** `build me a website --skip-interview`

| Signal | Weight | Evidence |
|---|---|---|
| bypass_marker | +1.00 | `--skip-interview` |
| vagueness_penalty | −0.10 | "build me" |

**Score:** 0.90 (clamped) → **bypass** (decision forced regardless of score)

---

## Bypass Syntax

Append `--skip-interview` anywhere in the prompt to skip the interview phase:

```
fix the auth service --skip-interview
```

This is the **only** bypass syntax. The `!` prefix is NOT supported.

---

## Threshold Override

### Per-config (project-level)

Set `router.vagueness_threshold` in `.omni/config.json`:

```json
{
  "router": {
    "vagueness_threshold": 0.5
  }
}
```

### Per-session (CLI override)

```bash
python3 scripts/router.py --threshold 0.5 --prompt "your prompt"
```

---

## Inspecting Router Decisions

### Via omni doctor

```bash
python3 scripts/omni.py doctor --verbose
```

This prints the router config (threshold) and the most recent router decision from MCP state.

### Via state reader script

```bash
python3 scripts/router_state.py --read --mode router
```

Returns the stored body dict for the `mode="router"` state slot, or
`{"status": "none", "reason": "no state found"}` if no decision has been persisted.

### Raw MCP state

The decision is stored under `mode="router"` in the `state` table of `$OMNI_HOME/omni.db`.
Schema: see `docs/STATE_CONTRACT.md`.

---

## Limitations

- **Stub state reader**: `scripts/router_state.py` returns
  `{"status": "unknown", "reason": "WS5 not yet shipped"}` for pipeline modes other than
  `router` (autopilot, ralph, ultrawork). WS5b will replace this stub with real state reads.

- **LLM-honoring of the decision block**: The `<router-decision>` tag emitted by
  `hooks/user_prompt_submit.py` is a system-reminder that the LLM reads. The LLM is expected
  to honor it, but this is a best-effort contract — the tag is advisory, not a hard gate at the
  transport layer. Phase C TODO: enforce at the transport layer.

- **Pattern-based scoring**: The classifier uses regex patterns, not semantics. A meaningless
  file path like `xyz/asdf.foo` triggers the file-path signal even if the path is nonsensical.
  This is a known limitation; the threshold and interview step compensate.
