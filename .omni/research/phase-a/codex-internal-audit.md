# Internal Audit (Codex Cross-Check)

## 1. Pipeline reality-check — per-skill verdict

### Autopilot

**Verdict: doc-only orchestration; not executable as described in the current Copilot harness.**

`skills/autopilot/SKILL.md` describes a five-phase autonomous pipeline that writes to `.omc`, skips phases based on `.omc/specs` and `.omc/plans`, and finishes by invoking `/oh-my-claudecode:cancel` (`skills/autopilot/SKILL.md:39-72`). The actual repository contract, however, is `.omni`-centric: `AGENTS.md` defines project state under `.omni/` (`AGENTS.md:77-90`), `scripts/omni.py` scaffolds `.omni/` (`scripts/omni.py:83-104`), `mcp/server.py` mirrors artifacts to `.omni/runs/<run_id>/...` (`mcp/server.py:349-359`), and `commands/omni-init.md`/`commands/omni-plan.md` likewise point to `.omni` (`commands/omni-init.md:8-10`, `commands/omni-plan.md:8`). That means autopilot’s file-discovery and cleanup rules target a state tree the harness never creates.

Autopilot also assumes Claude-native subagent calls for review: `Task(subagent_type="oh-my-claudecode:architect")`, `security-reviewer`, and `code-reviewer` (`skills/autopilot/SKILL.md:75-81`). The only documented Copilot translation in this repo is `scripts/subagent.py`, which can spawn a plain `copilot -p ... --agent <name>` process (`AGENTS.md:62-75`, `scripts/subagent.py:24-42`). There is no runtime layer that parses `Task(...)` syntax inside a skill and rewrites it to `scripts/subagent.py`. In practice, the skill text is aspirational, not backed by code.

The trigger story is inconsistent too. The skill claims it should activate on phrases including `"auto pilot"`, `"autonomous"`, `"build me"`, `"create me"`, `"make me"`, and `"I want a/an..."` (`skills/autopilot/SKILL.md:12-17`), but `hooks/user_prompt_submit.py` only matches `autopilot`, `full auto`, and `handle it all` (`hooks/user_prompt_submit.py:13-24`). The front door therefore misses most of the skill’s own advertised intent surface.

### Ralph

**Verdict: heavily Claude-coupled; the core persistence/review loop is not wired to the Copilot runtime that ships here.**

Ralph’s contract depends on several primitives the repo does not implement: `Task(...)` subagents, `Skill("ai-slop-cleaner")`, `run_in_background: true`, and `/oh-my-claudecode:cancel` (`skills/ralph/SKILL.md:48-53`, `skills/ralph/SKILL.md:93-131`). The local Copilot bridge does not expose any of those abstractions. `scripts/subagent.py` supports only a blocking subprocess with `--agent` and optional `--model`; there is no background mode, no skill invocation bridge, and no orchestration state machine (`scripts/subagent.py:24-42`).

Ralph also hard-depends on `docs/shared/agent-tiers.md` for model routing (`skills/ralph/SKILL.md:52`, `skills/ralph/SKILL.md:224-228`), but that file is absent from the repo. This is not a soft reference; the skill says to read it before first delegation.

The Codex-review lane is explicitly broken in the current harness. Ralph instructs the model to run `omc ask codex --agent-prompt critic ...` (`skills/ralph/SKILL.md:98-102`, `skills/ralph/SKILL.md:127`), but `scripts/omni.py` only implements `version`, `doctor`, `init`, `status`, `plugin-install`, `mcp`, and `list` subcommands (`scripts/omni.py:165-194`). There is no `ask` subcommand at all.

State handling is also incompatible with the shipped MCP server. Ralph expects `state_write` / `state_read` to persist named mode state between iterations (`skills/ralph/SKILL.md:130`), but later skills in the same pipeline assume those tools accept flat keyword arguments like `active`, `iteration`, `session_id`, and `current_phase`. The actual server accepts only `mode` and an optional nested `body` object (`mcp/server.py:470-480`, `mcp/server.py:857-881`). Anything written in the documented Ralph style would be semantically wrong unless manually rewrapped.

Finally, Ralph’s own docs contradict the repo contract about cleanup. It insists on `/oh-my-claudecode:cancel` for success cleanup (`skills/ralph/SKILL.md:119`, `skills/ralph/SKILL.md:218`), but there is no implementation of that command in `commands/` and no executable cancel harness beyond another Markdown skill.

### Ultrawork

**Verdict: parallel-execution prose with no executable parallel runtime in this checkout.**

