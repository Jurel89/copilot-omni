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

    return 0 if ok else 1


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
