#!/usr/bin/env python3
"""Phase-B plugin-contract verifier.

Grows with each Phase-B workstream. At Wave 0 only `--check-rename-stub`
and `--list-checks` exist; later waves append checks by adding functions
to CHECKS and wiring them into main().

Every check returns (ok: bool, messages: list[str]). Exit code is 0 on
all-green, 1 on any failure.

Contract: stdlib only. No third-party deps. Idempotent.

Exemption semantics
-------------------
``--all``         (default)  Exemptions up to the budget cap (MAX_EXEMPTIONS_TOTAL)
                             are accepted; only excess triggers a failure in
                             check_exemption_budget.  Individual checks also
                             enforce their own per-marker caps.

``--all-strict``             Runs every registered check AND treats ANY non-zero
                             exemption count as a failure.  Use this in release
                             gates where zero-exemption cleanliness is required.

Usage:
    python3 scripts/verify_plugin_contract.py --all
    python3 scripts/verify_plugin_contract.py --all-strict
    python3 scripts/verify_plugin_contract.py --check-rename
    python3 scripts/verify_plugin_contract.py --check-rename-stub
    python3 scripts/verify_plugin_contract.py --list-checks
    python3 scripts/verify_plugin_contract.py --list-rename-exemptions
"""
from __future__ import annotations

import argparse
import ast
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
    ".omni/plans/wave-2-review-",      # Wave 2 adversarial review outputs (prefix match)
    ".omni/plans/wave-2.x-patch-report.md",
    "docs/ADR/ADR-0000",               # prefix match
    # Runtime state dirs — not source files
    ".omc/",
    ".git/",
    # This file defines banned patterns as regex strings; self-allowlisted
    "scripts/verify_plugin_contract.py",
    # WS1 report documents the rename; legitimately cites old names
    ".omni/plans/wave-1-WS1-report.md",
    # WS9 report documents the validator; legitimately cites exemption markers
    ".omni/plans/wave-1-WS9-report.md",
    # WS3 report documents the router migration; legitimately cites historical names
    ".omni/plans/wave-2-WS3-report.md",
    # WS5a report documents the subagent primitives; legitimately cites exemption markers
    ".omni/plans/wave-2-WS5a-report.md",
    # WS5b report documents autopilot/ralph rewrite; legitimately cites old patterns
    ".omni/plans/wave-2-WS5b-report.md",
    # WS6 report documents team orchestration rewrite; legitimately cites old primitives
    ".omni/plans/wave-3-WS6-report.md",
    # WS7 report documents hook hardening; legitimately cites OMC legacy env vars
    ".omni/plans/wave-3-WS7-report.md",
    # WS10 report documents test strategy; cites historical module names
    ".omni/plans/wave-3-WS10-report.md",
    # WS7 hook library legitimately references the legacy sentinel filename for backward compat
    "hooks/_hook_lib.py",
    # WS7 tests reference the sentinel filename to test the deprecation-warn path
    "tests/test_hooks_kill_switch.py",
    "tests/test_hooks_audit_logging.py",
    # WS7 doc references the legacy sentinel filename
    "docs/HOOK_CONTRACT.md",
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

# Max allowed inline exemptions across the whole tree (hard cap for --all)
MAX_EXEMPTIONS = 10

# Hard cap for the aggregate exemption budget check (sum of all three markers)
# WS3: raised 15 → 25 to accommodate new historical citations introduced by the
# router migration (hook rewrite, ADR citations, command files referencing old patterns).
MAX_EXEMPTIONS_TOTAL = 25

# Marker pattern for inline allowlist — supports both HTML comments (<!-- -->) and
# shell/gitignore hash comments (# omni-rename-allow: reason)
ALLOW_MARKER_RE = re.compile(
    r"(?:<!--\s*|#\s*)omni-rename-allow\s*:.*?(?:-->|$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML-ish frontmatter block (between leading --- delimiters).

    Returns an empty dict if no valid frontmatter block is found.
    This is the single canonical frontmatter parser used by all checks.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


# ---------------------------------------------------------------------------
# WS1: rename check
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# WS2 checks
# ---------------------------------------------------------------------------

# Banned Claude-Code-specific primitive patterns in source files
_CC_PRIMITIVE_PATTERNS: tuple[str, ...] = (
    r'Task\s*\(\s*subagent_type\s*=',
    r'AskUserQuestion\s*\(',
    r'Skill\s*\(\s*["\'](?!.*SKILL\.md)',  # Skill("name") calls, not file refs
    r'\bstate_list_active\b',
    r'\bSendMessage\(',      # requires immediate paren — avoids "SendMessage (no team)" prose
    r'\bTeamCreate\(',
    r'\bTeamDelete\(',
)

# Paths allowlisted for the primitives check
_CC_PRIMITIVE_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",  # this file defines the patterns
    "scripts/subagent.py",               # documents the replacement
    "AGENTS.md",                         # prose documenting the translation layer
    "docs/ARCHITECTURE.md",              # prose documenting the translation layer
    ".git/",
    ".omc/",
    ".omni/",
)

# Marker that explicitly opts a line out of the primitives check
_CC_ALLOW_MARKER_RE = re.compile(
    r"(?:<!--\s*|#\s*)cc-primitive-allow\s*:.*?(?:-->|$)",
    re.IGNORECASE,
)


def _is_cc_primitive_allowlisted(rel: str) -> bool:
    for prefix in _CC_PRIMITIVE_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def check_no_claude_primitives() -> CheckResult:
    """Verify no Claude-Code-only primitives remain outside allowlisted files.

    Scans .md and .py files for Task(subagent_type=...), AskUserQuestion(),
    Skill("..."), state_list_active, SendMessage(), TeamCreate(), TeamDelete().
    Lines inside markdown code fences are skipped (they may document the old API).
    Lines with a cc-primitive-allow marker nearby are reported as exemptions.
    """
    compiled = [re.compile(p) for p in _CC_PRIMITIVE_PATTERNS]
    md_py_exts = frozenset({".md", ".py"})
    violations: list[str] = []
    exemptions: list[str] = []

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in md_py_exts:
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if _is_cc_primitive_allowlisted(rel):
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
                    if _CC_ALLOW_MARKER_RE.search(lines_raw[line_idx]):
                        exemptions.append(
                            f"  [exempt] {rel}:{line_idx + 1}: {lines_raw[line_idx].strip()[:120]}"
                        )
                    else:
                        violations.append(
                            f"  {rel}:{line_idx + 1}: {lines_raw[line_idx].strip()[:120]}"
                        )
                    break

    messages: list[str] = []
    ok = True

    if exemptions:
        messages.append(f"cc-primitive exemptions ({len(exemptions)}):")
        messages.extend(exemptions)

    if violations:
        ok = False
        messages.append(f"FAIL: {len(violations)} banned Claude-Code primitive(s) found:")
        messages.extend(violations)
    else:
        if ok:
            messages.append("no-claude-primitives check passed")

    return ok, messages


