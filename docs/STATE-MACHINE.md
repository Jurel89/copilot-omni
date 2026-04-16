# Four-Gate State Machine (Phase-C C19)

Long-running copilot-omni workflows pass through four gates in order:

```
discuss ─▶ plan ─▶ execute ─▶ verify ─▶ done
```

Every run directory under `.omni/runs/<run-id>/` may carry a `state.json`
that records the current gate and a history of transitions. `omni` CLI
subcommands can require the run to be at a given gate before proceeding;
downstream skills (ralph, autopilot, team, ralplan) are free to set the
gate themselves or ignore it entirely.

## State shape

```jsonc
{
  "gate": "plan",
  "updated_at": 1713312000.0,
  "history": [
    { "gate": "discuss", "ended_at": 1713311900.0, "note": "ambiguity cleared" }
  ]
}
```

## Transitions

| From → To | Allowed | Notes |
|---|---|---|
| `discuss → plan`     | yes | normal forward |
| `plan → execute`     | yes | normal forward |
| `execute → verify`   | yes | normal forward |
| `verify → done`      | yes | terminal |
| any → same           | yes | idempotent |
| step back once       | yes | e.g. `plan → discuss` after a critic rejection |
| step back twice      | no  | would indicate thrashing; surfaces a StateMachineError |
| skip a gate          | no  | `discuss → execute` is rejected |

## CLI

```bash
# Inspect
python3 scripts/state_machine.py read .omni/runs/<run-id>

# Advance
python3 scripts/state_machine.py advance .omni/runs/<run-id> plan \
    --note "consensus reached in cycle 2"

# Gate check (non-zero exit blocks callers)
python3 scripts/state_machine.py require .omni/runs/<run-id> execute
```

## Integration points

- `omni execute` should call `require .. execute` (wired by the artifact
  gate in C20).
- `omni verify` should call `require .. verify` before running checks.
- Skill bash blocks may call `advance` directly when they know they have
  reached a new gate — e.g. ralplan advances from `discuss` to `plan`
  when the Critic APPROVEs.

## Non-goals

- No timers. The state machine does not care how long a gate lasts.
- No branching. Parallel plans live in sibling run-dirs, each with their
  own state machine.
- No retry policy. Re-entering a gate is idempotent but rewinding more
  than one step is explicitly blocked to surface stuck workflows.
