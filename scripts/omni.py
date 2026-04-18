#!/usr/bin/env python3
"""omni — Copilot Omni user-facing CLI.

Pure-Python, stdlib-only. Provides:
  omni init           Scaffold .omni/ in the current project
  omni doctor         Check environment (python, copilot CLI, MCP server)
  omni status         Show current run and mode state
  omni memory         Interact with the memory store (search, list, capture, prune, export)
  omni wiki           Inspect the persistent wiki store (list, show, search, graph, validate)
  omni state          Inspect persisted mode state
  omni notepad        Inspect persisted notes
  omni shared-memory  Inspect shared memory entries
  omni trace          Inspect stored traces
  omni codebase       Inspect the codebase graph and immediate refactor impact
  omni plugin-install Install the plugin into the local Copilot CLI
  omni mcp            Launch the MCP server in the foreground (stdio)
  omni version        Print version
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VERSION = "1.0.0"


def _plugin_root() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"omni {VERSION}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    py_ok = sys.version_info >= (3, 9)
    print(
        f"python:        {sys.version.split()[0]:<12} "
        + ("OK" if py_ok else "FAIL (need >=3.9)")
    )
    ok = ok and py_ok

    copilot = shutil.which("copilot")
    copilot_ok = copilot is not None
    print(
        f"copilot CLI:   {copilot or 'NOT FOUND':<40} "
        + ("OK" if copilot_ok else "FAIL (install @github/copilot or add to PATH)")
    )
    ok = ok and copilot_ok

    root = _plugin_root()
    manifest = root / "plugin.json"
    manifest_ok = manifest.exists()
    print(f"plugin.json:   {str(manifest):<40} " + ("OK" if manifest_ok else "FAIL"))
    ok = ok and manifest_ok

    mcp = root / "mcp" / "server.py"
    mcp_ok = mcp.exists()
    print(f"MCP server:    {str(mcp):<40} " + ("OK" if mcp_ok else "FAIL"))
    ok = ok and mcp_ok

    skills = (root / "skills").glob("*/SKILL.md")
    skills_count = sum(1 for _ in skills)
    print(f"skills:        {skills_count} " + ("OK" if skills_count >= 25 else "FAIL"))
    ok = ok and (skills_count >= 25)

    agents = list((root / "agents").glob("*.md"))
    print(f"agents:        {len(agents)} " + ("OK" if len(agents) >= 15 else "FAIL"))
    ok = ok and (len(agents) >= 15)

    print(f"platform:      {platform.system()} {platform.release()}")
    home = Path(os.environ.get("OMNI_HOME") or (Path.home() / ".omni"))
    print(f"omni_home:     {home}")
    home.mkdir(parents=True, exist_ok=True)

    strict = getattr(args, "strict", False)

    # WS5a: subagent pool state
    pool_ok = _doctor_subagent_pool(root, strict=strict)
    if strict and not pool_ok:
        ok = False

    # WS5a: recent runs summary
    _doctor_recent_runs(root)

    # WS5d: ralplan active runs + awaiting-input warning
    ralplan_ok = _doctor_ralplan_runs(root, strict=strict)
    if strict and not ralplan_ok:
        ok = False

    # WS6: active team runs + stale-team warning
    team_ok = _doctor_team_runs(root, strict=strict)
    if strict and not team_ok:
        ok = False

    # Phase-C C32: optional garbage-collection pass on .omni/runs/
    if getattr(args, "gc", False):
        _doctor_run_gc(root, apply_=getattr(args, "gc_apply", False))

    # Python-interpreter calibration (cross-OS). When requested, rewrite
    # `.mcp.json` and `hooks/hooks.json` so Copilot CLI spawns the Python the
    # user actually has — not a hardcoded `python3` that may not exist on
    # Windows corporate boxes. Dry-run by default; use --fix-python-apply to
    # persist.
    if getattr(args, "fix_python", False):
        fix_ok = _doctor_fix_python(
            root, apply_=getattr(args, "fix_python_apply", False)
        )
        if not fix_ok and getattr(args, "fix_python_apply", False):
            ok = False

    return 0 if ok else 1


def _doctor_fix_python(root: Path, *, apply_: bool) -> bool:
    """Calibrate `.mcp.json` + `hooks/hooks.json` to the current interpreter.

    Copilot CLI launches MCP servers and hooks by invoking the literal
    `command` string in each JSON. On Windows corporate installs the default
    `python3` often isn't on PATH (only `py` / `python` are), which surfaces
    as MCP error -32000 (connection closed). This helper rewrites the two
    config files so they use the exact interpreter currently running
    (`sys.executable`), making the plugin work on any machine that could
    already launch this script.

    Dry-run unless `apply_` is True. Idempotent: rewrites only when the
    current command does not resolve to an executable on the current PATH.
    Returns True on success (including when nothing needed fixing).
    """
    targets: list[tuple[Path, str, list[str]]] = [
        # (path, label, list of JSON-pointer-ish selectors for audit output)
        (root / ".mcp.json", ".mcp.json", ["$.mcpServers.*.command"]),
        (root / "hooks" / "hooks.json", "hooks/hooks.json", ["$.hooks.*[*].command"]),
    ]
    current = sys.executable
    print("")
    print(f"fix-python:    current interpreter -> {current}")
    print(
        "fix-python:    mode               -> "
        + ("APPLY (in-place rewrite)" if apply_ else "DRY-RUN")
    )

    all_ok = True
    for path, label, _selectors in targets:
        if not path.exists():
            print(f"fix-python:    {label}: NOT FOUND — skipping")
            continue
        try:
            orig_text = path.read_text(encoding="utf-8")
            data = json.loads(orig_text)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"fix-python:    {label}: FAIL to read/parse — {exc}")
            all_ok = False
            continue

        changed, data = _rewrite_python_in_config(data, current)
        # Also expand ${OMNI_PLUGIN_ROOT} / ${CLAUDE_PLUGIN_ROOT} to the
        # absolute plugin root so the spawn argv is self-contained even if
        # Copilot CLI (or the user's shell) does not set that variable.
        changed += _expand_plugin_root_vars(data, plugin_root=root)
        if not changed:
            print(f"fix-python:    {label}: already calibrated — no change")
            continue

        preview = json.dumps(data, indent=2) + "\n"
        print(f"fix-python:    {label}: {len(changed)} command(s) would change:")
        for before, after in changed:
            print(f"                 {before!r} -> {after!r}")

        if not apply_:
            continue

        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(preview, encoding="utf-8")
            os.replace(tmp, path)
            print(f"fix-python:    {label}: WRITTEN")
        except OSError as exc:
            print(f"fix-python:    {label}: FAIL to write — {exc}")
            all_ok = False

    if not apply_:
        print("fix-python:    (dry-run) re-run with --fix-python-apply to persist")
    return all_ok


def _is_usable_python(cmd_path: Optional[str]) -> bool:
    """Return True iff *cmd_path* actually runs as Python >= 3.9.

    Guards against the Microsoft Store reparse stub at
    ``WindowsApps\\python3.exe`` / ``WindowsApps\\python.exe``: the unblessed
    stub is a zero-byte reparse point that either opens the Store or exits
    silently. Launching it under Copilot CLI causes ``MCP error -32000:
    Connection closed`` because the child never speaks JSON-RPC.

    We distinguish the stub from a real Store-installed Python by
    *executing* the candidate with a tiny version probe and a 3-second
    timeout: a blessed interpreter prints nothing and exits 0; the stub
    either blocks on a Store dialog (killed by timeout) or exits non-zero.
    Zero-byte reparse points are short-circuited before the spawn so users
    without the Store subscription don't pay the full timeout.
    """
    if not cmd_path:
        return False
    # Zero-byte reparse points never execute Python; skip the spawn and fail
    # fast. Real installed Python.exe under WindowsApps has a non-zero size.
    try:
        if os.name == "nt" and os.path.getsize(cmd_path) == 0:
            return False
    except OSError:
        return False
    try:
        result = subprocess.run(
            [
                cmd_path,
                "-c",
                "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)",
            ],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _rewrite_python_in_config(
    data: object, interpreter: str
) -> tuple[list[tuple[str, str]], object]:
    """Walk the JSON tree and replace bare `python3` / `python` in any
    `command` field with the absolute interpreter path when the current one
    doesn't actually run.

    Returns (list of (before, after) pairs, mutated data). The data is
    mutated in place but also returned for convenience.
    """
    changed: list[tuple[str, str]] = []

    def _needs_rewrite(cmd: str) -> bool:
        # Absolute path: rewrite unless it actually runs.
        if os.path.isabs(cmd):
            return not _is_usable_python(cmd)
        # Bare name: resolve via PATH, then probe the resolved path.
        return not _is_usable_python(shutil.which(cmd))

    # Fields whose value is a shell-ish string whose head we may need to
    # rewrite. ``command`` is the MCP config shape; ``bash`` / ``powershell``
    # are the Copilot CLI hooks-config shape documented in the hooks-
    # configuration reference.
    _SHELL_STRING_FIELDS = ("command", "bash", "powershell")

    def _recurse(node: object) -> None:
        if isinstance(node, dict):
            for field in _SHELL_STRING_FIELDS:
                cmd = node.get(field)
                if not isinstance(cmd, str):
                    continue
                # Hook commands are shell-ish strings (`python3 "..."` or
                # `"C:\Program Files\Python311\python.exe" "..."`). The MCP
                # `command` is a bare executable name. `_split_cmd_head`
                # honours quoting so a path with spaces is not truncated on
                # the first space (which would break Windows installs).
                head, rest = _split_cmd_head(cmd)
                if head and _needs_rewrite(head):
                    new_cmd = f'"{interpreter}" {rest}' if rest else interpreter
                    node[field] = new_cmd
                    changed.append((cmd, new_cmd))
            for v in node.values():
                _recurse(v)
        elif isinstance(node, list):
            for v in node:
                _recurse(v)

    _recurse(data)
    return changed, data


def _expand_plugin_root_vars(data: object, plugin_root: Path) -> list[tuple[str, str]]:
    """Expand ``${OMNI_PLUGIN_ROOT}`` / ``${CLAUDE_PLUGIN_ROOT}`` to *plugin_root*.

    Copilot CLI auto-exports ``COPILOT_PLUGIN_ROOT`` / ``CLAUDE_PLUGIN_ROOT`` /
    ``PLUGIN_ROOT`` and substitutes ``${VAR}`` tokens at spawn time, so this
    pass is usually a no-op. It's kept as a belt-and-braces calibration for:
    (a) ``OMNI_PLUGIN_ROOT`` tokens left over from legacy configs,
    (b) environments where the auto-export is disabled or the variable has
        been filtered out (corporate shell profiles).
    After this helper runs, ``.mcp.json`` and ``hooks/hooks.json`` contain
    absolute paths that don't depend on any env var at all.

    Mutates *data* in place. Returns the list of (before, after) replacements.
    """
    root_str = str(plugin_root.resolve())
    changed: list[tuple[str, str]] = []

    def _expand(s: str) -> str:
        if "${" not in s:
            return s
        return (
            s.replace("${COPILOT_PLUGIN_ROOT}", root_str)
            .replace("${CLAUDE_PLUGIN_ROOT}", root_str)
            .replace("${PLUGIN_ROOT}", root_str)
            .replace("${OMNI_PLUGIN_ROOT}", root_str)
        )

    def _recurse(node: object) -> None:
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if isinstance(v, str):
                    expanded = _expand(v)
                    if expanded != v:
                        node[k] = expanded
                        changed.append((v, expanded))
                else:
                    _recurse(v)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, str):
                    expanded = _expand(v)
                    if expanded != v:
                        node[i] = expanded
                        changed.append((v, expanded))
                else:
                    _recurse(v)

    _recurse(data)
    return changed


def _split_cmd_head(cmd: str) -> tuple[str, str]:
    """Split a shell-style command string into (interpreter, rest).

    Honours both double- and single-quoted interpreter paths so that a
    Windows install like `"C:\\Program Files\\Python311\\python.exe" ...`
    is not truncated at the first space. Unquoted commands are split at
    the first whitespace, matching the default `shlex`/`CreateProcess`
    behaviour. The returned `interpreter` is always unquoted; `rest` keeps
    its original whitespace and quoting so the caller can splice a new
    interpreter back in without mangling downstream arguments.

    Returns `("", "")` for empty input.
    """
    s = cmd.lstrip()
    if not s:
        return "", ""

    if s[0] in ('"', "'"):
        quote = s[0]
        end = s.find(quote, 1)
        if end < 0:
            # Unterminated quote — treat the whole string as the head.
            return s[1:], ""
        head = s[1:end]
        rest = s[end + 1 :].lstrip()
        return head, rest

    # Unquoted: split on first whitespace run.
    for i, ch in enumerate(s):
        if ch.isspace():
            return s[:i], s[i:].lstrip()
    return s, ""


def _doctor_run_gc(root: Path, *, apply_: bool) -> None:
    """Run the runs-GC from inside `omni doctor`.

    The delegation avoids duplicating the policy — runs_gc.py owns the TTL
    resolution and deletion logic.
    """
    gc_path = root / "scripts" / "runs_gc.py"
    if not gc_path.exists():
        print("gc:           runs_gc.py not found — skipping")
        return
    try:
        import importlib.util as _ilu

        spec = _ilu.spec_from_file_location("runs_gc", gc_path)
        if spec is None or spec.loader is None:
            print("gc:           could not load runs_gc — skipping")
            return
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"gc:           WARN: could not import runs_gc: {exc}")
        return

    ttl_env = os.environ.get("OMNI_RUNS_TTL_DAYS")
    try:
        ttl_days = float(ttl_env) if ttl_env else mod.DEFAULT_TTL_DAYS
    except ValueError:
        ttl_days = mod.DEFAULT_TTL_DAYS
    print(f"gc:           {'APPLY' if apply_ else 'DRY-RUN'} ttl={ttl_days:.1f}d")
    mod.run_gc(root, ttl_days=ttl_days, apply_=apply_)


def _doctor_subagent_pool(root: Path, *, strict: bool = False) -> bool:
    """WS5a: show subagent pool state (cap, acquired slots)."""
    pool_path = root / "scripts" / "subagent_pool.py"
    if not pool_path.exists():
        print("subagent pool: subagent_pool.py not found — skipping")
        return True

    try:
        import importlib.util as _ilu

        spec = _ilu.spec_from_file_location("subagent_pool", pool_path)
        if spec is None or spec.loader is None:
            print("subagent pool: could not load subagent_pool — skipping")
            return True
        pool_mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(pool_mod)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"subagent pool: WARN: could not import subagent_pool: {exc}")
        return True

    try:
        cap = pool_mod.get_cap()
        pool = pool_mod.SubagentPool(cap=cap)
        status = pool.status()
        acquired = status.get("acquired", [])
        job_ids = [e.get("job_id", "?") for e in acquired]
        print(
            f"subagent pool: cap={cap}, acquired={len(acquired)}"
            + (f" (job ids: {job_ids})" if job_ids else "")
            + " OK"
        )

        if strict:
            import time

            now = time.time()
            orphaned = [
                e
                for e in acquired
                if now - e.get("ts", now) > 1800  # 30 min
            ]
            if orphaned:
                print(
                    f"subagent pool: FAIL (--strict): {len(orphaned)} acquired"
                    " entry(ies) older than 30 min (likely orphaned)"
                )
                return False
    except Exception as exc:
        print(f"subagent pool: WARN: could not read pool status: {exc}")

    return True


def _doctor_ralplan_runs(root: Path, *, strict: bool = False) -> bool:
    """WS5d: show ralplan active runs and warn on stale awaiting-input (--strict)."""
    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        return True

    import json as _json
    import time as _time

    ralplan_runs: list[dict] = []
    try:
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            if not run_dir.name.startswith("ralplan-"):
                continue
            sp = run_dir / "status.json"
            if not sp.exists():
                continue
            try:
                data = _json.loads(sp.read_text(encoding="utf-8"))
                ralplan_runs.append(
                    {
                        "name": run_dir.name,
                        "state": data.get("state", "unknown"),
                        "cycle": data.get("current_cycle", 0),
                        "verdict": data.get("last_verdict"),
                        "mtime": sp.stat().st_mtime,
                    }
                )
            except Exception:
                pass
    except Exception as exc:
        print(f"ralplan runs:  WARN: could not read runs: {exc}")
        return True

    if not ralplan_runs:
        print("ralplan runs:  (none)")
        return True

    active = [
        r
        for r in ralplan_runs
        if r["state"] not in ("converged", "unconverged", "rejected", "cancelled")
    ]
    print(f"ralplan runs:  {len(ralplan_runs)} total, {len(active)} active")
    for r in ralplan_runs[-5:]:
        print(
            f"  {r['name']}: state={r['state']}, cycle={r['cycle']}, verdict={r['verdict']}"
        )

    if not strict:
        return True

    # --strict: warn if any run has been awaiting-input for >24h
    now = _time.time()
    stale = [
        r
        for r in ralplan_runs
        if r["state"] == "awaiting-input" and (now - r["mtime"]) > 86400
    ]
    if stale:
        print(
            f"ralplan runs:  FAIL (--strict): {len(stale)} run(s) in state='awaiting-input'"
            " for >24h (user may have abandoned the clarification)"
        )
        for r in stale:
            age_h = (now - r["mtime"]) / 3600
            print(f"  {r['name']}: awaiting-input for {age_h:.1f}h")
        return False

    return True


def _doctor_recent_runs(root: Path) -> None:
    """WS5a: show last 5 run IDs with job state counts."""
    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        print("recent runs:   (no .omni/runs/ directory)")
        return

    try:
        run_dirs = sorted(
            (d for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )[:5]

        if not run_dirs:
            print("recent runs:   (none)")
            return

        import json as _json

        print("recent runs:")
        for run_dir in run_dirs:
            counts: dict = {}
            for job_dir in run_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                sp = job_dir / "status.json"
                if not sp.exists():
                    continue
                try:
                    data = _json.loads(sp.read_text(encoding="utf-8"))
                    state = data.get("state", "unknown")
                    counts[state] = counts.get(state, 0) + 1
                except Exception:
                    counts["unreadable"] = counts.get("unreadable", 0) + 1
            count_str = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
            print(f"  {run_dir.name}: {count_str or '(no jobs)'}")
    except Exception as exc:
        print(f"recent runs:   WARN: could not read runs: {exc}")


def _doctor_team_runs(root: Path, *, strict: bool = False) -> bool:
    """WS6: show active team runs (mode startswith 'team') with worker counts.

    In strict mode, warn if any team has been in state='dispatched' for >24h
    without collection (likely abandoned).
    """
    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        print("team runs:     (no .omni/runs/ directory)")
        return True

    import json as _json
    import time as _time

    team_runs: list[dict] = []
    try:
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            if not run_dir.name.startswith("team-"):
                continue
            sp = run_dir / "status.json"
            mp = run_dir / "manifest.json"
            if not sp.exists():
                continue
            try:
                status_data = _json.loads(sp.read_text(encoding="utf-8"))
                manifest_data = (
                    _json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
                )
                workers = manifest_data.get("workers", [])
                team_runs.append(
                    {
                        "name": run_dir.name,
                        "state": status_data.get("state", "unknown"),
                        "worker_count": len(workers),
                        "mtime": sp.stat().st_mtime,
                    }
                )
            except Exception:
                pass
    except Exception as exc:
        print(f"team runs:     WARN: could not read team runs: {exc}")
        return True

    if not team_runs:
        print("team runs:     (none)")
        return True

    active = [
        r for r in team_runs if r["state"] not in ("cleaned", "cancelled", "done")
    ]
    print(f"team runs:     {len(team_runs)} total, {len(active)} active")
    for r in team_runs[-5:]:
        print(f"  {r['name']}: state={r['state']}, workers={r['worker_count']}")

    if not strict:
        return True

    # --strict: warn if any team has been in state='dispatched' for >24h
    now = _time.time()
    stale = [
        r
        for r in team_runs
        if r["state"] == "dispatched" and (now - r["mtime"]) > 86400
    ]
    if stale:
        print(
            f"team runs:     FAIL (--strict): {len(stale)} team run(s) in"
            " state='dispatched' for >24h (likely abandoned collection)"
        )
        for r in stale:
            age_h = (now - r["mtime"]) / 3600
            print(
                f"  {r['name']}: dispatched for {age_h:.1f}h, workers={r['worker_count']}"
            )
        return False

    return True


def _cmd_init(args: argparse.Namespace) -> int:
    cwd = Path(args.path or os.getcwd()).resolve()
    target = cwd / ".omni"
    target.mkdir(parents=True, exist_ok=True)
    config = target / "config.json"
    if not config.exists() or args.force:
        config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "project_name": cwd.name,
                    "profile": args.profile,
                    "memory_scope": "project",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    for sub in ("runs", "specs", "plans", "decisions", "audit", "support"):
        (target / sub).mkdir(parents=True, exist_ok=True)
    # Write scaffolded AGENTS.md for the target project if missing
    agents_md = cwd / "AGENTS.md"
    if not agents_md.exists() and not args.no_agents_md:
        tmpl = _plugin_root() / "templates" / "AGENTS.md.tmpl"
        if tmpl.exists():
            agents_md.write_text(tmpl.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"initialized {target}")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    cwd = Path(os.getcwd())
    config = cwd / ".omni" / "config.json"
    if not config.exists():
        print("not initialized — run `omni init` first")
        return 1
    print(config.read_text(encoding="utf-8"))
    runs = cwd / ".omni" / "runs"
    if runs.exists():
        print("\nruns:")
        for run in sorted(runs.iterdir()):
            print(f"  - {run.name}")
    return 0


def _cmd_plugin_install(args: argparse.Namespace) -> int:
    copilot = shutil.which("copilot")
    if not copilot:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2
    root = _plugin_root()
    source = args.source or str(root)
    cmd = [copilot, "plugin", "install", source]
    print(f"running: {' '.join(cmd)}")
    return subprocess.call(cmd)


def _cmd_mcp(_args: argparse.Namespace) -> int:
    server = _plugin_root() / "mcp" / "server.py"
    return subprocess.call([sys.executable, str(server)])


# ---------------------------------------------------------------------------
# Phase-C C20: artifact-first lifecycle enforcement
# ---------------------------------------------------------------------------

_ARTIFACT_REQUIRED: dict[str, tuple[str, ...]] = {
    "execute": ("spec.json",),
    "verify": ("plan.md",),
}


def _load_state_machine():
    path = _plugin_root() / "scripts" / "state_machine.py"
    if not path.exists():
        return None
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("state_machine", path)
    if spec is None or spec.loader is None:
        return None
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _resolve_run_dir(raw: str) -> Path:
    """Accept either an explicit path or a bare run-id (resolved under .omni/runs/)."""
    cand = Path(raw)
    if cand.is_absolute() or cand.exists():
        return cand
    return Path(os.getcwd()) / ".omni" / "runs" / raw


def _enforce_artifacts(run_dir: Path, gate: str) -> list[str]:
    """Return a list of missing-artifact paths for *gate*; empty on success."""
    required = _ARTIFACT_REQUIRED.get(gate, ())
    return [str(run_dir / name) for name in required if not (run_dir / name).exists()]


_GATE_ARTIFACT_REQUIRED: dict[str, tuple[str, ...]] = {
    # Each intermediate gate requires the same artifacts as the target gate
    # that was requested from CLI — e.g. `omni execute` enforces spec.json,
    # but `omni verify` should still require spec.json at the implicit
    # execute step so we never silently jump through a gate without its
    # artifact being present.
    "plan": ("spec.json",),  # plan lands once a spec exists
    "execute": ("spec.json",),
    "verify": ("plan.md",),
    "done": ("plan.md",),
}


def _walk_gates(sm, run_dir: Path, target: str, note: str) -> None:
    """Step-advance through every gate between current and *target*.

    The state machine enforces single-step forward moves; this helper walks
    those steps one-by-one AND re-checks the per-gate artifact requirement
    for each intermediate gate. Earlier versions of this helper delegated
    enforcement to the caller's single up-front artifact check — the
    adversarial architect review (Phase-C C34) flagged that as a silent
    bypass. Every intermediate gate now re-enforces its own contract.
    """
    order = list(sm.GATES)
    state = sm.read_state(run_dir)
    current = state.get("gate", "discuss")
    # Codex P2: corrupt or manually-edited state.json can carry an unknown
    # gate value. Raise a controlled StateMachineError instead of the bare
    # ValueError that order.index would throw.
    if current not in order:
        raise sm.StateMachineError(
            f"unknown gate {current!r} in {run_dir / 'state.json'}; "
            f"valid: {', '.join(order)}"
        )
    if target not in order:
        raise sm.StateMachineError(
            f"unknown target gate {target!r}; valid: {', '.join(order)}"
        )
    target_idx = order.index(target)
    current_idx = order.index(current)
    if current_idx >= target_idx:
        sm.advance(run_dir, target, note=note)
        return
    for intermediate in order[current_idx + 1 : target_idx + 1]:
        required = _GATE_ARTIFACT_REQUIRED.get(intermediate, ())
        missing = [name for name in required if not (run_dir / name).exists()]
        if missing:
            raise sm.StateMachineError(
                f"gate {intermediate!r} requires missing artifact(s): "
                + ", ".join(missing)
            )
        sm.advance(run_dir, intermediate, note=note)


def _cmd_execute(args: argparse.Namespace) -> int:
    run_dir = _resolve_run_dir(args.run_id)
    if not run_dir.exists():
        print(f"error: run-dir not found: {run_dir}", file=sys.stderr)
        return 2
    missing = _enforce_artifacts(run_dir, "execute")
    if missing:
        print(
            "error: artifact-first lifecycle — missing required artifacts:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2
    sm = _load_state_machine()
    if sm is None:
        print(
            "warn: state_machine.py unavailable — skipping gate advance",
            file=sys.stderr,
        )
    else:
        try:
            _walk_gates(sm, run_dir, "execute", note="omni execute")
        except sm.StateMachineError as exc:
            print(f"error: state machine: {exc}", file=sys.stderr)
            return 2
    print(f"omni execute: {run_dir} — ready to run (gate=execute)")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    run_dir = _resolve_run_dir(args.run_id)
    if not run_dir.exists():
        print(f"error: run-dir not found: {run_dir}", file=sys.stderr)
        return 2
    missing = _enforce_artifacts(run_dir, "verify")
    if missing:
        print(
            "error: artifact-first lifecycle — missing required artifacts:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2
    sm = _load_state_machine()
    if sm is None:
        print(
            "warn: state_machine.py unavailable — skipping gate advance",
            file=sys.stderr,
        )
    else:
        try:
            _walk_gates(sm, run_dir, "verify", note="omni verify")
        except sm.StateMachineError as exc:
            print(f"error: state machine: {exc}", file=sys.stderr)
            return 2
    print(f"omni verify: {run_dir} — ready to run (gate=verify)")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = _plugin_root()
    if args.kind in ("skills", "all"):
        print("# Skills")
        for skill in sorted((root / "skills").glob("*/SKILL.md")):
            name = skill.parent.name
            desc_line = ""
            try:
                for line in skill.read_text(encoding="utf-8").splitlines():
                    if line.startswith("description:"):
                        desc_line = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
            print(f"  - {name}: {desc_line}")
    if args.kind in ("agents", "all"):
        print("\n# Agents")
        for agent in sorted((root / "agents").glob("*.md")):
            print(f"  - {agent.stem}")
    return 0


def _omni_home() -> Path:
    return Path(os.environ.get("OMNI_HOME") or (Path.home() / ".omni"))


def _current_project() -> str:
    """Return a project identifier (git repo root or cwd hash)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def _omni_db() -> Optional[sqlite3.Connection]:
    db_path = _omni_home() / "omni.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_memory_project_column(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(memory)").fetchall()
    if not rows or any(row[1] == "project" for row in rows):
        return
    try:
        conn.execute("ALTER TABLE memory ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _memory_db():
    conn = _omni_db()
    if conn is None:
        return None
    _ensure_memory_project_column(conn)
    return conn


def _dump_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, default=str)
    print()


