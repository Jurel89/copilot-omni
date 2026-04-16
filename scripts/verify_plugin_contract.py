#!/usr/bin/env python3
"""Phase-B plugin-contract verifier.

Grows with each Phase-B workstream. At Wave 0 only `--check-rename-stub`
and `--list-checks` exist; later waves append checks by adding functions
to CHECKS and wiring them into main().

Every check returns (ok: bool, messages: list[str]). Exit code is 0 on
all-green, 1 on any failure.

Contract: stdlib only. No third-party deps. Idempotent.

Usage:
    python3 scripts/verify_plugin_contract.py --all
    python3 scripts/verify_plugin_contract.py --check-rename
    python3 scripts/verify_plugin_contract.py --check-rename-stub
    python3 scripts/verify_plugin_contract.py --list-checks
    python3 scripts/verify_plugin_contract.py --list-rename-exemptions
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable, Tuple

ROOT = Path(__file__).resolve().parent.parent

CheckResult = Tuple[bool, list]

# ---------------------------------------------------------------------------
# Allowlisted paths — these files legitimately cite upstream project names.
# Paths are relative to ROOT and support fnmatch-style glob prefix matching.
# ---------------------------------------------------------------------------
ALLOWLIST_PATHS: tuple[str, ...] = (
    ".omni/research/",
    ".omni/plans/phase-b-master-plan-v1-backup.md",
    ".omni/plans/phase-b-critique-",   # prefix match
    ".omni/plans/phase-b-master-plan.md",
    "docs/ADR/ADR-0000",               # prefix match
    # Runtime state dirs — not source files
    ".omc/",
    ".git/",
    # This file defines banned patterns as regex strings; self-allowlisted
    "scripts/verify_plugin_contract.py",
    # WS1 report documents the rename; legitimately cites old names
    ".omni/plans/wave-1-WS1-report.md",
)

# Banned token patterns
BANNED_PATTERNS: tuple[str, ...] = (
    r"oh-my-claudecode",
    r"\.omc/",
    r"omc-",
    r"\bOMC\b",
)

# File extensions to scan (text files only)
SCAN_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt",
    ".cfg", ".sh", ".bash", ".zsh", ".ps1", ".cmd", ".bat",
    ".html", ".rst", ".ini",
})

# Max allowed inline exemptions across the whole tree
MAX_EXEMPTIONS = 10

# Marker pattern for inline allowlist — supports both HTML comments (<!-- -->) and
# shell/gitignore hash comments (# omni-rename-allow: reason)
ALLOW_MARKER_RE = re.compile(
    r"(?:<!--\s*|#\s*)omni-rename-allow\s*:.*?(?:-->|$)",
    re.IGNORECASE,
)


def _is_allowlisted_path(rel: str) -> bool:
    """Return True if this relative path is in the hard allowlist."""
    for prefix in ALLOWLIST_PATHS:
        if rel.startswith(prefix):
            return True
    return False


def _strip_code_fences(lines: list[str]) -> list[str]:
    """Return lines with code-fence blocks replaced by blank lines.

    We blank out lines *inside* fenced blocks (``` ... ```) so that
    tokens inside fences are not flagged. The fence delimiter line itself
    is also blanked so its content does not trigger false positives.
    """
    result: list[str] = []
    in_fence = False
    fence_re = re.compile(r"^(\s*)(```|~~~)")
    for line in lines:
        if fence_re.match(line):
            in_fence = not in_fence
            result.append("")  # blank the fence line
        elif in_fence:
            result.append("")  # blank interior
        else:
            result.append(line)
    return result


def _has_allow_marker_nearby(lines: list[str], line_idx: int, window: int = 3) -> bool:
    """Return True if an omni-rename-allow marker is within `window` lines."""
    start = max(0, line_idx - window)
    end = min(len(lines), line_idx + window + 1)
    for i in range(start, end):
        if ALLOW_MARKER_RE.search(lines[i]):
            return True
    return False


def check_rename() -> CheckResult:
    """Walk the whole tree and verify no banned tokens remain outside allowlisted paths.

    Algorithm:
    1. Walk every file under ROOT.
    2. Skip allowlisted paths, non-text files, and binary files.
    3. Strip markdown code fences from content before scanning.
    4. For each banned token hit, check for an omni-rename-allow marker within 3 lines.
    5. Report exemptions; fail if any residual hit lacks a marker or if exemptions > MAX_EXEMPTIONS.
    """
    compiled = [re.compile(p) for p in BANNED_PATTERNS]
    violations: list[str] = []
    exemptions: list[dict] = []

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if _is_allowlisted_path(rel):
            continue
        if path.suffix not in SCAN_EXTENSIONS and path.suffix != "":
            # Still scan extensionless files that are text (e.g. shebang scripts)
            # but skip binary-ish extensions quickly
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines_raw = raw.splitlines()
        lines = _strip_code_fences(lines_raw)

        for line_idx, line in enumerate(lines):
            for pattern in compiled:
                if pattern.search(line):
                    if _has_allow_marker_nearby(lines_raw, line_idx):
                        exemptions.append({
                            "file": rel,
                            "line": line_idx + 1,
                            "text": lines_raw[line_idx].strip()[:120],
                        })
                    else:
                        violations.append(
                            f"  {rel}:{line_idx + 1}: {lines_raw[line_idx].strip()[:120]}"
                        )
                    break  # only report once per line

    messages: list[str] = []
    ok = True

    if exemptions:
        messages.append(
            f"rename-allow exemptions ({len(exemptions)}/{MAX_EXEMPTIONS}):"
        )
        for e in exemptions:
            messages.append(f"  [exempt] {e['file']}:{e['line']}: {e['text']}")

    if len(exemptions) > MAX_EXEMPTIONS:
        ok = False
        messages.append(
            f"FAIL: too many inline exemptions ({len(exemptions)} > {MAX_EXEMPTIONS})"
        )

    if violations:
        ok = False
        messages.append(f"FAIL: {len(violations)} residual banned-token hit(s):")
        messages.extend(violations)
    else:
        if ok:
            messages.append("rename check passed — no residual banned tokens")

    return ok, messages


def _list_rename_exemptions() -> int:
    """Print the exemption map and exit."""
    compiled = [re.compile(p) for p in BANNED_PATTERNS]
    exemptions: list[dict] = []

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if _is_allowlisted_path(rel):
            continue
        if path.suffix not in SCAN_EXTENSIONS and path.suffix != "":
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines_raw = raw.splitlines()
        lines = _strip_code_fences(lines_raw)
        for line_idx, line in enumerate(lines):
            for pattern in compiled:
                if pattern.search(line):
                    if _has_allow_marker_nearby(lines_raw, line_idx):
                        exemptions.append({
                            "file": rel,
                            "line": line_idx + 1,
                            "reason": "omni-rename-allow marker found",
                            "text": lines_raw[line_idx].strip()[:120],
                        })
                    break

    if not exemptions:
        print("No rename exemptions found.")
        return 0
    print(f"Rename exemptions ({len(exemptions)} total):")
    for e in exemptions:
        print(f"  {e['file']}:{e['line']} — {e['reason']}")
        print(f"    {e['text']}")
    return 0


def check_rename_stub() -> CheckResult:
    """Wave-0 stub. Verifies only that the check harness itself is alive.

    WS1 replaces this with the real whole-tree grep for `.omc/` /
    `oh-my-claudecode` with an explicit allowlist.
    """
    return True, ["rename stub: harness alive; WS1 will implement the real check"]


CHECKS: dict = {
    "rename": check_rename,
    "rename-stub": check_rename_stub,
}


def run_checks(names: list) -> int:
    overall_ok = True
    for name in names:
        if name not in CHECKS:
            print(f"[error] unknown check: {name}", file=sys.stderr)
            overall_ok = False
            continue
        ok, messages = CHECKS[name]()
        status = "ok" if ok else "FAIL"
        print(f"[{status}] {name}")
        for m in messages:
            print(f"       {m}")
        overall_ok = overall_ok and ok
    return 0 if overall_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-B plugin-contract verifier")
    parser.add_argument("--all", action="store_true", help="Run every registered check")
    parser.add_argument("--list-checks", action="store_true", help="Print the registered checks and exit")
    parser.add_argument("--list-rename-exemptions", action="store_true",
                        help="Print the inline rename-allowlist exemption map and exit")
    for name in CHECKS:
        parser.add_argument(f"--check-{name}", action="append_const",
                            dest="requested", const=name,
                            help=f"Run only the {name} check")
    parser.set_defaults(requested=[])
    args = parser.parse_args()

    if args.list_checks:
        for name in CHECKS:
            print(name)
        return 0

    if args.list_rename_exemptions:
        return _list_rename_exemptions()

    if args.all:
        names = list(CHECKS.keys())
    elif args.requested:
        names = args.requested
    else:
        parser.print_help()
        return 2

    return run_checks(names)


if __name__ == "__main__":
    sys.exit(main())
