#!/usr/bin/env python3
"""Phase-C C21: resolve a user-facing skill description per OMNI_SKILL_LANG.

Skills keep their executable logic in SKILL.md (English). Optional
translations live at skills/<name>/translations/<lang>.md and override
the user-facing frontmatter fields (description, argument-hint) plus the
<Purpose> body.

    $ OMNI_SKILL_LANG=es python3 scripts/skill_i18n.py resolve omni-plan
    {
      "name": "omni-plan",
      "description": "Planificación estratégica con flujo opcional de entrevista",
      ...
    }

stdlib only; tolerant of malformed translation files (falls back to
English).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_LANG = "en"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter, body). Malformed input → ({}, full text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    block = text[3:end]
    body = text[end + 4:]
    data: dict[str, str] = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2).strip()
    return data, body


def _skill_path(skill_name: str) -> Path:
    return _REPO_ROOT / "skills" / skill_name / "SKILL.md"


def _translation_path(skill_name: str, lang: str) -> Path:
    return _REPO_ROOT / "skills" / skill_name / "translations" / f"{lang}.md"


def resolve(skill_name: str, lang: str | None = None) -> dict[str, Any]:
    """Return the localised frontmatter + body for *skill_name*.

    Falls back to the English SKILL.md when:
    - *lang* is None/empty,
    - *lang* is "en",
    - the translation file is missing,
    - the translation file fails to parse.
    """
    base = _skill_path(skill_name)
    if not base.exists():
        raise FileNotFoundError(f"skill not found: {skill_name}")
    base_fm, base_body = _parse_frontmatter(base.read_text(encoding="utf-8"))
    resolved: dict[str, Any] = {
        "name": skill_name,
        "lang": DEFAULT_LANG,
        "description": base_fm.get("description", ""),
        "argument-hint": base_fm.get("argument-hint", ""),
        "body": base_body,
    }
    lang = (lang or os.environ.get("OMNI_SKILL_LANG") or DEFAULT_LANG).strip()
    if not lang or lang == DEFAULT_LANG:
        return resolved
    tr = _translation_path(skill_name, lang)
    if not tr.exists():
        return resolved
    try:
        tr_fm, tr_body = _parse_frontmatter(tr.read_text(encoding="utf-8"))
    except Exception:
        return resolved
    if tr_fm.get("description"):
        resolved["description"] = tr_fm["description"]
    if tr_fm.get("argument-hint"):
        resolved["argument-hint"] = tr_fm["argument-hint"]
    if tr_body:
        resolved["body"] = tr_body
    resolved["lang"] = lang
    return resolved


def list_translations(skill_name: str) -> list[str]:
    """Return the sorted list of language codes with translations on disk."""
    tr_dir = _REPO_ROOT / "skills" / skill_name / "translations"
    if not tr_dir.is_dir():
        return []
    out: list[str] = []
    for path in sorted(tr_dir.iterdir()):
        if path.suffix == ".md" and path.stem:
            out.append(path.stem)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve skill metadata for the current OMNI_SKILL_LANG."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("resolve")
    r.add_argument("skill")
    r.add_argument("--lang", default=None)

    ls = sub.add_parser("list-translations")
    ls.add_argument("skill")

    args = parser.parse_args(argv)
    if args.command == "resolve":
        try:
            data = resolve(args.skill, lang=args.lang)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    if args.command == "list-translations":
        for lang in list_translations(args.skill):
            print(lang)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
