# Changelog

## [Unreleased] — v2.1.0 Copilot-CLI-native cleanup

### Fixed

- **MCP `-32000 Connection closed` on fresh installs** — `.mcp.json` `args` now ships a relative path (`mcp/server.py`) instead of `${COPILOT_PLUGIN_ROOT}/mcp/server.py`. Copilot CLI does **not** interpolate `${VAR}` tokens inside the MCP `args` array — it forwards them verbatim — which caused the child to spawn with a literal `${COPILOT_PLUGIN_ROOT}` path segment and exit before speaking JSON-RPC. Copilot CLI sets cwd to the plugin root, so a relative path resolves correctly. (Regression guarded by `TestShippedConfigShape.test_mcp_args_is_a_relative_path`.)
- **`spawn pwsh.exe ENOENT` on every tool call** — `hooks/hooks.json` no longer ships a `powershell` key. Copilot CLI hard-codes PowerShell Core (`pwsh.exe`) for that field and never falls back to Windows PowerShell 5.1 (`powershell.exe`), so shipping a `powershell` entry made every `preToolUse` fire fail on corporate Windows boxes that only have 5.1. The `bash` entry remains, and Copilot CLI uses it cross-shell. (Regression guarded by `TestShippedConfigShape.test_hooks_do_not_ship_powershell_key`.)
- **Windows Python stub** — `py` launcher now preferred over bare `python3` on Windows; fallback chain handles missing interpreters gracefully.

### Removed

- **`.claude-plugin/` directory** — legacy plugin root directory deleted; `OMNI_PLUGIN_ROOT` is the sole root reference going forward.
- **Router and model-category availability checks** — `scripts/router.py` front-door intent router and `scripts/category_resolver.py` model-category resolver removed. Model selection is now owned entirely by the Copilot CLI host via the `/model` slash command.
- **`docs/MODELS.md` and `docs/ROUTER.md`** — dead reference docs deleted; superseded by Copilot CLI native model management.

### Changed

- **Hooks reduced to `sessionStart`** — `preToolUse`, `postToolUse`, and `stop` hooks removed from default hook set; only `sessionStart` is registered out of the box.
- **Agent frontmatter normalized** — `model: claude-*` and `category: quick|deep|ultrabrain` frontmatter fields removed from all agent files; model selection delegated to Copilot CLI host.
- **`CLAUDE_PLUGIN_ROOT` removed** — all remaining references in `skills/` and `docs/` replaced with `OMNI_PLUGIN_ROOT`. Legacy fallback alias dropped.
- **ADR-0003 superseded** — model-category contract marked superseded; `category_resolver` retained as thin passthrough for backward compatibility only.

## [2.0.0] — 2026-04-16

> **Breaking release.** See [docs/MIGRATION.md](docs/MIGRATION.md) for the full upgrade guide.

### Breaking

- **`.omc/` → `.omni/`** — state directory renamed. Run `python3 scripts/omni_migrate_v1_to_v2.py --apply` to migrate.
- **`/oh-my-claudecode:*` → `/copilot-omni:*`** — all slash-command namespaces changed. Update any saved macros or scripts.
- **`OMC_SKIP_HOOKS` / `DISABLE_OMC`** — renamed to `OMNI_SKIP_HOOKS` / `DISABLE_OMNI`. Aliases still work through v2.x; removed in v3.0.0.
- **7 skills deleted** (ADR-0002): `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory`. Git history retains them.
- **`configure-notifications` deferred** — moved to `.omni/deferred/configure-notifications/`. Retrievable from git. Phase-C.
- **`CLAUDE.md` deleted** — `AGENTS.md` is the sole agent entrypoint.
- **`CLAUDE_PLUGIN_ROOT` → `COPILOT_PLUGIN_ROOT`** — env-var used in skill bodies updated.
- **MCP tool surface shrank from 30 → 20** — removed `subtask`, `workspace`, `memory_prune`, and several legacy helpers. `run_status` and `artifact_write` were also marked UNUSED-OUTSIDE-TESTS and are removed in Phase-C C23; `state_*` is the supported orchestration API. (Phase-C C17/C18/C24 subsequently re-introduced `memory_prune`, `notepad_prune`, `wiki_ingest`, `wiki_graph`, and `lsp_*` / `ast_grep_*` — net surface at end of Phase C is 27 tools.)
- **`model: claude-*`** frontmatter dropped — use `category: quick|deep|ultrabrain` in agent files.

### Added — Wave 1: rename + decontamination (WS1, WS2, WS9)

- Brand rename sweep: all `oh-my-claudecode`/`omc-*`/`.omc/` references replaced. CI validator enforces zero residual hits.
- `scripts/verify_plugin_contract.py` — 17-check contract validator; CI merge gate.
- `scripts/omni_migrate_v1_to_v2.py` — safe, idempotent v1 → v2 migrator. `--dry-run` default, `--apply` to execute.
- All 29 surviving skills decontaminated of Claude-Code primitives (`Task()`, `Skill()`, `AskUserQuestion`, `SendMessage`, `TeamCreate`).

