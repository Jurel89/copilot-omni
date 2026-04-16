#!/usr/bin/env python3
"""User-prompt-submit hook — WS3 structured router integration + WS7 trigger hints.

Reads the prompt from stdin JSON, runs the WS3 classifier, persists the
decision to MCP state (best-effort), and emits a structured
<router-decision ...> block that Copilot CLI honors.

Additionally scans skill frontmatter for declared triggers: fields and emits
a <skill-trigger-hint> block when the prompt matches a skill trigger.  The
trigger map is built once at hook startup from disk (< 30ms overhead).

Output format:
  redirect  -> <router-decision redirect="deep-interview" reason="vague-prompt" score="N">...</router-decision>
  bypass    -> <router-decision bypass="true" score="N">...</router-decision>
  proceed   -> <router-decision proceed="true" score="N"></router-decision>
  + optional <skill-trigger-hint skill="NAME" triggers="T1,T2">...</skill-trigger-hint>

Never blocks the hook pipeline: all failures are logged to stderr and
execution continues.

Kill switches:
  OMNI_SKIP_HOOKS=1             -- disable all hooks (canonical)
  DISABLE_OMNI=1                -- disable all hooks (canonical alternate)
  OMC_SKIP_HOOKS=1              -- legacy alias, deprecated, removed in v3.0.0
  DISABLE_OMC=1                 -- legacy alias, deprecated, removed in v3.0.0
  OMNI_SKIP_USER_PROMPT_SUBMIT=1 -- disable only this hook

Budget: <100ms, stdlib only.
"""
from __future__ import annotations

import sys
import os as _os

_HOOK_NAME = "user_prompt_submit"


def _quick_disabled() -> bool:
    env = _os.environ
    if env.get("DISABLE_OMNI") or env.get("OMNI_SKIP_HOOKS"):
        return True
    if env.get("DISABLE_OMC") or env.get("OMC_SKIP_HOOKS"):
        import importlib.util as _iu
        _lib_path = _os.path.join(_os.path.dirname(__file__), "_hook_lib.py")
        _spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
        if _spec and _spec.loader:
            _mod = _iu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _mod._deprecation_warn()
        return True
    if env.get("OMNI_SKIP_USER_PROMPT_SUBMIT"):
        return True
    return False


if _quick_disabled():
    sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)

import importlib.util
import json
import os
import re
import time
from pathlib import Path

import importlib.util as _iu
_lib_path = os.path.join(os.path.dirname(__file__), "_hook_lib.py")
_spec = _iu.spec_from_file_location("_hook_lib", _lib_path)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_append_audit = _mod._append_audit
_write_metric = _mod._write_metric

# Plugin root: OMNI_PLUGIN_ROOT (primary) > CLAUDE_PLUGIN_ROOT (legacy fallback) > file-relative default.
# NOTE: Path("") == Path(".") which is truthy, so we must NOT use `or` with Path("").
_PLUGIN_ROOT = (
    Path(os.environ["OMNI_PLUGIN_ROOT"]) if os.environ.get("OMNI_PLUGIN_ROOT")
    else Path(os.environ["CLAUDE_PLUGIN_ROOT"]) if os.environ.get("CLAUDE_PLUGIN_ROOT")
    else Path(__file__).resolve().parent.parent
)


# ---------------------------------------------------------------------------
# Skill frontmatter trigger map (built once at import time)
# ---------------------------------------------------------------------------

def _parse_trigger_list(raw: str) -> list[str]:
    """Parse a frontmatter triggers value into a list of strings.

    Handles both:
      triggers: ["foo", "bar"]  (JSON array)
      triggers: foo, bar        (comma-separated)
    """
    raw = raw.strip()
    if raw.startswith("["):
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return [str(x).strip() for x in result if str(x).strip()]
        except Exception:
            pass
    return [t.strip() for t in raw.split(",") if t.strip()]


def _build_trigger_map(skills_dir: Path) -> dict[str, list[str]]:
    """Walk skills/ and build {skill_name: [trigger, ...]} from frontmatter.

    Only parses SKILL.md files.  Runs once at hook startup.
    Expected overhead: < 20ms for a 30-skill tree.
    """
    trigger_map: dict[str, list[str]] = {}
    if not skills_dir.is_dir():
        return trigger_map
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            continue
        # Simple frontmatter parse: look for "triggers:" line between --- delimiters
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end < 0:
            continue
        block = text[3:end]
        for line in block.splitlines():
            if line.strip().startswith("triggers:"):
                _, _, value = line.partition(":")
                triggers = _parse_trigger_list(value)
                if triggers:
                    skill_name = skill_md.parent.name
                    trigger_map[skill_name] = triggers
                break
    return trigger_map


# Build trigger map once (at import)
_TRIGGER_MAP: dict[str, list[str]] = _build_trigger_map(_PLUGIN_ROOT / "skills")


