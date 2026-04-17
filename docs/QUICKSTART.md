# Quickstart

Zero-to-running in about a minute.

## 1. Prerequisites

| Tool | Minimum | Check |
|---|---|---|
| Python | 3.9 | `python3 --version` |
| GitHub Copilot CLI | any | `copilot --version` |
| git | any recent | `git --version` |

Python 3.9 is available out-of-the-box on RHEL 8+, Ubuntu 20.04+, macOS 12+, and Windows 10+
(neither the Microsoft Store Python nor the `python.org` installer require admin rights).

## 2. Install the plugin

```bash
copilot plugin marketplace add https://github.com/Jurel89/copilot-omni
copilot plugin install copilot-omni@copilot-omni
```

The marketplace flow is the forward-compatible path — Copilot CLI is deprecating direct
`owner/repo` installs. Prefer a local clone or air-gapped path? See
[INSTALL.md](INSTALL.md) for all five supported install paths.

## 3. (Windows only) Calibrate the Python interpreter

If you're on a corporate Windows box where `python3` isn't on `PATH`, run this once
so the MCP server + hooks spawn against `py` / `python` instead:

```cmd
scripts\omni.cmd doctor --fix-python --fix-python-apply
```

Idempotent; no-op when already calibrated. Skip on POSIX.

## 4. Verify the environment

```bash
python3 scripts/omni.py doctor
```

Expect `OK` on every line, with `skills: 30`, `agents: 19`, `commands: 10`, `mcp tools: 20`.

If `doctor` flags a missing hook file, policy directory, or MCP binding, open an
issue with the redacted output — it is the most useful single diagnostic we have.

## 5. Scaffold your project

```bash
python3 scripts/omni.py init
```

Creates `.omni/` in the current directory with:

- `.omni/config.json` — category overrides, back-pressure cap, policy profile.
- `.omni/plans/`       — plans produced by the `plan` / `ralplan` skills.
- `.omni/runs/`        — per-run artifacts (gitignored by default).
- `.omni/audit/`       — atomic append-only tool audit log (gitignored).

## 6. Your first Copilot Omni command

Let the front-door [router](ROUTER.md) decide:

```bash
copilot -p "autopilot build a habit-tracker CLI with streaks" --allow-all
```

Because the prompt scores concrete (anchors + verbs + constraints), `autopilot`
fires directly. A vague prompt like `"autopilot build me something cool"` would
auto-redirect through `deep-interview` until the spec is sharp enough.

Known exactly what you want? Bypass the gate:

```bash
copilot -p "autopilot refactor scripts/router.py to use dataclasses --skip-interview" --allow-all
```

## 7. Run work in parallel

```bash
copilot -p "team run wave-3 plan" --allow-all
```

`team` creates one git worktree per worker and (on POSIX) attaches them to a
tmux session with one pane each. Windows hosts use the subprocess worker host
fallback (no multiplexer UI — set `OMNI_EXPERIMENTAL_TEAM=1` to opt into native
tmux when available). See [TEAM.md](TEAM.md) and [TEAM-WINDOWS.md](TEAM-WINDOWS.md).

## 8. Cancel anything, cleanly

```bash
copilot -p "cancel" --allow-all        # via the cancel skill
# or
python3 scripts/omni.py cancel <run-id>
```

Cancel cascades through nested pipelines via the `--parent-run-id` thread, so
cancelling a `ralplan` inside an `autopilot` stops both without leaving
orphan worktrees.

## Next steps

- Browse the [skill catalog](SKILLS.md) or run `omni list skills`.
- Read the [architecture](ARCHITECTURE.md) to see how hooks, router, MCP, and
  subagents fit together.
- Tune your [policy profile](../policies/) — `strict`, `standard`, or `permissive`.
- Upgrading from v1.x? Start at [MIGRATION.md](MIGRATION.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| MCP fails with `-32000 connection closed` (Windows) | `python3` not on `PATH` | `scripts\omni.cmd doctor --fix-python --fix-python-apply` |
| `doctor` reports MCP unhealthy | `python3` not on `PATH` or blocked by policy | `which python3` → fix PATH / allow-list, or run `--fix-python` |
| Prompt always redirects to `deep-interview` | Prompt score < 0.4 | Add anchors (file paths, function names) or use `--skip-interview` |
| `team` falls back to subprocess on Linux | `tmux` not on `PATH` | `apt install tmux` / `brew install tmux` |
| Hooks silently stop running | Kill-switch env var set | `env | grep OMNI_SKIP` and unset |
| `.omni/runs/` fills the working tree | Normal — it's runtime state | `.omni/runs/` is gitignored; purge with `python3 scripts/omni.py clean --runs` |
