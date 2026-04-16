#!/usr/bin/env python3
"""Subagent helper — invoke a specialized agent via `copilot -p ... --agent <name>`.

This is the Copilot-CLI equivalent of Claude Code's `Task(subagent_type=...)`.
Ported skills call this module to spawn an agent and capture its output.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def _load_resolver():
    """Dynamically import category_resolver from the scripts/ directory.

    Returns the module, or None if it cannot be loaded (graceful degradation).
    """
    here = Path(__file__).resolve().parent
    resolver_path = here / "category_resolver.py"
    if not resolver_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("category_resolver", resolver_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


def _resolve_category(category: str) -> Optional[str]:
    """Resolve a semantic category to a concrete model string.

    Returns the model string, or None if resolution fails (callers treat None
    as 'no model override').
    """
    resolver = _load_resolver()
    if resolver is None:
        print(
            f"warning: category_resolver not found; ignoring --category {category!r}",
            file=sys.stderr,
        )
        return None
    known = resolver.known_categories()
    if category not in known:
        print(
            f"error: unknown category '{category}'. Known: {', '.join(sorted(known))}",
            file=sys.stderr,
        )
        return None
    res = resolver.resolve(category)
    return res["model"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_agent(
    name: str,
    prompt: str,
    allow_all: Optional[bool] = None,
    model: Optional[str] = None,
    category: Optional[str] = None,
    timeout: int = 1800,
) -> int:
    """Invoke a Copilot subagent.

    Category resolution
    -------------------
    If *category* is given and *model* is not, the category is resolved to a
    concrete model via category_resolver.resolve() and passed as --model.
    If both *category* and *model* are given, *model* wins (explicit beats
    implicit — the category is silently ignored).
    If neither is given, no --model flag is passed to copilot.
    """
    copilot = shutil.which("copilot")
    if not copilot:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2
    if allow_all is None:
        # Default OFF unless OMNI_SUBAGENT_ALLOW_ALL=1 — corporate-safe default
        allow_all = _env_bool("OMNI_SUBAGENT_ALLOW_ALL", False)

    # Resolve category → model only when --model is not explicitly given
    effective_model = model
    if effective_model is None and category is not None:
        effective_model = _resolve_category(category)
        if effective_model is None:
            # Unknown category — surface the error, don't proceed
            return 1

    cmd = [copilot, "-p", prompt, "--agent", name]
    if allow_all:
        cmd.append("--allow-all")
    if effective_model:
        cmd.extend(["--model", effective_model])
    try:
        result = subprocess.run(cmd, timeout=timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"error: agent {name!r} timed out after {timeout}s", file=sys.stderr)
        return 124


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Copilot Omni subagent")
    parser.add_argument("name", help="Agent name (matches agents/<name>.md)")
    parser.add_argument("prompt", help="Task prompt to send the agent")
    parser.add_argument(
        "--model",
        default=None,
        help="Concrete model name to pass to copilot --model. Overrides --category.",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="CATEGORY",
        help=(
            "Semantic model category (quick|deep|ultrabrain). "
            "Resolved to a concrete model via category_resolver. "
            "Ignored when --model is also given."
        ),
    )
    parser.add_argument("--allow-all", dest="allow_all", action="store_true",
                        help="Pass --allow-all to the spawned copilot session")
    parser.add_argument("--no-allow-all", dest="allow_all", action="store_false",
                        help="Require the spawned session to ask for permissions (default)")
    parser.set_defaults(allow_all=None)
    args = parser.parse_args()
    return run_agent(
        args.name,
        args.prompt,
        allow_all=args.allow_all,
        model=args.model,
        category=args.category,
    )


if __name__ == "__main__":
    sys.exit(main())