### Added — Wave 2: router + models + MCP + pipeline (WS3–WS5d)

- **Front-door intent router** (`scripts/router.py`, ADR-0005): concreteness scorer; `score < 0.4` redirects to `deep-interview`; `--skip-interview` bypasses.
- **Semantic model categories** (`scripts/category_resolver.py`, ADR-0003): `quick|deep|ultrabrain` resolved at runtime. Overridable in `.omni/config.json`.
- **MCP server rewrite** (`mcp/server.py`): 20 tools, schema-validated `tools/call`, WAL-mode SQLite, `UNIQUE(mode, session_id)` constraint, exception message sanitisation.
- **Autonomous pipeline modes**: `autopilot`, `ralph`, `ultrawork`, `ultraqa`, `ralplan` rebuilt with typed mode-key registry (ADR-0006) and cancel-cascade semantics.
- **Subagent back-pressure** (`scripts/subagent.py`, ADR-0010): file-lock semaphore, default cap `min(8, cpu_count())`, configurable via `.omni/config.json`.
- **Skill-as-agent dispatcher** (B1): `subagent.py` routes known skills via `/copilot-omni:<name>`, real agents via `--agent <name>`. No more silent fall-through.
- **FAKE-mode production guard** (T4/B2): `OMNI_FAKE=1` flag refused outside test environment; injection via stderr impossible.
- **Cancel cascade nesting** (B5): `--parent-run-id` threads outer cancel signal into nested ralplan workers.
- `docs/ROUTER.md`, `docs/MODELS.md`, `docs/STATE_MODES.md` — new reference docs.

### Added — Wave 3: team + hooks + tests (WS6, WS7, WS10)

- **Team orchestration** (`scripts/omni_team.py`): tmux + git-worktree parallelism; subprocess fallback; MCP state machine per worker; Windows experimental via `OMNI_EXPERIMENTAL_TEAM=1`.
- **Shared hook library** (`hooks/_hook_lib.py`): kill-switch logic, atomic audit append (`fcntl.flock` / `msvcrt.locking`), metrics writer, deprecation-warn helper.
- **Five kill-switch env vars**: `OMNI_SKIP_HOOKS`, `DISABLE_OMNI`, plus per-hook `OMNI_SKIP_PRE_TOOL_USE`, `OMNI_SKIP_POST_TOOL_USE`, `OMNI_SKIP_SESSION_START`, `OMNI_SKIP_USER_PROMPT_SUBMIT`.
- **Session-start banner** with tree-hash cache in `.omni/cache/banner.json`.
- **Frontmatter trigger hints**: `user_prompt_submit.py` builds trigger map from `triggers:` fields in every `skills/*/SKILL.md`; emits `<skill-trigger-hint>` on match.
- **Per-module coverage gate** (`scripts/measure_coverage.py`): `mcp/` ≥ 80 %, `hooks/` ≥ 70 %, `scripts/` ≥ 60 %.
- **~520 tests** (unit + integration + MCP-smoke + discovery-smoke + coverage).
- `docs/HOOK_CONTRACT.md`, `docs/TEST_STRATEGY.md`, `docs/TEAM.md` — new reference docs.

### Changed

- MCP tool surface: 30 → 22 tools (removed `subtask`, `workspace`, folded `memory_prune` into `notepad_prune`).
- Hooks gained kill-switch matrix (5 global + 4 per-hook vars); session banner cached.
- `scripts/subagent.py` now wraps every subprocess in `_subagent_wrapper.py` sidecar for reliable status reporting.
- `scripts/wait_for_jobs.py` exit codes formalised: 0 = all succeeded, 1 = job failure, 2 = config error.
- `scripts/parse_critic_verdict.py` strips trailing fenced code blocks before extracting VERDICT.
- `scripts/router_state.py` reads real MCP state (stub replaced, WS5d / B4).
- Policy files `strict.json` / `standard.json` / `permissive.json` permission-checked on session start.

### Removed

- 7 Claude-Code-only skills: `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory` (ADR-0002).
- `configure-notifications` deferred to Phase C.
- `CLAUDE.md` root file (sole entrypoint is `AGENTS.md`).
- Go sidecar / wrapper binaries (removed in v1.0.0; no regression).
- MCP tools `subtask`, `workspace` (use `state_write` + team orchestration instead).

### Deprecated

- `OMC_SKIP_HOOKS=1` — use `OMNI_SKIP_HOOKS=1`. **Removed in v3.0.0.** <!-- omni-rename-allow: OMC legacy env var names documented here -->
- `DISABLE_OMC=1` — use `DISABLE_OMNI=1`. **Removed in v3.0.0.**

### Fixed (Wave 2.x — 5 BLOCKERs + 9 TIER-2)

