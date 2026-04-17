# Migration Guide

---

## Migrating from v1.x to v2.0.0

v2.0.0 is a **breaking release**. The changes are mechanical and a migration script handles
the most disruptive one (directory rename). Work through the checklist below top-to-bottom.

### Quick-migrate commands

```bash
# 1. Preview what the migrator will do
python3 scripts/omni_migrate_v1_to_v2.py --dry-run

# 2. Execute (renames .omc/ → .omni/ in repo and in ~/.omc/)
python3 scripts/omni_migrate_v1_to_v2.py --apply

# 3. Verify the plugin contract is still green
python3 scripts/verify_plugin_contract.py --all

# 4. Run tests
python3 -m pytest -q
```

---

### 1. Directory rename: `.omc/` → `.omni/`

**What changed:** The per-project state directory was `.omc/`; it is now `.omni/`.
The global user state was `~/.omc/`; it is now `~/.omni/`.

**Migration:** `scripts/omni_migrate_v1_to_v2.py` handles this automatically.

- `--dry-run` (default): prints what would move, makes no changes.
- `--apply`: executes `shutil.move()` (or `git mv` inside a git repo).
- Idempotent: if `.omni/` already exists at the target path, the script warns and skips.
- The script never touches `.bashrc`, `.zshrc`, or any user dotfile. It prints guidance
  for env-var updates instead.

If you prefer to rename manually:

```bash
# Per-project
git mv .omc .omni

# User home (outside git)
mv ~/.omc ~/.omni
```

---

### 2. Env-var renames

| v1.x var | v2.0.0 canonical | Removed in |
|----------|-----------------|-----------|
| `OMC_SKIP_HOOKS=1` | `OMNI_SKIP_HOOKS=1` | v3.0.0 |
| `DISABLE_OMC=1` | `DISABLE_OMNI=1` | v3.0.0 |

The old names still work in v2.x but emit a one-time deprecation warning to stderr.
Update your shell profile now to avoid the warning and to be ready for v3.0.0:

```bash
# In ~/.bashrc or ~/.zshrc — replace:
# export OMC_SKIP_HOOKS=1
# with:
export OMNI_SKIP_HOOKS=1

# And replace:
# export DISABLE_OMC=1
# with:
export DISABLE_OMNI=1
```

New per-hook kill switches (v2.0.0-only):
- `OMNI_SKIP_PRE_TOOL_USE=1`
- `OMNI_SKIP_POST_TOOL_USE=1`
- `OMNI_SKIP_SESSION_START=1`
- `OMNI_SKIP_USER_PROMPT_SUBMIT=1`

---

### 3. Slash-command rename

All slash-commands moved to the `copilot-omni` namespace.

| v1.x command | v2.0.0 command |
|-------------|----------------|
| `/oh-my-claudecode:omc-doctor` | `/copilot-omni:omni-doctor` |
| `/oh-my-claudecode:omc-setup` | `/copilot-omni:omni-setup` |
| `/oh-my-claudecode:omc-reference` | `/copilot-omni:omni-reference` |
| `/oh-my-claudecode:omc-teams` | *(deleted in v2.1 — see section 4b)* |
| `/oh-my-claudecode:autopilot` | `/copilot-omni:autopilot` |
| `/oh-my-claudecode:ralph` | `/copilot-omni:ralph` |
| `/oh-my-claudecode:team` | `/copilot-omni:team` |
| `/oh-my-claudecode:cancel` | `/copilot-omni:cancel` |

Update any saved macros, shell aliases, or documentation that reference the old namespace.

---

### 4. Skill deletions (ADR-0002)

Seven Claude-Code-only skills were deleted. If you relied on any, see the git history
(`git log --all --full-history -- skills/<name>/`) to retrieve the last version.

| Deleted skill | Reason | Alternative |
|---------------|--------|-------------|
| `ccg` | Violated decision 7 (no external CLIs: codex, gemini) | Use `deep` model category directly |
| `learner` | Paper-only; no Copilot surface | Use `wiki` + `remember` |
| `project-session-manager` | Claude-Code-worktree-specific | Use `omni team` (WS6 rebuild) |
| `sciomc` | Deepest brand contamination; Claude-specific orchestration | Use `sciomni` (clean rebuild) |
| `self-improve` | Claude tournament-selection loop; no Copilot surface | Use `autopilot` + `ralph` |
| `visual-verdict` | No vision primitive available in Copilot CLI | Deferred to Phase C |
| `writer-memory` | Deep brand contamination, low ROI | Use `remember` + `wiki` |

`configure-notifications` was deferred (not deleted) — it lives in
`.omni/deferred/configure-notifications/` and is retrievable from git history.

---

### 4b. Skills removed in v2.1 (April 2026)

Three additional skills shipped in v2.0 but violated the same ADR-0000 decisions
that drove the Phase-B cleanup. They were deleted in v2.1 because they only
surfaced runtime failures for users on Copilot-only corporate machines (no
Claude Code, no external AI CLIs installed) — exactly the audience the plugin
promises to serve.

| Deleted skill | Reason | Alternative |
|---------------|--------|-------------|
| `hud` | Violated decision 1 — configured Claude Code's `~/.claude/settings.json` `statusLine` and copied a wrapper to `~/.claude/hud/omni-hud.mjs`. Neither path exists in GitHub Copilot CLI. | None shipped. If Copilot CLI adds a statusline surface upstream, a Copilot-native skill can be proposed. |
| `ask` | Violated decision 7 — wrapped `omc ask <claude\|codex\|gemini>`, which spawns external AI CLI binaries. The wrapper failed on every corporate machine without those CLIs installed. | Use `copilot -p "..."` directly, or `python3 scripts/subagent.py <agent> "..."` for a specialist. |
| `omni-teams` | Violated decision 7 — spawned N tmux panes running `claude` / `codex` / `gemini` workers. | Use the surviving `team` skill (Copilot-native; `scripts/omni_team.py` remains, but only wired to the surviving `team` skill). |

