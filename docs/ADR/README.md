# Architecture Decision Records — Index

All ADRs for the copilot-omni Phase B rewrite. Ordered by number.
"Locked" = decision is final and must not be re-opened without explicit user sign-off.
"Living" = may be amended as implementation evidence accumulates.

| ADR | Title | Status | Lock |
|-----|-------|--------|------|
| [ADR-0000](ADR-0000-phase-b-charter.md) | Phase B Charter — locked decisions + scope | Accepted | Locked |
| [ADR-0001](#adr-0001) | Host = GitHub Copilot CLI only (no Claude Code primitives) | Accepted | Locked |
| [ADR-0002](#adr-0002) | Skill deletions — 7 deleted, 1 deferred, 29 kept/rewritten | Accepted | Locked |
| [ADR-0003](ADR-0003-model-categories.md) | Model category contract — `quick`, `deep`, `ultrabrain` | Accepted | Locked |
| [ADR-0004](#adr-0004) | Team orchestration = tmux + worktrees + MCP state machine | Accepted | Locked |
| [ADR-0005](ADR-0005-router-scoring-rubric.md) | Router scoring rubric — concreteness signals + threshold | Accepted | Locked |
| [ADR-0006](ADR-0006-mode-composition.md) | Mode composition + cancel cascade semantics | Accepted | Locked |
| [ADR-0007](ADR-0007-state-store-ownership.md) | State store ownership matrix | Accepted | Living |
| [ADR-0008](#adr-0008) | Plugin distribution migration — `omni_migrate_v1_to_v2.py` | Accepted | Locked |
| [ADR-0009](#adr-0009) | `.omni/config.json` schema versioning | Accepted | Living |
| [ADR-0010](ADR-0010-subagent-back-pressure.md) | Subagent back-pressure via file-lock semaphore | Accepted | Locked |
| [ADR-0011](#adr-0011) | deep-interview turn-based resume on Copilot CLI `-p` | Accepted | Living |

---

## One-line summaries

### ADR-0000 — Phase B Charter
Establishes the 8 locked decisions for Phase B, the scope boundary (Copilot CLI only, no
Claude Code), and the four missed-item defaults (ADR-0008 through ADR-0011).
**Companion:** `.omni/plans/phase-b-master-plan.md`.

### ADR-0001 — Copilot CLI only
No Claude Code primitives (`Task()`, `Skill()`, `AskUserQuestion`, `SendMessage`,
`TeamCreate`) survive in `skills/`, `agents/`, `scripts/`, or `hooks/`. The CI validator
check `no-claude-primitives` enforces this at every push.

### ADR-0002 — Skill deletions
**Deleted (7):** `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`,
`visual-verdict`, `writer-memory`. **Deferred (1):** `configure-notifications` → Phase C.
**Kept/rewritten (29).** Full rationale per skill in `.omni/plans/wave-1-WS2-report.md`.

### ADR-0003 — Model categories
Three semantic tiers — `quick`, `deep`, `ultrabrain` — resolve to concrete subscription
models at runtime via `scripts/category_resolver.py`. Hardcoded model names in skill or
agent files are forbidden (CI check `no-raw-model-names`). Override in `.omni/config.json`.

### ADR-0004 — Team orchestration
Team = real tmux sessions + git worktrees + MCP state machine. Non-tmux subprocess fallback
is first-class on Linux/macOS/Windows. Windows native tmux gated behind
`OMNI_EXPERIMENTAL_TEAM=1`. State machine per worker: `created → running → done/failed`.

### ADR-0005 — Router scoring rubric
Concreteness signals (file refs, code blocks, error keywords, etc.) summed to a score in
[-1.0, +1.0]. Default threshold 0.4: below → redirect to `deep-interview`; above → proceed.
`--skip-interview` adds +1.0 (always bypasses). Full signal table in `docs/ROUTER.md`.

### ADR-0006 — Mode composition
Typed mode-key registry: each autonomous mode (`autopilot`, `ralph`, `ultrawork`,
`ralplan`, `team`) exports a `MODE_KEY` constant. Nested modes write scoped sub-keys.
Cancel cascade: `cancel.signal` file in a run dir propagates to all children via
`--parent-run-id`. Full registry in `docs/STATE_MODES.md`.

### ADR-0007 — State store ownership
MCP server owns all persistent state. Scripts may read state via `state_read`; only the
MCP server writes to `omni.db`. Nine protected table/mode combinations enforced by CI
check `state-store-canonical`. Full ownership matrix in `docs/STATE_MODES.md`.

### ADR-0008 — Plugin distribution migration
`scripts/omni_migrate_v1_to_v2.py` is the canonical v1→v2 migration tool. Renames `.omc/`
to `.omni/` in repo root and `~/.omc/` in user home. Idempotent. `--dry-run` default,
`--apply` to execute. Never modifies user dotfiles; prints env-var guidance only.

### ADR-0009 — Config schema versioning
`.omni/config.json` has a top-level `schema_version` integer. `omni doctor` rewrites
missing/stale keys, warns on unknown keys, never silently drops. Plugin upgrades ship a
scripted `migrate_config_v1_to_v2()` for breaking schema changes.

### ADR-0010 — Subagent back-pressure
File-lock semaphore in `scripts/subagent.py` caps concurrent subagent spawns at
`min(8, os.cpu_count())`. Overridable via `.omni/config.json > runtime.max_parallel_subagents`.
New spawns **block** (not fail) when cap is reached. Per-subagent memory policing deferred
to Phase C.

### ADR-0011 — deep-interview turn-based resume
On Copilot CLI `-p` mode, deep-interview cannot block for synchronous input. Instead:
questions are emitted in the response; control returns to the CLI; next user turn carries
answers. State persisted to `.omni/specs/deep-interview-<slug>.md` and resumed on next
turn. Documented in `docs/ROUTER.md`.