- **B1** Skill-as-agent dispatcher: known skills now routed via `/copilot-omni:<name>` not raw subshell.
- **B2** FAKE subprocess injection: `_build_cmd` no longer interpolates stderr into shell command.
- **B3** MCP connection-pool deadlock: `_pool_acquire` now releases on all exception paths.
- **B4** Router-state stub: `router_state.read_pipeline_state` reads real MCP; stub removed.
- **B5** Cancel cascade nesting: outer cancel propagates into nested ralplan via `--parent-run-id`.
- **T2** `UNIQUE(mode, session_id)` constraint added to MCP state table (schema migration v3).
- **T3** `_looks_sensitive` over-redaction tightened; benign messages no longer redacted.
- **T5** Pool double-release: `_spawn_foreground/background` use try-finally to guarantee semaphore release.
- **T6** `wait_for_jobs.py` exit codes formalised.
- **T7** Critic verdict fence-stripping: trailing fenced VERDICT block now parsed correctly.
- **T8** `ultrawork` cap-sanity guard rejects task count > pool cap at plan time.

### Security

- **MCP schema validation**: every `tools/call` payload validated against registered JSON schema; malformed payloads return a structured error, never execute.
- **Exception message sanitisation** (`mcp/server.py`): internal Python tracebacks are stripped; only a safe summary is returned to the caller.
- **FAKE-mode production guard**: `OMNI_FAKE=1` is refused unless `OMNI_TEST_ALLOW_FAKE=1` is also set; prevents test injection in production.
- **File-locked audit logging**: `.omni/audit/hooks.jsonl` written with `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows). Race condition (Phase-A finding 3.1) eliminated.
- **Over-permissive policy warning**: `session_start.py` emits `<policy-warning>` when any `policies/*.json` has mode > `0o644`.

---

## [1.1.0] — 2026-04-16 (WS1 rename sweep)

<!-- omni-rename-allow: changelog-entry -->
### Changed — rename/rebrand (non-breaking for users; breaking for direct `omc-*` skill invocations)

- **Brand rename sweep (WS1).** All internal references to the legacy `oh-my-claudecode` upstream and `omc-*`/`.omc/` path scheme have been replaced with `copilot-omni`/`omni-*`/`.omni/` respectively.
<!-- omni-rename-allow: changelog-entry -->
- Skill directories renamed: `omc-doctor` → `omni-doctor`, `omc-reference` → `omni-reference`, `omc-setup` → `omni-setup`, `omc-teams` → `omni-teams`, `sciomc` → `sciomni`.
- All slash-command references updated: `/copilot-omni:omni-*` replaces `/oh-my-claudecode:omc-*`.
- Runtime state path `.omc/` → `.omni/` (tracked plans/research stay in `.omni/`).

### Added

- **Kill-switch env vars.** All four lifecycle hooks (`session_start`, `pre_tool_use`, `post_tool_use`, `user_prompt_submit`) now honour:
  - `OMNI_SKIP_HOOKS=1` — primary kill-switch (new).
  - `DISABLE_OMNI=1` — alternate form (new).
  - `OMC_SKIP_HOOKS=1` — backward-compat alias (deprecated; removed in v3.0.0).
  - `DISABLE_OMC=1` — backward-compat alias (deprecated; removed in v3.0.0).
- **Rename verifier.** `python3 scripts/verify_plugin_contract.py --check-rename` walks the whole tree, strips code fences, respects the 5 allowlisted paths, and supports `omni-rename-allow` inline markers (cap ≤10).

## [1.0.0] — 2026-04-16

### Changed — breaking
- **Complete rewrite** from Go runtime to pure Python stdlib. No compiled binaries. No third-party dependencies.
- Plugin manifest moved to canonical `.claude-plugin/plugin.json`.
- MCP tool names dropped `omni_` prefix (e.g. `omni_health` → `health`).

### Added
- 27 skills: autopilot, ralph, ultrawork, team, ralplan, plan, deep-interview, deep-dive, verify, ultraqa, debug, trace, remember, wiki, external-context, ai-slop-cleaner, skill, skillify, setup, omni-setup, omni-doctor, mcp-setup, release, cancel, deepinit, configure-notifications, omni-reference.
- 19 agents (up from 5): analyst, architect, planner, critic, executor, explore, debugger, tracer, verifier, qa-tester, test-engineer, code-reviewer, security-reviewer, code-simplifier, document-specialist, writer, git-master, designer, scientist.
- Slash commands removed in v2.1.0 — use skills directly via Copilot CLI prompts.
- 28 MCP tools across memory, wiki, notepad, state, shared_memory, trace, policy, health, doctor, lsp, ast-grep.
- 1 lifecycle hook (`session_start`) as pure Python script.
- Three-profile policy engine: `strict`, `standard`, `permissive`.
- Windows, macOS, and Linux CI matrix on Python 3.9 / 3.11 / 3.12.

### Removed
- Go sidecar and wrapper binaries (CrowdStrike EDR incompatibility).
- Signed release bundle / SBOM machinery (no binaries → nothing to sign).
- `omni_guarded_patch`, `omni_release_bundle`, `omni_benchmark`, `omni_enterprise_diagnose` MCP tools — folded into native Copilot tools or postponed to v1.1.

## [0.1.0] — 2026-04-15

Initial release with Go sidecar runtime. Superseded by v1.0.0 because of EDR incompatibility.
