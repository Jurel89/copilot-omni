# ADR-0000 — Phase B Charter

- **Status:** Accepted
- **Date:** 2026-04-16
- **Supersedes:** (none — first ADR for the project)
- **Reviewers:** critic `[phase-b-critique-critic.md]`, architect `[phase-b-critique-architect.md]`
- **Companion plan:** `.omni/plans/phase-b-master-plan.md` (v2, 15 workstreams)

## Context

`copilot-omni` v1.0.0 shipped as a "corporate-safe Python/Markdown" plugin derived from `oh-my-claudecode` (OMC). Phase-A research (`.omni/research/phase-a/`) confirmed the v1 codebase is a Claude-port with a thin Copilot harness: flagship skills still reference `Task()` / `Skill()` / `TeamCreate` / `AskUserQuestion`, state is split across `.omc/` and `.omni/`, the intent router is advisory regex, and `team` orchestration relies on Claude-native primitives. Phase B re-targets the plugin as a Copilot-CLI-native v2.0.0.

## Locked decisions

These eight decisions were confirmed by the user on 2026-04-16 and are **not** to be revisited during Phase B execution. Any workstream requiring a change to these decisions must escalate to the user before proceeding.

1. **Host = GitHub Copilot CLI only.** No Claude Code primitives. Where a skill currently relies on `Task()` / `Skill()` / `AskUserQuestion` / `SendMessage` / `TeamCreate`, the skill is rewritten or deleted. Claude Code coexistence is a non-goal.
2. **Architecture = OMC-style composable autonomous modes** (`autopilot`, `ralph`, `ultrawork`, `ralplan`, `team`, `deep-interview`, `plan`, `cancel`). Useful patterns cherry-picked from `oh-my-openagent` (OMOA, MIT). GSD's phase state machine is explicitly rejected.
3. **Front-door intent router.** Every user prompt is classified. Vague prompts auto-redirect to `deep-interview`. Bypass syntax = `--skip-interview` only (`!` prefix dropped per `[critic §7 #4]`).
4. **Directory + brand rename = mandatory.** `.omc/` → `.omni/` and `OMC` / `oh-my-claudecode` / `omc-*` → `omni` / `copilot-omni` / `omni-*` everywhere in `skills/`, `agents/`, `scripts/`, `hooks/`, `commands/`, `docs/`, `templates/`, `.github/`, `.claude-plugin/`, `.mcp.json`, `plugin.json`, `CHANGELOG.md`. A verification script fails CI on any residual hit.
5. **Team orchestration = real Copilot-native rebuild** (tmux + git worktrees + MCP state machine). Non-tmux subprocess fallback is first-class on Linux/macOS/Windows. Windows native tmux gated behind `OMNI_EXPERIMENTAL_TEAM=1`.
6. **Model selection = OMOA-style semantic categories** (`quick`, `deep`, `ultrabrain`). Resolve to concrete Copilot subscription models (Claude Sonnet / Opus, GPT-5.x, Gemini 2.x). User-overridable via `.omni/config.json`. Schema entries are `{model: str, fallbacks: [str]}` per `[critic §1 P9]`.
7. **External CLIs forbidden.** No `codex`, `gemini`, or other AI CLIs invoked. Stdlib-only, Copilot-only. CI enforces.
8. **deep-interview simplification = follow-up**, not in Phase B scope. Phase B only touches deep-interview for (a) `.omc → .omni` rename, (b) dropping `AskUserQuestion`, (c) router redirect contract, (d) turn-based persistence to `.omni/specs/deep-interview-<slug>.md` (ADR-0011).

## Missed-item defaults (locked as ADRs 0008–0011)

- **D1 — Plugin distribution migration.** Ship `scripts/omni_migrate_v1_to_v2.py` that runs on first load when `.omc/` exists. v2.0.0 is a breaking release. (ADR-0008.)
- **D2 — `.omni/config.json` schema versioning.** Harness-managed. Top-level `schema_version`. `omni doctor` rewrites missing/stale keys, warns on unknown keys, never silently drops. (ADR-0009.)
- **D3 — `subagent.py` back-pressure.** Semaphore-limited, default cap `min(8, os.cpu_count())`, overridable via `.omni/config.json > runtime.max_parallel_subagents`. Blocking (not failing) when cap reached. (ADR-0010.)
- **D4 — deep-interview on Copilot CLI `-p`.** Turn-based, not blocking. Questions emitted; control returned; next user turn carries answers. Spec persisted to `.omni/specs/deep-interview-<slug>.md`. (ADR-0011.)

## Scope: three remaining WS2/WS11 decisions

Resolved 2026-04-16 by user acceptance of defaults:

1. **WS2 DELETE roster.** `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory` will be deleted. (ADR-0002 forthcoming.)
2. **`configure-notifications`.** DEFER-TO-PHASE-C (moved to `.omni/deferred/configure-notifications/`, retrievable from git).
3. **`CLAUDE.md`.** Delete outright. `AGENTS.md` is the sole entrypoint.

## Out of scope (explicit non-goals for Phase B)

- Claude Code host support.
- Calls to external AI CLIs (`codex`, `gemini`, `ollama`).
- GSD-style phase state machine.
- Deep-interview algorithmic redesign (deferred to Phase C).
- Wiki / memory ingestion hooks, knowledge-graph features, LSP/AST-grep tools (Phase C).
- i18n / multi-language SKILL.md variants.
- Outbound network telemetry.

## Branch, tag, and rollback posture

- **Baseline tag:** `v1.0.0-pre-phase-b` on `main` (pre-execution snapshot; recovery anchor).
- **Long-lived branch:** `phase-b/main` off `main`. All wave branches merge here.
- **Wave branches:** `phase-b/wave-<N>/<ws-slug>`. One PR per workstream.
- **Merge to `main`:** forbidden until all waves complete and adversarial reviews approve.
- **Rollback:** wave-level via branch revert; v1 restorable via `git checkout v1.0.0-pre-phase-b`.

## Success signals (definition of done for Phase B → v2.0.0)

Enumerated verbatim in plan §9. Key hard gates:
- `scripts/verify_plugin_contract.py --all` exits 0.
- Whole-tree grep for banned tokens (`.omc/`, `oh-my-claudecode`, `Task(`, `Skill(`, `AskUserQuestion`, `TeamCreate`, `SendMessage`) returns 0 hits after stripping markdown code fences.
- `pytest -q` green on Linux / macOS / Windows (Windows e2e = manual smoke with `OMNI_EXPERIMENTAL_TEAM=1`).
- `OMNI_SKIP_HOOKS=1` verified to no-op all four hooks.
- Autopilot / ralph / ultrawork / ultraqa / ralplan e2e smokes green.
- Router regression harness (≥40 prompts, ≥8 near-threshold) green.
- Wave-0 `discovery_smoke.py --probe all` green (6 runtime contract assumptions verified).

## Record

This ADR is the canonical reference for Phase B decisions. Amendments require a new ADR that cites this one.
