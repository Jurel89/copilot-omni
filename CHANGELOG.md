# Changelog

## [1.0.0] — 2026-04-16

### Changed — breaking
- **Complete rewrite** from Go runtime to pure Python stdlib. No compiled binaries. No third-party dependencies.
- Plugin manifest moved to canonical `.claude-plugin/plugin.json`.
- MCP tool names dropped `omni_` prefix (e.g. `omni_health` → `health`).

### Added
- 37 skills (up from 8): autopilot, ralph, ultrawork, team, ralplan, plan, deep-interview, deep-dive, verify, ultraqa, debug, trace, remember, wiki, external-context, ask, ccg, ai-slop-cleaner, sciomc, skill, skillify, learner, self-improve, setup, omc-setup, omc-doctor, mcp-setup, release, cancel, deepinit, configure-notifications, hud, visual-verdict, omc-reference, omc-teams, writer-memory, project-session-manager.
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
