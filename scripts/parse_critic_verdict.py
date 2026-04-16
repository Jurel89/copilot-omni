#!/usr/bin/env python3
"""parse_critic_verdict — extract the VERDICT line from a critic review file.

Reads a critic-review-v<n>.md from stdin or a file path argument. Finds the LAST
line matching ``^VERDICT: (APPROVE|REVISE|REJECT)$`` (case-sensitive), prints just
the verdict word (e.g. ``APPROVE``), and exits 0.

Exits 1 if no valid verdict line is found.

Used by the ralplan consensus loop recipe (step 3d) to parse the Critic verdict
without having the LLM re-read the entire review file.

Usage
-----
    python3 scripts/parse_critic_verdict.py critic-review-v1.md
    python3 scripts/parse_critic_verdict.py < critic-review-v1.md
    cat critic-review-v1.md | python3 scripts/parse_critic_verdict.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_VERDICT_RE = re.compile(r"^VERDICT:\s*(APPROVE|REVISE|REJECT)\s*$")

_VALID_VERDICTS = frozenset({"APPROVE", "REVISE", "REJECT"})

# Matches opening and closing markdown code fences (``` or ~~~, with optional language tag)
_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})\S*\s*$")
_FENCE_CLOSE_RE = re.compile(r"^(`{3,}|~{3,})\s*$")


def _strip_code_fences(text: str) -> str:
    """Remove content inside markdown code fences from *text*.

    T7 fix: LLM-generated reviews sometimes illustrate what a VERDICT line
    should look like inside a fenced code block.  We must not treat VERDICT
    lines inside fences as authoritative.

    Returns the text with all fenced-block content replaced by empty lines so
    that line numbers are preserved.
    """
    result: list[str] = []
    in_fence = False
    fence_marker: str = ""

    for line in text.splitlines():
        stripped = line.rstrip()
        if not in_fence:
            m = _FENCE_OPEN_RE.match(stripped)
            if m:
                in_fence = True
                fence_marker = m.group(1)[0] * 3  # normalise to 3 chars
                result.append("")  # replace fence line with blank
            else:
                result.append(line)
        else:
            # Look for closing fence with same character
            close = _FENCE_CLOSE_RE.match(stripped)
            if close and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            result.append("")  # blank out all lines inside fence

    return "\n".join(result)


def extract_verdict(text: str) -> str | None:
    """Return the LAST valid verdict word from *text*, or None if absent.

    T7 fix: strips markdown code fences before scanning so that VERDICT lines
    inside illustrative code blocks are not mistaken for the authoritative verdict.

    Parameters
    ----------
    text:
        Full content of a critic-review file.

    Returns
    -------
    ``"APPROVE"``, ``"REVISE"``, ``"REJECT"``, or ``None``.
    """
    stripped = _strip_code_fences(text)
    last: str | None = None
    for line in stripped.splitlines():
        m = _VERDICT_RE.match(line.rstrip())
        if m:
            last = m.group(1)
    return last


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Usage::

        python3 scripts/parse_critic_verdict.py [file]

    If *file* is given, reads from that path; otherwise reads stdin.
    Prints the verdict word (APPROVE / REVISE / REJECT) on success.
    Exits 0 on success, 1 if no verdict found.
    """
    args = sys.argv[1:] if argv is None else argv

    if args:
        path = Path(args[0])
        if not path.exists():
            print(f"error: file not found: {path}", file=sys.stderr)
            return 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"error: could not read {path}: {exc}", file=sys.stderr)
            return 1
    else:
        # Read from stdin
        try:
            text = sys.stdin.read()
        except KeyboardInterrupt:
            return 1

    verdict = extract_verdict(text)
    if verdict is None:
        print("error: no VERDICT line found in input", file=sys.stderr)
        return 1

    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