Ultrawork says it fires independent work simultaneously and uses `run_in_background: true` for long operations (`skills/ultrawork/SKILL.md:30-35`, `skills/ultrawork/SKILL.md:45-58`). Nothing in the repo implements that. `scripts/subagent.py` invokes exactly one synchronous subprocess and returns its exit code (`scripts/subagent.py:35-42`). There is no queue, no worker pool, no promise handle, and no background job registry.

Like Ralph, Ultrawork requires the missing `docs/shared/agent-tiers.md` (`skills/ultrawork/SKILL.md:33`, `skills/ultrawork/SKILL.md:39`) and still uses the Claude-only `Task(subagent_type="oh-my-claudecode:executor", model="haiku|sonnet|opus")` idiom (`skills/ultrawork/SKILL.md:55-58`, `skills/ultrawork/SKILL.md:66-77`). The actual bridge does not parse that syntax, and it does not normalize the model names. It forwards any provided `model` string verbatim to `copilot --model ...` (`scripts/subagent.py:35-39`). That leaves Ultrawork depending on undocumented Copilot acceptance of bare strings like `haiku` and `opus`, while the agent frontmatter elsewhere uses different identifiers such as `claude-sonnet-4-6` (`agents/executor.md:1-6`, `agents/architect.md:1-6`).

### UltraQA

**Verdict: workflow spec only; no durable QA loop implementation.**

UltraQA defines a retry loop of `qa-tester -> architect -> executor` using `Task(...)` calls (`skills/ultraqa/SKILL.md:34-68`) and stores state in `.omc/ultraqa-state.json` / `.omc/state/ultraqa-state.json` (`skills/ultraqa/SKILL.md:94-131`). The shipped runtime never creates `.omc` state, and the MCP server’s state API stores JSON blobs in SQLite, not JSON files (`AGENTS.md:77-90`, `mcp/server.py:470-508`).

The skill’s cancellation model depends on `/oh-my-claudecode:cancel` (`skills/ultraqa/SKILL.md:110-112`), but the actual hook/command surface exposes only `/omni-*` commands (`commands/omni-doctor.md:1-16`, `commands/omni-init.md:1-10`, `commands/omni-status.md:1-12`). UltraQA therefore has no concrete control plane in this repo beyond the text of the skill itself.

### Ralplan

**Verdict: alias points at non-existent Copilot command/skill names and unsupported interaction tools.**

Ralplan calls itself shorthand for `/oh-my-claudecode:omc-plan --consensus` (`skills/ralplan/SKILL.md:10`, `skills/ralplan/SKILL.md:36`). There is no `omc-plan` command in `commands/`; the shipped command is `omni-plan` (`commands/omni-plan.md:1-8`). There is also no concrete implementation of a `Skill("oh-my-claudecode:team")` or `Skill("oh-my-claudecode:ralph")` bridge in the repo (`skills/ralplan/SKILL.md:56-58`).

Ralplan’s interactive flow requires `AskUserQuestion` (`skills/ralplan/SKILL.md:46`, `skills/ralplan/SKILL.md:56`) and sequential `Task(...)` reviewer passes. Again, the shipped runtime only includes `scripts/subagent.py` for raw agent subprocesses (`AGENTS.md:62-75`, `scripts/subagent.py:24-42`); it does not supply `AskUserQuestion`, `Skill`, or any plan-orchestration state engine.

### Team

**Verdict: fundamentally incompatible with current Copilot CLI runtime; most of the documented runtime is missing.**

`skills/team/SKILL.md` is written for Claude Code native team mode. It depends on `TeamCreate`, `TaskCreate`, `TaskUpdate`, `Task(team_name=...)`, `SendMessage`, and `TeamDelete` (`skills/team/SKILL.md:53-76`, `skills/team/SKILL.md:212-345`, `skills/team/SKILL.md:413-431`, `skills/team/SKILL.md:533-588`). None of those exist in `scripts/`, `mcp/server.py`, or `commands/`. A repo-wide search outside `skills/` finds no implementation of `TeamCreate`, `TeamDelete`, `TaskCreate`, `TaskUpdate`, or `SendMessage`.

The hybrid CLI-worker branch is also unimplemented here. The skill describes Codex/Gemini workers, outbox utilities like `readAllTeamOutboxMessages(...)`, status helpers like `getTeamStatus(...)`, and worktree helpers like `createWorkerWorktree(...)` / `cleanupTeamWorktrees(...)` (`skills/team/SKILL.md:660-716`, `skills/team/SKILL.md:920-935`), but there are no corresponding code files in the repo. The orphan cleanup step explicitly calls `node "${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-orphans.mjs"` (`skills/team/SKILL.md:577-582`), and that script does not exist.

