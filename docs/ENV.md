# copilot-omni environment variables

Reference for every env var copilot-omni consults at runtime. Variables
are additive — every one has a sensible default and nothing is required.

## Hooks

| Var | Default | Effect |
|---|---|---|
| `OMNI_SKIP_HOOKS` | unset | disable all hooks (canonical kill switch) |
| `DISABLE_OMNI` | unset | canonical alternate for `OMNI_SKIP_HOOKS` |
| `OMC_SKIP_HOOKS` | unset | legacy alias; deprecated, removed in v3.0.0 |
| `DISABLE_OMC` | unset | legacy alias; deprecated |
| `OMNI_SKIP_<HOOK>` | unset | per-hook kill switch (e.g. `OMNI_SKIP_PRE_TOOL_USE=1`) |
| `OMNI_POLICY_FILE` | unset | override policy file path (else `.omni/policy-<profile>.json`) |
| `OMNI_POLICY_PROFILE` | `standard` | selects `policies/<profile>.json` |

## Subagent back-pressure (C02, C08, C26)

| Var | Default | Effect |
|---|---|---|
| `OMNI_SUBAGENT_MEM_CAP_MB` | `512` | per-subagent memory ceiling used in the rollup projection |
| `OMNI_POOL_MEM_CAP_MB` | `4096` | hard ceiling for cumulative RSS across active subagents |
| `OMNI_SUBAGENT_ALLOW_ALL` | `false` | pass `--allow-all` to spawned copilot sessions |
| `OMNI_SUBAGENT_FAKE` | `false` | test hook: bypass real copilot (honoured only inside pytest) |
| `OMNI_TEST_MODE` | unset | when `1`, FAKE mode honoured outside pytest (for scripts) |
| `OMNI_SUBAGENT_FAKE_SLEEP_SECS` | `1` | fake subprocess sleep (tests only) |
| `OMNI_SUBAGENT_FAKE_EXIT_CODE` | `0` | fake subprocess exit code (tests only) |
| `OMNI_SUBAGENT_FAKE_STDERR` | `` | fake subprocess stderr payload (tests only) |
| `OMNI_SUBAGENT_FAKE_RESPONSE_FILE` | `` | per-agent scripted response JSON (tests only) |

## MCP tools

| Var | Default | Effect |
|---|---|---|
| `OMNI_HOME` | `~/.omni` | SQLite root for the MCP server + lock files |
| `OMNI_MEM_TTL_DAYS` | `30` | default TTL for `memory_prune` (C24) |
| `OMNI_NOTEPAD_TTL_DAYS` | `30` | default TTL for `notepad_prune` (C24) |
| `OMNI_RUNS_TTL_DAYS` | `14` | default TTL for `scripts/runs_gc.py` and `omni doctor --gc` (C32) |

## Contract validator (C03)

| Var | Default | Effect |
|---|---|---|
| `OMNI_EXEMPTION_CAP_OVERRIDE` | unset | hard-override the aggregate exemption budget cap |
| `OMNI_EXEMPTION_CAP_DATE` | unset | pin the effective date (YYYY-MM-DD) for the falling schedule |

## Team / tmux (C12)

| Var | Default | Effect |
|---|---|---|
| `OMNI_EXPERIMENTAL_TEAM` | unset | opt into the experimental Windows tmux path (still requires a tmux binary on PATH) |

## i18n (C21)

| Var | Default | Effect |
|---|---|---|
| `OMNI_SKILL_LANG` | `en` | select a skill translation when available under `skills/<name>/translations/<lang>.md` |

## Plugin install paths

| Var | Default | Effect |
|---|---|---|
| `OMNI_PLUGIN_ROOT` | computed from `__file__` | plugin root — primary |
| `OMNI_PLUGIN_ROOT` | computed from `__file__` | plugin root — primary |
| `OMNI_SESSION_ID` | unset | session identifier used by MCP state writes |

## Cancel cascade (C33)

| Var | Default | Effect |
|---|---|---|
| `PARENT_RUN_ID` | unset | outer run-id set by `scripts/subagent.py --parent-run-id` |
| `PARENT_RUN_DIR` | unset | outer run-dir path (`.omni/runs/<PARENT_RUN_ID>/`) |
