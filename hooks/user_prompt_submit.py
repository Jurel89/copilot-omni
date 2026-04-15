#!/usr/bin/env python3
"""User-prompt-submit hook — inject lightweight skill hints when keywords match.

Never blocks. Adds a system-reminder pointing at the right skill when the
user typed a known trigger. Budget: <50ms, stdlib only.
"""
from __future__ import annotations

import json
import re
import sys

TRIGGERS = {
    "autopilot": r"\b(autopilot|full\s*auto|handle\s*it\s*all)\b",
    "ralph": r"\bralph\b",
    "ultrawork": r"\b(ultrawork|parallel\s+work)\b",
    "team": r"\b(team\s+mode|/team)\b",
    "plan": r"\b(plan(?:ning)?|/plan)\b",
    "debug": r"\b(debug|diagnose)\b",
    "verify": r"\b(verify|verification)\b",
    "wiki": r"\b(wiki|knowledge\s+base)\b",
    "remember": r"\b(remember|save\s+this)\b",
    "ship": r"\b(ship\s+it|open\s+pr|create\s+pull\s+request)\b",
}


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        event = {}
    prompt = str(event.get("prompt", "")).lower()
    matched = [name for name, pat in TRIGGERS.items()
               if re.search(pat, prompt, re.IGNORECASE)]
    if matched:
        hint = (
            "copilot-omni: matched skill trigger(s): "
            + ", ".join(matched)
            + ". Consider invoking the corresponding skill via /skills."
        )
        sys.stdout.write(json.dumps({"additionalContext": hint}))
    else:
        sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
