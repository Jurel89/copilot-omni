# omni team on Windows (Phase-C C12)

`/omni team` and `scripts/omni_team.py` are built around tmux panes. tmux
is POSIX-only, so on Windows the default path is **the subprocess worker
host** — workers run detached with no multiplexer UI.

## Decision tree

```
tmux on PATH? ──── yes ──▶ _TmuxSession (panes UX)
        │                       │
        no                      └── OMNI_EXPERIMENTAL_TEAM=1 required on Windows
        │
        ▼
_SubprocessWorkerHost  (no panes, status.json + worker logs only)
```

## Running without tmux

```
# explicit — skip tmux even if present
python3 scripts/omni_team.py run --use-tmux=false …
```

Artifacts remain identical: each worker writes its `status.json`,
`stdout.log`, and `stderr.log` under `.omni/runs/team-<id>/<worker-id>/`.

## Running WITH tmux on Windows

Tmux binaries ship in WSL, Cygwin, Git-Bash's MSYS environment, and
MSYS2. Any of these on PATH is enough:

```
set OMNI_EXPERIMENTAL_TEAM=1
python3 scripts/omni_team.py run --use-tmux=true …
```

OMNI_EXPERIMENTAL_TEAM is required because tmux pane semantics on
Windows depend on the terminal host (ConEmu, Windows Terminal, wezterm)
and can drop ANSI escape sequences or mangle resize events. We keep the
gate until the Windows CI lane (C11) has a green tmux run.

## Alternative multiplexers on Windows

If tmux feels wrong on nt, these produce a similar experience:

| Tool | Pattern | Notes |
|---|---|---|
| **Windows Terminal** | `wt -w 0 new-tab --title worker-<n> pwsh -c <cmd>` | Each worker lands in its own tab; closest to the tmux UX |
| **wezterm CLI** | `wezterm cli spawn --cwd <dir> -- <cmd>` | Panels instead of tabs; windowed or tiled |
| **ConEmu `-runTab`** | `ConEmuC.exe -GuiMacro print("..."); tab("...")` | Power-user friendly; not default-install |

The `omni_team.py` code does NOT wrap these — they are documented
escape hatches for users who want a panel UX without running tmux under
WSL. If you automate one of them, add a focused test and update the
"Platform-dispatched sites" table in `docs/PORTABILITY-AUDIT.md`.

## Removing the gate

`OMNI_EXPERIMENTAL_TEAM=1` will stay the required flag until:

1. The Windows CI lane (C11) runs a green tmux-mode job for at least two
   consecutive weeks.
2. `docs/PORTABILITY-AUDIT.md` adds a confirmed entry under "current
   unit coverage" for tmux panes on nt.

Once both are true the gate can be dropped in a single commit and the
error message above reduces to "tmux not found on PATH".
