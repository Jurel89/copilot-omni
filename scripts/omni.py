#!/usr/bin/env python3
"""omni — Copilot Omni user-facing CLI.

Pure-Python, stdlib-only. Provides:
  omni init           Scaffold .omni/ in the current project
  omni doctor         Check environment (python, copilot CLI, MCP server)
  omni status         Show current run and mode state
  omni plugin-install Install the plugin into the local Copilot CLI
  omni mcp            Launch the MCP server in the foreground (stdio)
  omni version        Print version
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

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
    print(f"python:        {sys.version.split()[0]:<12} "
          + ("OK" if py_ok else "FAIL (need >=3.9)"))
    ok = ok and py_ok

    copilot = shutil.which("copilot")
    copilot_ok = copilot is not None
    print(f"copilot CLI:   {copilot or 'NOT FOUND':<40} "
          + ("OK" if copilot_ok else "FAIL (install @github/copilot or add to PATH)"))
    ok = ok and copilot_ok

    root = _plugin_root()
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest_ok = manifest.exists()
    print(f"plugin.json:   {str(manifest):<40} "
          + ("OK" if manifest_ok else "FAIL"))
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

    cmds = list((root / "commands").glob("*.md"))
    print(f"commands:      {len(cmds)} " + ("OK" if len(cmds) >= 6 else "FAIL"))
    ok = ok and (len(cmds) >= 6)

    print(f"platform:      {platform.system()} {platform.release()}")
    home = Path(os.environ.get("OMNI_HOME") or (Path.home() / ".omni"))
    print(f"omni_home:     {home}")
    home.mkdir(parents=True, exist_ok=True)

    # WS3: router config check
    _doctor_router(root, home, verbose=getattr(args, "verbose", False))

    # WS4: model category fallback check
    strict = getattr(args, "strict", False)
    categories_ok = _doctor_categories(root, strict=strict)
    if strict and not categories_ok:
        ok = False

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

    return 0 if ok else 1


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


def _doctor_categories(root: Path, *, strict: bool = False) -> bool:
    """WS4: resolve each model category and report; warn on drift.

    Returns True if all categories resolve to their primary (or check failed).
    Returns False only when strict=True and any category used a fallback.
    """
    resolver_path = root / "scripts" / "category_resolver.py"
    if not resolver_path.exists():
        print("models:        category_resolver.py not found — skipping")
        return True

    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("category_resolver", resolver_path)
        if spec is None or spec.loader is None:
            print("models:        could not load category_resolver — skipping")
            return True
        resolver = _ilu.module_from_spec(spec)
        spec.loader.exec_module(resolver)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"models:        WARN: could not import category_resolver: {exc}")
        return True

    all_ok = True
    all_failed = True  # track if every check failed (CLI not present)

    for cat in sorted(resolver.known_categories()):
        try:
            res = resolver.resolve(cat)
        except Exception as exc:
            print(f"models:        {cat}: WARN resolve error: {exc}")
            continue

        check = res.get("available_check", "?")
        model = res.get("model", "?")
        primary = res.get("primary", "?")
        tried = res.get("fallbacks_tried", [])

        if check != "failed":
            all_failed = False

        if tried:
            status = f"DRIFT (fallback: {model}; primary: {primary}; tried: {tried})"
            print(f"models:        {cat} → {status}")
            if strict:
                all_ok = False
        else:
            check_note = f"; check: {check}" if check != "ok" else ""
            print(f"models:        {cat} → {model} (primary{check_note})")

    if all_failed:
        print("models:        WARN: availability check failed for all categories "
              "(copilot models subcommand may not be available) — assuming primary OK")

    return all_ok


def _doctor_router(root: Path, home: Path, *, verbose: bool = False) -> None:
    """WS3: check and display router configuration."""
    config_path = root / ".omni" / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    router_cfg = config.get("router", {})
    threshold = router_cfg.get("vagueness_threshold", None)

    if threshold is None:
        # Populate default
        router_cfg["vagueness_threshold"] = 0.4
        config["router"] = router_cfg
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            threshold = 0.4
            print(f"router:        vagueness_threshold=0.4 (defaulted OK)")
        except Exception as exc:
            print(f"router:        WARN: could not write default threshold: {exc}")
    else:
        print(f"router:        vagueness_threshold={threshold} OK")

    if not verbose:
        return

    # Verbose: show last-N router decisions from MCP state
    print("\n--- router decisions (last 5) ---")
    try:
        import importlib.util
        state_path = root / "scripts" / "router_state.py"
        spec = importlib.util.spec_from_file_location("router_state", state_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            result = mod.read_pipeline_state(mode="router")
            if result is None:
                print("  (no router state found or MCP unavailable)")
            else:
                print(f"  decision:  {result.get('decision', '?')}")
                print(f"  score:     {result.get('classifier_score', '?')}")
                print(f"  excerpt:   {str(result.get('prompt_excerpt', ''))[:80]}")
                print(f"  ts:        {result.get('ts', '?')}")
    except Exception as exc:
        print(f"  (could not read router state: {exc})")


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
                e for e in acquired
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
                ralplan_runs.append({
                    "name": run_dir.name,
                    "state": data.get("state", "unknown"),
                    "cycle": data.get("current_cycle", 0),
                    "verdict": data.get("last_verdict"),
                    "mtime": sp.stat().st_mtime,
                })
            except Exception:
                pass
    except Exception as exc:
        print(f"ralplan runs:  WARN: could not read runs: {exc}")
        return True

    if not ralplan_runs:
        print("ralplan runs:  (none)")
        return True

    active = [r for r in ralplan_runs if r["state"] not in ("converged", "unconverged", "rejected", "cancelled")]
    print(f"ralplan runs:  {len(ralplan_runs)} total, {len(active)} active")
    for r in ralplan_runs[-5:]:
        print(f"  {r['name']}: state={r['state']}, cycle={r['cycle']}, verdict={r['verdict']}")

    if not strict:
        return True

    # --strict: warn if any run has been awaiting-input for >24h
    now = _time.time()
    stale = [
        r for r in ralplan_runs
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
                manifest_data = _json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
                workers = manifest_data.get("workers", [])
                team_runs.append({
                    "name": run_dir.name,
                    "state": status_data.get("state", "unknown"),
                    "worker_count": len(workers),
                    "mtime": sp.stat().st_mtime,
                })
            except Exception:
                pass
    except Exception as exc:
        print(f"team runs:     WARN: could not read team runs: {exc}")
        return True

    if not team_runs:
        print("team runs:     (none)")
        return True

    active = [r for r in team_runs if r["state"] not in ("cleaned", "cancelled", "done")]
    print(f"team runs:     {len(team_runs)} total, {len(active)} active")
    for r in team_runs[-5:]:
        print(f"  {r['name']}: state={r['state']}, workers={r['worker_count']}")

    if not strict:
        return True

    # --strict: warn if any team has been in state='dispatched' for >24h
    now = _time.time()
    stale = [
        r for r in team_runs
        if r["state"] == "dispatched" and (now - r["mtime"]) > 86400
    ]
    if stale:
        print(
            f"team runs:     FAIL (--strict): {len(stale)} team run(s) in"
            " state='dispatched' for >24h (likely abandoned collection)"
        )
        for r in stale:
            age_h = (now - r["mtime"]) / 3600
            print(f"  {r['name']}: dispatched for {age_h:.1f}h, workers={r['worker_count']}")
        return False

    return True


def _cmd_init(args: argparse.Namespace) -> int:
    cwd = Path(args.path or os.getcwd()).resolve()
    target = cwd / ".omni"
    target.mkdir(parents=True, exist_ok=True)
    config = target / "config.json"
    if not config.exists() or args.force:
        config.write_text(json.dumps({
            "version": 1,
            "project_name": cwd.name,
            "profile": args.profile,
            "memory_scope": "project",
        }, indent=2), encoding="utf-8")
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
        print(f"\nruns:")
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
    "verify":  ("plan.md",),
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
    return [str(run_dir / name) for name in required
            if not (run_dir / name).exists()]


_GATE_ARTIFACT_REQUIRED: dict[str, tuple[str, ...]] = {
    # Each intermediate gate requires the same artifacts as the target gate
    # that was requested from CLI — e.g. `omni execute` enforces spec.json,
    # but `omni verify` should still require spec.json at the implicit
    # execute step so we never silently jump through a gate without its
    # artifact being present.
    "plan":    ("spec.json",),   # plan lands once a spec exists
    "execute": ("spec.json",),
    "verify":  ("plan.md",),
    "done":    ("plan.md",),
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
    target_idx = order.index(target)
    current_idx = order.index(current)
    if current_idx >= target_idx:
        sm.advance(run_dir, target, note=note)
        return
    for intermediate in order[current_idx + 1:target_idx + 1]:
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
        print("error: artifact-first lifecycle — missing required artifacts:",
              file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2
    sm = _load_state_machine()
    if sm is None:
        print("warn: state_machine.py unavailable — skipping gate advance",
              file=sys.stderr)
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
        print("error: artifact-first lifecycle — missing required artifacts:",
              file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2
    sm = _load_state_machine()
    if sm is None:
        print("warn: state_machine.py unavailable — skipping gate advance",
              file=sys.stderr)
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
    if args.kind in ("commands", "all"):
        print("\n# Commands")
        for cmd in sorted((root / "commands").glob("*.md")):
            print(f"  - /{cmd.stem}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omni", description="Copilot Omni CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version").set_defaults(func=_cmd_version)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--verbose", action="store_true",
                        help="Show router config and recent decisions")
    doctor.add_argument("--strict", action="store_true",
                        help="Fail if any model category resolves to a fallback (signals drift)")
    doctor.add_argument("--gc", action="store_true",
                        help="Garbage-collect .omni/runs/ directories older than TTL (dry-run)")
    doctor.add_argument("--gc-apply", action="store_true",
                        help="With --gc, actually delete stale runs (default is dry-run)")
    doctor.set_defaults(func=_cmd_doctor)

    init = sub.add_parser("init", help="Scaffold .omni/ in the current project")
    init.add_argument("--path", default=None)
    init.add_argument("--profile", default="standard",
                      choices=["strict", "standard", "permissive"])
    init.add_argument("--force", action="store_true")
    init.add_argument("--no-agents-md", action="store_true")
    init.set_defaults(func=_cmd_init)

    sub.add_parser("status").set_defaults(func=_cmd_status)

    plug = sub.add_parser("plugin-install",
                          help="Install this plugin into the local Copilot CLI")
    plug.add_argument("--source", default=None,
                      help="Source path or owner/repo (default: this checkout)")
    plug.set_defaults(func=_cmd_plugin_install)

    mcp = sub.add_parser("mcp", help="Run the MCP server in stdio mode")
    mcp.set_defaults(func=_cmd_mcp)

    # Phase-C C20: artifact-first lifecycle gates.
    execute = sub.add_parser(
        "execute",
        help="Enforce the execute gate: require spec.json, advance state machine",
    )
    execute.add_argument("run_id",
                         help="run-id or absolute path to the run directory")
    execute.set_defaults(func=_cmd_execute)

    verify = sub.add_parser(
        "verify",
        help="Enforce the verify gate: require plan.md, advance state machine",
    )
    verify.add_argument("run_id",
                        help="run-id or absolute path to the run directory")
    verify.set_defaults(func=_cmd_verify)

    lst = sub.add_parser("list", help="List installed skills/agents/commands")
    lst.add_argument("kind", choices=["skills", "agents", "commands", "all"],
                     nargs="?", default="all")
    lst.set_defaults(func=_cmd_list)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