Two follow-on cleanups landed alongside: the `plan` skill lost its
`--architect codex` / `--critic codex` delegation flags (dormant dead code
that only failed under load), and `scripts/router.py` lost its
`parallel (claude|codex|gemini)` scoring pattern (misleading in a Copilot-only
environment). `scripts/verify_plugin_contract.py --all` now includes
`--check-external-cli` to block reintroduction via PR.

The local integration test harness (`./scripts/itest` /
`pytest -m integration_local`) was added in the same cycle so future
corporate-machine bugs surface before landing rather than in production.

---

### 5. Agent model frontmatter

v1.x agent files used `model: claude-sonnet-4.5` or similar concrete model names.
v2.0.0 introduced semantic categories resolved at runtime.

> **SUPERSEDED — Note (v2.1.0):** The `category:` frontmatter is removed entirely in v2.1.0. Model selection is owned by the Copilot CLI host via `/model`. Agent frontmatter has no `category`, `level`, or `disallowedTools` fields. The table below is retained as historical record only.

| v1.x frontmatter | v2.0.0 frontmatter (historical) |
|-----------------|--------------------------------|
| `model: claude-haiku-4-5` | `category: quick` |
| `model: claude-sonnet-4.5` | `category: deep` |
| `model: claude-opus-4-6` | `category: ultrabrain` |

If you have custom agents that still carry `category:` frontmatter, remove it — the field is now ignored.

The `.omni/config.json` models block below was used in v2.0.0 and is also obsolete in v2.1.0:

```json
{
  "models": {
    "quick":      { "primary": "claude-haiku-4-5", "fallbacks": ["gpt-5-mini"] },
    "deep":       { "primary": "claude-sonnet-4.5", "fallbacks": ["gpt-5"] },
    "ultrabrain": { "primary": "claude-opus-4-6",  "fallbacks": ["gpt-5-codex"] }
  }
}
```

---

### 6. MCP tools — surface change (30 → 22)

Two tools were removed; use the equivalents below.

| Removed tool | v2.0.0 equivalent |
|-------------|-------------------|
| `subtask` | `state_write` + `scripts/subagent.py` |
| `workspace` | `scripts/omni_worktree.py` + team state |

All remaining tools now validate their input payload against a JSON schema.
Invalid `tools/call` requests return a structured error instead of silently failing.
See `docs/STATE_MODES.md` for the full tool inventory and ownership matrix.

---

### 7. What stayed the same

- `.omni/runs/<run-id>/` artifact layout (JSON + Markdown) — forward-compatible.
- MCP tool names (other than the 2 removed) — no changes.
- Policy files (`policies/strict.json`, `standard.json`, `permissive.json`) — unchanged.
- `python3 scripts/omni.py doctor` — still the first thing to run.
- `pytest` invocation — `python3 -m pytest -q` still runs the full suite.

---

## Migrating from v0.1.0 (Go runtime) to v1.0.0 (Python)

v1.0.0 was a clean break from the Go sidecar runtime. See below for reference if you are
upgrading from the original Go-based release.

### What changed (v0.1.0 → v1.0.0)

| v0.1.0 | v1.0.0 |
|--------|--------|
| Go `omni-sidecar` binary | `python3 mcp/server.py` (stdlib only) |
| Go `omni` wrapper binary | `python3 scripts/omni.py` (stdlib only) |
| `plugin/plugin.json` | `.claude-plugin/plugin.json` |
| `plugin/.mcp.json` | `.mcp.json` at repo root |
| `plugin/hooks.json` (inline bash) | `hooks/hooks.json` + `hooks/*.py` |
| 5 agents, 8 skills | 19 agents, 27 skills |
| SQLite via Go `modernc.org/sqlite` | SQLite via Python stdlib `sqlite3` |
| `go build` to install | `git clone`, done |

### MCP tool renames (v0.1.0 → v1.0.0)

| v0.1.0 tool | v1.0.0 tool |
|-------------|-------------|
| `omni_health` | `health` |
| `omni_doctor` | `doctor` |
| `omni_memory_capture` | `memory_capture` |
| `omni_memory_search` | `memory_search` |
| `omni_memory_prune` | `memory_prune` |
| `omni_policy_check` | `policy_check` |

### Removed in v1.0.0 / Phase-C

- **Signed release bundles + SBOM** — no binaries, so nothing to sign.
- **`omni_guarded_patch`** — covered by native Copilot edit + `preToolUse` policy hook.
- **`omni_release_bundle`**, **`omni_benchmark`**, **`omni_enterprise_diagnose`** — removed.
- **`artifact_write`**, **`artifact_read`**, **`run_status`** — filesystem is canonical store (ADR-0007).
- **`support_bundle`** — folded into `omni doctor`.
- **Slash commands** removed in v2.1.0 — use skills directly via Copilot CLI prompts.

### Uninstalling v0.1.0

```bash
rm -f /usr/local/bin/omni /usr/local/bin/omni-sidecar
copilot plugin uninstall copilot-omni || true
copilot plugin install Jurel89/copilot-omni
```
