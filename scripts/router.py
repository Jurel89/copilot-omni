#!/usr/bin/env python3
"""WS3 front-door intent router — pure-CPU classifier.

Public API
----------
    classify(prompt, *, threshold=0.4, config=None) -> dict
    emit_router_state(decision, *, session_id=None) -> None

CLI
---
    python3 scripts/router.py --prompt "<text>"
    python3 scripts/router.py --stdin
    python3 scripts/router.py --threshold 0.5 --prompt "<text>"

Scoring follows ADR-0005 exactly. stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Signal weights (ADR-0005 §1)
# ---------------------------------------------------------------------------

_W_FILE_PATH   = 0.30
_W_FILE_LINE   = 0.10   # additional signal: file:line reference (e.g. foo.py:42)
_W_FUNC_NAME   = 0.25
_W_CODE_BLOCK  = 0.40
_W_ISSUE_REF   = 0.20
_W_ERROR_KW    = 0.20
_W_TECH_NAME   = 0.10
_W_NUMERIC_SPEC = 0.15
_W_BYPASS      = 1.00
_W_PENALTY     = -0.10
_MAX_PENALTY   = -0.50

# ---------------------------------------------------------------------------
# Compiled patterns (ADR-0005 §1, §2)
# ---------------------------------------------------------------------------

# File path: \S+/\S+\.\w+ (must have slash + extension)
_RE_FILE_PATH = re.compile(r"\b\S+/\S+\.\w+\b")

# File:line reference: a file path immediately followed by :NNN
_RE_FILE_LINE = re.compile(r"\b\S+/\S+\.\w+:\d+")

# Function / method name: word followed by ()
_RE_FUNC_CALL = re.compile(r"\b[a-zA-Z_]\w*\(\)")
# def foo / function foo  (catches definitions without parens in docstrings etc.)
_RE_FUNC_DEF  = re.compile(r"\b(?:def|function)\s+[a-zA-Z_]\w*")

# Issue / PR reference
_RE_ISSUE = re.compile(r"#\d{3,}|\b(?:PR|issue)\s+#?\d+\b", re.IGNORECASE)

# Error keywords — case-SENSITIVE per ADR-0005
_ERROR_KEYWORDS = ("Error:", "Traceback", "Exception", "panic:")

# Numeric spec: digit(s) followed by unit
_RE_NUMERIC = re.compile(r"\d+\s*(?:s|ms|MB|GB|%|x)\b")

# Bypass marker — literal substring
_BYPASS_MARKER = "--skip-interview"

# Vagueness penalty phrases (case-insensitive substring match)
_VAGUE_PHRASES = (
    "build me",
    "create something",
    "i want a",
    "do whatever",
    "you decide",
    "fix this",
)

# Tech-name dictionary (case-insensitive word boundary match)
_TECH_NAMES: frozenset[str] = frozenset({
    "postgres", "postgresql", "mysql", "sqlite", "redis", "mongodb", "kafka",
    "tmux", "pytest", "unittest", "django", "flask", "fastapi", "sqlalchemy",
    "git", "docker", "kubernetes", "k8s", "terraform", "ansible", "nginx", "apache",
    "python", "javascript", "typescript", "rust", "golang", "java", "kotlin", "swift",
    "ruby", "php", "haskell", "scala", "clojure", "elixir", "erlang",
    "react", "vue", "angular", "svelte", "nextjs", "nuxt",
    "mypy", "ruff", "pylint", "eslint", "webpack", "vite", "babel",
    "aws", "gcp", "azure", "lambda", "s3", "ec2", "rds",
    "ssh", "http", "https", "grpc", "graphql", "rest", "websocket",
    "linux", "ubuntu", "debian", "fedora", "macos", "windows",
    "bash", "zsh", "powershell", "curl", "wget", "jq", "awk", "sed",
})

# ---------------------------------------------------------------------------
# Code-block detection (ADR-0005 §2)
# ---------------------------------------------------------------------------

_RE_FENCE_OPEN = re.compile(r"^\s*`{3,}")


def _detect_code_block(prompt: str) -> str | None:
    """Return evidence string if a qualifying code block is found, else None.

    Rules (ADR-0005 §2):
    - Fenced block: ≥ 3 non-empty lines between opening and closing fence.
    - Indented block: ≥ 3 consecutive lines each starting with ≥ 4 spaces.
    Inline backticks do NOT count.
    """
    lines = prompt.splitlines()

    # --- fenced block check ---
    in_fence = False
    fence_body_lines: list[str] = []
    for line in lines:
        if _RE_FENCE_OPEN.match(line):
            if not in_fence:
                in_fence = True
                fence_body_lines = []
            else:
                # closing fence
                # Count non-empty body lines
                non_empty = [l for l in fence_body_lines if l.strip()]
                if len(non_empty) >= 3:
                    return "fenced code block ({} body lines)".format(len(non_empty))
                in_fence = False
                fence_body_lines = []
        elif in_fence:
            fence_body_lines.append(line)

    # --- indented block check (outside fenced regions) ---
    streak = 0
    in_fence2 = False
    for line in lines:
        if _RE_FENCE_OPEN.match(line):
            in_fence2 = not in_fence2
            streak = 0
            continue
        if in_fence2:
            streak = 0
            continue
        if not line.strip():
            # blank line does not reset or count
            continue
        if line.startswith("    "):
            streak += 1
            if streak >= 3:
                return "indented block ({} lines)".format(streak)
        else:
            streak = 0

    return None


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def classify(
    prompt: str,
    *,
    threshold: float = 0.4,
    config: dict | None = None,
) -> dict:
    """Classify a prompt and return a routing decision dict.

    Returns:
        {
            "score": float,
            "threshold": float,
            "decision": "proceed" | "redirect" | "bypass",
            "redirect_to": str | None,
            "signals": list[dict],   # [{name, weight, evidence}]
            "prompt_excerpt": str,   # first 240 chars
            "ts": str,               # ISO-8601 UTC
        }
    """
    # Apply config override for threshold
    if config:
        router_cfg = config.get("router", {})
        threshold = float(router_cfg.get("vagueness_threshold", threshold))

    signals: list[dict[str, Any]] = []
    raw_score: float = 0.0

    prompt_lower = prompt.lower()

    # ------------------------------------------------------------------
    # Bypass check — must happen before everything else so that a vague
    # prompt with --skip-interview always yields "bypass".
    # ------------------------------------------------------------------
    if _BYPASS_MARKER in prompt:
        signals.append({
            "name": "bypass_marker",
            "weight": _W_BYPASS,
            "evidence": "--skip-interview",
        })
        raw_score += _W_BYPASS
        # Compute penalty still (for auditability) but decision is bypass.
        penalty = _compute_penalty(prompt_lower, signals)
        score = _clamp(raw_score + penalty)
        return _build_result(
            score=score,
            threshold=threshold,
            decision="bypass",
            redirect_to=None,
            signals=signals,
            prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Positive signals
    # ------------------------------------------------------------------

    # File:line reference (more specific than bare file path — fires in addition)
    m_fl = _RE_FILE_LINE.search(prompt)
    if m_fl:
        signals.append({
            "name": "file_line_ref",
            "weight": _W_FILE_LINE,
            "evidence": m_fl.group(0)[:60],
        })
        raw_score += _W_FILE_LINE

    # File path
    m = _RE_FILE_PATH.search(prompt)
    if m:
        signals.append({
            "name": "file_path",
            "weight": _W_FILE_PATH,
            "evidence": m.group(0)[:60],
        })
        raw_score += _W_FILE_PATH

    # Function / method name
    m_call = _RE_FUNC_CALL.search(prompt)
    m_def  = _RE_FUNC_DEF.search(prompt)
    func_match = m_call or m_def
    if func_match:
        signals.append({
            "name": "func_name",
            "weight": _W_FUNC_NAME,
            "evidence": func_match.group(0)[:60],
        })
        raw_score += _W_FUNC_NAME

    # Code block
    code_evidence = _detect_code_block(prompt)
    if code_evidence:
        signals.append({
            "name": "code_block",
            "weight": _W_CODE_BLOCK,
            "evidence": code_evidence,
        })
        raw_score += _W_CODE_BLOCK

    # Issue / PR reference
    m_issue = _RE_ISSUE.search(prompt)
    if m_issue:
        signals.append({
            "name": "issue_ref",
            "weight": _W_ISSUE_REF,
            "evidence": m_issue.group(0),
        })
        raw_score += _W_ISSUE_REF

    # Error keywords (case-sensitive)
    for kw in _ERROR_KEYWORDS:
        if kw in prompt:
            signals.append({
                "name": "error_keyword",
                "weight": _W_ERROR_KW,
                "evidence": kw,
            })
            raw_score += _W_ERROR_KW
            break  # fire once

    # Tech name (case-insensitive, fire once)
    tech_found: str | None = None
    for tech in sorted(_TECH_NAMES):
        pat = re.compile(r"\b" + re.escape(tech) + r"\b", re.IGNORECASE)
        if pat.search(prompt):
            tech_found = tech
            break
    if tech_found:
        signals.append({
            "name": "tech_name",
            "weight": _W_TECH_NAME,
            "evidence": tech_found,
        })
        raw_score += _W_TECH_NAME

    # Numeric spec
    m_num = _RE_NUMERIC.search(prompt)
    if m_num:
        signals.append({
            "name": "numeric_spec",
            "weight": _W_NUMERIC_SPEC,
            "evidence": m_num.group(0),
        })
        raw_score += _W_NUMERIC_SPEC

    # ------------------------------------------------------------------
    # Vagueness penalties
    # ------------------------------------------------------------------
    penalty = _compute_penalty(prompt_lower, signals)

    # ------------------------------------------------------------------
    # Final score and decision
    # ------------------------------------------------------------------
    score = _clamp(raw_score + penalty)

    if score < threshold:
        decision = "redirect"
        redirect_to = "deep-interview"
    else:
        decision = "proceed"
        redirect_to = None

    return _build_result(
        score=score,
        threshold=threshold,
        decision=decision,
        redirect_to=redirect_to,
        signals=signals,
        prompt=prompt,
    )


def _compute_penalty(prompt_lower: str, signals: list[dict]) -> float:
    """Compute cumulative vagueness penalty (capped at _MAX_PENALTY).

    Appends penalty entries to the signals list in-place.
    Returns the total penalty as a non-positive float.
    """
    seen_phrases: set[str] = set()
    raw_penalty: float = 0.0
    for phrase in _VAGUE_PHRASES:
        if phrase in prompt_lower and phrase not in seen_phrases:
            seen_phrases.add(phrase)
            raw_penalty += _W_PENALTY
    # Cap at _MAX_PENALTY
    capped_penalty = max(_MAX_PENALTY, raw_penalty)
    if capped_penalty < 0:
        signals.append({
            "name": "vagueness_penalty",
            "weight": capped_penalty,
            "evidence": ", ".join(f'"{p}"' for p in seen_phrases),
        })
    return capped_penalty


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _build_result(
    *,
    score: float,
    threshold: float,
    decision: str,
    redirect_to: str | None,
    signals: list[dict],
    prompt: str,
) -> dict:
    return {
        "score": round(score, 10),  # keep full precision; callers may round
        "threshold": threshold,
        "decision": decision,
        "redirect_to": redirect_to,
        "signals": signals,
        "prompt_excerpt": prompt[:240],
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# MCP state writer (best-effort; zero I/O in classify())
# ---------------------------------------------------------------------------


def emit_router_state(decision: dict, *, session_id: str | None = None) -> None:
    """Write the router decision to MCP state (mode="router").

    Best-effort: if the MCP server is unavailable, logs to stderr and returns.
    The classifier itself (classify()) stays pure — this helper is wired in by
    hooks/CLI only.
    """
    try:
        _emit_via_mcp(decision, session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[router] warn: could not persist state to MCP: {exc}", file=sys.stderr)


def _emit_via_mcp(decision: dict, *, session_id: str | None) -> None:
    """Internal: attempt to call mcp.server state_write via subprocess JSON-RPC."""
    import subprocess
    import uuid

    server_py = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    if not server_py.exists():
        raise FileNotFoundError(f"MCP server not found at {server_py}")

    body = {
        "prompt_excerpt": decision.get("prompt_excerpt", ""),
        "classifier_score": decision.get("score", 0.0),
        "decision": decision.get("decision", "unknown"),
        "redirect_to": decision.get("redirect_to"),
        "signals": decision.get("signals", []),
        "ts": decision.get("ts", ""),
    }
    if session_id:
        body["session_id"] = session_id

    rpc_request = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": "state_write",
            "arguments": {
                "mode": "router",
                "body": body,
                **({"session_id": session_id} if session_id else {}),
            },
        },
    })

    proc = subprocess.run(
        [sys.executable, str(server_py)],
        input=rpc_request,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"MCP server exited {proc.returncode}: {proc.stderr[:200]}")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load .omni/config.json from CWD upward. Returns empty dict if not found."""
    cwd = Path.cwd()
    for candidate in [cwd / ".omni" / "config.json", cwd.parent / ".omni" / "config.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WS3 router classifier — classify a prompt and print a JSON decision."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", metavar="TEXT", help="Prompt text to classify")
    group.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Vagueness threshold (default: from config or 0.4)"
    )
    parser.add_argument(
        "--emit-state", action="store_true",
        help="Also persist decision to MCP state (best-effort)"
    )
    parser.add_argument(
        "--session-id", default=None,
        help="Session ID to attach to state write (used with --emit-state)"
    )
    args = parser.parse_args(argv)

    if args.stdin:
        prompt_text = sys.stdin.read()
    else:
        prompt_text = args.prompt

    config = _load_config()

    kwargs: dict[str, Any] = {"config": config}
    if args.threshold is not None:
        kwargs["threshold"] = args.threshold

    result = classify(prompt_text, **kwargs)

    if args.emit_state:
        emit_router_state(result, session_id=args.session_id)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
