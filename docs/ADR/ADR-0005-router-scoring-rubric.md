---
id: ADR-0005
title: Router Scoring Rubric
status: accepted
date: 2026-04-16
deciders: [WS3]
---

# ADR-0005 — Router Scoring Rubric

## Context

WS3 introduces a front-door intent router that classifies every user prompt before any skill
dispatch occurs. The router must decide whether a prompt is concrete enough to proceed directly,
vague enough to redirect to `deep-interview`, or carries an explicit bypass marker
(`--skip-interview`) that forces execution regardless of score.

The classifier needs a deterministic, auditable scoring algorithm so that:
1. The decision can be reproduced and debugged (signal trail in `signals` list).
2. Threshold changes are centralised in `.omni/config.json` without code changes.
3. Test cases can be authored against exact scores, not fuzzy ranges.

## Decision

### 1. Signal Table

Each signal fires at most once per prompt unless noted otherwise.

| Signal | Weight | Source pattern |
|---|---|---|
| Explicit file path or `path:` reference | +0.30 | `\b\S+/\S+\.\w+\b` OR contains `/` followed by extension |
| File:line reference (`path/to/file.py:42`) | +0.10 | `\b\S+/\S+\.\w+:\d+` — fires in addition to file-path signal |
| Function or method name (`foo()` / `def foo` / `function foo`) | +0.25 | `\b[a-zA-Z_]\w*\(\)` or `\bdef [a-zA-Z_]` or `\bfunction [a-zA-Z_]` |
| Code block (fenced ``` or 4-space indent ≥3 lines) | +0.40 | Markdown fence detection (see §2) |
| Issue / PR reference (`#1234`, `PR #x`, `issue x`) | +0.20 | `#\d{3,}` or `\b(?:PR|issue)\s+#?\d+\b` (case-insensitive) |
| Concrete error message keywords (`Error:`, `Traceback`, `Exception`, `panic:`) | +0.20 | Exact case-sensitive token match |
| Specific tech name (see §3) | +0.10 | Dictionary lookup |
| Concrete numeric specification (timeout/cap/version ≥X) | +0.15 | `\d+\s*(?:s|ms|MB|GB|%|x)\b` |
| Bypass marker `--skip-interview` literal | +1.00 | Substring match (forces `decision="bypass"`) |

**Vagueness penalties** (cumulative, capped at −0.50 total):

| Phrase | Penalty |
|---|---|
| `build me` | −0.10 |
| `create something` | −0.10 |
| `I want a` | −0.10 |
| `do whatever` | −0.10 |
| `you decide` | −0.10 |
| `fix this` (without a concrete object after it) | −0.10 |

Penalty detection is case-insensitive substring match. A penalty phrase is counted once per
distinct match (same phrase appearing twice still contributes only one penalty).

### 2. Code-Block Detection Rules

The code-block signal fires (+0.40) if the prompt contains:

- **Fenced block**: a line starting with ` ``` ` (three or more back-ticks) followed by at least
  two more lines before the closing ` ``` `. I.e. the fenced block has ≥ 3 lines total (opening
  fence + body + closing fence means at least one body line; but the rule requires the fenced
  region to contain ≥ 2 body lines so that ```` ```\nfoo\n``` ```` — one body line — does NOT
  trigger, while ```` ```\nfoo\nbar\n``` ```` — two body lines — DOES trigger). Concretely: the
  number of lines strictly between the opening and closing fence must be ≥ 2.

  > **Correction / canonical rule**: the fenced block signal fires when ≥ 3 lines appear between
  > the opening and closing fence delimiters (i.e. the fence contains ≥ 3 non-fence lines). This
  > matches the "3-line fenced block" language in the task spec. A 2-line body does NOT fire.

  **Canonical rule (normalised):**
  - Opening fence line: `^\s*` ``` ` `` \s*` (three or more backticks, optional language tag, rest of line ignored).
  - Count the number of non-empty lines strictly inside the fence.
  - Signal fires if that count ≥ 3.
  - The closing fence line does not count.
  - Only the first qualifying fence is needed — once the signal fires it is not added again.

- **Indented block**: ≥ 3 consecutive lines that each begin with 4 or more spaces (outside a
  fenced region). A line that is blank (zero non-space chars) does NOT count toward the streak,
  but also does NOT reset it.

**What does NOT count as a code block:**
- Inline backtick sequences (e.g. `` `path/to/file` `` or `` `foo()` ``).
- A single-line or two-line fenced block.
- Fewer than 3 consecutively indented lines.

### 3. Tech-Name Dictionary

The following tokens trigger the +0.10 specific-tech-name signal (case-insensitive):

```
postgres, postgresql, mysql, sqlite, redis, mongodb, kafka,
tmux, pytest, unittest, django, flask, fastapi, sqlalchemy,
git, docker, kubernetes, k8s, terraform, ansible, nginx, apache,
python, javascript, typescript, rust, golang, java, kotlin, swift,
ruby, php, haskell, scala, clojure, elixir, erlang,
react, vue, angular, svelte, nextjs, nuxt,
pytest, mypy, ruff, pylint, eslint, webpack, vite, babel,
aws, gcp, azure, lambda, s3, ec2, rds,
ssh, http, https, grpc, graphql, rest, websocket,
linux, ubuntu, debian, fedora, macos, windows,
bash, zsh, powershell, curl, wget, jq, awk, sed
```

The signal fires at most once regardless of how many distinct tech names appear.

### 4. Score Computation

```
raw_score = sum(weight for each signal that fires)
penalty   = max(-0.50, sum(penalty for each unique vagueness phrase matched))
score     = clamp(raw_score + penalty, -1.0, +1.0)
```

**Bypass override:** if the literal substring `--skip-interview` is found anywhere in the prompt,
the final `decision` is ALWAYS `"bypass"` regardless of `score`. The score is still computed and
reported for auditability (it will reflect the +1.00 bypass-marker weight).

**Threshold comparison:**
- `decision = "bypass"` → `--skip-interview` present (skip score check).
- `decision = "redirect"` → `score < threshold`.
- `decision = "proceed"` → `score >= threshold`.

Default threshold: `0.4` (configurable via `.omni/config.json` key `router.vagueness_threshold`).

### 5. Tie-Breaker Rules

When `score == threshold` exactly, the prompt is treated as **concrete** (`decision = "proceed"`).
The threshold is a strict lower bound: only `score < threshold` triggers a redirect.

### 6. Capping Rules

- Positive signals: no per-signal cap; each fires at most once.
- Vagueness penalties: cumulative sum is capped at −0.50 (i.e. `max(-0.50, raw_penalty_sum)`).
- Final score: clamped to [−1.0, +1.0] after applying penalty.
- Bypass marker weight (+1.00) can push the score above +1.0 before clamping; after clamping the
  score is still reported as +1.00 (or lower if no other signals fired — the bypass marker alone
  produces +1.00 clamped).

### 7. `signals` Audit Trail

The classifier returns a `signals` list of `{name, weight, evidence}` dicts:
- `name`: short identifier (e.g. `"file_path"`, `"code_block"`, `"vagueness_penalty"`).
- `weight`: the numeric weight applied (+/−).
- `evidence`: a short string excerpt or match showing what triggered the signal.

Each fired signal produces one entry. Unfired signals are omitted. Penalty phrases each produce a
separate entry (up to a maximum of 5 distinct penalty phrases, corresponding to the −0.50 cap).

### 8. Session Override

The threshold can be overridden per-session by setting `router.vagueness_threshold` in the current
session's `.omni/config.json` (project-local). The `classify()` function accepts a `config` dict
that takes precedence over the default threshold parameter.

## Consequences

- `scripts/router.py` implements this rubric exactly; any deviation is a bug.
- `tests/test_router.py` authors test cases AFTER this ADR is finalised; it must assert exact
  scores (rounded to 2 dp) and decisions.
- The bypass syntax is `--skip-interview` ONLY. The `!` prefix is not supported.
- Any change to signal weights or the tech-name dictionary is a new ADR revision.