# ---------------------------------------------------------------------------

_REVIEWER_AGENTS: tuple[str, ...] = (
    "agents/critic.md",
    "agents/code-reviewer.md",
    "agents/security-reviewer.md",
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def check_writable_frontmatter() -> CheckResult:
    """Verify that reviewer agent files have `writable: false` in their frontmatter."""
    messages: list[str] = []
    ok = True

    for rel in _REVIEWER_AGENTS:
        path = ROOT / rel
        if not path.exists():
            ok = False
            messages.append(f"FAIL: {rel} not found")
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            ok = False
            messages.append(f"FAIL: could not read {rel}: {exc}")
            continue

        m = _FRONTMATTER_RE.match(content)
        if not m:
            ok = False
            messages.append(f"FAIL: {rel} has no YAML frontmatter block")
            continue

        frontmatter = m.group(1)
        if not re.search(r"^\s*writable\s*:\s*false\s*$", frontmatter, re.MULTILINE):
            ok = False
            messages.append(f"FAIL: {rel} missing 'writable: false' in frontmatter")
        else:
            messages.append(f"  ok: {rel} has writable: false")

    if ok:
        messages.insert(0, "writable-frontmatter check passed")

    return ok, messages


# ---------------------------------------------------------------------------
# WS9 checks
# ---------------------------------------------------------------------------

# Minimum counts for frontmatter schema check (ported from validate_plugin.py)
_MIN_SKILLS = 25
_MIN_AGENTS = 15
_MIN_COMMANDS = 6


def check_frontmatter_schema(root: Path = ROOT) -> CheckResult:
    """Verify that every skill, agent, and command has required frontmatter fields.

    Merges / supersedes scripts/validate_plugin.py shape checks (WS9).

    Rules:
    - Every skills/*/SKILL.md must have 'name' and 'description'.
    - Every agents/*.md must have 'name' and 'description'.
    - Every commands/*.md must have 'name'.
    - If 'writable' field is present, its value must be 'true' or 'false' (strings).
    - Minimum count thresholds: 25 skills, 15 agents, 6 commands.
    """
    failures: list[str] = []

    skills = sorted((root / "skills").glob("*/SKILL.md"))
    for skill in skills:
        meta = _parse_frontmatter(skill.read_text(encoding="utf-8", errors="replace"))
        missing = {"name", "description"} - meta.keys()
        if missing:
            rel = str(skill.relative_to(root)).replace("\\", "/")
            failures.append(f"FAIL: {rel}: missing frontmatter fields {sorted(missing)}")
        if "writable" in meta and meta["writable"] not in ("true", "false"):
            rel = str(skill.relative_to(root)).replace("\\", "/")
            failures.append(
                f"FAIL: {rel}: 'writable' must be 'true' or 'false', got {meta['writable']!r}"
            )

    agents = sorted((root / "agents").glob("*.md"))
    for agent in agents:
        meta = _parse_frontmatter(agent.read_text(encoding="utf-8", errors="replace"))
        missing = {"name", "description"} - meta.keys()
        if missing:
            rel = str(agent.relative_to(root)).replace("\\", "/")
            failures.append(f"FAIL: {rel}: missing frontmatter fields {sorted(missing)}")
        if "writable" in meta and meta["writable"] not in ("true", "false"):
            rel = str(agent.relative_to(root)).replace("\\", "/")
            failures.append(
                f"FAIL: {rel}: 'writable' must be 'true' or 'false', got {meta['writable']!r}"
            )

    commands = sorted((root / "commands").glob("*.md"))
    for cmd in commands:
        meta = _parse_frontmatter(cmd.read_text(encoding="utf-8", errors="replace"))
        if "name" not in meta:
            rel = str(cmd.relative_to(root)).replace("\\", "/")
            failures.append(f"FAIL: {rel}: missing 'name' frontmatter")
        if "writable" in meta and meta["writable"] not in ("true", "false"):
            rel = str(cmd.relative_to(root)).replace("\\", "/")
            failures.append(
                f"FAIL: {rel}: 'writable' must be 'true' or 'false', got {meta['writable']!r}"
            )

    messages: list[str] = []
    messages.append(f"  skills: {len(skills)}, agents: {len(agents)}, commands: {len(commands)}")

    if len(skills) < _MIN_SKILLS:
        failures.append(f"FAIL: insufficient skills: {len(skills)} < {_MIN_SKILLS}")
    if len(agents) < _MIN_AGENTS:
        failures.append(f"FAIL: insufficient agents: {len(agents)} < {_MIN_AGENTS}")
    if len(commands) < _MIN_COMMANDS:
        failures.append(f"FAIL: insufficient commands: {len(commands)} < {_MIN_COMMANDS}")

    ok = len(failures) == 0
    if ok:
        messages.insert(0, "frontmatter-schema check passed")
    else:
        messages.insert(0, f"FAIL: frontmatter-schema: {len(failures)} issue(s)")
        messages.extend(failures)

    return ok, messages


# ---------------------------------------------------------------------------
# Agent reference patterns
# ---------------------------------------------------------------------------
_AGENT_REF_PATTERNS: list[tuple[str, re.Pattern]] = [
    # scripts/subagent.py <name>  (first token after subagent.py, no angle brackets)
    ("subagent.py", re.compile(r"scripts/subagent\.py\s+([A-Za-z0-9_-]+)")),
    # /copilot-omni:<name>  — agent name follows colon
    ("slash-cmd", re.compile(r"/copilot-omni:([A-Za-z0-9_-]+)")),
    # agent: <name>  in frontmatter (not a placeholder)
    ("frontmatter-agent", re.compile(r"^\s*agent\s*:\s*([A-Za-z0-9_-]+)", re.MULTILINE)),
    # subagent_type=<name>  (without quotes, in prose; not angle-bracket placeholder)
    ("subagent_type", re.compile(r"subagent_type\s*=\s*[\"']([A-Za-z0-9_-]+)[\"']")),
]

# Placeholder names and common English words that should be ignored in ref checks
_PLACEHOLDER_NAMES: frozenset[str] = frozenset({
    "skill-name", "agent-name", "name", "my-skill", "my-agent",
    "follow-up-skill", "omni-",
    # Common English words that may appear after subagent.py in prose
    "or", "and", "to", "via", "the", "a", "an", "in", "of", "for",
})

# Marker to allow a reference inside code fences used as examples
_REF_ALLOW_MARKER_RE = re.compile(
    r"(?:<!--\s*|#\s*)omni-ref-allow\s*:\s*example.*?(?:-->|$)",
    re.IGNORECASE,
)

# Paths excluded from the agent-refs check
_AGENT_REF_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",
    "scripts/subagent.py",
    "AGENTS.md",
    "docs/",
    ".git/",
    ".omc/",
    ".omni/",
    "tests/",
)