State expectations are wrong too. The skill says `state_write(mode="team", active=true, current_phase="team-plan", state={...})` and even warns that the MCP tool transports values as strings (`skills/team/SKILL.md:235-247`). The actual `state_write` handler accepts only `mode` and a nested `body`; it does not flatten keys, does not coerce values to strings, and does not understand `session_id` (`mcp/server.py:470-480`, `mcp/server.py:857-881`). The skill is describing a different state API than the one this repo ships.

The skill also points users toward `omc team ...` behavior for CLI workers (`skills/team/SKILL.md:492`, `skills/team/SKILL.md:481`), but `scripts/omni.py` has no `team` subcommand (`scripts/omni.py:165-194`).

### Deep-Interview

**Verdict: rich interactive spec-gathering design, but not runnable with the repo’s current tool surface.**

Deep-interview depends on `state_write(mode="deep-interview")`, `AskUserQuestion`, `Task(subagent_type="oh-my-claudecode:explore")`, direct file writes into `.omc/specs/`, and `Skill()`-based handoffs into `omc-plan`, `autopilot`, `ralph`, or `team` (`skills/deep-interview/SKILL.md:73`, `skills/deep-interview/SKILL.md:132`, `skills/deep-interview/SKILL.md:261`, `skills/deep-interview/SKILL.md:348-409`). None of those orchestration primitives are present in the shipped Copilot bridge, and its file targets are again `.omc`, not `.omni`.

This is not just a naming drift. The actual repo contract for persisted artifacts is `.omni/` (`AGENTS.md:77-90`, `scripts/omni.py:83-104`), while deep-interview’s resume path reads `.omc/state/deep-interview-state.json` (`skills/deep-interview/SKILL.md:565`). There is no code path in the repo that would ever create that file.

### Plan

**Verdict: the most important orchestration skill is wired to absent commands, absent tools, and the wrong storage contract.**

The plan skill expects `AskUserQuestion`, `Task(...)` for `architect`/`critic`/`planner`/`analyst`, `Skill("oh-my-claudecode:team")`, `Skill("oh-my-claudecode:ralph")`, and `Skill("compact")` (`skills/plan/SKILL.md:92-122`, `skills/plan/SKILL.md:146-157`). None of these are implemented in the repo’s executable layer. There is no `compact` command or skill in `commands/` or `skills/`. There is no `start-work` command either, even though the planner agent still insists on it (`agents/planner.md:31-34`, `agents/planner.md:51-52`, `agents/planner.md:94-97`).

The Codex escalation path is especially concrete and especially broken: the skill documents `omc ask codex --agent-prompt architect|critic ...` (`skills/plan/SKILL.md:74-75`), but `scripts/omni.py` does not implement `ask` (`scripts/omni.py:165-194`).

Plan’s state contract is also from a different world. It expects `state_write(mode="ralplan", active=true, session_id=<current_session_id>)` and `state_clear(..., session_id=...)` (`skills/plan/SKILL.md:79-81`, `skills/plan/SKILL.md:117-121`, `skills/plan/SKILL.md:156-157`). The shipped MCP server has no `session_id` parameter for any state tool and no special cancel-signal behavior (`mcp/server.py:470-508`, `mcp/server.py:857-881`).

### Cancel

**Verdict: the cancellation model is largely fictional relative to the shipped MCP server and command surface.**

Cancel depends on `state_list_active` and `state_get_status` (`skills/cancel/SKILL.md:41-47`, `skills/cancel/SKILL.md:104-108`, `skills/cancel/SKILL.md:136-142`, `skills/cancel/SKILL.md:188-190`, `skills/cancel/SKILL.md:318-320`), but the MCP server exposes only `state_write`, `state_read`, and `state_clear` (`AGENTS.md:48-58`, `mcp/server.py:857-881`). Those extra tools do not exist.

It also requires Claude-native `ToolSearch`, `SendMessage`, and `TeamDelete` (`skills/cancel/SKILL.md:43-47`, `skills/cancel/SKILL.md:215-240`, `skills/cancel/SKILL.md:270-277`) and calls the missing `cleanup-orphans.mjs` script (`skills/cancel/SKILL.md:247-255`). The fallback shell snippet is `.omc`-based and Unix-first, using `rm`, `find`, and GNU/BSD date behaviors (`skills/cancel/SKILL.md:60-100`), while the actual runtime is `.omni` + SQLite (`AGENTS.md:77-90`, `mcp/server.py:46-72`).

