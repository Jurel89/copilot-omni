# Installing Copilot Omni

This plugin is designed to install cleanly on locked-down corporate machines. It has **no compiled binaries** and **no third-party Python dependencies**.

## Prerequisites

| Requirement | Minimum | How to verify |
|-------------|---------|---------------|
| Python | 3.9 | `python3 --version` |
| GitHub Copilot CLI | any | `copilot --version` |
| git | any recent | `git --version` |

Python 3.9 ships with RHEL 8 (`dnf install python39`), Ubuntu 20.04+, macOS 12+, and Windows 10+ (via the Microsoft Store app or `python.org` installer — neither requires admin).

## Install path A — marketplace (recommended, forward-compatible)

```bash
copilot plugin marketplace add https://github.com/Jurel89/copilot-omni
copilot plugin install copilot-omni@copilot-omni
```

The first command registers the repository as a marketplace; the second installs the
`copilot-omni` plugin from it. This is the syntax the Copilot CLI is moving to — direct
`owner/repo` installs now emit a deprecation warning and will be removed in a future
release. Copilot reads `plugin.json` at the repository root and wires up skills,
agents, the session-start hook, and the MCP server automatically.

## Install path B — local clone

```bash
git clone https://github.com/Jurel89/copilot-omni.git
copilot plugin install ./copilot-omni
```

Useful when your organization mirrors the repo internally and blocks direct GitHub plugin installs. Local-path installs are still supported alongside the marketplace flow.

## Install path C — plugin-dir (no install)

```bash
git clone https://github.com/Jurel89/copilot-omni.git
copilot --plugin-dir ./copilot-omni -p "list all skills" --allow-all
```

Zero state in `~/.copilot`. Great for trial runs or air-gapped evaluation.

## Install path D — air-gapped

1. On an internet-connected machine, `git clone --depth=1 https://github.com/Jurel89/copilot-omni.git`, then `tar czf copilot-omni.tgz copilot-omni/`.
2. Transfer the tarball through your approved channel.
3. Extract, then either:
   - `copilot plugin install /path/to/copilot-omni` (local path — still supported), or
   - `copilot plugin marketplace add /path/to/copilot-omni` then `copilot plugin install copilot-omni@copilot-omni` (marketplace, forward-compatible).

No external downloads happen during install — the MCP server and all skills are vendored as source files.

## Install path E — legacy direct install (DEPRECATED)

```bash
copilot plugin install Jurel89/copilot-omni   # emits a deprecation warning
```

Supported for now but slated for removal by Copilot CLI. Prefer path A.

## Windows one-time calibration

Corporate Windows installs commonly ship `py` and/or `python` but not `python3`, which
causes the MCP server to fail with `-32000 connection closed`. After installing the plugin,
run the calibration command once so `.mcp.json` and `hooks\hooks.json` reference your
actual interpreter:

```cmd
:: from the plugin directory
scripts\omni.cmd doctor --fix-python --fix-python-apply
```

`doctor --fix-python` is idempotent and a dry-run by default; add `--fix-python-apply`
to persist the change. Re-run after a plugin upgrade if MCP starts failing again.

## Verify the install

```bash
python3 scripts/omni.py doctor
```

Expected output: `OK` on every line, plus `skills: 27`, `agents: 19`, `commands: 10`, `mcp tools: 20`.

```bash
copilot -p "list available skills" --allow-all
# should list autopilot, ralph, plan, team, ...
```

## Corporate EDR notes

- `file mcp/server.py` reports `ASCII text`. There is no ELF/PE signature for an EDR to match.
- The plugin invokes `python3` for all hooks and the MCP server. Ensure `python3` is on your corporate allow-list (it typically is).
- The SQLite state file lives at `$OMNI_HOME/omni.db` (default `~/.omni/omni.db`). You can relocate it by setting `OMNI_HOME`.

## Uninstall

```bash
copilot plugin uninstall copilot-omni
rm -rf ~/.omni      # clears memory/wiki/notepad/state if you want a clean slate
```
