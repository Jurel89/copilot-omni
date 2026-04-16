# ADR-0003 — Model Category Contract

- **Status:** Accepted
- **Date:** 2026-04-16
- **Supersedes:** (none)
- **Related:** ADR-0000 locked decision 6, phase-b-master-plan.md §2.WS4 + §7 WS4

## Context

`copilot-omni` v1 inherited skill and agent files that hard-coded concrete model
names (`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-6`).  This creates
three problems:

1. **Subscription-menu drift.** The GitHub Copilot subscription menu changes
   periodically.  When a model is renamed or removed, every hard-coded reference
   breaks silently.
2. **Tier portability.** Users on a Copilot for Business subscription may not
   have the same model set as users on Copilot Individual.  Hard-coded names fail
   on the wrong tier.
3. **Fallback safety.** If the primary model is temporarily unavailable, there is
   no recovery path without manual intervention.

The solution is a **three-level semantic category system** that resolves a logical
tier name to a concrete model at runtime, walking a per-category fallback chain
if the primary is unavailable.

## Decision

### Three categories

| Category    | Intended use                                    | Default primary       |
|-------------|------------------------------------------------|----------------------|
| `quick`     | Fast, lightweight tasks (search, short answers) | `claude-haiku-4-5`   |
| `deep`      | Standard work (implementation, analysis)        | `claude-sonnet-4-5`  |
| `ultrabrain`| Heavy reasoning, architecture, large context    | `claude-opus-4-6`    |

No other categories are introduced in Phase B.  `reasoning`, `vision`, and
similar specialised categories are deferred to Phase C.

### Per-category schema

The `.omni/config.json` file gains a top-level `models` block.  Each entry is:

```json
{
  "models": {
    "quick": {
      "model": "claude-haiku-4-5",
      "fallbacks": ["gpt-5-mini", "claude-sonnet-4.5"]
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

The value `{model: str, fallbacks: [str]}` is the canonical schema for every
category entry.  A flat-string value is **not** supported; `omni doctor` will
warn if it encounters one.

### Default category mappings (user-overridable)

If `.omni/config.json` does not contain a `models` block, the resolver uses
built-in defaults:

```
quick      → claude-haiku-4-5   fallbacks: [gpt-5-mini, claude-sonnet-4.5]
deep       → claude-sonnet-4.5  fallbacks: [gpt-5, gemini-2.5-pro]
ultrabrain → claude-opus-4-6    fallbacks: [gpt-5-codex, gemini-2.5-pro]
```

### Resolution policy

1. Load the category config (user config merged over built-in defaults).
2. Call the **availability checker** for the primary model.
3. If the primary is available (or the availability check fails/is skipped),
   return the primary model immediately.
4. If the primary is unavailable, walk `fallbacks` in order, calling the
   availability checker for each.
5. Return the first available fallback.
6. If all fallbacks are exhausted and none are available, return the primary
   model anyway.  **The resolver never raises an exception — it always returns
   a model string.**

### Availability checker

The default availability checker shells out to `copilot models --json` (or the
equivalent subcommand as exposed by the installed Copilot CLI).

- If the subcommand does not exist or the call fails, `available_check` is set
  to `"failed"` and the resolver proceeds as if the primary is available.
- If the call succeeds but returns no model list, `available_check` is set to
  `"skipped"`.
- Callers may inject a custom `availability_checker(model_name) -> bool` for
  testing or offline use.

### Override mechanism

Users may override any category by editing `.omni/config.json`:

```jsonc
{
  "models": {
    "quick": {
      "model": "gpt-5-mini",           // override primary
      "fallbacks": ["claude-haiku-4-5"] // override fallback chain
    }
  }
}
```

`omni doctor` validates the config on every run:
- Unknown category names are logged as warnings (not errors).
- Missing `model` field is an error.
- Missing `fallbacks` field is treated as an empty list (warning only).
- Invalid schema shape (flat string instead of object) is an error.

On `omni doctor --strict`, the doctor also calls the resolver for each known
category and fails if any category resolves to a fallback (signals
subscription-menu drift that the user should investigate).

### Validator gate

No raw model name may appear in `skills/`, `agents/`, `commands/`, or `hooks/`
outside the following allowlist:

- `docs/MODELS.md`
- `.omni/config.json`
- `scripts/category_resolver.py`
- `docs/ADR/ADR-0003-*`

The check is implemented in `scripts/verify_plugin_contract.py` as
`check_no_raw_model_names`.  Patterns:

```
claude-haiku|claude-sonnet|claude-opus|gpt-[0-9]|gemini-[0-9]
```

The check is **character-class aware**: it does not flag strings inside markdown
code fences, and it uses concatenation-defeating character-class regex to prevent
trivial evasion.

Per-file exemption: add `<!-- omni-model-allow: <reason> -->` within three lines
of the offending text.  These count against the global exemption budget
(MAX_EXEMPTIONS_TOTAL = 25).

### Frontmatter migration

Agent `.md` files with a `model:` field are migrated to `category:` during the
WS4 sweep.  The frontmatter parser treats `model:` as a deprecated alias for
`category:` during a transition period.  A warning is emitted when a `model:`
key is encountered so that downstream tooling is updated.

### Subscription-menu drift

When the Copilot subscription menu adds a new model:

1. Add the model name to the appropriate fallback chain in `.omni/config.json`.
2. Optionally promote it to primary if it supersedes the current primary.
3. Run `omni doctor --strict` to confirm all categories resolve to primary.
4. Run `python3 scripts/category_resolver.py --check` to see the resolution
   output before committing.

### Why categories instead of raw names

- **Portability:** A skill that says `category: quick` works on every Copilot
  tier; a skill that says `model: claude-haiku-4-5` breaks on tiers that don't
  include that model.
- **Future-proofing:** When Anthropic releases a new Haiku revision, only the
  config changes — skills and agents need no edits.
- **Fallback safety:** The resolver automatically walks the fallback chain when
  the primary is unavailable, with zero impact on skill logic.
- **Auditability:** The validator gate ensures raw names cannot creep back in,
  and the exemption budget keeps the allowlist from growing unbounded.

## Consequences

- All `model:` frontmatter fields in `agents/*.md` must be replaced with
  `category:` during WS4.
- All skill/command/hook prose that references a concrete model name must be
  updated to use a category.
- `scripts/subagent.py` gains a `--category` flag that resolves via
  `category_resolver.resolve()`.
- `omni doctor` exercises fallback chains and reports drift.
- The validator check is added to `verify_plugin_contract.py` and runs as part
  of `--all`.

## Phase-C open questions

- Per-agent override of fallback chains (e.g., a single skill that needs Opus
  regardless of the `deep` category primary).
- `vision` and `reasoning` categories (deferred).
- Automatic category promotion when a new model outperforms the current primary
  on the user's subscription.