def _is_agent_ref_allowlisted(rel: str) -> bool:
    for prefix in _AGENT_REF_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def _has_ref_allow_marker_nearby(lines: list[str], line_idx: int, window: int = 3) -> bool:
    """Return True if an omni-ref-allow:example marker is within `window` lines."""
    start = max(0, line_idx - window)
    end = min(len(lines), line_idx + window + 1)
    for i in range(start, end):
        if _REF_ALLOW_MARKER_RE.search(lines[i]):
            return True
    return False


def check_skill_agent_refs(root: Path = ROOT) -> CheckResult:
    """Verify every agent name referenced in skills/agents/commands exists as agents/<name>.md.

    Patterns checked (WS9):
    - scripts/subagent.py <name>
    - /copilot-omni:<name>  (agent-style refs)
    - agent: <name>  in frontmatter
    - subagent_type=<name>  in prose

    Note: /copilot-omni:<name> references that match a skill or command are handled
    by check_command_refs; this check only flags names that also don't match any agent.
    Lines covered by omni-ref-allow: example within 3 lines are skipped.
    """
    known_agents: set[str] = {
        p.stem for p in (root / "agents").glob("*.md")
    }

    # Also collect known skills and commands (slash-cmd refs may point to skills)
    known_skills: set[str] = {
        p.parent.name for p in (root / "skills").glob("*/SKILL.md")
    }
    known_commands: set[str] = {
        p.stem for p in (root / "commands").glob("*.md")
    }

    violations: list[str] = []

    scan_dirs = [root / "skills", root / "agents", root / "commands"]
    for scan_dir in scan_dirs:
        for path in sorted(scan_dir.rglob("*.md")):
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _is_agent_ref_allowlisted(rel):
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines_raw = raw.splitlines()
            lines = _strip_code_fences(lines_raw)

            for line_idx, line in enumerate(lines):
                for kind, pattern in _AGENT_REF_PATTERNS:
                    for m in pattern.finditer(line):
                        name = m.group(1)
                        # Skip placeholder/example names
                        if name in _PLACEHOLDER_NAMES or name.startswith("<") or name.endswith("`"):
                            continue
                        # slash-cmd refs: skip if known skill or command (handled by check_command_refs)
                        if kind == "slash-cmd" and (name in known_skills or name in known_commands):
                            continue
                        # subagent.py refs: skip known skills too (scripts may invoke skills)
                        if kind == "subagent.py" and (name in known_skills or name in known_commands):
                            continue
                        if name not in known_agents:
                            if _has_ref_allow_marker_nearby(lines_raw, line_idx):
                                continue
                            violations.append(
                                f"  {rel}:{line_idx + 1}: [{kind}] unknown agent ref '{name}'"
                            )

    messages: list[str] = []
    ok = len(violations) == 0
    if ok:
        messages.append("skill-agent-refs check passed")
    else:
        messages.append(f"FAIL: {len(violations)} unknown agent reference(s):")
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# Command reference check
# ---------------------------------------------------------------------------
_SLASH_CMD_RE = re.compile(r"/copilot-omni:([A-Za-z0-9_-]+)")

_CMD_REF_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",
    ".git/",
    ".omc/",
    ".omni/",
    "docs/ADR/",
    "tests/",
)


def _is_cmd_ref_allowlisted(rel: str) -> bool:
    for prefix in _CMD_REF_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def check_command_refs(root: Path = ROOT) -> CheckResult:
    """Every /copilot-omni:<name> reference must resolve to skills/<name>/SKILL.md or commands/<name>.md.

    Scans all .md and .py files under skills/, agents/, commands/ (WS9).
    """
    known_skills: set[str] = {
        p.parent.name for p in (root / "skills").glob("*/SKILL.md")
    }
    known_commands: set[str] = {
        p.stem for p in (root / "commands").glob("*.md")
    }
    known = known_skills | known_commands

    violations: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in (".md", ".py"):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if _is_cmd_ref_allowlisted(rel):
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines_raw = raw.splitlines()
        lines = _strip_code_fences(lines_raw)

        for line_idx, line in enumerate(lines):
            for m in _SLASH_CMD_RE.finditer(line):
                name = m.group(1)
                # Skip placeholder/example names
                if name in _PLACEHOLDER_NAMES or name.startswith("<"):
                    continue
                if name not in known:
                    if _has_ref_allow_marker_nearby(lines_raw, line_idx):
                        continue
                    violations.append(
                        f"  {rel}:{line_idx + 1}: unknown slash-command '/copilot-omni:{name}'"
                    )

    messages: list[str] = []
    ok = len(violations) == 0
    if ok:
        messages.append("command-refs check passed")
    else:
        messages.append(f"FAIL: {len(violations)} unknown slash-command reference(s):")
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# MCP tool reference check
# ---------------------------------------------------------------------------
# Tools referenced via these name patterns in skills/agents
_MCP_TOOL_REF_RE = re.compile(
    r"\b(?:mcp__copilot_omni_(?:\w+)|omni_(\w+))\b"
)

# Alternative pattern: prose references like "omni_<tool>" where tool maps to TOOLS key
_OMNI_TOOL_REF_RE = re.compile(r"\bomni_([a-z_]+)\b")


def _extract_mcp_tool_names(server_py: Path) -> set[str]:
    """Extract registered tool names from mcp/server.py by parsing the TOOLS dict.

    Uses stdlib AST for structured parsing; falls back to regex if AST parse fails.
    Returns a set of tool name strings.
    """
    try:
        source = server_py.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set()

    # Primary: AST parse — find TOOLS dict assignment, collect string keys
    try:
        tree = ast.parse(source, filename=str(server_py))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "TOOLS"
                and isinstance(node.value, ast.Dict)
            ):
                names: set[str] = set()
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        names.add(key.value)
                return names
    except SyntaxError:
        pass

    # Fallback: regex for quoted keys immediately after "{" or ","
    names_fb: set[str] = set()
    for m in re.finditer(r'["{](\w+)"\s*:\s*\{', source):
        names_fb.add(m.group(1))
    return names_fb


