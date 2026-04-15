# Migrating from Copilot Omni v0.1.0 (Go) to v1.0.0 (Python)

v1.0.0 is a **clean break**. There is no in-place upgrade. This is intentional: the v0.1.0 runtime was built on Go binaries (`omni-sidecar`, `omni`) that corporate EDRs quarantined as unsigned executables. v1.0.0 eliminates all compiled binaries.

## What changed

| v0.1.0 | v1.0.0 |
|--------|--------|
| Go `omni-sidecar` binary | `python3 mcp/server.py` (stdlib only) |
| Go `omni` wrapper binary | `python3 scripts/omni.py` (stdlib only) |
| `plugin/plugin.json` | `.claude-plugin/plugin.json` (Copilot-discoverable path) |
| `plugin/.mcp.json` | `.mcp.json` at repo root |
| `plugin/hooks.json` (inline bash) | `hooks/hooks.json` + `hooks/*.py` |
| 5 agents, 8 skills | 19 agents, 37 skills |
| SQLite in Go `modernc.org/sqlite` | SQLite via Python stdlib `sqlite3` |
| `go build` to install | `git clone`, done |

## Migrating your project data

If you had `.omni/runs/*/` artifacts from v0.1.0, they still work — the artifact layout is unchanged (JSON and Markdown). The MCP tool names changed (dropped `omni_` prefix); update any custom scripts that called them:

| v0.1.0 MCP tool | v1.0.0 MCP tool |
|-----------------|-----------------|
| `omni_health` | `health` |
| `omni_doctor` | `doctor` |
| `omni_artifact_write` | `artifact_write` |
| `omni_artifact_read` | `artifact_read` |
| `omni_run_status` | `run_status` |
| `omni_resume_context` | `resume_context` |
| `omni_memory_capture` | `memory_capture` |
| `omni_memory_search` | `memory_search` |
| `omni_policy_check` | `policy_check` |
| `omni_support_bundle` | `support_bundle` |
| *(v1.0.0-new)* | `wiki_*`, `notepad_*`, `state_*`, `shared_memory_*`, `trace_*`, `session_search` |

## Removed features

- **Signed release bundles + SBOM** — we don't ship binaries anymore, so there's nothing to sign. Provenance is the git tag.
- **`omni_guarded_patch`** — Copilot's native edit tool + the `preToolUse` policy hook cover this.
- **`omni_release_bundle`** — no binary releases.
- **`omni_benchmark`** — postponed to v1.1.
- **`omni_enterprise_diagnose`** — superseded by `doctor` + `support_bundle`.

## Uninstalling v0.1.0 before installing v1.0.0

```bash
# Remove old binaries if you compiled them
rm -f /usr/local/bin/omni /usr/local/bin/omni-sidecar

# Uninstall old plugin
copilot plugin uninstall copilot-omni || true

# Install v1.0.0
copilot plugin install Jurel89/copilot-omni
```

Your per-project `.omni/` directories are forward-compatible and need no changes.
