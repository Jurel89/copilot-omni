---
name: omni-do
description: "Route a freeform task to the right next action via the WS3 router"
---

# /omni-do — Router-Driven Task Dispatch

Route the user's freeform task through the WS3 intent classifier and act on the result.

## What this command does

1. Pass the user's task text to the router classifier:

   ```
   python3 scripts/router.py --stdin
   ```

   (pipe the task text via stdin, or use `--prompt "<task>"` for inline invocation)

2. Parse the JSON decision returned by the classifier.

3. Act on `decision`:
   - **`proceed`** — Execute the task directly. The prompt is concrete enough.
   - **`redirect`** — The prompt is vague. Invoke `/copilot-omni:deep-interview` to gather
     requirements before proceeding. Include the `signals` list from the decision in your
     context so the interview agent knows what is missing.
   - **`bypass`** — The user included `--skip-interview` in their prompt. Execute the task
     immediately without running the interview, regardless of concreteness score.

## Decision format

The router returns a JSON object:

```json
{
  "score": 0.27,
  "threshold": 0.4,
  "decision": "redirect",
  "redirect_to": "deep-interview",
  "signals": [{"name": "file_path", "weight": 0.3, "evidence": "hooks/foo.py"}],
  "prompt_excerpt": "...",
  "ts": "2026-04-16T11:00:00+00:00"
}
```

## Bypass syntax

Append `--skip-interview` anywhere in the task text to force `decision=bypass` and skip the
interview phase entirely. Example:

```
/omni-do fix the auth service --skip-interview
```

## Notes

- The classifier is pure-CPU and adds < 5ms overhead.
- The decision is persisted to MCP state (`mode="router"`) so downstream skills can inspect it
  without re-running the classifier.
- To inspect recent decisions: `omni doctor --verbose` or
  `python3 scripts/router_state.py --read --mode router`.