_MCP_REF_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",
    "mcp/server.py",
    ".git/",
    ".omc/",
    ".omni/",
    "tests/",
)


def _is_mcp_ref_allowlisted(rel: str) -> bool:
    for prefix in _MCP_REF_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def check_mcp_tool_refs(root: Path = ROOT) -> CheckResult:
    """Verify every mcp__copilot_omni_* / omni_<tool> reference matches a registered tool.

    Tool names are extracted from mcp/server.py TOOLS dict via AST parsing (WS9).
    """
    server_py = root / "mcp" / "server.py"
    known_tools = _extract_mcp_tool_names(server_py)

    violations: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in (".md", ".py"):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if _is_mcp_ref_allowlisted(rel):
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines_raw = raw.splitlines()
        lines = _strip_code_fences(lines_raw)

        for line_idx, line in enumerate(lines):
            # mcp__copilot_omni_<tool> pattern
            for m in re.finditer(r"\bmcp__copilot_omni_(\w+)\b", line):
                tool_name = m.group(1)
                if tool_name not in known_tools:
                    if _has_ref_allow_marker_nearby(lines_raw, line_idx):
                        continue
                    violations.append(
                        f"  {rel}:{line_idx + 1}: unknown MCP tool 'mcp__copilot_omni_{tool_name}'"
                    )

    messages: list[str] = []
    ok = len(violations) == 0
    if ok:
        messages.append(f"mcp-tool-refs check passed (known tools: {len(known_tools)})")
    else:
        messages.append(f"FAIL: {len(violations)} unknown MCP tool reference(s):")
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# Exemption budget check
# ---------------------------------------------------------------------------
_EXEMPTION_MARKERS: dict[str, re.Pattern] = {
    "omni-rename-allow": re.compile(
        r"(?:<!--\s*|#\s*)omni-rename-allow\s*:.*?(?:-->|$)", re.IGNORECASE
    ),
    "cc-primitive-allow": re.compile(
        r"(?:<!--\s*|#\s*)cc-primitive-allow\s*:.*?(?:-->|$)", re.IGNORECASE
    ),
    "omni-ref-allow": re.compile(
        r"(?:<!--\s*|#\s*)omni-ref-allow\s*:.*?(?:-->|$)", re.IGNORECASE
    ),
    "omni-model-allow": re.compile(
        r"(?:<!--\s*|#\s*)omni-model-allow\s*:.*?(?:-->|$)", re.IGNORECASE
    ),
}

_BUDGET_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",
    ".git/",
    ".omc/",
    ".omni/",
)


def _is_budget_allowlisted(rel: str) -> bool:
    for prefix in _BUDGET_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def check_exemption_budget(root: Path = ROOT) -> CheckResult:
    """Sum all exemption markers across the tree; fail if total > MAX_EXEMPTIONS_TOTAL (15).

    Counts per marker:
    - omni-rename-allow
    - cc-primitive-allow
    - omni-ref-allow

    Reports counts per marker and fails if sum exceeds MAX_EXEMPTIONS_TOTAL (WS9).
    """
    counts: dict[str, int] = {k: 0 for k in _EXEMPTION_MARKERS}

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS and path.suffix != "":
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if _is_budget_allowlisted(rel):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for marker, pattern in _EXEMPTION_MARKERS.items():
            counts[marker] += len(pattern.findall(raw))

    total = sum(counts.values())
    messages: list[str] = []
    for marker, count in counts.items():
        messages.append(f"  {marker}: {count}")
    messages.append(f"  total: {total}/{MAX_EXEMPTIONS_TOTAL}")

    ok = total <= MAX_EXEMPTIONS_TOTAL
    if ok:
        messages.insert(0, "exemption-budget check passed")
    else:
        messages.insert(0, f"FAIL: exemption budget exceeded ({total} > {MAX_EXEMPTIONS_TOTAL})")
    return ok, messages


# ---------------------------------------------------------------------------
# Stdlib-only imports check
# ---------------------------------------------------------------------------

# Stdlib module names — use sys.stdlib_module_names on Python >= 3.10,
# fall back to a frozen list for earlier runtimes.
def _get_stdlib_names() -> frozenset[str]:
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
    # Frozen fallback covering Python 3.9 stdlib
    _STDLIB_FALLBACK = frozenset({
        "__future__", "_thread", "abc", "aifc", "argparse", "array", "ast",
        "asynchat", "asyncio", "asyncore", "atexit", "audioop", "base64",
        "bdb", "binascii", "binhex", "bisect", "builtins", "bz2", "calendar",
        "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
        "colorsys", "compileall", "concurrent", "configparser", "contextlib",
        "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes",
        "curses", "dataclasses", "datetime", "dbm", "decimal", "difflib",
        "dis", "distutils", "doctest", "email", "encodings", "enum",
        "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
        "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
        "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac",
        "html", "http", "idlelib", "imaplib", "imghdr", "importlib",
        "inspect", "io", "ipaddress", "itertools", "json", "keyword",
        "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
        "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
        "netrc", "nis", "nntplib", "numbers", "operator", "optparse",
        "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools",
        "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix",
        "posixpath", "pprint", "profile", "pstats", "pty", "pwd", "py_compile",
        "pyclbr", "pydoc", "queue", "quopri", "random", "re", "readline",
        "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets",
        "select", "selectors", "shelve", "shlex", "shutil", "signal",
        "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
        "spwd", "sqlite3", "sre_compile", "sre_constants", "sre_parse",
        "ssl", "stat", "statistics", "string", "stringprep", "struct",
        "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
        "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
        "textwrap", "threading", "time", "timeit", "tkinter", "token",
        "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
        "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
        "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
        "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
        "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
        "_collections_abc", "_weakrefset", "antigravity", "cmath", "ntpath",
        "posixpath", "genericpath",
        # Platform-specific stdlib (Windows)
        "msvcrt", "_winapi",
    })
    return _STDLIB_FALLBACK


_STDLIB_NAMES = _get_stdlib_names()

# Directories to scan for stdlib-only enforcement
_STDLIB_SCAN_DIRS = ("scripts", "hooks", "mcp", "tests")

