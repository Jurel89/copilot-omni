# State Mode Registry

Canonical list of `mode` values written to the MCP `state` table.
Every literal `mode=` string in `skills/**/SKILL.md`, `agents/**/*.md`,
and `scripts/**/*.py` MUST appear here. The
`check_mode_key_registry` validator in
`scripts/verify_plugin_contract.py` enforces this.

## Naming convention

Dotted notation `<outer>.<inner>` identifies nested mode keys per
ADR-0006 §3.

## Session scopes

- **session**: row is keyed by `(mode, $OMNI_SESSION_ID)`; multiple
  sessions on the same host do not collide.
- **global**: row is keyed by `(mode, "")`; shared across sessions by
  design (the mode string itself already encodes any per-job identity).

## Registered modes

| Mode key               | Owner                       | Session scope | Description                                      |
|------------------------|-----------------------------|---------------|--------------------------------------------------|
| `subagent`             | scripts/subagent.py         | global        | Per-job subagent run status (key embeds `subagent:<id>`) |
| `autopilot`            | skills/autopilot/SKILL.md   | session       | Autopilot outer run state (phase, status)        |
| `autopilot.ralplan`    | skills/autopilot/SKILL.md   | session       | Inner ralplan run nested under autopilot         |
| `autopilot.ralph`      | skills/autopilot/SKILL.md   | session       | Inner ralph run nested under autopilot           |
| `ralph`                | skills/ralph/SKILL.md       | session       | Ralph stand-alone run state                      |
| `ralplan`              | skills/ralplan/SKILL.md     | session       | Ralplan stand-alone consensus run state          |
| `ralplan.architect`    | skills/ralplan/SKILL.md     | session       | Inner architect review run under ralplan         |
| `ralplan.critic`       | skills/ralplan/SKILL.md     | session       | Inner critic review run under ralplan            |
| `ultrawork`            | skills/ultrawork/SKILL.md   | session       | Ultrawork parallel task execution state          |
| `ultraqa`              | skills/ultraqa/SKILL.md     | session       | Ultraqa QA convergence run state                 |
| `team`                 | skills/team/SKILL.md        | session       | Team orchestration run state (WS6 orchestrator)  |
| `team.<worker-slug>`   | scripts/omni_team.py        | session       | Per-worker team state (dynamic key per ADR-0006) |
| `team.<slug>.ralph`    | scripts/omni_team.py        | session       | Inner ralph run nested under team worker         |
| `team.<slug>.autopilot`| scripts/omni_team.py        | session       | Inner autopilot run nested under team worker     |
| `plan`                 | skills/plan/SKILL.md        | session       | Plan skill run state (spec path, cycle)          |
| `deep-interview`       | skills/deep-interview/SKILL.md | session    | Deep-interview run state (phase, ambiguity score) |

## Governance

- Add a new row before shipping any new `state_write(mode="...")` call.
- Remove a row only when the associated code is deleted.
- The `check_mode_key_registry` validator in
  `scripts/verify_plugin_contract.py` scans `scripts/`, `mcp/`, and
  `skills/**/*.md` for literal `mode=` strings (positional and keyword)
  and cross-references this table.