## 2. Harness engineering findings

The harness is internally split between two incompatible products. The executable side uses `.omni`, SQLite-backed MCP state, and a tiny `copilot --agent` subprocess bridge (`AGENTS.md:17`, `AGENTS.md:77-90`, `scripts/omni.py:83-104`, `mcp/server.py:46-72`, `scripts/subagent.py:24-42`). A large part of the Markdown contract still assumes `.omc`, JSON file state, Claude team tools, and slash commands in the `oh-my-claudecode` namespace (`skills/autopilot/SKILL.md:39-72`, `skills/plan/SKILL.md:79-122`, `skills/cancel/SKILL.md:104-142`). This is the repo’s central inconsistency.

Platform compatibility is weaker than the repo claims. Windows support is advertised via `scripts/omni.cmd`, but that wrapper still calls `python3`, not `py -3` or `python` (`scripts/omni.cmd:1-3`). `.mcp.json` also hardcodes `command: "python3"` (`.mcp.json:3-7`), `hooks/hooks.json` hardcodes `python3` for every hook (`hooks/hooks.json:5-32`), and the command docs tell users to run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/omni.py" ...` (`commands/omni-doctor.md:8`, `commands/omni-init.md:8`, `commands/omni-list.md:8`, `commands/omni-status.md:8`). On a stock Windows installation without a `python3` shim, the wrapper, hooks, and MCP server launch string all fail.

The repo also ships stale user-facing metadata. `hooks/session_start.py` advertises `29 MCP tools, 28+ skills, 17+ agents` (`hooks/session_start.py:8-12`), while the repo currently contains 30 registered MCP tools, 37 skills, and 19 agents (`AGENTS.md:7-13`, `mcp/server.py:738-1016`). That is a documentation drift problem in the first message every session sees.

`scripts/subagent.py` contradicts the repo contract in two ways. First, `AGENTS.md` says the bridge spawns `copilot -p ... --agent <name> --allow-all` and “collects the output” (`AGENTS.md:72-75`), but `scripts/subagent.py` defaults `allow_all` to false unless `OMNI_SUBAGENT_ALLOW_ALL=1` is set and does not capture stdout/stderr at all (`scripts/subagent.py:32-42`). Second, the bridge returns only an integer exit code, so any skill that assumes it can inspect the delegated agent’s response text is relying on behavior not implemented here.

The bundled validation and smoke scripts prove only shallow structure. `scripts/validate_plugin.py` checks frontmatter presence and counts (`scripts/validate_plugin.py:8-69`); `scripts/discovery_smoke.py` checks file existence and counts (`scripts/discovery_smoke.py:16-63`); neither validates that commands referenced from skills actually exist, that skill references map to real runtime tools, that `.omni` and `.omc` are coherent, or that agent/tool names are resolvable. The repo can therefore pass all harness smoke tests while still shipping non-runnable orchestration docs.

A smaller but important harness leak: tests are not hermetic against the working tree. `tests/test_security.py` exercises `artifact_write` with `run_id="run-2"` and `path="spec.md"` (`tests/test_security.py:138-151`), and `mcp/server.py` mirrors artifacts into the current repo’s `.omni/runs/<run_id>/...` tree (`mcp/server.py:349-359`). The checked-out repo currently contains `.omni/runs/run-2/spec.md` with `# hello` (`.omni/runs/run-2/spec.md:1`). That means a test run dirties the repository by default.

## 3. Intent-routing trigger table and conflicts

The only explicit front-door keyword router is `hooks/user_prompt_submit.py` (`hooks/user_prompt_submit.py:13-44`). It does not invoke skills directly; it emits a generic context hint listing all matched names (`hooks/user_prompt_submit.py:33-40`). There is no precedence model, no disambiguation, and no guaranteed handoff.