# Local package imports that are allowed (relative or sibling)
_LOCAL_PREFIXES = (".", "scripts", "hooks", "mcp", "tests")

# Test-only framework imports that are permitted inside tests/ directories
_TEST_FRAMEWORK_NAMES: frozenset[str] = frozenset({"pytest", "unittest"})

_STDLIB_FILE_ALLOWLIST: tuple[str, ...] = (
    "scripts/verify_plugin_contract.py",
    ".git/",
)


def _is_stdlib_allowlisted(rel: str) -> bool:
    for prefix in _STDLIB_FILE_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def _get_imports_from_file(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, module_top_level) for every import in a Python file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    result: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                result.append((node.lineno, top))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import — always local
                continue
            if node.module:
                top = node.module.split(".")[0]
                result.append((node.lineno, top))
    return result


def check_stdlib_only_imports(root: Path = ROOT) -> CheckResult:
    """Verify Python files under scripts/, hooks/, mcp/, tests/ use only stdlib imports.

    Uses sys.stdlib_module_names on Python >= 3.10; falls back to a frozen list (WS9).
    Third-party imports are flagged. Local/relative imports are allowed.
    """
    violations: list[str] = []

    # Collect local module names from scanned dirs (e.g. verify_plugin_contract, server, etc.)
    local_module_names: set[str] = set()
    for dir_name in _STDLIB_SCAN_DIRS:
        scan_dir = root / dir_name
        if scan_dir.exists():
            for py in scan_dir.rglob("*.py"):
                local_module_names.add(py.stem)

    for dir_name in _STDLIB_SCAN_DIRS:
        scan_dir = root / dir_name
        if not scan_dir.exists():
            continue
        in_tests = dir_name == "tests"
        for path in sorted(scan_dir.rglob("*.py")):
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _is_stdlib_allowlisted(rel):
                continue
            for lineno, top in _get_imports_from_file(path):
                if top in _STDLIB_NAMES:
                    continue
                if top in _LOCAL_PREFIXES:
                    continue
                if top in local_module_names:
                    continue
                if in_tests and top in _TEST_FRAMEWORK_NAMES:
                    continue
                violations.append(
                    f"  {rel}:{lineno}: third-party import '{top}'"
                )

    messages: list[str] = []
    ok = len(violations) == 0
    if ok:
        messages.append("stdlib-only-imports check passed")
    else:
        messages.append(f"FAIL: {len(violations)} third-party import(s) found:")
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# WS8b: State-store canonical check
# ---------------------------------------------------------------------------

# MCP-owned tables: any Python file (outside mcp/server.py) that contains
# direct SQL writes to these tables bypasses the canonical MCP tool layer.
# We look for .execute( patterns containing INSERT/UPDATE/DELETE + table name
# in Python source files under scripts/, hooks/, mcp/ (but NOT mcp/server.py).
#
# Skills (.md files) are intentionally excluded — they call MCP tools by name
# in prose/instructions, which is correct usage of the canonical write API.
_MCP_OWNED_TABLES: tuple[str, ...] = (
    "memory",
    "artifacts",
    "runs",
    "state",
    "wiki",
    "notepad",
    "shared_memory",
    "trace",
    "sessions",
)

# SQL write verb pattern: INSERT/UPDATE/DELETE/REPLACE INTO <table>
_SQL_WRITE_RE = re.compile(
    r"(?:INSERT|UPDATE|DELETE|REPLACE)\s+(?:INTO\s+|FROM\s+)?(\w+)",
    re.IGNORECASE,
)

# Directories to scan for direct-DB-write violations (Python files only)
_STATE_SCAN_DIRS_PY = ("scripts", "hooks", "mcp")

# Python files allowed to write directly to MCP-owned tables
_STATE_CANONICAL_ALLOWLIST_PY = (
    "mcp/server.py",
    "scripts/verify_plugin_contract.py",
    # WS5a: subagent.py _mcp_write_best_effort() is an intentional best-effort
    # MCP proxy — it writes to the state table only when the MCP server is
    # unavailable (offline / no DB yet). This is the documented exception per
    # ADR-0007 §best-effort-writes.
    "scripts/subagent.py",
    # WS6: omni_team.py _mcp_write_best_effort() follows the same best-effort
    # proxy pattern — writes to the state table only when MCP server is offline.
    "scripts/omni_team.py",
)

# Test files are excluded — they may seed the DB directly for test setup
_STATE_TEST_DIRS = ("tests",)


def _is_state_py_allowlisted(rel: str) -> bool:
    for prefix in _STATE_CANONICAL_ALLOWLIST_PY:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


def check_state_store_canonical(root: Path = ROOT) -> CheckResult:
    """Verify no Python file outside mcp/server.py writes directly to MCP-owned SQLite tables.

    Scans scripts/, hooks/, mcp/ (Python files only) for SQL write statements
    (INSERT/UPDATE/DELETE/REPLACE) targeting the tables owned by the MCP server.
    Any match outside the allowlist is a split-brain violation per ADR-0007.

    Skills (.md files) are not scanned — calling MCP tools by name in skill prose
    is the correct usage of the canonical write API.
    """
    violations: list[str] = []
    messages: list[str] = []

    mcp_table_set = set(_MCP_OWNED_TABLES)

    for dir_name in _STATE_SCAN_DIRS_PY:
        scan_dir = root / dir_name
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*.py")):
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _is_state_py_allowlisted(rel):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for line_idx, line in enumerate(content.splitlines()):
                for m in _SQL_WRITE_RE.finditer(line):
                    table = m.group(1).lower()
                    if table in mcp_table_set:
                        violations.append(
                            f"  {rel}:{line_idx + 1}: direct SQL write to MCP-owned"
                            f" table '{table}': {line.strip()[:100]}"
                        )

    ok = len(violations) == 0
    if ok:
        messages.append(
            f"state-store-canonical check passed"
            f" (scanned {sum(1 for d in _STATE_SCAN_DIRS_PY if (root / d).exists())} dirs,"
            f" {len(_MCP_OWNED_TABLES)} protected tables)"
        )
    else:
        messages.append(
            f"FAIL: state-store-canonical: {len(violations)} direct-write violation(s):"
        )
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# WS4: No raw model names check
# ---------------------------------------------------------------------------

