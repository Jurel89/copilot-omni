# Changelog

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
- 37 skills (up from 8): autopilot, ralph, ultrawork, team, ralplan, plan, deep-interview, deep-dive, verify, ultraqa, debug, trace, remember, wiki, external-context, ask, ccg, ai-slop-cleaner, sciomni, skill, skillify, learner, self-improve, setup, omni-setup, omni-doctor, mcp-setup, release, cancel, deepinit, configure-notifications, hud, visual-verdict, omni-reference, omni-teams, writer-memory, project-session-manager.
- 19 agents (up from 5): analyst, architect, planner, critic, executor, explore, debugger, tracer, verifier, qa-tester, test-engineer, code-reviewer, security-reviewer, code-simplifier, document-specialist, writer, git-master, designer, scientist.
- 8 slash commands: `/omni-init`, `/omni-doctor`, `/omni-status`, `/omni-list`, `/omni-plan`, `/omni-ship`, `/omni-verify`, `/omni-memory`.
- 30 MCP tools across memory, artifacts, runs, policy, wiki, notepad, state, shared_memory, trace, session_search, subtask, workspace, health, doctor, config_resolve, support_bundle.
- 4 lifecycle hooks as pure Python scripts.
- Three-profile policy engine: `strict`, `standard`, `permissive`.
- Windows, macOS, and Linux CI matrix on Python 3.9 / 3.11 / 3.12.

### Removed
- Go sidecar and wrapper binaries (CrowdStrike EDR incompatibility).
- Signed release bundle / SBOM machinery (no binaries → nothing to sign).
- `omni_guarded_patch`, `omni_release_bundle`, `omni_benchmark`, `omni_enterprise_diagnose` MCP tools — folded into native Copilot tools or postponed to v1.1.

## [0.1.0] — 2026-04-15

Initial release with Go sidecar runtime. Superseded by v1.0.0 because of EDR incompatibility.
