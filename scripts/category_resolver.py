#!/usr/bin/env python3
"""category_resolver — Semantic model category resolution for copilot-omni.

Maps the three logical tiers (quick / deep / ultrabrain) to concrete model
strings drawn from the GitHub Copilot subscription menu, with per-category
fallback chains when the primary model is unavailable.

Contract
--------
- Stdlib only.  No third-party dependencies.
- resolve() NEVER raises; it always returns a resolution dict.
- If the availability check fails, the resolver assumes the primary is
  available and proceeds (fail-open, not fail-closed).

Usage (CLI)
-----------
    python3 scripts/category_resolver.py quick
    python3 scripts/category_resolver.py --json quick
    python3 scripts/category_resolver.py --known
    python3 scripts/category_resolver.py --check
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

_KNOWN_CATEGORIES: frozenset[str] = frozenset({"quick", "deep", "ultrabrain"})

_DEFAULT_CONFIG: dict = {
    "quick": {
        "model": "claude-haiku-4-5",
        "fallbacks": ["gpt-5-mini", "claude-sonnet-4.5"],
    },
    "deep": {
        "model": "claude-sonnet-4.5",
        "fallbacks": ["gpt-5", "gemini-2.5-pro"],
    },
    "ultrabrain": {
        "model": "claude-opus-4-6",
        "fallbacks": ["gpt-5-codex", "gemini-2.5-pro"],
    },
}

# Default location of .omni/config.json relative to this script's repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / ".omni" / "config.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def known_categories() -> set[str]:
    """Return the set of valid category names."""
    return set(_KNOWN_CATEGORIES)


def load_default_categories() -> dict:
    """Return the built-in default category definitions.

    Returns a deep copy so callers cannot mutate the module-level constant.
    """
    return json.loads(json.dumps(_DEFAULT_CONFIG))


def load_config(path: Optional[Path] = None) -> dict:
    """Load .omni/config.json and return the merged category definitions.

    If *path* is None, uses the default location (_DEFAULT_CONFIG_PATH).
    If the file does not exist or cannot be parsed, returns built-in defaults.

    The returned dict maps each category name to {model: str, fallbacks: [str]}.
    User config is merged over built-in defaults (user wins on overlap).
    """
    config_path = path or _DEFAULT_CONFIG_PATH
    base = load_default_categories()

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        return base

    user_models = data.get("models", {})
    if not isinstance(user_models, dict):
        return base

    for cat, entry in user_models.items():
        if not isinstance(entry, dict):
            # Flat string or malformed — skip; omni doctor warns separately
            continue
        merged: dict = dict(base.get(cat, {}))
        if "model" in entry:
            merged["model"] = str(entry["model"])
        if "fallbacks" in entry:
            fallbacks = entry["fallbacks"]
            if isinstance(fallbacks, list):
                merged["fallbacks"] = [str(f) for f in fallbacks]
        base[cat] = merged

    return base


def _default_availability_checker(model_name: str) -> tuple[bool, str]:
    """Shell out to `copilot models --json` to check availability.

    Returns (is_available: bool, check_status: str).
    check_status is one of "ok", "skipped", "failed".

    If the subcommand does not exist or the call fails, returns
    (True, "failed") so the resolver fails open.
    """
    try:
        result = subprocess.run(
            ["copilot", "models", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return True, "failed"
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return True, "failed"

        # Tolerate both list-of-strings and list-of-dicts formats
        models: list = []
        if isinstance(data, list):
            models = data
        elif isinstance(data, dict):
            # e.g. {"models": [...]}
            models = data.get("models", [])

        if not models:
            return True, "skipped"

        available_names: set[str] = set()
        for item in models:
            if isinstance(item, str):
                available_names.add(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("model")
                if name:
                    available_names.add(str(name))

        if not available_names:
            return True, "skipped"

        is_available = model_name in available_names
        return is_available, "ok"

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # copilot CLI not found or timed out — fail open
        return True, "failed"


def resolve(
    category: str,
    *,
    config: Optional[dict] = None,
    availability_checker: Optional[Callable[[str], bool]] = None,
) -> dict:
    """Resolve *category* to a concrete model string.

    Parameters
    ----------
    category:
        One of "quick", "deep", "ultrabrain".  An unknown category causes
        a resolution with available_check="failed" and the model set to the
        category name itself (signals misconfiguration without raising).
    config:
        Pre-loaded category config dict.  If None, load_config() is called
        to read .omni/config.json (falling back to built-in defaults).
    availability_checker:
        Optional callable ``(model_name: str) -> bool``.  If provided, it is
        called for each candidate in the fallback walk.  If not provided, the
        default checker shells out to ``copilot models --json``.

    Returns
    -------
    dict with keys:
        category          str   — the requested category
        model             str   — chosen concrete model
        primary           str   — configured primary for this category
        fallbacks_tried   list  — fallback names attempted (in order); empty
                                  if primary was chosen
        available_check   str   — "ok" | "skipped" | "failed"
        ts                str   — ISO-8601 UTC timestamp
    """
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if config is None:
        config = load_config()

    if category not in _KNOWN_CATEGORIES:
        return {
            "category": category,
            "model": category,
            "primary": category,
            "fallbacks_tried": [],
            "available_check": "failed",
            "ts": ts,
        }

    cat_cfg = config.get(category, _DEFAULT_CONFIG.get(category, {}))
    primary: str = cat_cfg.get("model", "")
    fallbacks: list[str] = cat_cfg.get("fallbacks", [])

    if not primary:
        # Degenerate config — return built-in default primary
        primary = _DEFAULT_CONFIG[category]["model"]
        fallbacks = _DEFAULT_CONFIG[category]["fallbacks"]

    # Wrap availability_checker if provided (it must return bool; we adapt to
    # the internal (bool, str) tuple used by _default_availability_checker).
    def _check(model: str) -> tuple[bool, str]:
        if availability_checker is not None:
            try:
                return bool(availability_checker(model)), "ok"
            except Exception:
                return True, "failed"
        return _default_availability_checker(model)

    # Check primary
    is_avail, check_status = _check(primary)
    if is_avail:
        return {
            "category": category,
            "model": primary,
            "primary": primary,
            "fallbacks_tried": [],
            "available_check": check_status,
            "ts": ts,
        }

    # Walk fallbacks
    fallbacks_tried: list[str] = []
    last_check_status = check_status
    for fb in fallbacks:
        fb_avail, fb_status = _check(fb)
        last_check_status = fb_status
        fallbacks_tried.append(fb)
        if fb_avail:
            return {
                "category": category,
                "model": fb,
                "primary": primary,
                "fallbacks_tried": fallbacks_tried,
                "available_check": last_check_status,
                "ts": ts,
            }

    # All exhausted — return primary anyway (fail-open)
    return {
        "category": category,
        "model": primary,
        "primary": primary,
        "fallbacks_tried": fallbacks_tried,
        "available_check": last_check_status,
        "ts": ts,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _fmt_resolution(res: dict) -> str:
    tried = res["fallbacks_tried"]
    if tried:
        tried_str = ", ".join(tried)
        return (
            f"{res['category']} → {res['model']}"
            f"  (primary: {res['primary']}; fallbacks tried: [{tried_str}];"
            f" check: {res['available_check']})"
        )
    return (
        f"{res['category']} → {res['model']}"
        f"  (primary; check: {res['available_check']})"
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="category_resolver",
        description="Resolve a copilot-omni model category to a concrete model string.",
    )
    parser.add_argument(
        "category",
        nargs="?",
        help="Category to resolve: quick | deep | ultrabrain",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Print the full resolution dict as JSON",
    )
    parser.add_argument(
        "--known",
        action="store_true",
        help="List the known category names and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Resolve all known categories and report; non-zero exit if any uses a fallback",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to .omni/config.json (default: auto-detect from repo root)",
    )
    args = parser.parse_args(argv)

    if args.known:
        for cat in sorted(known_categories()):
            print(cat)
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    if args.check:
        any_fallback = False
        for cat in sorted(known_categories()):
            res = resolve(cat, config=config)
            print(_fmt_resolution(res))
            if res["fallbacks_tried"]:
                any_fallback = True
        return 1 if any_fallback else 0

    if not args.category:
        parser.print_help()
        return 2

    cat = args.category
    if cat not in _KNOWN_CATEGORIES:
        print(f"error: unknown category '{cat}'. Known: {', '.join(sorted(_KNOWN_CATEGORIES))}", file=sys.stderr)
        return 1

    res = resolve(cat, config=config)

    if args.output_json:
        print(json.dumps(res, indent=2))
    else:
        print(res["model"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
