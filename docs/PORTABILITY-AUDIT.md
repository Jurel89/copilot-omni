# Cross-OS Portability Audit (Phase-C C13)

This document enumerates the Windows-vs-POSIX code paths in copilot-omni and
what each site does differently. It is maintained in-repo so regressions can
be caught at review time rather than by a Windows CI user.

## Platform-dispatched sites

| Site | File:line | POSIX path | Windows path |
|---|---|---|---|
| File locking (audit log) | `hooks/_hook_lib.py:~164` | `fcntl.flock(fh, LOCK_EX \| LOCK_NB)` | `msvcrt.locking(fd, LK_NBLCK, 1)` on a sidecar `.lock` file |
| File locking (subagent pool) | `scripts/subagent_pool.py:~26` | `fcntl.flock(fd, LOCK_EX)` | `msvcrt.locking(fd, LK_NBLCK, 1)` |
| Background detach | `scripts/subagent.py:_spawn_background` | `start_new_session=True` | `creationflags = DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP` (C02) |
| PID liveness probe | `scripts/subagent_pool.py:_is_pid_alive` | `os.kill(pid, 0)` | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess` (C02) |
| RSS reading | `scripts/subagent_pool.py:_rss_mb` | `/proc/<pid>/status` VmRSS | `GetProcessMemoryInfo` WorkingSetSize (C08/C26) |
| Atomic file replace | everywhere (uses `os.replace`) | posix rename(2) | Win32 MoveFileEx semantics (atomic within a volume) |
| Audit dir permissions | `hooks/_hook_lib.py:_ensure_dir(mode=0o700)` | `os.chmod(path, 0o700)` | ACL-inherited; chmod is best-effort (C04) |

## Path handling

- All path construction goes through `pathlib.Path`. No raw `str + "/" + str`.
- `os.path.normpath(path).replace("\\", "/")` is the canonical form used by
  the pre-tool-use hook when comparing against `protected_paths`. Both the
  candidate and the policy entry pass through `unicodedata.normalize("NFC", …)`
  (C05) so an NFD-decomposed path cannot bypass an NFC policy.
- `PATH` separator: nowhere do we split on `:` explicitly. Subprocess
  invocations rely on `shutil.which` which handles `;` on Windows.

## Process management

- Subprocess spawning is exclusively through `subprocess.Popen` / `run`.
- `shell=False` is the default and never overridden.
- Shebangs appear only in `scripts/omni` (the POSIX launcher). The Windows
  counterpart is `scripts/omni.cmd`. Both shims probe PATH in priority order
  and fail loudly when no Python 3 is found:
  - `scripts/omni.cmd`: `py -3` → `python` → `python3`
  - `scripts/omni`    : `python3` → `python` (with `sys.version_info` guard)
- Copilot CLI invokes `.mcp.json` and `hooks/hooks.json` directly, before any
  Python is running, so the `command` field cannot use `sys.executable`. On
  Windows corporate installs where `python3` is absent, run
  `scripts\omni.cmd doctor --fix-python --fix-python-apply` once after
  installation — it detects the current interpreter and rewrites both JSON
  files in place with the absolute interpreter path (idempotent).

## Known non-portabilities (documented, not fixed)

| Site | Reason |
|---|---|
| `scripts/omni_team.py` tmux panes | Tmux is POSIX-only; `OMNI_EXPERIMENTAL_TEAM=1` gate + documented `wezterm` / PowerShell fallback on Windows (C12) |
| `tests/test_pipeline_e2e_*` | Use `pytest` markers (`e2e`, `slow`, `tmux`) — `tmux` subset is gated on Linux/macOS |
| Linux-only signals | `SIGUSR1` /`SIGHUP` are not used anywhere in runtime code |

## How to add a new platform-dispatched path

1. Write both branches behind a `sys.platform == "win32"` check.
2. Update the "Platform-dispatched sites" table above.
3. Add a targeted test in `tests/test_portability.py` that runs on the
   current OS and skips the opposite branch with a `@unittest.skipUnless`
   guard.
4. If the behaviour is observable only under Windows, mark the test
   `windows` and rely on the Windows CI lane (C11) to exercise it.

## Current unit coverage

Runs as part of the default `pytest` invocation:

- `tests/test_portability.py`: asserts that critical path helpers (pathlib,
  os.replace, NFC normalisation, `_is_pid_alive`, `_rss_mb`) behave correctly
  on the current OS and that the Windows-only code paths do not import
  `fcntl`/`msvcrt` at module level.
- `tests/test_hooks_audit_logging.py` / `TestAuditDirPermissions`: POSIX
  perm enforcement (C04).
- `tests/test_subagent_windows_detach.py`: Windows creationflags + pid
  probe (C02), with POSIX asserting source-level branch presence.
- `tests/test_hooks.py::test_protected_path_unicode_nfd_is_normalised`:
  NFC/NFD path enforcement (C05).
