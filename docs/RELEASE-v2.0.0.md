# Release — v2.0.0

## Summary

v2.0.0 is a breaking release that re-targets copilot-omni as a Copilot-CLI-native
multi-agent orchestration platform. The Go sidecar runtime is gone. Every runtime
component is Python 3.9 stdlib or Markdown. A front-door intent router, semantic model
categories, real team orchestration (tmux + git worktrees), MCP-backed state, and a
17-check contract validator were added across three waves of Phase B. ~520 tests enforce
the new invariants.

---

## Breaking-change highlights

1. **`.omc/` → `.omni/`** — per-project and user-home state directory renamed.
   Run `python3 scripts/omni_migrate_v1_to_v2.py --apply` before first use.
2. **`/oh-my-claudecode:*` → `/copilot-omni:*`** — all slash-command namespaces changed.
   Update saved macros and scripts.
3. **`OMC_SKIP_HOOKS` / `DISABLE_OMC` deprecated** — use `OMNI_SKIP_HOOKS` /
   `DISABLE_OMNI`. Aliases work through v2.x; removed in v3.0.0.
4. **7 skills deleted** (ADR-0002) — `ccg`, `learner`, `project-session-manager`,
   `sciomc`, `self-improve`, `visual-verdict`, `writer-memory`.
5. **MCP surface shrank from 30 → 20 tools** — `subtask` and `workspace` removed;
   use `state_write` + team orchestration instead.

See [docs/MIGRATION.md](MIGRATION.md) for the complete upgrade path.

---

## Feature highlights

- **Front-door intent router** — concreteness-scored prompt classifier (ADR-0005).
  Vague prompts → `deep-interview`; concrete prompts proceed; `--skip-interview` bypasses.
- **Semantic model categories** — `quick`, `deep`, `ultrabrain` resolve at runtime
  (ADR-0003). No hardcoded model names in skill/agent code (CI-enforced).
- **Autonomous pipeline modes** — `autopilot`, `ralph`, `ultrawork`, `ultraqa`, `ralplan`
  with typed mode-key registry and cancel-cascade semantics (ADR-0006).
- **Team orchestration** — real tmux + git-worktree parallelism with MCP state machine
  per worker. Subprocess fallback for non-tmux environments.
- **MCP-backed state** — 20 tools, schema-validated `tools/call`, WAL-mode SQLite,
  `UNIQUE(mode, session_id)` constraint.
- **17-check contract validator** — `scripts/verify_plugin_contract.py --all` is the
  merge gate. Checks rename hygiene, primitive absence, mode-key registry, cancel-signal
  pairing, worktree hygiene, and more.
- **Subagent back-pressure** — file-lock semaphore, default cap `min(8, cpu_count())`,
  configurable, blocks instead of fails (ADR-0010).
- **Hook hardening** — atomic audit logging, 5 kill-switch env vars, per-hook switches,
  session-start banner, policy permission checks, metrics writer.
- **v1 → v2 migration script** — `scripts/omni_migrate_v1_to_v2.py`, idempotent,
  dry-run by default.
- **~520 tests** — unit, integration, MCP-smoke, discovery-smoke, coverage gates.

---

## Upgrade path

See [docs/MIGRATION.md](MIGRATION.md) for the step-by-step guide including:
- Quick-migrate commands
- Directory rename details
- Env-var update checklist
- Slash-command rename table
- Skill deletion table with alternatives
- Agent frontmatter update
- MCP tool changes

---

## Known limitations

- **Windows support is experimental.** Team orchestration on Windows requires
  `OMNI_EXPERIMENTAL_TEAM=1`. Full Windows hardening is Phase-C.
  See [docs/PHASE-C-BACKLOG.md](PHASE-C-BACKLOG.md).
- **Real-Copilot nightly CI** is not yet wired (requires a Copilot subscription in CI).
  The `copilot-smoke` job is best-effort / continue-on-error.
- **deep-interview redesign** deferred to Phase C. v2.0.0 ships turn-based persistence
  only (ADR-0011).
- **`configure-notifications` skill** deferred to Phase C.
- **Full Phase-C backlog** — see [docs/PHASE-C-BACKLOG.md](PHASE-C-BACKLOG.md).

---

## Required CI checks before tagging v2.0.0

All of the following matrix cells must be green on `phase-b/main` before the tag is
created. Use `python3 scripts/release_preflight.py` to verify locally.

| Check | Matrix | Required |
|-------|--------|----------|
| `lint` (contract validator + JSON manifests + no-Go files) | ubuntu × py 3.9 / 3.10 / 3.11 / 3.12 | Yes |
| `unit-tests` | ubuntu × py 3.9 / 3.10 / 3.11 / 3.12 | Yes |
| `mcp-smoke` | ubuntu × py 3.9 | Yes |
| `discovery-smoke` | ubuntu × py 3.9 | Yes |
| `coverage` (per-module gate) | ubuntu × py 3.11 | Yes |
| `release-gate` (validator + pytest + coverage + mcp-smoke) | ubuntu × py 3.11 | Yes |
| `copilot-smoke` | ubuntu × py 3.9 | Best-effort (continue-on-error) |

**Branch-protection note:** Enable "Require status checks to pass before merging" for
`main` in GitHub Settings → Branches, with the following checks required:
`lint`, `unit-tests (3.9)`, `unit-tests (3.10)`, `unit-tests (3.11)`,
`unit-tests (3.12)`, `mcp-smoke`, `discovery-smoke`, `coverage`, `release-gate`.
(Admin UI only — not configurable from code.)

---

## Post-tag checklist

- [ ] `git tag -s v2.0.0 -m 'v2.0.0 release'` (user approval required)
- [ ] `git push origin v2.0.0` (user approval required)
- [ ] Merge `phase-b/main` → `main` (user approval required)
- [ ] Update `README.md` badge from `version-2.0.0` to latest (auto on push)
- [ ] Submit to Copilot CLI plugin registry (if available)
- [ ] Post release announcement (Discord / Slack / GitHub Discussions)
- [ ] Open Phase-C milestone in GitHub Issues and link [docs/PHASE-C-BACKLOG.md](PHASE-C-BACKLOG.md)
