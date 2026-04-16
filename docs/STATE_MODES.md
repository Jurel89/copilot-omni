# State Mode Registry

Canonical list of all `mode` values written to the MCP `state` table.
Every literal `mode=` string in SKILL.md recipes and `*.py` files MUST
appear here.  The `check_mode_key_registry` validator (T1) enforces this.

## Naming convention

Dotted notation `<outer>.<inner>` identifies nested mode keys per ADR-0006 §3.

## Registered modes

| Mode key               | Owner skill / file          | Description                                      |
|------------------------|-----------------------------|--------------------------------------------------|
| `router`               | scripts/router.py           | WS3 router decision (concreteness score etc.)    |
| `subagent`             | scripts/subagent.py         | Per-job subagent run status (key: subagent:<id>) |
| `autopilot`            | skills/autopilot/SKILL.md   | Autopilot outer run state (phase, status)        |
| `autopilot.ralplan`    | skills/autopilot/SKILL.md   | Inner ralplan run nested under autopilot         |
| `autopilot.ralph`      | skills/autopilot/SKILL.md   | Inner ralph run nested under autopilot           |
| `ralph`                | skills/ralph/SKILL.md       | Ralph stand-alone run state                      |
| `ralplan`              | skills/ralplan/SKILL.md     | Ralplan stand-alone consensus run state          |
| `ralplan.architect`    | skills/ralplan/SKILL.md     | Inner architect review run under ralplan         |
| `ralplan.critic`       | skills/ralplan/SKILL.md     | Inner critic review run under ralplan            |
| `ultrawork`            | skills/ultrawork/SKILL.md   | Ultrawork parallel task execution state          |
| `ultraqa`              | skills/ultraqa/SKILL.md     | Ultraqa QA convergence run state                 |
| `team`                 | skills/team/SKILL.md        | Team orchestration run state (WS6 orchestrator)  |
| `team.<worker-slug>`   | scripts/omni_team.py        | Per-worker team state (dynamic key per ADR-0006) |
| `team.<slug>.ralph`    | scripts/omni_team.py        | Inner ralph run nested under team worker         |
| `team.<slug>.autopilot`| scripts/omni_team.py        | Inner autopilot run nested under team worker     |

## Governance

- Add new rows before shipping any new `state_write(mode="...")` call.
- Remove rows only when the associated code is deleted.
- The `check_mode_key_registry` validator in `scripts/verify_plugin_contract.py`
  scans `scripts/`, `mcp/`, and `skills/**/*.md` for literal `mode=` strings
  and cross-references this table.