| Triggered skill | Regex in hook | What it fires | Main conflict / miss |
|---|---|---|---|
| `autopilot` | `\b(autopilot|full\s*auto|handle\s*it\s*all)\b` (`hooks/user_prompt_submit.py:14`) | Adds a generic hint mentioning `autopilot` (`hooks/user_prompt_submit.py:36-41`) | Misses most of the skill’s own documented triggers: `auto pilot`, `autonomous`, `build me`, `create me`, `make me`, `I want a/an...` (`skills/autopilot/SKILL.md:13-16`). |
| `ralph` | `\bralph\b` (`hooks/user_prompt_submit.py:15`) | Adds a generic hint for `ralph` | Misses Ralph’s advertised natural-language triggers like `don't stop`, `must complete`, `finish this`, `keep going until done` (`skills/ralph/SKILL.md:16-20`). |
| `ultrawork` | `\b(ultrawork|parallel\s+work)\b` (`hooks/user_prompt_submit.py:16`) | Adds a generic hint for `ultrawork` | Misses the documented shorthand `ulw` (`skills/ultrawork/SKILL.md:12-16`). |
| `team` | `\b(team\s+mode|/team)\b` (`hooks/user_prompt_submit.py:17`) | Adds a generic hint for `team` | Misses plain `team` phrasing and the documented `team ralph` composition unless the user literally types `/team` or `team mode` (`skills/team/SKILL.md:750-760`). |
| `plan` | `\b(plan(?:ning)?|/plan)\b` (`hooks/user_prompt_submit.py:18`) | Adds a generic hint for `plan` | Broad enough to fire on ordinary prose containing “plan” or “planning”; no check that the user actually wants the planning skill. |
| `debug` | `\b(debug|diagnose)\b` (`hooks/user_prompt_submit.py:19`) | Adds a generic hint for `debug` | Overlaps with normal conversational phrasing like “diagnose why” and can co-fire with `plan` or `verify`. |
| `verify` | `\b(verify|verification)\b` (`hooks/user_prompt_submit.py:20`) | Adds a generic hint for `verify` | Broad noun matching can co-fire in contexts where the user only wants explanation or planning. |
| `wiki` | `\b(wiki|knowledge\s+base)\b` (`hooks/user_prompt_submit.py:21`) | Adds a generic hint for `wiki` | Reasonable, but still hint-only. |
| `remember` | `\b(remember|save\s+this)\b` (`hooks/user_prompt_submit.py:22`) | Adds a generic hint for `remember` | `save this` is extremely broad and can fire during unrelated requests. |
| `ship` | `\b(ship\s+it|open\s+pr|create\s+pull\s+request)\b` (`hooks/user_prompt_submit.py:23`) | Adds a generic hint for `ship` | Can trigger in discussion contexts with no actual repo-ready state. |

The key shadowing issue is that the hook returns **all** matches without ranking them (`hooks/user_prompt_submit.py:33-40`). A prompt like “plan and verify this before you open a PR” can emit `plan`, `verify`, and `ship` simultaneously, but there is no resolver telling Copilot which one should win. Conversely, there is no `cancel` trigger at all, even though `cancel` is documented as the standard way to exit every active mode (`skills/cancel/SKILL.md:12-16`, `skills/cancel/SKILL.md:33-37`).

The other hooks are simpler but still notable:

- `session_start.py` injects a stale banner with wrong counts and `.omni` setup wording (`hooks/session_start.py:8-15`).
- `pre_tool_use.py` enforces policy from `.omni/policy-<profile>.json` and `CLAUDE_PLUGIN_ROOT` (`hooks/pre_tool_use.py:8-12`, `hooks/pre_tool_use.py:39-55`), not from `.omc`, which further proves the harness and skill docs are split-brain.
- `post_tool_use.py` appends a best-effort audit line into `.omni/audit/tool-audit.log` (`hooks/post_tool_use.py:18-27`), again using `.omni`, not `.omc`.
- `hooks/hooks.json` launches every hook via `python3 "${CLAUDE_PLUGIN_ROOT}/..."` (`hooks/hooks.json:5-32`), which is stale Claude-centric naming and a Windows portability risk.

## 4. Skill+agent contract violations

The biggest contract violation is that many skills and agents still prescribe Claude-native tools the Copilot plugin does not ship. Examples:

- `planner` requires `AskUserQuestion` and a handoff to `/oh-my-claudecode:start-work` (`agents/planner.md:33-34`, `agents/planner.md:51-52`, `agents/planner.md:94-97`), but there is no `start-work` command in `commands/`.
- `architect`, `executor`, `code-reviewer`, `security-reviewer`, `test-engineer`, and others advise `Task(subagent_type="oh-my-claudecode:...")` or `/team` for extra review lanes (`agents/architect.md:55-60`, `agents/executor.md:66-67`, `agents/code-reviewer.md:63-68`, `agents/security-reviewer.md:57-60`, `agents/test-engineer.md:72-76`). The only shipped bridge is `scripts/subagent.py`, and it is never referenced from those prompts.
- Several agents rely on tool names like `lsp_diagnostics`, `lsp_diagnostics_directory`, `ast_grep_search`, `WebSearch`, and `WebFetch` (`agents/executor.md:58-62`, `agents/verifier.md:38-46`, `agents/code-reviewer.md:47-60`, `agents/document-specialist.md:35-38`). None of those are part of `mcp/server.py` (`mcp/server.py:738-1016`). They may exist in some other environment, but they are not provided by this plugin.

