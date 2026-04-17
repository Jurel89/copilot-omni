#!/usr/bin/env python3
"""category_resolver — semantic model-category passthrough for copilot-omni.

This module used to shell out to ``copilot models --json`` to probe model
availability and pick a fallback on drift. That subcommand does not exist in
GitHub Copilot CLI, so the probe always failed and the feature was cosmetic.

**v2.1.0**: model selection is owned by the Copilot CLI host via the
``/model`` slash command. ``resolve()`` is now a pure mapping from a logical
category (``quick`` / ``deep`` / ``ultrabrain``) to whatever concrete model
string is configured for that category in ``.omni/config.json``. No subprocess
calls, no availability probing, no fallback chain.

The function signatures are preserved so existing callers (``scripts/omni.py``,
``scripts/subagent.py``) and the slimmed-down passthrough contract tests keep
working.

Contract
--------
- Stdlib only. No third-party dependencies. No subprocess.
- ``resolve()`` never raises; always returns a resolution dict with the keys
  ``category``, ``model``, ``primary``, ``fallbacks_tried`` (always empty),
  and ``available_check`` (always ``"skipped"``).
- Unknown categories return ``model=None`` so callers can fall back to the
  Copilot CLI default model.

Usage (CLI)
-----------
    python3 scripts/category_resolver.py quick
    python3 scripts/category_resolver.py --json quick
    python3 scripts/category_resolver.py --known
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_KNOWN_CATEGORIES: frozenset[str] = frozenset({"quick", "deep", "ultrabrain"})

# Default category → model mapping. These are Copilot-CLI-hosted model IDs.
# Users can override any entry in `.omni/config.json` under the `categories`
# key. If Copilot CLI does not expose the chosen model for the active
# subscription, the user-side `/model` command takes precedence at runtime.
_DEFAULT_CONFIG: dict = {
    "quick": {"model": "claude-haiku-4-5"},
    "deep": {"model": "claude-sonnet-4.5"},
    "ultrabrain": {"model": "gpt-5"},
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / ".omni" / "config.json"


def known_categories() -> frozenset[str]:
    return _KNOWN_CATEGORIES


def load_default_categories() -> dict:
    """Return a fresh copy of the built-in default mapping."""
    return {cat: dict(entry) for cat, entry in _DEFAULT_CONFIG.items()}


def load_config(path: Optional[Path] = None) -> dict:
    """Merge the default mapping with user overrides from .omni/config.json."""
    base = load_default_categories()
    cfg_path = path or _DEFAULT_CONFIG_PATH
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return base

    overrides = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(overrides, dict):
        return base

    for cat, entry in overrides.items():
        if cat not in _KNOWN_CATEGORIES or not isinstance(entry, dict):
            continue
        merged = dict(base.get(cat, {}))
        if "model" in entry:
            merged["model"] = str(entry["model"])
        base[cat] = merged
    return base


def resolve(
    category: str,
    *,
    config: Optional[dict] = None,
) -> dict:
    """Resolve *category* to a concrete model string.

    No subprocess calls. No availability probing. The returned dict shape is
    preserved for backward compatibility with callers that expect the v1
    fields (``primary``, ``fallbacks_tried``, ``available_check``).
    """
    cfg = config if config is not None else load_config()
    entry = cfg.get(category) if isinstance(cfg, dict) else None
    if not isinstance(entry, dict):
        return {
            "category": category,
            "model": None,
            "primary": None,
            "fallbacks_tried": [],
            "available_check": "skipped",
        }
    primary = str(entry.get("model")) if entry.get("model") else None
    return {
        "category": category,
        "model": primary,
        "primary": primary,
        "fallbacks_tried": [],
        "available_check": "skipped",
    }


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="category_resolver",
        description="Resolve a semantic model category to a model string.",
    )
    parser.add_argument("category", nargs="?", help="quick | deep | ultrabrain")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--known", action="store_true", help="print known categories and exit"
    )
    args = parser.parse_args(argv)

    if args.known:
        for cat in sorted(_KNOWN_CATEGORIES):
            print(cat)
        return 0

    if not args.category:
        parser.error("category is required (or pass --known)")

    res = resolve(args.category)
    if args.json:
        print(json.dumps(res, indent=2, sort_keys=True))
    else:
        model = res.get("model") or "(unset — using Copilot CLI default)"
        print(f"{res['category']}: {model}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