def _format_timestamp(raw: object) -> str:
    if raw in (None, ""):
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(raw)))
    except (TypeError, ValueError, OSError):
        return str(raw)


def _preview_text(value: object, *, limit: int = 60) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def _query_all(
    conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()
) -> list[sqlite3.Row]:
    try:
        return conn.execute(query, params).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _query_one(
    conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()
) -> Optional[sqlite3.Row]:
    try:
        return conn.execute(query, params).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise


def _print_fields(fields: list[tuple[str, object]]) -> None:
    for label, value in fields:
        print(f"{label}: {value}")


def _print_body(value: object) -> None:
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    print(value if value not in (None, "") else "-")


def _parse_json_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


_CODEBASE_FILE_EXTENSIONS = {".py", ".md", ".json", ".toml", ".yaml", ".yml"}
_CODEBASE_SKIP_DIRS = {
    ".git",
    ".omni",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_WIKI_LINK_RE = re.compile(r"\[\[\s*(?:[^\]|]*\|)?\s*([^\]|]+?)\s*\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*?\]\(\s*([^)\s]+?)\s*\)")
_PY_FILE_LITERAL_RE = re.compile(r"['\"]([^'\"]+\.py)['\"]")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:80] or "untitled"


def _extract_wiki_targets(body: str) -> list[str]:
    targets: list[str] = []
    for match in _WIKI_LINK_RE.finditer(body):
        targets.append(_slugify(match.group(1)))
    for match in _MD_LINK_RE.finditer(body):
        destination = match.group(1)
        if "://" in destination or destination.startswith("#"):
            continue
        target = destination.rsplit("/", 1)[-1]
        if target.endswith(".md"):
            target = target[:-3]
        targets.append(_slugify(target))
    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        if target and target not in seen:
            seen.add(target)
            unique.append(target)
    return unique