def _match_skill_triggers(prompt: str) -> list[tuple[str, list[str]]]:
    """Return list of (skill_name, matched_triggers) for skills whose triggers match prompt."""
    matches = []
    lower_prompt = prompt.lower()
    for skill_name, triggers in _TRIGGER_MAP.items():
        matched = [t for t in triggers if t.lower() in lower_prompt]
        if matched:
            matches.append((skill_name, matched))
    return matches


def _build_skill_trigger_hint(matches: list[tuple[str, list[str]]]) -> str:
    """Render <skill-trigger-hint> blocks for each matched skill."""
    parts = []
    for skill_name, matched in matches:
        triggers_str = ", ".join(matched)
        parts.append(
            f'<skill-trigger-hint skill="{skill_name}" triggers="{triggers_str}">'
            f'Skill /{skill_name} matched trigger(s): {triggers_str}'
            f'</skill-trigger-hint>'
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Router helpers (unchanged from WS3)
# ---------------------------------------------------------------------------

def _load_router():
    """Dynamically import scripts/router.py without requiring it on sys.path."""
    router_path = Path(__file__).resolve().parent.parent / "scripts" / "router.py"
    spec = importlib.util.spec_from_file_location("router", router_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load router from {router_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_config() -> dict:
    """Load .omni/config.json from the project root (best-effort)."""
    root = Path(__file__).resolve().parent.parent
    config_path = root / ".omni" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _build_router_decision_tag(decision: dict) -> str:
    """Render the <router-decision ...> XML-like tag."""
    score = round(decision.get("score", 0.0), 4)
    d = decision.get("decision", "proceed")
    signals = decision.get("signals", [])
    signals_json = json.dumps(signals)

    if d == "redirect":
        return (
            f'<router-decision redirect="deep-interview" reason="vague-prompt" score="{score}">'
            f'{{"signals": {signals_json}, "bypass": "use --skip-interview to bypass"}}'
            f'</router-decision>'
        )
    elif d == "bypass":
        return (
            f'<router-decision bypass="true" score="{score}">'
            f'{{"signals": {signals_json}}}'
            f'</router-decision>'
        )
    else:
        return f'<router-decision proceed="true" score="{score}"></router-decision>'


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    t_start = time.monotonic()
    try:
        raw = sys.stdin.read() or "{}"
        event = json.loads(raw)
    except Exception:
        event = {}

    prompt = str(event.get("prompt", ""))

    try:
        router = _load_router()
        config = _load_config()
        decision = router.classify(prompt, config=config)
    except Exception as exc:
        print(f"[user_prompt_submit] warn: router classify failed: {exc}", file=sys.stderr)
        sys.stdout.write("{}")
        _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME, "router_decision": "error"})
        _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                      {"hook": _HOOK_NAME})
        return 0

    # Persist decision to MCP (best-effort)
    try:
        session_id = event.get("session_id") or os.environ.get("OMNI_SESSION_ID")
        router.emit_router_state(decision, session_id=session_id)
    except Exception as exc:
        print(f"[user_prompt_submit] warn: emit_router_state failed: {exc}", file=sys.stderr)

    # Phase-C C25: persist last decision to a sentinel file so
    # hooks/pre_tool_use.py can enforce it when OMNI_ROUTER_ENFORCE=1.
    try:
        sentinel_dir = Path(os.getcwd()) / ".omni" / "cache"
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        sentinel = sentinel_dir / "router-last.json"
        sentinel.write_text(json.dumps({
            "decision": decision.get("decision", "proceed"),
            "redirect_to": decision.get("redirect_to"),
            "score": decision.get("score", 0.0),
            "ts": decision.get("ts", ""),
            "prompt_excerpt": decision.get("prompt_excerpt", ""),
        }, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[user_prompt_submit] warn: could not persist router sentinel: {exc}",
              file=sys.stderr)

    # Build output context
    tag = _build_router_decision_tag(decision)

    # Frontmatter trigger hints
    trigger_matches = _match_skill_triggers(prompt)
    skill_hint = _build_skill_trigger_hint(trigger_matches) if trigger_matches else ""

    context_parts = [tag]
    if skill_hint:
        context_parts.append(skill_hint)
    context = "\n".join(context_parts)

    sys.stdout.write(json.dumps({"additionalContext": context}))

    router_decision_val = decision.get("decision", "proceed")
    skill_trigger_matched = bool(trigger_matches)

    _append_audit({
        "hook": _HOOK_NAME,
        "event_name": "user_prompt_submit",
        "tool_name": "",
        "prompt_excerpt": prompt[:120],
        "action": "router_dispatch",
        "reason": router_decision_val,
    })
    _write_metric("router_decision", router_decision_val, {"hook": _HOOK_NAME})
    _write_metric("skill_trigger_matched", int(skill_trigger_matched), {"hook": _HOOK_NAME})
    _write_metric("hook_exit_code", 0, {"hook": _HOOK_NAME})
    _write_metric("hook_latency_ms", round((time.monotonic() - t_start) * 1000, 2),
                  {"hook": _HOOK_NAME})

    return 0


if __name__ == "__main__":
    sys.exit(main())