# Patterns that must not appear in skills/, agents/, commands/, hooks/
# Uses character classes to defeat 'hai' + 'ku' string concatenation evasion
# (per critic §4 WS4).
_RAW_MODEL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"claude-[Hh][Aa][Ii][Kk][Uu]"),          # claude-haiku variants
    re.compile(r"claude-[Ss][Oo][Nn][Nn][Ee][Tt]"),        # claude-sonnet variants
    re.compile(r"claude-[Oo][Pp][Uu][Ss]"),                # claude-opus variants
    re.compile(r"gpt-[0-9]"),                               # gpt-4, gpt-5, etc.
    re.compile(r"gemini-[0-9]"),                            # gemini-2.x, etc.
)

# Directories in scope for this check
_RAW_MODEL_SCAN_DIRS: tuple[str, ...] = ("skills", "agents", "commands", "hooks")

# Paths allowlisted for the raw-model-names check (relative to ROOT)
_RAW_MODEL_ALLOWLIST: tuple[str, ...] = (
    "docs/MODELS.md",
    ".omni/config.json",
    "scripts/category_resolver.py",
    "docs/ADR/ADR-0003-",              # prefix match
    ".omni/plans/wave-2-WS4-report.md",
    "scripts/verify_plugin_contract.py",
    ".git/",
    ".omc/",
    ".omni/",
)

# Marker for per-file inline exemption
_MODEL_ALLOW_MARKER_RE = re.compile(
    r"(?:<!--\s*|#\s*)omni-model-allow\s*:.*?(?:-->|$)",
    re.IGNORECASE,
)


def _is_raw_model_allowlisted(rel: str) -> bool:
    for prefix in _RAW_MODEL_ALLOWLIST:
        if rel.startswith(prefix):
            return True
    return False


def check_no_raw_model_names(root: Path = ROOT) -> CheckResult:
    """Verify no raw model names appear in skills/, agents/, commands/, hooks/.

    Patterns checked (WS4):
    - claude-haiku (any case variant)
    - claude-sonnet (any case variant)
    - claude-opus (any case variant)
    - gpt-<digit>
    - gemini-<digit>

    Character-class regex defeats 'hai'+'ku' concatenation evasion.
    Lines inside markdown code fences are skipped.
    Lines with an omni-model-allow marker nearby are reported as exemptions.
    """
    violations: list[str] = []
    exemptions: list[str] = []

    for dir_name in _RAW_MODEL_SCAN_DIRS:
        scan_dir = root / dir_name
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_EXTENSIONS and path.suffix != "":
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _is_raw_model_allowlisted(rel):
                continue

            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines_raw = raw.splitlines()
            lines = _strip_code_fences(lines_raw)

            for line_idx, line in enumerate(lines):
                for pattern in _RAW_MODEL_PATTERNS:
                    if pattern.search(line):
                        nearby = max(0, line_idx - 3)
                        far = min(len(lines_raw), line_idx + 4)
                        has_marker = any(
                            _MODEL_ALLOW_MARKER_RE.search(lines_raw[i])
                            for i in range(nearby, far)
                        )
                        entry = (
                            f"  {rel}:{line_idx + 1}: "
                            f"{lines_raw[line_idx].strip()[:120]}"
                        )
                        if has_marker:
                            exemptions.append(f"  [exempt] {rel}:{line_idx + 1}: "
                                              f"{lines_raw[line_idx].strip()[:120]}")
                        else:
                            violations.append(entry)
                        break  # one report per line

    messages: list[str] = []
    ok = True

    if exemptions:
        messages.append(f"model-name exemptions ({len(exemptions)}):")
        messages.extend(exemptions)

    if violations:
        ok = False
        messages.append(f"FAIL: {len(violations)} raw model name(s) found:")
        messages.extend(violations)
    else:
        if ok:
            messages.append("no-raw-model-names check passed — 0 violations")

    return ok, messages


# ---------------------------------------------------------------------------
# WS5a: Run-directory invariants check
# ---------------------------------------------------------------------------

_RUN_STALE_SECS = 1800  # 30 minutes


