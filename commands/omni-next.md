---
name: omni-next
description: "Determine the next action for the current session by reading router state"
---

# /omni-next — Router-State-Driven Next Action

Read the most recent WS3 router decision for the current session and determine what to do next.

## What this command does

1. Read the persisted router state by running:

   ```
   python3 scripts/router_state.py --read --mode router --session-id <current-session-id>
   ```

   If the session ID is not known, omit `--session-id` to read the global router slot.

2. Parse the returned JSON.

3. Act on `decision`:
   - **`proceed`** — Continue with the task that was previously classified. No interview needed.
   - **`redirect`** — The previous classification suggested an interview. Invoke
     `/copilot-omni:deep-interview` now if it has not already run.
   - **`bypass`** — The user previously opted out of the interview. Execute without interviewing.
   - **`none` / no state** — No prior routing decision exists for this session. Prompt the user
     for their task and run `/omni-do` to classify it.

## Decision format

```json
{
  "decision": "proceed",
  "classifier_score": 0.55,
  "redirect_to": null,
  "prompt_excerpt": "fix hooks/pre_tool_use.py:42...",
  "ts": "2026-04-16T11:00:00+00:00"
}
```

## Important caveats

**This command is a markdown-driven LLM instruction, not an executable script.** The
determinism comes from `scripts/router_state.py`'s output — the LLM reads that output and
acts on it. The command file itself is consumed by the LLM as instructions; it does not
execute independently. Reviewers should not expect a standalone CLI binary here.

- The state reader returns a stub `{"status": "unknown", "reason": "WS5 not yet shipped"}` for
  pipeline modes other than `router` (autopilot, ralph, ultrawork). This is intentional per the
  WS3 plan (F4). WS5b will replace the stub with real pipeline state.
- To write a fresh decision: `/omni-do <task>`.
- To inspect all recent decisions: `omni doctor --verbose`.