There is also a hard storage-contract contradiction between agents and harness. `planner`, `executor`, `git-master`, `scientist`, and others speak in `.omc/*` terms (`agents/planner.md:11-12`, `agents/planner.md:25-33`, `agents/executor.md:38-39`, `agents/git-master.md:35`, `agents/scientist.md:25`) while the actual executable harness uses `.omni/*` (`AGENTS.md:77-90`, `scripts/omni.py:83-104`, `mcp/server.py:349-359`). An executor following the agent prompt literally will write plans and notes into directories the CLI scaffolder never created.

The team skill has the worst contract sprawl. It claims native Claude teams are the canonical runtime (`skills/team/SKILL.md:11`, `skills/team/SKILL.md:829`) while the repo-level `AGENTS.md` tells Copilot users to delegate with `scripts/subagent.py` (`AGENTS.md:17`, `AGENTS.md:60-75`). Those are two incompatible delegation models.

Finally, command naming is inconsistent across the repo:

- Real commands are `/omni-doctor`, `/omni-init`, `/omni-list`, `/omni-memory`, `/omni-plan`, `/omni-ship`, `/omni-status`, and `/omni-verify` (`commands/*.md`).
- Skills and agents repeatedly reference `/oh-my-claudecode:omc-plan`, `/oh-my-claudecode:cancel`, `/oh-my-claudecode:team`, `/oh-my-claudecode:start-work`, and similar names (`skills/ralplan/SKILL.md:10`, `skills/cancel/SKILL.md:33-37`, `skills/team/SKILL.md:18-20`, `agents/planner.md:33`, `agents/planner.md:52`).

That mismatch is not cosmetic. It means the written instructions route users and agents toward names the installed command set does not define.

## 5. MCP server audit

The MCP server is one of the few pieces of real code here, and it is materially better than the skill layer. It has working JSON-RPC handling, dual newline/content-length framing, path traversal checks for artifacts and workspaces, and SQLite-backed persistence (`mcp/server.py:56-72`, `mcp/server.py:89-108`, `mcp/server.py:337-367`, `mcp/server.py:680-703`, `mcp/server.py:1022-1215`). The bundled smoke tests and unit tests confirm the basics (`scripts/mcp_smoke.py:14-77`, `tests/test_mcp_server.py:43-170`).

But the MCP surface still has several important gaps.

**No schema enforcement.** `TOOLS` publishes JSON Schemas (`mcp/server.py:738-1016`), but `_handle()` never validates `params["arguments"]` against them. It simply pulls `spec = TOOLS.get(name)` and calls `spec["handler"](args)` (`mcp/server.py:1053-1061`). This means `additionalProperties`, required fields, enum restrictions, and types are advisory only unless a handler manually checks them. For example, `state_write`’s schema only describes `mode` and `body`, but nothing stops callers from passing extra undeclared keys; they are silently ignored because the handler just reads `args["mode"]` and `args.get("body", {})` (`mcp/server.py:470-480`, `mcp/server.py:857-865`).

**Raw exception leakage.** `_handle()` serializes `str(exc)` straight into the JSON-RPC error message (`mcp/server.py:1062-1063`). That is convenient for debugging, but it means filesystem paths and internal validation details can leak directly to the client.

**State API is far smaller than the docs assume.** The server exposes only `state_write`, `state_read`, and `state_clear` (`mcp/server.py:857-881`). There is no `state_list_active`, no `state_get_status`, no session-scoped storage, and no cancel-signal lifecycle. Yet the cancel, plan, and team skills all rely on those absent semantics (`skills/cancel/SKILL.md:41-47`, `skills/cancel/SKILL.md:104-142`, `skills/plan/SKILL.md:79-81`, `skills/team/SKILL.md:235-247`).

**`session_search` is effectively dead.** The server creates a `sessions` table (`mcp/server.py:187-193`) and offers a `session_search` reader (`mcp/server.py:650-658`, `mcp/server.py:976-982`), but there is no handler that inserts sessions. The list of all `INSERT` statements in the file covers `memory`, `artifacts`, `state`, `wiki`, `notepad`, `shared_memory`, and `runs` only (`mcp/server.py:271-274`, `mcp/server.py:346-347`, `mcp/server.py:475-477`, `mcp/server.py:518-521`, `mcp/server.py:561-562`, `mcp/server.py:602-605`, `mcp/server.py:668-669`). `session_search` therefore has no first-party data source.