def _resolve_graph_root(root_arg: str | None) -> Path:
    root = Path(root_arg).expanduser().resolve() if root_arg else Path.cwd().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"root does not exist or is not a directory: {root}")
    return root


def _iter_codebase_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in _CODEBASE_SKIP_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if path.suffix.lower() in _CODEBASE_FILE_EXTENSIONS:
                files.append(path)
    files.sort()
    return files


def _module_name_for(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _build_module_index(files: list[Path], root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        module_name = _module_name_for(path, root)
        if module_name:
            out[module_name] = path.relative_to(root).as_posix()
    return out


def _resolve_local_import(
    module_index: dict[str, str],
    current_module: str,
    module_name: str | None,
    level: int,
) -> str | None:
    base_parts = current_module.split(".") if current_module else []
    if current_module and level > 0:
        base_parts = base_parts[:-1]
        if level > 1:
            trim = min(level - 1, len(base_parts))
            base_parts = base_parts[:-trim]
    candidates: list[str] = []
    if module_name:
        parts = module_name.split(".") if level == 0 else base_parts + module_name.split(".")
        for end in range(len(parts), 0, -1):
            candidates.append(".".join(parts[:end]))
    elif base_parts:
        candidates.append(".".join(base_parts))
    for candidate in candidates:
        if candidate in module_index:
            return module_index[candidate]
        init_name = f"{candidate}.__init__"
        if init_name in module_index:
            return module_index[init_name]
    return None


def _extract_python_graph(
    path: Path, root: Path, module_index: dict[str, str]
) -> tuple[list[str], list[str]]:
    rel_path = path.relative_to(root).as_posix()
    current_module = _module_name_for(path, root)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return [], []
    symbols: list[str] = []
    imports: list[str] = []
    seen_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    for node in ast.walk(tree):
        target: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_local_import(module_index, current_module, alias.name, 0)
                if target and target != rel_path and target not in seen_imports:
                    seen_imports.add(target)
                    imports.append(target)
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_local_import(module_index, current_module, node.module, node.level)
            if not target and node.module:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    qualified = f"{node.module}.{alias.name}"
                    target = _resolve_local_import(module_index, current_module, qualified, node.level)
                    if target:
                        break
            if target and target != rel_path and target not in seen_imports:
                seen_imports.add(target)
                imports.append(target)
    for match in _PY_FILE_LITERAL_RE.finditer(source):
        candidate = (path.parent / match.group(1)).resolve()
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            rel = candidate.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel != rel_path and rel not in seen_imports:
            seen_imports.add(rel)
            imports.append(rel)
    return symbols, imports


def _extract_markdown_graph(path: Path, root: Path) -> list[str]:
    try:
        body = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    targets: list[str] = []
    seen: set[str] = set()
    for match in _MD_LINK_RE.finditer(body):
        destination = match.group(1)
        if "://" in destination or destination.startswith("#"):
            continue
        candidate = (path.parent / destination).resolve()
        options = [candidate]
        if candidate.suffix == "":
            options.append(candidate.with_suffix(".md"))
            options.append(candidate.with_suffix(".py"))
        for option in options:
            if not option.exists() or not option.is_file():
                continue
            try:
                rel = option.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel not in seen:
                seen.add(rel)
                targets.append(rel)
            break
    return targets


def _build_codebase_graph(root_arg: str | None, include_symbols: bool = True) -> dict[str, Any]:
    root = _resolve_graph_root(root_arg)
    files = _iter_codebase_files(root)
    module_index = _build_module_index(files, root)
    file_nodes: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    symbol_count = 0
    for path in files:
        rel_path = path.relative_to(root).as_posix()
        language = path.suffix.lstrip(".") or "text"
        symbols: list[str] = []
        imports: list[str] = []
        references: list[str] = []
        if path.suffix == ".py":
            symbols, imports = _extract_python_graph(path, root, module_index)
        elif path.suffix == ".md":
            references = _extract_markdown_graph(path, root)
        file_node = {
            "id": rel_path,
            "kind": "file",
            "path": rel_path,
            "language": language,
            "symbol_count": len(symbols),
        }
        file_nodes.append(file_node)
        nodes.append(file_node)
        for target in imports:
            edges.append({"source": rel_path, "target": target, "type": "imports"})
        for target in references:
            edges.append({"source": rel_path, "target": target, "type": "references"})
        if include_symbols:
            for symbol in symbols:
                symbol_count += 1
                symbol_id = f"{rel_path}#{symbol}"
                nodes.append({"id": symbol_id, "kind": "symbol", "path": rel_path, "symbol": symbol})
                edges.append({"source": rel_path, "target": symbol_id, "type": "defines"})
    return {
        "root": str(root),
        "files": file_nodes,
        "nodes": nodes,
        "edges": edges,
        "file_count": len(file_nodes),
        "symbol_count": symbol_count,
        "edge_count": len(edges),
    }


def _normalize_target_path(root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    resolved = path.expanduser().resolve() if path.is_absolute() else (root / path).resolve()
    return resolved.relative_to(root).as_posix()


def _compute_codebase_impact(graph: dict[str, Any], path_arg: str) -> dict[str, Any]:
    root = Path(graph["root"])
    target = _normalize_target_path(root, path_arg)
    file_paths = {node["path"] for node in graph["files"]}
    if target not in file_paths:
        raise ValueError(f"path not found in analyzed graph: {path_arg}")
    imported_by = sorted(
        {
            edge["source"]
            for edge in graph["edges"]
            if edge["target"] == target and edge["type"] in {"imports", "references"}
        }
    )
    references = sorted(
        {
            edge["target"]
            for edge in graph["edges"]
            if edge["source"] == target and edge["type"] in {"imports", "references"}
        }
    )
    defines = sorted(
        node["symbol"]
        for node in graph["nodes"]
        if node["kind"] == "symbol" and node["path"] == target
    )
    return {
        "root": graph["root"],
        "path": target,
        "imported_by": imported_by,
        "references": references,
        "defines": defines,
        "imported_by_count": len(imported_by),
        "references_count": len(references),
        "defines_count": len(defines),
    }


def _wiki_graph(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _query_all(conn, "SELECT slug, title, body FROM wiki ORDER BY slug")
    slugs = {row["slug"] for row in rows}
    nodes = [{"slug": row["slug"], "title": row["title"]} for row in rows]
    edges: list[dict[str, str]] = []
    dangling: list[dict[str, str]] = []
    for row in rows:
        for target in _extract_wiki_targets(row["body"] or ""):
            if target == row["slug"]:
                continue
            edge = {"source": row["slug"], "target": target}
            if target in slugs:
                edges.append(edge)
            else:
                dangling.append(edge)
    return {
        "nodes": nodes,
        "edges": edges,
        "dangling": dangling,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "dangling_count": len(dangling),
    }


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("No entries.")
        return
    all_rows = [headers] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in all_rows[1:]:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def _cmd_memory_search(args: argparse.Namespace) -> int:
    conn = _memory_db()
    if conn is None:
        print("Memory database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        query = f"%{args.query}%"
        project = _current_project()
        scope = getattr(args, "scope", None)
        limit = getattr(args, "limit", 20)
        if scope:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at"
                " FROM memory WHERE scope=? AND (content LIKE ? OR key LIKE ?)"
                " AND project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (scope, query, query, project, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at"
                " FROM memory WHERE (content LIKE ? OR key LIKE ?)"
                " AND project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (query, query, project, limit),
            ).fetchall()
        entries = [dict(r) for r in rows]
        if getattr(args, "json", False):
            json.dump(
                {"results": entries, "count": len(entries)},
                sys.stdout,
                indent=2,
                default=str,
            )
            print()
            return 0
        if not entries:
            print("No matches found.")
            return 0
        _print_table(
            ["Scope", "Key", "Content", "Updated"],
            [
                [
                    e["scope"],
                    e["key"] or "-",
                    e["content"][:60],
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["updated_at"])),
                ]
                for e in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_memory_list(args: argparse.Namespace) -> int:
    conn = _memory_db()
    if conn is None:
        print("Memory database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        project = _current_project()
        scope = getattr(args, "scope", None)
        limit = getattr(args, "limit", 20)
        if scope:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at"
                " FROM memory WHERE scope=?"
                " AND project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (scope, project, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, updated_at"
                " FROM memory WHERE project=?"
                " ORDER BY updated_at DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        entries = [dict(r) for r in rows]
        if getattr(args, "json", False):
            json.dump(
                {"entries": entries, "count": len(entries)},
                sys.stdout,
                indent=2,
                default=str,
            )
            print()
            return 0
        if not entries:
            print("No memory entries.")
            return 0
        _print_table(
            ["Scope", "Key", "Content", "Updated"],
            [
                [
                    e["scope"],
                    e["key"] or "-",
                    e["content"][:60],
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["updated_at"])),
                ]
                for e in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_memory_capture(args: argparse.Namespace) -> int:
    db_path = _omni_home() / "omni.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory"
            " (id TEXT PRIMARY KEY, scope TEXT NOT NULL, key TEXT,"
            " content TEXT NOT NULL, tags TEXT, created_at REAL NOT NULL,"
            " updated_at REAL NOT NULL)"
        )
        _ensure_memory_project_column(conn)
        now = time.time()
        entry_id = uuid.uuid4().hex
        project = _current_project()
        scope = getattr(args, "scope", "project")
        key = getattr(args, "key", None)
        tags = ",".join(getattr(args, "tags", []) or [])
        conn.execute(
            "INSERT INTO memory(id, scope, key, content, tags, project, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, scope, key, args.content, tags, project, now, now),
        )
        conn.commit()
        entry = {
            "id": entry_id,
            "scope": scope,
            "key": key,
            "content": args.content,
            "project": project,
        }
        if getattr(args, "json", False):
            json.dump(entry, sys.stdout, indent=2, default=str)
            print()
            return 0
        print(f"Captured: [{scope}] {key or args.content[:40]}")
        return 0
    finally:
        conn.close()


def _cmd_memory_prune(args: argparse.Namespace) -> int:
    conn = _memory_db()
    if conn is None:
        print("Memory database not found.", file=sys.stderr)
        return 1
    try:
        cutoff = time.time() - getattr(args, "older_than", 30) * 86400
        project = _current_project()
        scope = getattr(args, "scope", None)
        dry_run = getattr(args, "dry_run", False)
        if scope:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory"
                " WHERE updated_at < ? AND scope=?"
                " AND project=?",
                (cutoff, scope, project),
            ).fetchone()[0]
            if not dry_run:
                conn.execute(
                    "DELETE FROM memory WHERE updated_at < ? AND scope=? AND project=?",
                    (cutoff, scope, project),
                )
                conn.commit()
        else:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory WHERE updated_at < ? AND project=?",
                (cutoff, project),
            ).fetchone()[0]
            if not dry_run:
                conn.execute(
                    "DELETE FROM memory WHERE updated_at < ? AND project=?",
                    (cutoff, project),
                )
                conn.commit()
        result = {
            "deleted": count,
            "dry_run": dry_run,
            "older_than_days": getattr(args, "older_than", 30),
        }
        if getattr(args, "json", False):
            json.dump(result, sys.stdout, indent=2)
            print()
            return 0
        action = "Would prune" if dry_run else "Pruned"
        print(
            f"{action} {count} entries older than {getattr(args, 'older_than', 30)} days."
        )
        return 0
    finally:
        conn.close()


def _cmd_memory_export(args: argparse.Namespace) -> int:
    conn = _memory_db()
    if conn is None:
        print("Memory database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        project = _current_project()
        scope = getattr(args, "scope", None)
        if scope:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, created_at, updated_at"
                " FROM memory WHERE scope=? AND project=?"
                " ORDER BY updated_at DESC",
                (scope, project),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, scope, key, content, tags, project, created_at, updated_at"
                " FROM memory WHERE project=?"
                " ORDER BY updated_at DESC",
                (project,),
            ).fetchall()
        entries = [dict(r) for r in rows]
        output = json.dumps(
            {"entries": entries, "count": len(entries)}, indent=2, default=str
        )
        output_path = getattr(args, "output", None)
        if output_path:
            Path(output_path).write_text(output + "\n", encoding="utf-8")
            print(f"Exported {len(entries)} entries to {output_path}")
        else:
            print(output)
        return 0
    finally:
        conn.close()


def _cmd_state_list(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        rows = _query_all(
            conn,
            "SELECT mode, updated_at FROM state ORDER BY updated_at DESC LIMIT ?",
            (getattr(args, "limit", 20),),
        )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"modes": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No state entries.")
            return 0
        _print_table(
            ["Mode", "Updated"],
            [[entry["mode"], _format_timestamp(entry["updated_at"])] for entry in entries],
        )
        return 0
    finally:
        conn.close()


def _cmd_state_show(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        row = _query_one(
            conn,
            "SELECT mode, body, updated_at FROM state WHERE mode=?",
            (args.mode,),
        )
        if row is None:
            if getattr(args, "json", False):
                _dump_json({"error": "not found", "mode": args.mode})
            else:
                print(f"No state entry for mode '{args.mode}'.", file=sys.stderr)
            return 1
        payload = {
            "mode": row["mode"],
            "body": _parse_json_text(row["body"]),
            "updated_at": row["updated_at"],
        }
        if getattr(args, "json", False):
            _dump_json(payload)
            return 0
        _print_fields(
            [
                ("Mode", payload["mode"]),
                ("Updated", _format_timestamp(payload["updated_at"])),
            ]
        )
        print()
        _print_body(payload["body"])
        return 0
    finally:
        conn.close()


def _cmd_wiki_list(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        rows = _query_all(
            conn,
            "SELECT slug, title, updated_at FROM wiki ORDER BY updated_at DESC LIMIT ?",
            (getattr(args, "limit", 20),),
        )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"entries": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No wiki entries.")
            return 0
        _print_table(
            ["Slug", "Title", "Updated"],
            [
                [entry["slug"], entry["title"], _format_timestamp(entry["updated_at"])]
                for entry in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_wiki_search(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        query = f"%{args.query}%"
        rows = _query_all(
            conn,
            "SELECT slug, title, updated_at FROM wiki"
            " WHERE body LIKE ? OR title LIKE ? OR tags LIKE ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (query, query, query, getattr(args, "limit", 20)),
        )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"results": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No matches found.")
            return 0
        _print_table(
            ["Slug", "Title", "Updated"],
            [
                [entry["slug"], entry["title"], _format_timestamp(entry["updated_at"])]
                for entry in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_wiki_show(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        row = _query_one(
            conn,
            "SELECT slug, title, body, tags, updated_at FROM wiki WHERE slug=?",
            (args.slug,),
        )
        if row is None:
            if getattr(args, "json", False):
                _dump_json({"error": "not found", "slug": args.slug})
            else:
                print(f"No wiki page for slug '{args.slug}'.", file=sys.stderr)
            return 1
        entry = dict(row)
        if getattr(args, "json", False):
            _dump_json(entry)
            return 0
        _print_fields(
            [
                ("Slug", entry["slug"]),
                ("Title", entry["title"]),
                ("Tags", entry["tags"] or "-"),
                ("Updated", _format_timestamp(entry["updated_at"])),
            ]
        )
        print()
        print(entry["body"])
        return 0
    finally:
        conn.close()


def _cmd_wiki_graph(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        graph = _wiki_graph(conn)
        if getattr(args, "json", False):
            _dump_json(graph)
            return 0
        print(
            "Wiki graph: "
            f"{graph['node_count']} node(s), {graph['edge_count']} edge(s), "
            f"{graph['dangling_count']} dangling link(s)."
        )
        nodes = graph["nodes"]
        edges = graph["edges"]
        dangling = graph["dangling"]
        if nodes:
            print()
            _print_table(
                ["Slug", "Title"],
                [[node["slug"], node["title"]] for node in nodes],
            )
        if edges:
            print()
            _print_table(
                ["Source", "Target"],
                [[edge["source"], edge["target"]] for edge in edges],
            )
        if dangling:
            print()
            _print_table(
                ["Dangling From", "Missing Target"],
                [[edge["source"], edge["target"]] for edge in dangling],
            )
        return 0
    finally:
        conn.close()


def _cmd_wiki_validate(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        report = _wiki_graph(conn)
        report["ok"] = report["dangling_count"] == 0
        if getattr(args, "json", False):
            _dump_json(report)
        else:
            status = "OK" if report["ok"] else "FAIL"
            print(f"Wiki validation: {status}")
            print(f"Nodes:    {report['node_count']}")
            print(f"Edges:    {report['edge_count']}")
            print(f"Dangling: {report['dangling_count']}")
            if report["dangling"]:
                print()
                _print_table(
                    ["Dangling From", "Missing Target"],
                    [
                        [edge["source"], edge["target"]]
                        for edge in report["dangling"]
                    ],
                )
        return 0 if report["ok"] else 1
    finally:
        conn.close()


def _cmd_notepad_list(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        limit = getattr(args, "limit", 20)
        kind = getattr(args, "kind", None)
        if kind:
            rows = _query_all(
                conn,
                "SELECT id, kind, body, created_at FROM notepad"
                " WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            )
        else:
            rows = _query_all(
                conn,
                "SELECT id, kind, body, created_at FROM notepad"
                " ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"notes": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No notepad notes.")
            return 0
        _print_table(
            ["ID", "Kind", "Body", "Created"],
            [
                [
                    entry["id"],
                    entry["kind"],
                    _preview_text(entry["body"]),
                    _format_timestamp(entry["created_at"]),
                ]
                for entry in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_notepad_show(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        row = _query_one(
            conn,
            "SELECT id, kind, body, created_at FROM notepad WHERE id=?",
            (args.note_id,),
        )
        if row is None:
            if getattr(args, "json", False):
                _dump_json({"error": "not found", "id": args.note_id})
            else:
                print(f"No notepad note with id '{args.note_id}'.", file=sys.stderr)
            return 1
        note = dict(row)
        if getattr(args, "json", False):
            _dump_json(note)
            return 0
        _print_fields(
            [
                ("ID", note["id"]),
                ("Kind", note["kind"]),
                ("Created", _format_timestamp(note["created_at"])),
            ]
        )
        print()
        print(note["body"])
        return 0
    finally:
        conn.close()


def _cmd_shared_memory_list(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        rows = _query_all(
            conn,
            "SELECT key, updated_at FROM shared_memory"
            " ORDER BY updated_at DESC LIMIT ?",
            (getattr(args, "limit", 20),),
        )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"entries": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No shared memory entries.")
            return 0
        _print_table(
            ["Key", "Updated"],
            [[entry["key"], _format_timestamp(entry["updated_at"])] for entry in entries],
        )
        return 0
    finally:
        conn.close()


def _cmd_shared_memory_show(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        row = _query_one(
            conn,
            "SELECT key, body, updated_at FROM shared_memory WHERE key=?",
            (args.key,),
        )
        if row is None:
            if getattr(args, "json", False):
                _dump_json({"error": "not found", "key": args.key})
            else:
                print(f"No shared memory entry for key '{args.key}'.", file=sys.stderr)
            return 1
        entry = dict(row)
        entry["body"] = _parse_json_text(entry["body"])
        if getattr(args, "json", False):
            _dump_json(entry)
            return 0
        _print_fields(
            [
                ("Key", entry["key"]),
                ("Updated", _format_timestamp(entry["updated_at"])),
            ]
        )
        print()
        _print_body(entry["body"])
        return 0
    finally:
        conn.close()


def _cmd_trace_list(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        rows = _query_all(
            conn,
            "SELECT id, observation, verdict, created_at FROM trace"
            " ORDER BY created_at DESC LIMIT ?",
            (getattr(args, "limit", 20),),
        )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"traces": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No trace entries.")
            return 0
        _print_table(
            ["ID", "Observation", "Verdict", "Created"],
            [
                [
                    entry["id"],
                    _preview_text(entry["observation"]),
                    entry["verdict"] or "-",
                    _format_timestamp(entry["created_at"]),
                ]
                for entry in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_trace_show(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        row = _query_one(
            conn,
            "SELECT id, observation, hypothesis, evidence, verdict, created_at"
            " FROM trace WHERE id=?",
            (args.trace_id,),
        )
        if row is None:
            if getattr(args, "json", False):
                _dump_json({"error": "not found", "id": args.trace_id})
            else:
                print(f"No trace entry with id '{args.trace_id}'.", file=sys.stderr)
            return 1
        trace = dict(row)
        if getattr(args, "json", False):
            _dump_json(trace)
            return 0
        _print_fields(
            [
                ("ID", trace["id"]),
                ("Created", _format_timestamp(trace["created_at"])),
                ("Verdict", trace["verdict"] or "-"),
            ]
        )
        print()
        print("Observation:")
        print(trace["observation"])
        if trace.get("hypothesis"):
            print()
            print("Hypothesis:")
            print(trace["hypothesis"])
        if trace.get("evidence"):
            print()
            print("Evidence:")
            _print_body(_parse_json_text(trace["evidence"]))
        return 0
    finally:
        conn.close()


def _cmd_trace_timeline(args: argparse.Namespace) -> int:
    conn = _omni_db()
    if conn is None:
        print("Omni database not found. Run `omni init` first.", file=sys.stderr)
        return 1
    try:
        limit = getattr(args, "limit", 20)
        contains = getattr(args, "contains", None)
        if contains:
            rows = _query_all(
                conn,
                "SELECT id, observation, verdict, created_at FROM trace"
                " WHERE observation LIKE ? ORDER BY created_at LIMIT ?",
                (f"%{contains}%", limit),
            )
        else:
            rows = _query_all(
                conn,
                "SELECT id, observation, verdict, created_at FROM trace"
                " ORDER BY created_at LIMIT ?",
                (limit,),
            )
        entries = [dict(row) for row in rows]
        if getattr(args, "json", False):
            _dump_json({"timeline": entries, "count": len(entries)})
            return 0
        if not entries:
            print("No trace timeline entries.")
            return 0
        _print_table(
            ["ID", "Observation", "Verdict", "Created"],
            [
                [
                    entry["id"],
                    _preview_text(entry["observation"]),
                    entry["verdict"] or "-",
                    _format_timestamp(entry["created_at"]),
                ]
                for entry in entries
            ],
        )
        return 0
    finally:
        conn.close()


def _cmd_codebase_graph(args: argparse.Namespace) -> int:
    try:
        graph = _build_codebase_graph(
            getattr(args, "root", None),
            include_symbols=not getattr(args, "no_symbols", False),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        _dump_json(graph)
        return 0
    print(
        "Codebase graph: "
        f"{graph['file_count']} file node(s), {graph['symbol_count']} symbol node(s), "
        f"{graph['edge_count']} edge(s)."
    )
    file_nodes = graph["files"]
    if file_nodes:
        print()
        _print_table(
            ["Path", "Language", "Symbols"],
            [[node["path"], node["language"], str(node["symbol_count"])] for node in file_nodes[:20]],
        )
    return 0


def _cmd_codebase_impact(args: argparse.Namespace) -> int:
    try:
        graph = _build_codebase_graph(
            getattr(args, "root", None),
            include_symbols=not getattr(args, "no_symbols", False),
        )
        report = _compute_codebase_impact(graph, args.path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        _dump_json(report)
        return 0
    _print_fields(
        [
            ("Path", report["path"]),
            ("Imported by", report["imported_by_count"]),
            ("References", report["references_count"]),
            ("Defines", report["defines_count"]),
        ]
    )
    if report["imported_by"]:
        print()
        print("Imported by:")
        for item in report["imported_by"]:
            print(f"- {item}")
    if report["references"]:
        print()
        print("References:")
        for item in report["references"]:
            print(f"- {item}")
    if report["defines"]:
        print()
        print("Defines:")
        for item in report["defines"]:
            print(f"- {item}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omni", description="Copilot Omni CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version").set_defaults(func=_cmd_version)
    doctor = sub.add_parser("doctor")
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any environment drift (stale team runs, pool caps, etc.)",
    )
    doctor.add_argument(
        "--gc",
        action="store_true",
        help="Garbage-collect .omni/runs/ directories older than TTL (dry-run)",
    )
    doctor.add_argument(
        "--gc-apply",
        action="store_true",
        help="With --gc, actually delete stale runs (default is dry-run)",
    )
    doctor.add_argument(
        "--fix-python",
        action="store_true",
        help="Calibrate .mcp.json + hooks/hooks.json to the "
        "current Python interpreter. Dry-run by default; "
        "use --fix-python-apply to persist. Fix for "
        "Windows corporate boxes where `python3` is not "
        "on PATH.",
    )
    doctor.add_argument(
        "--fix-python-apply",
        action="store_true",
        help="With --fix-python, actually rewrite the config "
        "files (default is dry-run).",
    )
    doctor.set_defaults(func=_cmd_doctor)

    init = sub.add_parser("init", help="Scaffold .omni/ in the current project")
    init.add_argument("--path", default=None)
    init.add_argument(
        "--profile", default="standard", choices=["strict", "standard", "permissive"]
    )
    init.add_argument("--force", action="store_true")
    init.add_argument("--no-agents-md", action="store_true")
    init.set_defaults(func=_cmd_init)

    sub.add_parser("status").set_defaults(func=_cmd_status)

    plug = sub.add_parser(
        "plugin-install", help="Install this plugin into the local Copilot CLI"
    )
    plug.add_argument(
        "--source",
        default=None,
        help="Source path or owner/repo (default: this checkout)",
    )
    plug.set_defaults(func=_cmd_plugin_install)

    mcp = sub.add_parser("mcp", help="Run the MCP server in stdio mode")
    mcp.set_defaults(func=_cmd_mcp)

    # Phase-C C20: artifact-first lifecycle gates.
    execute = sub.add_parser(
        "execute",
        help="Enforce the execute gate: require spec.json, advance state machine",
    )
    execute.add_argument("run_id", help="run-id or absolute path to the run directory")
    execute.set_defaults(func=_cmd_execute)

    verify = sub.add_parser(
        "verify",
        help="Enforce the verify gate: require plan.md, advance state machine",
    )
    verify.add_argument("run_id", help="run-id or absolute path to the run directory")
    verify.set_defaults(func=_cmd_verify)

    lst = sub.add_parser("list", help="List installed skills and agents")
    lst.add_argument(
        "kind", choices=["skills", "agents", "all"], nargs="?", default="all"
    )
    lst.set_defaults(func=_cmd_list)

    mem = sub.add_parser("memory", help="Interact with the memory store")
    mem_sub = mem.add_subparsers(dest="memory_cmd", required=True)

    mem_search = mem_sub.add_parser("search", help="Search memory entries")
    mem_search.add_argument("query", help="Search query")
    mem_search.add_argument("--scope", default=None, help="Filter by scope")
    mem_search.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    mem_search.add_argument("--json", action="store_true", help="JSON output")
    mem_search.set_defaults(func=_cmd_memory_search)

    mem_list = mem_sub.add_parser("list", help="List recent memory entries")
    mem_list.add_argument("--scope", default=None, help="Filter by scope")
    mem_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    mem_list.add_argument("--json", action="store_true", help="JSON output")
    mem_list.set_defaults(func=_cmd_memory_list)

    mem_capture = mem_sub.add_parser("capture", help="Capture a memory entry")
    mem_capture.add_argument("content", help="Content to store")
    mem_capture.add_argument(
        "--scope", default="project", help="Scope (default: project)"
    )
    mem_capture.add_argument("--key", default=None, help="Optional key")
    mem_capture.add_argument("--tags", nargs="*", default=None, help="Optional tags")
    mem_capture.add_argument("--json", action="store_true", help="JSON output")
    mem_capture.set_defaults(func=_cmd_memory_capture)

    mem_prune = mem_sub.add_parser("prune", help="Prune old memory entries")
    mem_prune.add_argument(
        "--older-than", type=int, default=30, help="Days threshold (default: 30)"
    )
    mem_prune.add_argument("--scope", default=None, help="Filter by scope")
    mem_prune.add_argument(
        "--dry-run", action="store_true", help="Show count without deleting"
    )
    mem_prune.add_argument("--json", action="store_true", help="JSON output")
    mem_prune.set_defaults(func=_cmd_memory_prune)

    mem_export = mem_sub.add_parser("export", help="Export memory entries as JSON")
    mem_export.add_argument("--scope", default=None, help="Filter by scope")
    mem_export.add_argument(
        "--output", "-o", default=None, help="Output file (default: stdout)"
    )
    mem_export.set_defaults(func=_cmd_memory_export)

    state = sub.add_parser("state", help="Inspect persisted state")
    state_sub = state.add_subparsers(dest="state_cmd", required=True)

    state_list = state_sub.add_parser("list", help="List stored state modes")
    state_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    state_list.add_argument("--json", action="store_true", help="JSON output")
    state_list.set_defaults(func=_cmd_state_list)

    state_show = state_sub.add_parser("show", help="Show a stored state body")
    state_show.add_argument("mode", help="State mode to inspect")
    state_show.add_argument("--json", action="store_true", help="JSON output")
    state_show.set_defaults(func=_cmd_state_show)

    wiki = sub.add_parser("wiki", help="Inspect the persistent wiki store")
    wiki_sub = wiki.add_subparsers(dest="wiki_cmd", required=True)

    wiki_list = wiki_sub.add_parser("list", help="List wiki pages")
    wiki_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    wiki_list.add_argument("--json", action="store_true", help="JSON output")
    wiki_list.set_defaults(func=_cmd_wiki_list)

    wiki_show = wiki_sub.add_parser("show", help="Show a wiki page")
    wiki_show.add_argument("slug", help="Wiki slug to inspect")
    wiki_show.add_argument("--json", action="store_true", help="JSON output")
    wiki_show.set_defaults(func=_cmd_wiki_show)

    wiki_search = wiki_sub.add_parser("search", help="Search wiki pages")
    wiki_search.add_argument("query", help="Search query")
    wiki_search.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    wiki_search.add_argument("--json", action="store_true", help="JSON output")
    wiki_search.set_defaults(func=_cmd_wiki_search)

    wiki_graph = wiki_sub.add_parser("graph", help="Show the wiki knowledge graph")
    wiki_graph.add_argument("--json", action="store_true", help="JSON output")
    wiki_graph.set_defaults(func=_cmd_wiki_graph)

    wiki_validate = wiki_sub.add_parser(
        "validate", help="Validate wiki cross-references"
    )
    wiki_validate.add_argument("--json", action="store_true", help="JSON output")
    wiki_validate.set_defaults(func=_cmd_wiki_validate)

    notepad = sub.add_parser("notepad", help="Inspect persisted notes")
    notepad_sub = notepad.add_subparsers(dest="notepad_cmd", required=True)

    notepad_list = notepad_sub.add_parser("list", help="List recent notes")
    notepad_list.add_argument("--kind", default=None, help="Filter by note kind")
    notepad_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    notepad_list.add_argument("--json", action="store_true", help="JSON output")
    notepad_list.set_defaults(func=_cmd_notepad_list)

    notepad_show = notepad_sub.add_parser("show", help="Show a note body")
    notepad_show.add_argument("note_id", help="Note id to inspect")
    notepad_show.add_argument("--json", action="store_true", help="JSON output")
    notepad_show.set_defaults(func=_cmd_notepad_show)

    shared_memory = sub.add_parser("shared-memory", help="Inspect shared memory")
    shared_memory_sub = shared_memory.add_subparsers(
        dest="shared_memory_cmd", required=True
    )

    shared_memory_list = shared_memory_sub.add_parser(
        "list", help="List shared memory keys"
    )
    shared_memory_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    shared_memory_list.add_argument(
        "--json", action="store_true", help="JSON output"
    )
    shared_memory_list.set_defaults(func=_cmd_shared_memory_list)

    shared_memory_show = shared_memory_sub.add_parser(
        "show", help="Show a shared memory entry"
    )
    shared_memory_show.add_argument("key", help="Shared memory key to inspect")
    shared_memory_show.add_argument(
        "--json", action="store_true", help="JSON output"
    )
    shared_memory_show.set_defaults(func=_cmd_shared_memory_show)

    trace = sub.add_parser("trace", help="Inspect stored traces")
    trace_sub = trace.add_subparsers(dest="trace_cmd", required=True)

    trace_list = trace_sub.add_parser("list", help="List recent trace entries")
    trace_list.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    trace_list.add_argument("--json", action="store_true", help="JSON output")
    trace_list.set_defaults(func=_cmd_trace_list)

    trace_show = trace_sub.add_parser("show", help="Show a trace entry")
    trace_show.add_argument("trace_id", help="Trace id to inspect")
    trace_show.add_argument("--json", action="store_true", help="JSON output")
    trace_show.set_defaults(func=_cmd_trace_show)

    trace_timeline = trace_sub.add_parser(
        "timeline", help="Show trace entries in chronological order"
    )
    trace_timeline.add_argument(
        "--contains", default=None, help="Filter observations by substring"
    )
    trace_timeline.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    trace_timeline.add_argument("--json", action="store_true", help="JSON output")
    trace_timeline.set_defaults(func=_cmd_trace_timeline)

    codebase = sub.add_parser(
        "codebase", help="Inspect the current codebase graph and refactor impact"
    )
    codebase_sub = codebase.add_subparsers(dest="codebase_cmd", required=True)

    codebase_graph = codebase_sub.add_parser("graph", help="Show the codebase graph")
    codebase_graph.add_argument(
        "--root", default=None, help="Root directory to analyze (default: cwd)"
    )
    codebase_graph.add_argument(
        "--no-symbols", action="store_true", help="Skip symbol nodes in the graph"
    )
    codebase_graph.add_argument("--json", action="store_true", help="JSON output")
    codebase_graph.set_defaults(func=_cmd_codebase_graph)

    codebase_impact = codebase_sub.add_parser(
        "impact", help="Show immediate refactor impact for a file path"
    )
    codebase_impact.add_argument("path", help="File path to inspect")
    codebase_impact.add_argument(
        "--root", default=None, help="Root directory to analyze (default: cwd)"
    )
    codebase_impact.add_argument(
        "--no-symbols", action="store_true", help="Skip symbol nodes in the graph"
    )
    codebase_impact.add_argument("--json", action="store_true", help="JSON output")
    codebase_impact.set_defaults(func=_cmd_codebase_impact)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
