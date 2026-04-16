#!/usr/bin/env python3
"""User-prompt-submit hook — WS3 structured router integration.

Reads the prompt from stdin JSON, runs the WS3 classifier, persists the
decision to MCP state (best-effort), and emits a structured
<router-decision …> block that Copilot CLI honors.

Output format:
  redirect  → <router-decision redirect="deep-interview" reason="vague-prompt" score="N">…</router-decision>
  bypass    → <router-decision bypass="true" score="N">…</router-decision>
  proceed   → <router-decision proceed="true" score="N"></router-decision>

Never blocks the hook pipeline: MCP failures are logged to stderr and
execution continues. Kill switches are honored.

Budget: <100ms, stdlib only.
"""

# ---------------------------------------------------------------------------
# Kill-switch: OMNI_SKIP_HOOKS=1 or DISABLE_OMNI=1 disables this hook.
# Backward-compat aliases: OMC_SKIP_HOOKS and DISABLE_OMC are honoured
# during the deprecation window and will be removed in v3.0.0.
# ---------------------------------------------------------------------------
import os as _os
if (_os.environ.get("OMNI_SKIP_HOOKS") or _os.environ.get("DISABLE_OMNI")
        or _os.environ.get("OMC_SKIP_HOOKS") or _os.environ.get("DISABLE_OMC")):
    import sys as _sys
    _sys.stdout.write("{}")
    _sys.stdout.flush()
    _sys.exit(0)
del _os

import importlib.util
import json
import os
import sys
from pathlib import Path


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
    """Render the <router-decision …> XML-like tag for the Copilot CLI system-reminder."""
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
        # proceed
        return f'<router-decision proceed="true" score="{score}"></router-decision>'


def main() -> int:
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
        # Router failure must not block the pipeline
        print(f"[user_prompt_submit] warn: router classify failed: {exc}", file=sys.stderr)
        sys.stdout.write("{}")
        return 0

    # Persist decision to MCP (best-effort)
    try:
        session_id = event.get("session_id") or os.environ.get("OMNI_SESSION_ID")
        router.emit_router_state(decision, session_id=session_id)
    except Exception as exc:
        print(f"[user_prompt_submit] warn: emit_router_state failed: {exc}", file=sys.stderr)

    # Emit the structured decision tag as a system-reminder via additionalContext
    tag = _build_router_decision_tag(decision)
    sys.stdout.write(json.dumps({"additionalContext": tag}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