def check_run_directory_invariants(root: Path = ROOT) -> CheckResult:
    """For every .omni/runs/<run-id>/<job-id>/ that exists:
    - assert status.json is present AND parseable (fail if missing or corrupt)
    - warn (not fail) if a job is 'running' for > 30 min (likely stuck)

    Returns ok=True with warnings if only stuck jobs detected.
    Returns ok=False if any status.json is missing or unparseable.
    """
    import time as _time

    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        return True, ["run-directory-invariants: no .omni/runs/ directory — skip"]

    messages: list[str] = []
    ok = True
    n_checked = 0
    n_missing = 0
    n_corrupt = 0
    n_stuck = 0
    now = _time.time()

    # Pattern for subagent job dirs (UUID or job-N); pipeline phase/iteration dirs are skipped
    import re as _re
    _JOB_DIR_RE = _re.compile(
        r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|job-\d+)$",
        _re.IGNORECASE,
    )
    # Additional marker: a subagent job dir always contains spec.json (written by WS5a)
    def _is_subagent_job_dir(d: Path) -> bool:
        """Return True if this directory is a subagent job dir (not a pipeline phase dir)."""
        return (d / "spec.json").exists() or _JOB_DIR_RE.match(d.name) is not None

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        for job_dir in sorted(run_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            # Skip pipeline phase/iteration dirs — they are managed by autopilot/ralph,
            # not by subagent.py, and do not require the WS5a status.json contract.
            if not _is_subagent_job_dir(job_dir):
                continue
            n_checked += 1
            status_path = job_dir / "status.json"

            if not status_path.exists():
                ok = False
                n_missing += 1
                rel = str(status_path.relative_to(root)).replace("\\", "/")
                messages.append(f"  FAIL: missing status.json: {rel}")
                continue

            try:
                import json as _json
                data = _json.loads(status_path.read_text(encoding="utf-8"))
            except Exception as exc:
                ok = False
                n_corrupt += 1
                rel = str(status_path.relative_to(root)).replace("\\", "/")
                messages.append(f"  FAIL: unparseable status.json: {rel}: {exc}")
                continue

            # Warn on stuck running jobs
            state = data.get("state", "")
            started_at = data.get("started_at")
            if state == "running" and started_at:
                try:
                    from datetime import datetime, timezone
                    fmt = "%Y-%m-%dT%H:%M:%SZ"
                    t0 = datetime.strptime(started_at, fmt).replace(
                        tzinfo=timezone.utc)
                    age_s = now - t0.timestamp()
                    if age_s > _RUN_STALE_SECS:
                        n_stuck += 1
                        rel = str(status_path.relative_to(root)).replace("\\", "/")
                        messages.append(
                            f"  WARN: job stuck in 'running' for {age_s/60:.0f} min: {rel}"
                        )
                except Exception:
                    pass

    summary = (
        f"run-directory-invariants: checked={n_checked},"
        f" missing={n_missing}, corrupt={n_corrupt}, stuck_warn={n_stuck}"
    )
    if ok:
        messages.insert(0, summary + " OK")
    else:
        messages.insert(0, f"FAIL: {summary}")

    return ok, messages


# ---------------------------------------------------------------------------
# WS5b: Cancel-signal pairing check
# ---------------------------------------------------------------------------


def check_cancel_signal_pairing(root: Path = ROOT) -> CheckResult:
    """For every .omni/runs/<run-id>/cancel.signal that exists, assert that at least
    one status.json in the same run-dir has state="cancelled".

    A cancel.signal with no matching cancelled status.json is a stale signal —
    it means the cancel was never observed or cleaned up.

    Returns ok=False (FAIL) if any stale cancel.signal is found.
    Returns ok=True (with info message) if all cancel.signals are paired.
    """
    import json as _json

    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        return True, ["cancel-signal-pairing: no .omni/runs/ directory — skip"]

    messages: list[str] = []
    ok = True
    n_checked = 0
    n_stale = 0
    n_paired = 0

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        signal_file = run_dir / "cancel.signal"
        if not signal_file.exists():
            continue

        n_checked += 1
        rel_run = str(run_dir.relative_to(root)).replace("\\", "/")

        # Search all status.json files in this run-dir for state="cancelled"
        found_cancelled = False
        for status_path in run_dir.rglob("status.json"):
            try:
                data = _json.loads(status_path.read_text(encoding="utf-8"))
                if data.get("state") == "cancelled":
                    found_cancelled = True
                    break
            except Exception:
                continue

        if found_cancelled:
            n_paired += 1
        else:
            ok = False
            n_stale += 1
            messages.append(
                f"  FAIL: stale cancel.signal (no cancelled status.json): {rel_run}"
            )

    summary = (
        f"cancel-signal-pairing: checked={n_checked},"
        f" paired={n_paired}, stale={n_stale}"
    )
    if ok:
        messages.insert(0, summary + " OK")
    else:
        messages.insert(0, f"FAIL: {summary}")

    return ok, messages


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# T1: Mode key registry check
# ---------------------------------------------------------------------------

# Path to the canonical mode registry
_STATE_MODES_DOC = ROOT / "docs" / "STATE_MODES.md"

# Patterns that identify a literal mode string in Python source or SKILL.md
# Matches: state_write(mode="foo"), _mcp_write_best_effort('foo', ...), mode="foo"
_MODE_LITERAL_RE = re.compile(
    r"""(?:state_write|state_read|_mcp_write_best_effort)\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# Directories to scan for mode= literal strings
_MODE_SCAN_DIRS = ("scripts", "mcp", "skills")
_MODE_SCAN_EXTENSIONS = (".py", ".md")

# Mode prefixes that are dynamic (contain {var}) — skip these
_DYNAMIC_MODE_PREFIX = re.compile(r"[\{\}]")


def _parse_registered_modes(doc_path: Path) -> set[str]:
    """Parse the | mode | ... table from STATE_MODES.md."""
    if not doc_path.exists():
        return set()
    modes: set[str] = set()
    for line in doc_path.read_text(encoding="utf-8").splitlines():
        # Match table rows: | `mode.key` | ... |
        m = re.search(r'\|\s*`([^`]+)`\s*\|', line)
        if m:
            modes.add(m.group(1))
    return modes


def check_mode_key_registry(root: Path = ROOT) -> CheckResult:
    """T1: verify every literal mode string in source is listed in docs/STATE_MODES.md.

    Scans scripts/, mcp/, skills/**/*.md|*.py for calls to
    state_write/state_read/_mcp_write_best_effort with a literal mode string.
    Compares against the registry in docs/STATE_MODES.md.
    Reports any unregistered mode literal as a violation.
    Skips dynamic mode strings (containing { or }).
    Subagent mode keys of form 'subagent:<id>' are covered by the 'subagent' prefix.
    """
    registered = _parse_registered_modes(root / "docs" / "STATE_MODES.md")
    violations: list[str] = []
    messages: list[str] = []

    if not registered:
        messages.append(
            "WARN: docs/STATE_MODES.md not found or has no registered modes; "
            "check_mode_key_registry is a no-op until STATE_MODES.md is populated."
        )
        return True, messages

    # Self-allowlist: this file defines the regex pattern, skip it
    _self = str(Path(__file__).relative_to(root)).replace("\\", "/")

    scanned = 0
    for dir_name in _MODE_SCAN_DIRS:
        scan_dir = root / dir_name
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in _MODE_SCAN_EXTENSIONS:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if rel == _self:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            scanned += 1
            for line_idx, line in enumerate(content.splitlines()):
                for m in _MODE_LITERAL_RE.finditer(line):
                    mode_val = m.group(1)
                    # Skip dynamic strings
                    if _DYNAMIC_MODE_PREFIX.search(mode_val):
                        continue
                    # 'subagent:<id>' patterns are covered by 'subagent' in registry
                    if mode_val.startswith("subagent:"):
                        if "subagent" in registered:
                            continue
                    if mode_val not in registered:
                        violations.append(
                            f"  {rel}:{line_idx + 1}: unregistered mode "
                            f"'{mode_val}' — add to docs/STATE_MODES.md"
                        )

    ok = len(violations) == 0
    if ok:
        messages.append(
            f"mode-key-registry check passed (scanned {scanned} files, "
            f"{len(registered)} registered modes)"
        )
    else:
        messages.append(
            f"FAIL: mode-key-registry: {len(violations)} unregistered mode literal(s):"
        )
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# WS6: Team modes declared check
# ---------------------------------------------------------------------------


def check_team_modes_declared(root: Path = ROOT) -> CheckResult:
    """WS6: every mode starting with 'team' or 'team.' used in code must be
    registered in docs/STATE_MODES.md.

    Scans scripts/, mcp/, skills/**/ for literal mode strings that start with
    'team' (e.g. 'team', 'team.worker-1') and cross-references against the
    registered modes in docs/STATE_MODES.md.

    Dynamic patterns like 'team.{slug}' are skipped.
    """
    registered = _parse_registered_modes(root / "docs" / "STATE_MODES.md")
    if not registered:
        return True, ["team-modes-declared: STATE_MODES.md not found or empty — skip"]

    violations: list[str] = []
    _self = str(Path(__file__).relative_to(root)).replace("\\", "/")

    for dir_name in _MODE_SCAN_DIRS:
        scan_dir = root / dir_name
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in _MODE_SCAN_EXTENSIONS:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if rel == _self:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for line_idx, line in enumerate(content.splitlines()):
                for m in _MODE_LITERAL_RE.finditer(line):
                    mode_val = m.group(1)
                    # Only check team modes
                    if not mode_val.startswith("team"):
                        continue
                    # Skip dynamic strings (contain { or })
                    if _DYNAMIC_MODE_PREFIX.search(mode_val):
                        continue
                    # 'team' exact match is registered
                    if mode_val == "team":
                        if "team" not in registered:
                            violations.append(
                                f"  {rel}:{line_idx + 1}: unregistered team mode "
                                f"'{mode_val}' — add to docs/STATE_MODES.md"
                            )
                        continue
                    # 'team.<slug>' — check if 'team.<worker-slug>' pattern is registered
                    # We accept any team.<x> if 'team' root is registered (per-worker keys
                    # are dynamic by nature; only the pattern needs documenting)
                    if "team" in registered:
                        continue
                    if mode_val not in registered:
                        violations.append(
                            f"  {rel}:{line_idx + 1}: unregistered team mode "
                            f"'{mode_val}' — add to docs/STATE_MODES.md"
                        )

    ok = len(violations) == 0
    messages: list[str] = []
    if ok:
        messages.append("team-modes-declared check passed")
    else:
        messages.append(f"FAIL: team-modes-declared: {len(violations)} unregistered team mode(s):")
        messages.extend(violations)
    return ok, messages


# ---------------------------------------------------------------------------
# WS6: Worktree hygiene check
# ---------------------------------------------------------------------------


def check_worktree_hygiene(root: Path = ROOT) -> CheckResult:
    """WS6: walk .omni/runs/team-*; assert any worktree listed in manifest.json
    also exists OR was pruned (no orphans in git worktree list).

    An orphan is a worktree path that appears in manifest.json but is NOT in
    `git worktree list` and the path doesn't exist on disk.
    """
    import json as _json
    import subprocess as _subprocess

    runs_dir = root / ".omni" / "runs"
    if not runs_dir.exists():
        return True, ["worktree-hygiene: no .omni/runs/ directory — skip"]

    messages: list[str] = []
    ok = True
    n_checked = 0
    n_orphans = 0

    # Get git worktree list once
    try:
        result = _subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        git_worktree_paths: set[str] = set()
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                git_worktree_paths.add(line[len("worktree "):].strip())
    except Exception:
        git_worktree_paths = set()

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        if not run_dir.name.startswith("team-"):
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        workers = manifest.get("workers", [])
        for w in workers:
            wt_path_str = w.get("worktree_path", "")
            if not wt_path_str:
                continue
            n_checked += 1
            wt_path = Path(wt_path_str)

            # Check: path exists on disk OR is in git worktree list
            exists_on_disk = wt_path.exists()
            in_git_list = wt_path_str in git_worktree_paths

            if not exists_on_disk and not in_git_list:
                # This is an orphan only if team status is not "cleaned" or "cancelled"
                team_status_path = run_dir / "status.json"
                team_status = {}
                try:
                    team_status = _json.loads(team_status_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
                team_state = team_status.get("state", "")
                if team_state not in ("cleaned", "cancelled", "done"):
                    n_orphans += 1
                    rel_wt = str(wt_path).replace(str(root) + "/", "")
                    messages.append(
                        f"  WARN: possible orphan worktree (not on disk, not in git list): "
                        f"{rel_wt} (team state: {team_state!r})"
                    )

    summary = f"worktree-hygiene: checked={n_checked}, possible_orphans={n_orphans}"
    if n_orphans == 0:
        messages.insert(0, summary + " OK")
    else:
        # Warn but don't fail (orphans may be in-progress teams)
        messages.insert(0, f"WARN: {summary} (see below)")
    return ok, messages


CHECKS: dict = {
    "rename": check_rename,
    "rename-stub": check_rename_stub,
    "no-claude-primitives": check_no_claude_primitives,
    "writable-frontmatter": check_writable_frontmatter,
    "frontmatter-schema": check_frontmatter_schema,
    "skill-agent-refs": check_skill_agent_refs,
    "command-refs": check_command_refs,
    "mcp-tool-refs": check_mcp_tool_refs,
    "exemption-budget": check_exemption_budget,
    "stdlib-only-imports": check_stdlib_only_imports,
    "state-store-canonical": check_state_store_canonical,
    "no-raw-model-names": check_no_raw_model_names,
    "run-directory-invariants": check_run_directory_invariants,
    "cancel-signal-pairing": check_cancel_signal_pairing,
    "mode-key-registry": check_mode_key_registry,
    "team-modes-declared": check_team_modes_declared,
    "worktree-hygiene": check_worktree_hygiene,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_checks(names: list, strict: bool = False) -> int:
    """Run the named checks.  If strict=True, any exemption count > 0 is a failure."""
    overall_ok = True
    for name in names:
        if name not in CHECKS:
            print(f"[error] unknown check: {name}", file=sys.stderr)
            overall_ok = False
            continue

        fn = CHECKS[name]
        # Root-accepting checks accept an optional root kwarg
        try:
            ok, messages = fn()
        except TypeError:
            ok, messages = fn(ROOT)

        # In strict mode: if a check passes but produced exemption messages, fail it
        if strict and ok:
            has_exemption = any(
                "exempt" in m.lower() or "exemption" in m.lower()
                for m in messages
            )
            if has_exemption:
                ok = False
                messages.append("FAIL (--all-strict): non-zero exemption count not allowed")

        status = "ok" if ok else "FAIL"
        print(f"[{status}] {name}")
        for m in messages:
            print(f"       {m}")
        overall_ok = overall_ok and ok
    return 0 if overall_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-B plugin-contract verifier")
    parser.add_argument("--all", action="store_true",
                        help="Run every registered check (exemptions up to budget cap accepted)")
    parser.add_argument("--all-strict", action="store_true",
                        help="Run every check AND treat any non-zero exemption count as failure")
    parser.add_argument("--list-checks", action="store_true",
                        help="Print the registered checks and exit")
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

    strict = args.all_strict

    if args.all or args.all_strict:
        names = list(CHECKS.keys())
    elif args.requested:
        names = args.requested
    else:
        parser.print_help()
        return 2

    return run_checks(names, strict=strict)


if __name__ == "__main__":
    sys.exit(main())