**Trace tools are read-only with no write path.** The schema creates a `trace` table (`mcp/server.py:178-185`) and exposes `trace_summary` / `trace_timeline` (`mcp/server.py:624-647`, `mcp/server.py:960-974`), but there is no corresponding writer. As with `session_search`, the tool exists without a native producer.

**`subtask.route` is stub logic.** The `subtask` tool’s `route` action always returns `{"route": "executor", "reason": "default routing"}` (`mcp/server.py:675-676`), which makes the tool name sound smarter than the implementation actually is.

**Storage contract drift remains unresolved.** `artifact_write` mirrors to `.omni/runs/<run_id>/...` (`mcp/server.py:349-359`), `config_resolve` reads `.omni/config.json` (`mcp/server.py:251-258`), `policy_check` protects `.omni/config.json` (`mcp/server.py:417-423`), and `workspace` manipulates `.omni/workspaces/` (`mcp/server.py:680-703`). That is internally coherent, but it is incompatible with the `.omc` conventions documented across the skills and agents.

## 6. Test coverage gaps

The tests are real, not pure stubs, but they only validate the thin executable layer. `tests/test_cli.py` covers CLI basics like `version`, `init`, `list`, and partial `doctor` output (`tests/test_cli.py:23-51`). `tests/test_mcp_server.py` covers initialize, tools/list, health, memory, policy_check, wiki, unknown tool handling, and content-length framing (`tests/test_mcp_server.py:43-170`). `tests/test_hooks.py` checks a couple of policy cases, one autopilot trigger, and the banner (`tests/test_hooks.py:25-82`). `tests/test_security.py` adds traversal and policy regressions (`tests/test_security.py:41-169`).

What is missing is exactly the area this audit focused on:

- No test parses any pipeline skill and checks whether referenced tools or commands exist.
- No test asserts that `.omni` and `.omc` references are consistent.
- No test validates that `oh-my-claudecode:*` names map to installed commands or skills.
- No test verifies that `omc ask codex`, `omc team`, `compact`, or `start-work` exist, even though core skills rely on them.
- No test checks hook trigger coverage against the skills’ own declared trigger phrases.
- No test exercises session-aware cancellation because the MCP server does not implement the required tools.

Even `tests/test_discovery.py`, which sounds like the right place, only checks manifest existence, counts, simple frontmatter, and that `mcp/*.py` uses approved imports (`tests/test_discovery.py:28-99`). It does not perform referential integrity across the Markdown contracts.

The tests also miss the platform-compatibility hazards. There is no Windows-path or launcher test for `.mcp.json`, `hooks/hooks.json`, or `scripts/omni.cmd`, so the hardcoded `python3` dependency can slip through CI untouched (`.mcp.json:3-7`, `hooks/hooks.json:5-32`, `scripts/omni.cmd:1-3`).

## 7. Ranked bug/inconsistency list (Critical/High/Medium/Low) with file:line

### Critical

- **The documented state/cancel architecture does not exist in the shipped MCP server.** Skills depend on `state_list_active`, `state_get_status`, session ids, and cancel-signal semantics (`skills/cancel/SKILL.md:41-47`, `skills/cancel/SKILL.md:104-142`, `skills/plan/SKILL.md:79-81`), but the server exposes only `state_write`, `state_read`, and `state_clear` with `mode` + `body` (`mcp/server.py:470-508`, `mcp/server.py:857-881`). Core orchestration and cleanup paths are therefore non-runnable.
- **The repo has a split-brain storage contract: executable code uses `.omni`, while major skills/agents still use `.omc`.** See the real harness contract in `AGENTS.md:77-90`, `scripts/omni.py:83-104`, and `mcp/server.py:349-359`, versus skill/agent references like `skills/autopilot/SKILL.md:39-72`, `skills/plan/SKILL.md:109-123`, `skills/deep-interview/SKILL.md:261-265`, and `agents/planner.md:11-12`. This breaks plan/spec/state discovery across the pipeline.
- **Team mode is documented as a first-class orchestration surface but none of its native primitives exist in the repo.** The skill requires `TeamCreate`, `TaskCreate`, `TaskUpdate`, `SendMessage`, and `TeamDelete` (`skills/team/SKILL.md:53-76`, `skills/team/SKILL.md:212-345`, `skills/team/SKILL.md:413-431`, `skills/team/SKILL.md:533-588`). There is no implementation in `scripts/`, `commands/`, or `mcp/server.py`.
- **Plan/Ralph Codex escalation paths are impossible because `omc ask codex` does not exist.** The skills call it directly (`skills/plan/SKILL.md:74-75`, `skills/ralph/SKILL.md:98-102`, `skills/ralph/SKILL.md:127`), while `scripts/omni.py` exposes no `ask` subcommand (`scripts/omni.py:165-194`).

