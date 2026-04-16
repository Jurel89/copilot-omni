# Model Categories Reference

This document is the user-facing reference for copilot-omni's semantic model
category system, introduced in WS4 of Phase B.

> **Allowlisted file.** This document may contain concrete model names for
> documentation purposes. The validator check `no-raw-model-names` excludes
> this file via `docs/MODELS.md` in its allowlist.

---

## The Three Categories

### `quick`

**Purpose:** Fast, lightweight tasks — codebase search, short summaries,
single-file lookups, anything where latency matters more than reasoning depth.

**Default primary:** `claude-haiku-4-5`
**Default fallbacks:** `gpt-5-mini`, `claude-sonnet-4.5`

Use `quick` for agents like `explore` and `writer`, and for skills that need
a snappy first-pass response.

---

### `deep`

**Purpose:** Standard implementation and analysis work — writing code, debugging,
planning, reviewing, designing UI. This is the workhorse tier.

**Default primary:** `claude-sonnet-4.5`
**Default fallbacks:** `gpt-5`, `gemini-2.5-pro`

Use `deep` for agents like `executor`, `debugger`, `designer`, and most skill
orchestration.

---

### `ultrabrain`

**Purpose:** Heavy reasoning, large context, architecture-level analysis, and
long-horizon planning.  Use this when you need the most capable model available.

**Default primary:** `claude-opus-4-6`
**Default fallbacks:** `gpt-5-codex`, `gemini-2.5-pro`

Use `ultrabrain` for agents like `architect`, `planner`, `critic`, and
`analyst`.

---

## How to Override

Edit `.omni/config.json` in your project (create it with `omni init` if it
does not exist yet):

```json
{
  "models": {
    "quick": {
      "model": "gpt-5-mini",
      "fallbacks": ["claude-haiku-4-5"]
    },
    "deep": {
      "model": "claude-sonnet-4.5",
      "fallbacks": ["gpt-5", "gemini-2.5-pro"]
    },
    "ultrabrain": {
      "model": "claude-opus-4-6",
      "fallbacks": ["gpt-5-codex", "gemini-2.5-pro"]
    }
  }
}
```

You only need to include the categories you want to override. Omitted
categories use the built-in defaults.

To override just the primary for one category, omit `fallbacks`:

```json
{
  "models": {
    "quick": { "model": "gpt-5-mini" }
  }
}
```

---

## Current Copilot Subscription Models

The following models are available on GitHub Copilot subscriptions as of the
WS4 release snapshot (2026-04-16). **This list drifts** — consult the Copilot
model picker in your IDE for the authoritative current list.

| Provider  | Model              | Tier guidance            |
|-----------|--------------------|--------------------------|
| Anthropic | claude-haiku-4-5   | quick                    |
| Anthropic | claude-sonnet-4.5  | deep                     |
| Anthropic | claude-opus-4-6    | ultrabrain               |
| OpenAI    | gpt-5              | deep fallback            |
| OpenAI    | gpt-5-mini         | quick fallback           |
| OpenAI    | gpt-5-codex        | ultrabrain fallback      |
| Google    | gemini-2.5-pro     | deep / ultrabrain fallback |

When a new model appears in your subscription, add it to the appropriate
`fallbacks` array (or promote it to primary) in `.omni/config.json`.

---

## Resolution Semantics

At runtime, `scripts/category_resolver.py` applies the following algorithm:

1. Load the category config from `.omni/config.json`, merged over built-in
   defaults (user config wins on overlap).
2. Call the **availability checker** (`copilot models --json`) for the primary
   model.
3. If the primary is available (or the availability check fails — fail-open),
   return the primary model immediately.
4. If the primary is not available, walk the `fallbacks` list in order.
5. Return the first available fallback.
6. If all fallbacks are exhausted, return the primary anyway — **the resolver
   never raises; it always returns a model string**.

The `available_check` field in the resolution result is set to:
- `"ok"` — the availability check ran and returned a model list.
- `"skipped"` — the check ran but returned an empty list (treated as available).
- `"failed"` — the check failed or the `copilot models` subcommand is absent
  (treated as available — fail-open).

---

## How to Verify

### Quick check — resolver CLI

```bash
# Print the concrete model for a category
python3 scripts/category_resolver.py quick
python3 scripts/category_resolver.py deep
python3 scripts/category_resolver.py ultrabrain

# Print the full resolution dict as JSON
python3 scripts/category_resolver.py --json deep

# List all known category names
python3 scripts/category_resolver.py --known

# Resolve all categories and report drift
python3 scripts/category_resolver.py --check
```

### Full environment check — omni doctor

```bash
# Normal check (warn on drift, never fail for drift alone)
omni doctor

# Strict check — exit non-zero if any category resolves to a fallback
omni doctor --strict
```

The `models:` lines in the doctor output show the chosen model and check
status for each category.

---

## Why No Raw Names in Code

**Portability:** A skill file that says `category: quick` works on every
Copilot subscription tier. A file that embeds `claude-haiku-4-5` breaks
silently if that model is renamed or removed from the user's subscription.

**Future-proofing:** When a new Haiku revision ships, only `.omni/config.json`
changes. No skill files need editing.

**Fallback safety:** The category resolver walks the fallback chain
automatically. Hard-coded model names have no fallback path.

**Validator gate:** `scripts/verify_plugin_contract.py --check-no-raw-model-names`
enforces this at every CI run. Raw model names in `skills/`, `agents/`,
`commands/`, or `hooks/` cause a build failure. Exceptions require an
`<!-- omni-model-allow: <reason> -->` marker and count against the global
exemption budget (cap: 25).
