# WS4 Completion Report — Model Categories

**Branch:** `phase-b/wave-2/WS4-model-categories`
**Date:** 2026-04-16
**Status:** Complete

> **Allowlisted file.** This report may contain concrete model names for
> documentation purposes. The validator check `no-raw-model-names` excludes
> this file via its allowlist entry for `.omni/plans/wave-2-WS4-report.md`.

---

## ADR-0003 Summary

`docs/ADR/ADR-0003-model-categories.md` (~200 lines) documents:

- Three categories: `quick`, `deep`, `ultrabrain` (no others in Phase B).
- Per-category schema: `{model: str, fallbacks: [str]}` — not a flat string.
- Default mappings:
  - `quick` → `claude-haiku-4-5`, fallbacks: `[gpt-5-mini, claude-sonnet-4.5]`
  - `deep` → `claude-sonnet-4.5`, fallbacks: `[gpt-5, gemini-2.5-pro]`
  - `ultrabrain` → `claude-opus-4-6`, fallbacks: `[gpt-5-codex, gemini-2.5-pro]`
- Resolution policy: primary if available; walk fallbacks in order; fail-open
  (always returns a model, never raises).
- Override mechanism: edit `.omni/config.json > models > <category>`.
- Validator gate: `no-raw-model-names` enforced by `verify_plugin_contract.py`.
- Subscription-menu drift: add new model to fallback chain, then run
  `omni doctor --strict` to verify.
- Frontmatter migration: `model:` → `category:` in all agent `.md` files.

---

## Resolver (`scripts/category_resolver.py`)

**LOC:** ~250 (stdlib only).

**Public API:**

```python
def known_categories() -> set[str]:
    # Returns {"quick", "deep", "ultrabrain"}

def load_default_categories() -> dict:
    # Returns deep-copy of built-in defaults

def load_config(path: Path | None = None) -> dict:
    # Loads .omni/config.json, merges over built-in defaults

def resolve(category: str, *, config=None, availability_checker=None) -> dict:
    # Returns {category, model, primary, fallbacks_tried, available_check, ts}
    # Never raises; always returns a model string
```

**Availability-check semantics:**

- Default checker shells out to `copilot models --json`.
- If the subcommand is absent, times out, or fails: `available_check = "failed"`,
  resolver proceeds as if primary is available (fail-open).
- If the call succeeds but returns an empty list: `available_check = "skipped"`.
- Custom `availability_checker(model_name) -> bool` injectable for tests.

**CLI:**

```
python3 scripts/category_resolver.py quick           # prints model name
python3 scripts/category_resolver.py --json deep     # full resolution JSON
python3 scripts/category_resolver.py --known         # lists categories
python3 scripts/category_resolver.py --check         # resolves all, non-zero if any fallback used
```

---

## Subagent Flag Changes

`scripts/subagent.py` gained a `--category <quick|deep|ultrabrain>` flag.

**Back-compat:** Existing callers using `--model` are unaffected.
`--model` wins if both flags are given (explicit beats implicit).
If neither is given, no `--model` flag is passed to copilot (unchanged).
Unknown categories return exit code 1 without invoking copilot.

**Signature change:** `run_agent()` has a new optional `category: str = None`
parameter (keyword-only after `model`).

---

## Sweep Stats

| Directory  | Files modified | Raw model hits → categories |
|------------|----------------|------------------------------|
| `agents/`  | 19             | 19 `model:` → `category:`   |
| `skills/`  | 0              | 0 hits found                |
| `commands/`| 0              | 0 hits found                |
| `hooks/`   | 0              | 0 hits found                |

**Residual hits outside allowlist:** 0

Category breakdown for agents:
- `quick` (2): explore, writer
- `deep` (10): debugger, designer, document-specialist, executor, git-master,
  qa-tester, scientist, test-engineer, tracer, verifier
- `ultrabrain` (7): analyst, architect, code-reviewer, code-simplifier,
  critic, planner, security-reviewer

---

## Doctor Integration

`omni doctor` now runs `_doctor_categories()` after the router check:

```
models:        deep → claude-sonnet-4.5 (primary; check: failed)
models:        quick → claude-haiku-4-5 (primary; check: failed)
models:        ultrabrain → claude-opus-4-6 (primary; check: failed)
models:        WARN: availability check failed for all categories ...
```

`omni doctor --strict` exits non-zero if any category resolves to a fallback
(signals subscription-menu drift).

---

## Validator

**New check:** `no-raw-model-names` in `scripts/verify_plugin_contract.py`.

- Patterns: `claude-[Hh][Aa][Ii][Kk][Uu]`, `claude-[Ss][Oo][Nn][Nn][Ee][Tt]`,
  `claude-[Oo][Pp][Uu][Ss]`, `gpt-[0-9]`, `gemini-[0-9]`
- Scope: `skills/`, `agents/`, `commands/`, `hooks/`
- Code-fence-aware (`_strip_code_fences`).
- Character-class regex defeats `'hai'+'ku'` concatenation evasion.
- Allowlist: `docs/MODELS.md`, `.omni/config.json`, `scripts/category_resolver.py`,
  `docs/ADR/ADR-0003-*`, `.omni/plans/wave-2-WS4-report.md`,
  `scripts/verify_plugin_contract.py`.
- Inline exemption: `<!-- omni-model-allow: <reason> -->` within 3 lines.
- Exemption marker `omni-model-allow` added to `_EXEMPTION_MARKERS` (counts
  against MAX_EXEMPTIONS_TOTAL = 25).

**Current exemption budget:** 16/25 (well under cap).

---

## Test Count

| Test suite                     | Before WS4 | After WS4 |
|-------------------------------|-----------|-----------|
| All tests                      | 186       | 200       |
| `test_subagent_categories.py`  | 0         | 14        |

All 200 tests pass.

---

## Acceptance Gate Verification

| Gate                                                     | Status |
|----------------------------------------------------------|--------|
| `verify_plugin_contract.py --all` → all green            | PASS   |
| `no-raw-model-names` check green                         | PASS   |
| Exemption count ≤ 25                                     | 16/25  |
| `pytest -q` → all tests pass                             | 200    |
| `discovery_smoke.py --probe layout` → pass               | PASS   |
| `category_resolver.py --known` → quick deep ultrabrain   | PASS   |
| `category_resolver.py --json deep` → JSON with all keys  | PASS   |
| `subagent.py --help` → shows --category flag             | PASS   |
| `git grep` raw model names in skills/agents/commands/hooks | 0 hits |

---

## Handoff for WS5+

- `scripts/subagent.py` is now category-aware. Pipeline rewrites (WS5a, WS5b)
  should use `--category <tier>` rather than `--model <concrete-name>`.
- When spawning agents, map the agent's `category:` frontmatter field to the
  corresponding `--category` flag.
- The `_parse_frontmatter()` function in `verify_plugin_contract.py` already
  handles `category:` keys alongside `model:` (treated as deprecated alias).

---

## Open Phase-C Questions

1. **Per-agent fallback chains.** A single skill may need to override the
   category fallback chain (e.g., always use Opus for security review).
   Currently only global overrides via `.omni/config.json` are supported.
2. **`vision` and `reasoning` categories.** Deferred from Phase B; Phase C
   should evaluate whether these warrant their own categories or are addressed
   by per-agent overrides.
3. **Automatic category promotion.** When a new model outperforms the current
   primary on the user's subscription, should `omni doctor` suggest promoting
   it? Needs a benchmarking signal.
4. **Frontmatter backward-compat deprecation window.** The `model:` alias in
   frontmatter should emit a deprecation warning in Phase C and be removed
   in Phase D/v3.0.0.