### High

- **Schema publication without schema enforcement makes MCP contracts misleading.** `TOOLS` publishes JSON Schemas (`mcp/server.py:738-1016`), but `_handle()` does not validate arguments before dispatch (`mcp/server.py:1053-1061`). Tool behavior is looser than the advertised interface.
- **The only shipped Copilot subagent bridge is much weaker than the docs claim.** `AGENTS.md` says delegation uses `--allow-all` and “collects the output” (`AGENTS.md:72-75`), but `scripts/subagent.py` defaults `allow_all` off and does not capture output (`scripts/subagent.py:32-42`). Any skill counting on captured delegated output is broken.
- **Windows compatibility is overstated because the runtime hardcodes `python3` everywhere.** See `.mcp.json:3-7`, `hooks/hooks.json:5-32`, `scripts/omni.cmd:1-3`, and command docs like `commands/omni-init.md:8`.
- **The planner agent still routes to a non-existent `/oh-my-claudecode:start-work` command.** This appears in `agents/planner.md:31-34`, `agents/planner.md:51-52`, and `agents/planner.md:94-97`, but there is no such command in `commands/`.
- **Hook trigger coverage does not match skill contracts.** `autopilot`, `ralph`, `ultrawork`, and `team` all advertise broader intent phrases than the router matches (`skills/autopilot/SKILL.md:13-16`, `skills/ralph/SKILL.md:16-20`, `skills/ultrawork/SKILL.md:12-16`, `skills/team/SKILL.md:750-760` vs `hooks/user_prompt_submit.py:13-24`).

### Medium

- **`session_search` and trace tools have no first-party writers, so they are effectively empty.** Tables exist (`mcp/server.py:178-193`), readers exist (`mcp/server.py:624-658`, `mcp/server.py:960-982`), but no insert handlers exist for `trace` or `sessions`; the file’s insertions stop at memory/artifacts/state/wiki/notepad/shared_memory/runs (`mcp/server.py:271-274`, `mcp/server.py:346-347`, `mcp/server.py:475-477`, `mcp/server.py:518-521`, `mcp/server.py:561-562`, `mcp/server.py:602-605`, `mcp/server.py:668-669`).
- **`subtask.route` is a stub, not a router.** It always returns `executor` (`mcp/server.py:675-676`) despite being exposed as a routing tool (`mcp/server.py:984-994`).
- **Validation/smoke scripts prove layout, not runtime integrity.** `scripts/validate_plugin.py:28-69` and `scripts/discovery_smoke.py:16-63` never verify referenced command/tool names, namespace coherence, or executable orchestration paths.
- **The session banner is stale on day one of the session.** It says `29 MCP tools, 28+ skills, 17+ agents` (`hooks/session_start.py:8-12`) while the repo contract is 30/37/19 (`AGENTS.md:7-13`, `mcp/server.py:738-1016`).
- **Team documentation references missing cleanup/runtime utilities.** `cleanup-orphans.mjs` is referenced from `skills/team/SKILL.md:577-582` and `skills/cancel/SKILL.md:247-255`, but it is not present in `scripts/`.

### Low

- **Tests dirty the repo by writing mirrored artifacts into `.omni/runs/`.** The current repo contains `.omni/runs/run-2/spec.md:1`, created by the `artifact_write` happy-path test (`tests/test_security.py:138-151`) and the mirror behavior in `mcp/server.py:349-359`.
- **`user_prompt_submit.py` has no precedence model and only emits generic hints.** It gathers all regex matches and joins them into one message (`hooks/user_prompt_submit.py:33-40`), which is weak guidance for overlapping phrases.
- **`pre_tool_use.py` still uses Claude-era naming (`CLAUDE_PLUGIN_ROOT`) and a fail-open model.** The fail-open behavior is intentional (`hooks/pre_tool_use.py:4-6`, `hooks/pre_tool_use.py:65-71`), but it reduces the practical safety value of the policy hook when payload parsing breaks.

Overall assessment: the executable core of Copilot Omni is a small, functional `.omni` + SQLite + `copilot --agent` harness. The Markdown orchestration layer on top of it still describes a much larger Claude-native system. The repo currently passes its own tests because those tests exercise the small executable core and do not validate the much larger behavioral contract claimed by the skills and agents.
