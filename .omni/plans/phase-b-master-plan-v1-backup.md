# Phase B — Master Implementation Plan

*Plan author: Architect/Planner. Plan date: 2026-04-16. Plan type: OMC-style ralplan consensus artifact. Companion to `.omni/research/phase-a/SYNTHESIS.md` (reference by section as `[SYN §X]`). Other sources cited as `[int-pipeline §X]`, `[int-hooks §X]`, `[codex-internal §X]`. Sweep PRs will land on a `phase-b/*` branch family; `main` stays buildable every merge.*

## 0. Goal statement

Bring `copilot-omni` from a split-brain v1.0.0 "Claude-port with a thin Copilot harness" to a v2.0.0 **Copilot-CLI–native, corporate-safe multi-agent orchestration plugin**. Collapse the `.omc` / `.omni` and `oh-my-claudecode` / `omni` identity split, delete every Claude-only primitive (`Task()`, `Skill()`, `TeamCreate`, `SendMessage`, `AskUserQuestion`), rewrite the tier-0 autonomous pipeline (autopilot / ralph / ultrawork / ultraqa / ralplan / team / plan / cancel / deep-interview entry) around `scripts/subagent.py` + MCP state + Copilot-subscription semantic model categories (`quick` / `deep` / `ultrabrain`), replace the advisory regex intent hook with a real front-door router that auto-redirects vague prompts to `deep-interview` with a documented bypass syntax, rebuild `team` as a tmux+worktree+state-machine Copilot-native feature, harden hooks + MCP against every Critical/High finding in the two internal audits, and gate the whole thing behind a machine-checked skill/agent contract validator so Phase-B quality cannot regress silently. External AI CLIs (`codex`, `gemini`) are explicitly not called; everything runs through Copilot.

## 1. Locked decisions (user-confirmed, DO NOT revisit)

1. **Host = GitHub Copilot CLI only.** No Claude Code primitives. Where a skill currently relies on `Task()` / `Skill()` / `AskUserQuestion` / `SendMessage` / `TeamCreate`, the skill is rewritten or deleted. Claude Code coexistence is a non-goal.
2. **Architecture = OMC-style composable autonomous modes** (`autopilot`, `ralph`, `ultrawork`, `ralplan`, `team`, `deep-interview`, `plan`, `cancel`). Useful patterns cherry-picked from **oh-my-openagent (OMOA, MIT per user verification)**. GSD's phase state machine is explicitly rejected.
3. **Front-door intent router** must classify every user prompt, auto-trigger `deep-interview` on vague prompts, and expose a bypass (`!` prefix OR `--skip-interview` flag). P0 item.
4. **Directory + brand rename** is mandatory: `.omc/ → .omni/` and `OMC / oh-my-claudecode / omc-* → omni / copilot-omni / omni-*` everywhere in skills/, agents/, scripts/, hooks/, commands/, docs/, templates/. A mechanical sweep with a verification script that fails CI on any residual hit.
5. **Team orchestration = real Copilot-native rebuild** (tmux + git worktrees + MCP state machine). Not a shim; may be simplified but must work.
6. **Model selection = OMOA-style semantic categories** (`quick`, `deep`, `ultrabrain`) that resolve to concrete Copilot subscription models (Claude Sonnet / Opus, GPT-5.x, Gemini 2.x). User-overridable via `.omni/config.json`.
7. **External CLIs forbidden** — no `codex`, `gemini`, or other AI CLIs invoked. Stdlib-only, Copilot-only. CI enforces.
8. **deep-interview simplification = follow-up**, not in Phase B scope. Phase B only touches deep-interview for (a) `.omc → .omni` rename, (b) dropping `AskUserQuestion` references, (c) plumbing the router redirect contract.

## 2. Workstream inventory

Twelve workstreams. For each: Goal, Rationale (with citations), Entry criteria, Deliverables, Acceptance criteria (measurable), Risks + mitigations, Size (S <1d, M 1-3d, L 3-7d, XL >7d), Dependencies.

### WS1 — Rename + rebrand sweep (`.omc → .omni`, `OMC / oh-my-claudecode / omc-* → omni / copilot-omni / omni-*`)

- **Goal.** Produce a single identity and a single storage root. Eliminate the split-brain entirely before any other workstream starts touching the same files.
- **Rationale.** The Phase-A synthesis names split-brain as the single largest correctness problem `[SYN §0 #1, §2 gap "State persistence model"]`; Codex confirms `.omni` is the executable-side contract, `.omc` is only the skill-side contract `[codex-internal §2 Critical-2]`; Grep shows **189 occurrences of `.omc/` across 34 files** and **292 occurrences of `oh-my-claudecode` across 48 files** in the current repo (counted this session). This is mechanical, sweeping, and MUST come first so later workstreams don't need a moving target.
- **Entry criteria.** Phase A synthesis approved (done). Wave 0 baseline branch + tag created. No open PRs touching renamed files.
- **Deliverables.**
  - `scripts/verify_plugin_contract.py` — a new CI-executable script with a `--check-rename` mode that greps the tree and fails on any hit of the deprecated tokens.
  - Repo-wide sed/rename pass across `skills/`, `agents/`, `scripts/`, `hooks/`, `commands/`, `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin.json`, `.claude-plugin/plugin.json`, `.mcp.json`, tests, templates, policy files, state-file paths in Python.
  - Rename skill directories that still carry the `omc-` prefix (`skills/omc-doctor`, `skills/omc-setup`, `skills/omc-teams`, `skills/omc-reference`) to `omni-doctor` / `omni-setup` / `omni-teams` / `omni-reference`, including a redirect note in a small `docs/RENAMES.md` so external docs referencing the old names can find the new ones.
  - One-shot data-migration helper `scripts/omni_migrate.py` that moves any existing `.omc/` tree in a user project to `.omni/` on first run of `omni doctor`, emitting a warning if it found anything.
  - Update every command doc under `commands/` to drop any stale `/oh-my-claudecode:*` and `.omc/` references.
- **Acceptance criteria (measurable).**
  - `grep -r '\.omc/' skills/ agents/ scripts/ hooks/ commands/ docs/ tests/` returns **0 hits**.
  - `grep -rE 'oh-my-claudecode|\bomc-' skills/ agents/ scripts/ hooks/ commands/ docs/ tests/` returns **0 hits** (with an explicit allowlist only for the `docs/RENAMES.md` redirect note).
  - `scripts/verify_plugin_contract.py --check-rename` exits **0** from a clean tree; flipping any file back to `.omc/` makes it exit non-zero.
  - `python3 scripts/omni.py doctor` reports all paths under `.omni/` and no references to `.omc/`.
  - Session banner in `hooks/session_start.py` says "Copilot Omni v2.0.0" and is read from a single version constant reused by the banner and `scripts/omni.py version`.
- **Risks + mitigations.**
  - *Risk:* ripgrep false-positive on URLs or external references like a quoted upstream README. *Mitigation:* allowlist lives in `scripts/verify_plugin_contract.py` as an explicit `ALLOWLISTED_PATHS` list plus an inline `# omni-rename-allow` marker for lines that must keep the token.
  - *Risk:* user projects on disk carry old `.omc/` state. *Mitigation:* `scripts/omni_migrate.py` is a no-op if `.omni/` already exists; otherwise it moves files and logs a summary to `.omni/audit/migration.log`.
- **Size.** M (big but mechanical; the cost is in review, not invention).
- **Dependencies.** None. WS1 is the foundation.

### WS2 — Claude-Code decontamination

- **Goal.** Remove every Claude-only primitive from skills and agents; where a skill is built entirely on such primitives with no Copilot equivalent, delete it.
- **Rationale.** The synthesis and the internal audit both conclude **nine flagship skills are paper-only on Copilot CLI** because they require `Task()`, `Skill()`, `SendMessage`, `TeamCreate`, `AskUserQuestion`, `state_list_active`, `state_get_status`, `run_in_background` — none of which this harness implements `[SYN §0 #2, §3 "Autonomous pipeline" table]` `[codex-internal §1 all nine skills]`. Every ported skill must either lower itself onto `scripts/subagent.py` + MCP state + existing Copilot primitives, or be cut.
- **Entry criteria.** WS1 complete so that decontamination grep patterns are stable.
- **Deliverables.**
  - **Forbidden-primitive map** in `docs/CONTRACT.md` listing the banned Claude tokens (`Task(`, `Skill("`, `AskUserQuestion`, `TeamCreate`, `SendMessage`, `TaskCreate`, `TaskUpdate`, `TeamDelete`, `state_list_active`, `state_get_status`, `run_in_background: true`, `lsp_diagnostics`, `ast_grep_search`, `WebSearch`, `WebFetch`) and the Copilot-native replacement pattern for each.
  - Rewrite of every tier-0 skill body so it uses only: `scripts/subagent.py` (wrapped via a single markdown recipe), `/omni-*` commands, MCP tool calls via the usual stdio interface, the router `/omni-next` + `/omni-do` described in WS3, and plain shell where needed.
  - Deletion-by-audit of skills that remain impossible to port within Phase B. Candidates per the synthesis: verify/trim `skills/deep-dive`, `skills/skillify`, `skills/learner`, `skills/self-improve`, `skills/visual-verdict`, `skills/writer-memory`, and the Claude-only variants of `skills/ccg`, `skills/external-context`, `skills/mcp-setup`, `skills/project-session-manager`. Each decision logged in `docs/ADR-0002-skill-deletions.md` with one-line rationale and a "can be revived by" note.
  - A new skill contract validator step (added to `scripts/verify_plugin_contract.py`) that scans every `skills/**/SKILL.md` and `agents/*.md` for the forbidden-primitive set and fails CI with a per-file report.
- **Acceptance criteria.**
  - `scripts/verify_plugin_contract.py --check-no-claude-primitives` finds **0 occurrences** of any banned token in `skills/` and `agents/`.
  - Every surviving skill frontmatter has a `runtime: copilot` key; the validator asserts this field is present.
  - `docs/ADR-0002-skill-deletions.md` lists every deleted skill with rationale.
  - No skill/agent references `/oh-my-claudecode:*` commands; the validator scans for that regex too.
- **Risks + mitigations.**
  - *Risk:* deleting a skill users depend on. *Mitigation:* Wave-0 baseline tag preserves them; deletions are discoverable in git history; `docs/ADR-0002-skill-deletions.md` names each.
  - *Risk:* a skill body uses a Claude primitive only in prose (e.g., a README-style example). *Mitigation:* the validator accepts an inline marker `<!-- claude-ref: prose-only -->` to scope the check; abuse is visible in review.
- **Size.** L (every tier-0 skill gets edited or deleted; review cost is high).
- **Dependencies.** WS1 (naming must already be stable so we don't edit twice).

### WS3 — Front-door intent router with vague-detection + auto-redirect to deep-interview

- **Goal.** Replace the advisory regex hint in `hooks/user_prompt_submit.py` with a two-stage classifier → resolver that emits a **structured decision**, auto-redirects vague "implement" prompts to `deep-interview`, honors a bypass syntax, and is covered by a regression table of sample prompts → expected decisions.
- **Rationale.** The synthesis names front-door intent routing as **"the single most important gap"** `[SYN §5]` and the largest leverage point over the three upstreams; the hook today returns all regex matches comma-joined with no precedence or handoff `[int-hooks §5.1 Critical]` `[codex-internal §3]`. All three upstreams already do this better; the design target is GSD's `/omni-do` + `/omni-next` shape with OMOA's IntentGate classifier and OMC's ralplan-style vagueness gate layered on top `[SYN §5 R1–R6]`.
- **Entry criteria.** WS1 complete (so the router emits `copilot-omni: …` not `.omc`/`oh-my-claudecode`).
- **Deliverables.**
  - `hooks/router.py` — a new stdlib module that (a) classifies prompts into `{cancel, deep-interview, ralplan, autopilot, ralph, team, ultrawork, plan, verify, debug, wiki, remember, ship, research, ops, none}`, (b) scores concreteness signals (file paths, symbol casing, issue numbers, error strings, code blocks, numbered steps, explicit acceptance criteria), (c) applies the precedence table `cancel > deep-interview > ralplan > autopilot > ralph > team > ultrawork > plan > verify > debug > wiki > remember > ship`, (d) applies the vagueness gate: if `class == implement` and concreteness score < threshold, redirect to `deep-interview`, (e) emits a structured decision: `{"omni.router.decision": {"skill": "...", "confidence": float, "runner_up": "... | null", "redirect": "deep-interview | null", "reasoning": "short"}}`.
  - Rewrite of `hooks/user_prompt_submit.py` to consume `router.py`.
  - **Bypass syntax.** A leading `!` in the user prompt OR a `--skip-interview` flag (for skill/command callers) sets `router.decision.redirect=null` unconditionally and logs `bypass=true` to the audit log. The prefix is stripped from the prompt before downstream handling.
  - `commands/omni-do.md` + `commands/omni-next.md` — two new commands modeled on GSD's router shape. `omni-do` takes freeform input and runs the router deterministically (bypassing the hook layer), so tests can call it with a prompt and assert on the structured decision. `omni-next` reads MCP state + on-disk artifacts to pick the next action (resume autopilot Phase 2, advance team stage, etc.).
  - Trigger-table generator: `scripts/sync_triggers.py` that regenerates `hooks/router.py`'s keyword table from each surviving `skills/*/SKILL.md` frontmatter's declared triggers, and fails if the hook file is stale vs. frontmatter.
  - Regression harness: `tests/test_router.py` with a table of ≥40 sample prompts → expected `skill`, expected `redirect`, expected `bypass`. Covers every trigger in the synthesis' upstream-comparison table `[SYN §1]` and every example flagged in `[int-hooks §Bugs 4, 6]`.
- **Acceptance criteria.**
  - `tests/test_router.py` passes 100%.
  - Prompt "autopilot plan and verify" → decision `autopilot`, runner_up `plan` (or `verify`), redirect `null` (concrete enough OR bypass enabled in test).
  - Prompt "build me something cool" → decision `deep-interview`, redirect `deep-interview`, confidence ≥ threshold for vagueness.
  - Prompt "!build me something cool" → decision `autopilot`, redirect `null`, bypass logged.
  - Prompt "ralph fix the TypeError in api/user.py line 42" → decision `ralph`, redirect `null`, confidence high.
  - `scripts/sync_triggers.py --check` returns 0 from clean tree; flipping a SKILL.md trigger without updating the hook table fails CI.
  - Hook emits the `omni.router.decision` payload (verified in `tests/test_hooks.py`); downstream skills read it.
- **Risks + mitigations.**
  - *Risk:* threshold for "concreteness" is arbitrary. *Mitigation:* thresholds live in `.omni/config.json` under `router.vagueness_threshold` (default 0.4); tune during Wave 5; document in `docs/ROUTER.md` with the scoring rubric.
  - *Risk:* the LLM ignores the structured decision. *Mitigation:* downstream skills and `/omni-do` consult `state_read(mode="router")` (a new well-defined state slot, no new MCP tool needed) in their opening step and branch on it; this is testable end-to-end via `tests/test_router_handoff.py`.
  - *Risk:* bypass syntax collides with bash history expansion. *Mitigation:* document and provide `--skip-interview` as the shell-safe alternative.
- **Size.** L.
- **Dependencies.** WS1 (storage names). Feeds WS5, WS6, WS7.

### WS4 — Model-category resolver (`quick` / `deep` / `ultrabrain`) + Copilot subscription menu

- **Goal.** Stop hardcoding `haiku` / `sonnet` / `opus` in skills and agents. Introduce OMOA-style semantic categories and a resolver that maps each to a concrete Copilot-subscription model, with per-project overrides.
- **Rationale.** The synthesis recommends category-based delegation as a P2 "upstream parity feature worth stealing" `[SYN §10 P2 #7]`. The existing harness forwards raw model strings from agent frontmatter (`claude-sonnet-4-6`, etc.) verbatim to `copilot --model` `[codex-internal §1 Ultrawork]` — that's fragile across subscription menu changes and makes per-user override painful. Semantic categories decouple the layer.
- **Entry criteria.** WS1 complete.
- **Deliverables.**
  - `scripts/omni_models.py` — a tiny resolver module: `resolve(category, override_config) -> concrete_model_name`.
  - Default category → model mapping in `.omni/config.json` (created by `omni init`). Example defaults (subject to subscription-menu reality at install time — documented in `docs/MODELS.md`):
    - `quick` → Claude Haiku / GPT-5-mini / Gemini 2 Flash
    - `deep` → Claude Sonnet / GPT-5
    - `ultrabrain` → Claude Opus / GPT-5.1-thinking / Gemini 2 Pro-thinking
  - Update `scripts/subagent.py` to accept `--category quick|deep|ultrabrain` and resolve locally; keep raw `--model` as an escape hatch.
  - New `/omni-models` command doc explaining category semantics and how to override.
  - Edit every surviving skill and agent to reference categories, not concrete model names.
  - `tests/test_models.py` — unit tests for the resolver; include an override-config test.
- **Acceptance criteria.**
  - `grep -rE '\b(haiku|sonnet|opus)\b' skills/ agents/` returns **0 hits** outside the one reference doc `docs/MODELS.md`.
  - `scripts/subagent.py executor "hello" --category quick` successfully resolves and invokes Copilot (smoke test mocks the Copilot CLI subprocess).
  - `.omni/config.json` is the single source of truth for the mapping; tests prove overrides take precedence over defaults.
- **Risks + mitigations.**
  - *Risk:* Copilot subscription menu changes names. *Mitigation:* mapping is data, not code; `docs/MODELS.md` documents the update procedure; `omni doctor` warns when the configured model is not on Copilot's current menu (best-effort check by running `copilot models` if available, else no-op).
  - *Risk:* someone hard-codes a model name in a new skill. *Mitigation:* validator step (`scripts/verify_plugin_contract.py --check-no-raw-model-names`) fails CI on the banned regex.
- **Size.** M.
- **Dependencies.** WS1. Feeds WS5, WS6.

### WS5 — Autonomous pipeline rewrite (`autopilot` / `ralph` / `ultrawork` / `ultraqa` / `ralplan`) for Copilot primitives

- **Goal.** Make every tier-0 autonomous skill actually run on Copilot CLI, end to end, with MCP state + `scripts/subagent.py` + the new router + category resolver.
- **Rationale.** Nine tier-0 skills are paper-only today `[SYN §3]`; the plugin's reason for being is that these work. This is the single biggest functional deliverable of Phase B.
- **Entry criteria.** WS1, WS2, WS3, WS4 complete.
- **Deliverables.**
  - **`autopilot`** rewritten: 5-phase pipeline implemented as numbered bash/python recipes in `SKILL.md`, invoking `scripts/subagent.py <agent> --category <cat>`, writing state via `state_write(mode="autopilot", body={...})` (which now does accept `session_id` — see WS8), reading MCP state on resume. Drops every `Task()` / `Skill()` reference.
  - **`ralph`** rewritten: same treatment. PRD lives in `.omni/runs/<run-id>/prd.json`. Progress in `.omni/runs/<run-id>/progress.txt`. Reviewer lane uses `agents/critic.md` (and a new `security-reviewer-lite.md` if missing) via `scripts/subagent.py`, not via external CLIs. Deslop step invokes `skills/ai-slop-cleaner` inline via a documented shell invocation (the skill is a markdown runbook, not an external tool).
  - **`ultrawork`** rewritten: parallel work fans out via background `scripts/subagent.py &` spawns and a `wait` barrier. `scripts/subagent.py` gains a `--background` flag that writes a run directory under `.omni/runs/<run-id>/ultrawork/<job-id>/` with `status.json`, `stdout.log`, `stderr.log`. A synchronous helper `scripts/wait_for_jobs.py` polls the status files.
  - **`ultraqa`** rewritten: 5-cycle loop, using `scripts/subagent.py` for architect/executor round-trips, writing state under `mode="ultraqa"`.
  - **`ralplan`** rewritten: consensus loop (Planner → Architect → Critic), using `scripts/subagent.py`. No `AskUserQuestion` — "interactive" mode falls through to the router's bypass/confirm pattern (the skill asks the user a question in chat; the model emits it as plain text, the user answers, the skill continues). Writes to `.omni/plans/ralplan-*.md`.
  - Skill-body linter in `scripts/verify_plugin_contract.py` that asserts every tier-0 skill has a "Resume semantics" section and a "Cleanup" section.
- **Acceptance criteria.**
  - End-to-end smoke test `tests/test_pipeline_e2e.py`:
    1. `autopilot build a hello-world CLI in /tmp/scratch` completes without `Task()` / `Skill()` references (asserted by log scan).
    2. `ralph "fix the failing test in tests/test_sample.py"` completes one full iteration.
    3. `ultrawork "three independent lint fixes: a.py b.py c.py"` fires three `subagent.py --background` jobs and waits.
    4. `ultraqa --tests` cycles and either converges or stops at 5 cycles.
    5. `ralplan "refactor the auth module"` produces a `.omni/plans/ralplan-*.md` with the RALPLAN-DR structure.
  - `scripts/verify_plugin_contract.py --check-pipeline` validates every tier-0 skill has Resume and Cleanup sections.
  - `grep -rE 'Task\(|Skill\(|AskUserQuestion|SendMessage|TeamCreate' skills/` returns **0 hits**.
- **Risks + mitigations.**
  - *Risk:* Copilot CLI's `-p` mode timing out for long runs. *Mitigation:* the existing 1800s timeout in `subagent.py`; background mode bypasses single-request timeouts; resume is exercised in tests.
  - *Risk:* SQLite lock contention under parallel writes from multiple `subagent.py` jobs. *Mitigation:* WS8 adds a simple connection pool and file-scope write queue; e2e test includes 5-way concurrent state_write stress.
  - *Risk:* the e2e test is flaky because it drives a real `copilot` CLI. *Mitigation:* gate `tests/test_pipeline_e2e.py` behind `pytest -m e2e`, with a mock-copilot stub for CI; a periodic (not per-PR) real-Copilot job runs nightly.
- **Size.** XL.
- **Dependencies.** WS1, WS2, WS3, WS4. Feeds WS6 (team composes over ralph).

### WS6 — Team orchestration (Copilot-native rebuild)

- **Goal.** Rebuild `skills/team` as a real Copilot-native feature: tmux panes + git worktrees + MCP state machine + explicit handoff docs, with composable pipelines (`team-plan → team-prd → team-exec → team-verify → team-fix`). No Claude `TeamCreate`/`SendMessage` primitives.
- **Rationale.** User decision 5 (locked). The synthesis flags current `team` as the worst Claude-coupled skill and lists the Claude primitives it expects `[codex-internal §1 Team]`. Rebuilding it simpler, with the three ingredients OMC's `omc-teams` skill and GSD's worktree model both lean on (worktrees + a panel manager + a state file), is the locked plan.
- **Entry criteria.** WS1, WS2, WS3, WS4 complete. WS5 partially done (ralph must exist so team-exec can delegate to it).
- **Deliverables.**
  - `scripts/omni_team.py` — a stdlib Python orchestrator that:
    - creates a team directory `.omni/teams/<team-slug>/`
    - creates one git worktree per worker under `.omni/teams/<slug>/workers/<worker-id>/`
    - starts a tmux session with one pane per worker, each running `copilot -p <task> --agent <agent> --category <cat>`
    - maintains a state machine `{plan, prd, exec, verify, fix, done, failed}` in MCP under `mode="team"` with a new `session_id` slot (WS8)
    - writes per-stage handoff docs to `.omni/teams/<slug>/handoffs/<stage>.md`
    - implements a `team cancel` op that sends `tmux kill-session`, closes worktrees, `state_clear`
  - Rewrite `skills/team/SKILL.md` as a runbook on top of `scripts/omni_team.py` — all Claude primitives gone.
  - Delete the Claude-native "Mode 1" vs "Legacy CLI Mode 2" dual-mode explanation; there is one mode.
  - New command `commands/omni-team.md` for quick invocation.
  - `tests/test_team.py` — unit tests for the state machine transitions and handoff doc generation (the real tmux/worktree part is covered by a smoke test gated behind `pytest -m team-e2e`).
- **Acceptance criteria.**
  - `omni team plan "3 agents to fix lint in src/**" --agents 3` creates three worktrees, three tmux panes, one handoff doc per stage, and reaches state `done` in the smoke test.
  - `grep -rE 'TeamCreate|TaskCreate|TaskUpdate|SendMessage|TeamDelete' skills/ agents/ scripts/` returns **0 hits**.
  - Cancellation leaves no orphan worktrees (asserted in smoke test by `git worktree list`).
  - Team composes with ralph via `omni team plan "..." --ralph` (ralph wraps the verify/fix loop).
- **Risks + mitigations.**
  - *Risk:* tmux is not installed on user's corporate laptop. *Mitigation:* fall back to plain `subprocess.Popen` + per-worker log file when `shutil.which("tmux")` is None; document the degraded mode; emit `omni doctor` warning.
  - *Risk:* git worktree quota on the project root. *Mitigation:* configurable team root in `.omni/config.json` (default `.omni/teams/`), but always inside the repo for atomic cleanup.
  - *Risk:* Windows tmux story. *Mitigation:* fallback mode above; document "team mode requires WSL on Windows" in `docs/INSTALL.md`.
- **Size.** XL.
- **Dependencies.** WS1, WS2, WS3, WS4, partial WS5.

### WS7 — Hooks & triggers hardening

- **Goal.** Close every Critical and High finding in `[int-hooks-triggers-audit.md]`.
- **Rationale.** The audit lists 3 Critical + 4 High + 6 Medium items, several of which are security-relevant (shlex fallback bypass, policy file trust, audit log race) `[int-hooks §12]`. The top two critical items are the missing kill switches and the unsafe shlex fallback `[int-hooks §8.1, §2.1]`.
- **Entry criteria.** WS1 complete (rename), WS3 complete (router replaces the old hook content).
- **Deliverables.**
  - **Kill switches.** Add the exact snippet `if os.environ.get("OMNI_SKIP_HOOKS") or os.environ.get("DISABLE_OMNI"): sys.stdout.write("{}"); sys.exit(0)` at the top of every hook script. Rename historic variables: `OMC_SKIP_HOOKS` and `DISABLE_OMC` are kept as back-compat aliases with a deprecation warning, so users upgrading from v1 aren't surprised.
  - **shlex fallback fix** in `hooks/pre_tool_use.py`: on `ValueError` from `shlex.split(posix=True)`, **deny** the command with reason "malformed shell command"; do not fall back to `.split()`.
  - **Audit log hardening** in `hooks/post_tool_use.py`: use `fcntl.flock` on POSIX and a best-effort per-pid logfile on Windows (`tool-audit.<pid>.log`); fsync after append; expand the entry schema to `{ts, tool, status, args_digest (sha256 of args dict, capped), session_id, bypass, router_decision}`.
  - **Session-aware banner** in `hooks/session_start.py`: read MCP state via a direct SQLite query (not via the stdio server, to keep hook cheap) to surface active-mode resume hints. Static banner replaced by dynamic content. Counts (skills / agents / tools) are computed at install time and cached in `.omni/cache/banner.json`.
  - **`${CLAUDE_PLUGIN_ROOT}` → `${COPILOT_PLUGIN_ROOT}`** rename across `hooks/hooks.json` and any script that reads the env var. Keep `CLAUDE_PLUGIN_ROOT` as a fallback read (so Claude Code harnesses — if anyone ever runs one — don't crash), but document that Copilot CLI is the primary.
  - **Windows Python shim.** Introduce `scripts/launch_python.py` (tiny bootstrap) and replace every hardcoded `python3` with a `scripts/launch_python.py` reference OR a helper `launch_python()` in `.mcp.json` / `hooks/hooks.json`. The bootstrap tries `python3`, `python`, `py -3` in order.
  - **Unicode normalization** in `hooks/pre_tool_use.py`: `unicodedata.normalize('NFC', …)` before path compare.
  - **Policy-file permission check**: reject world-writable policy files; warn on non-0600.
  - **Hook precedence contract** moves into the router (WS3); the hook itself becomes a thin wrapper.
- **Acceptance criteria.**
  - `tests/test_hooks.py` gets a new class `KillSwitchTests` that sets `OMNI_SKIP_HOOKS=1` and asserts all four hooks become no-ops (empty JSON, exit 0).
  - `tests/test_security.py` regression for `rm'-rf /` now returns `deny` (not `allow`).
  - Parallel stress test writes 100 log lines from 10 processes; all 100 lines parse as valid JSONL.
  - `scripts/launch_python.py doctor` on a Windows VM (CI matrix) passes with Python installed as `py -3` only.
  - `scripts/verify_plugin_contract.py --check-env-vars` finds no bare `CLAUDE_PLUGIN_ROOT` in `hooks/hooks.json`, `.mcp.json`, or command docs (except documented back-compat fallbacks).
  - `python3 -c "import os; os.environ['OMNI_SKIP_HOOKS']='1'; …"` test proves kill switch.
- **Risks + mitigations.**
  - *Risk:* Copilot CLI injects env var named `CLAUDE_PLUGIN_ROOT`, not `COPILOT_PLUGIN_ROOT`. *Mitigation:* runtime reads both, with Copilot's name first; document the harness contract in `docs/HOOK_CONTRACT.md`; doctor warns if neither is set.
  - *Risk:* `fcntl` is POSIX-only. *Mitigation:* `os.name == 'nt'` branch uses per-pid logfile, which is weaker but still correct; audit log is additive across files.
- **Size.** L.
- **Dependencies.** WS1, WS3.

### WS8 — MCP server hardening + dead-code removal

- **Goal.** Close every Critical and High finding in `[codex-internal §5]` and `[int-hooks §11]`. Give skills the API they actually need (state listing, session scoping) and delete tools that are readers without writers.
- **Rationale.** Skills expect `state_list_active`, `state_get_status`, session-scoped writes, and cancel-signal semantics; the server exposes only `state_write`, `state_read`, `state_clear` with `mode` + `body` `[codex-internal §5]`. MCP schemas are published but never enforced `[int-hooks §11.1]`. `session_search` and `trace_*` are readers with no writer `[codex-internal §5]`. `subtask.route` is a stub `[codex-internal §5]`. The MCP file is otherwise sound (parameterized queries, WAL, retry) `[codex-internal §5]`.
- **Entry criteria.** WS1 complete.
- **Deliverables.**
  - **Schema enforcement.** In `mcp/server.py::_handle()`, validate `arguments` against the tool's `inputSchema` using a stdlib-only tiny JSON Schema subset validator (types, required, enum, additionalProperties:false). Return `-32602 invalid params` with a sanitized message.
  - **Expanded state API.**
    - `state_list_active` — returns the list of modes where `body.active == true`, honoring an optional `session_id` filter.
    - `state_get_status` — returns `{mode, active, session_id, updated_at, summary}` for a mode.
    - `state_write` gains an optional `session_id` top-level parameter; stored as a column for scoping.
    - `state_clear` gains an optional `session_id` parameter and a `reason` field stored in an audit table.
  - **Writers for readers.**
    - Implement `trace_write` (takes a `span_id`, `parent_id`, `actor`, `action`, `detail`, `duration_ms`); wire it into `scripts/subagent.py` entry/exit so every agent invocation produces a span automatically.
    - Implement `session_record` (takes a `session_id`, `prompt`, `decision`, `outcome`); call it from `hooks/user_prompt_submit.py` after router decision + from the autopilot/ralph/team skills on entry.
  - **Drop dead tools.** If `subtask.route` cannot be made non-stub within Phase B, remove the tool. Synthesis P2 #10 wants session_search + trace writers — now delivered — so those stay.
  - **Exception leak fix.** `_handle()` now returns a sanitized message (`"internal error"`) for unexpected exceptions; full traceback is logged to `.omni/support/mcp.log`.
  - **Connection pool.** Small pool (e.g., 4 connections) behind a thread-safe context manager. All handlers use the same `_Conn` wrapper.
  - **Policy-profile robustness.** Malformed policy JSON logs a loud warning to stderr (harness captures) and falls back to the default; silent fallback is gone.
  - **Artifact mirror sandbox.** `_tool_artifact_write` gains an `OMNI_ARTIFACT_ROOT` override so tests don't dirty the repo `[codex-internal §2 Low-1]`.
- **Acceptance criteria.**
  - `tests/test_mcp_server.py` grows: schema-validation tests (bad input → `-32602`), state API tests (`state_list_active` round-trip, `state_get_status` for unknown mode returns `{active: false}`), trace writer smoke test, session_record smoke test, connection-pool contention test (5 parallel writers, 0 errors).
  - No `_tool_*` function instantiates a raw `sqlite3.connect()`; all go through `_Conn`.
  - `tests/test_security.py` no longer creates `.omni/runs/run-2/spec.md` in the repo (asserted by CI cleanup step).
  - `grep 'str(exc)' mcp/server.py` returns 0 hits outside the sanitized `_handle()` path.
- **Risks + mitigations.**
  - *Risk:* reinventing JSON Schema validation poorly. *Mitigation:* implement only the strict subset the tools use; one validator function; ~120 LOC; fully unit-tested.
  - *Risk:* migration of the `state` SQLite table. *Mitigation:* schema migration bumps `schema_version` from 1 → 2; `mcp/server.py` runs `ALTER TABLE ADD COLUMN session_id` on startup if missing; existing rows default to `session_id=NULL`.
- **Size.** L.
- **Dependencies.** WS1.

### WS9 — Skill/agent contract audit — machine-checked contract

- **Goal.** Make the skill/agent contract enforceable. Every surviving `skills/*/SKILL.md` and `agents/*.md` must have valid frontmatter, exist on disk, reference only real commands/tools/agents, and pass a contract validator. Paper-only claims can't merge.
- **Rationale.** The synthesis' P1 recommendation #8 is a storage-contract test that fails CI on doc drift `[SYN §10 P1 #8]`. Tests today pass while shipping non-runnable orchestration docs `[SYN §0 #10]` `[codex-internal §6]`.
- **Entry criteria.** WS1 complete (rename target stable). Runs in parallel with WS7/WS8.
- **Deliverables.**
  - `scripts/verify_plugin_contract.py` — single entry point with subcommands:
    - `--check-rename` (WS1)
    - `--check-no-claude-primitives` (WS2)
    - `--check-no-raw-model-names` (WS4)
    - `--check-pipeline` (WS5)
    - `--check-env-vars` (WS7)
    - `--check-references` — new; for every `/omni-*` command reference in a skill, asserts the command file exists; for every `agents/<name>` reference, asserts the agent file exists; for every MCP tool name, asserts the tool is registered in `mcp/server.py::TOOLS`.
    - `--check-frontmatter` — validates each SKILL.md/agent.md frontmatter has `name`, `description`, `runtime: copilot`, and (skills only) `triggers: [...]`.
    - `--all` — runs every check; used by CI.
  - A single **`docs/CONTRACT.md`** document that codifies: frontmatter schema, banned primitives, allowed Copilot primitives, the router decision payload shape, the state API, the model category resolver, and the expected skill sections (Setup / Resume / Cleanup / Acceptance).
  - CI wiring (WS12) invokes `--all`.
  - Delete / archive paper-only skills still identified at this point (final pass after WS2).
- **Acceptance criteria.**
  - `scripts/verify_plugin_contract.py --all` exits 0 on a clean tree.
  - 100% of skills under `skills/` pass `--check-frontmatter` and `--check-references`.
  - Intentionally breaking one skill (e.g., referencing `/omni-nonexistent`) makes `--all` exit non-zero with a precise per-file report.
- **Risks + mitigations.**
  - *Risk:* validator is too strict and blocks legitimate work. *Mitigation:* per-file inline marker `<!-- omni-contract-exempt: <reason> -->` with an allowlist of reason strings; abuse is visible in review.
- **Size.** M.
- **Dependencies.** WS1. Consumed by WS12.

### WS10 — Test strategy (real tests, not stubs)

- **Goal.** Transition from "tests validate the small executable core" to "tests validate the behavioral contract" `[SYN §0 #10]`.
- **Rationale.** The synthesis flags `[SYN §9]` that no test verifies referenced commands exist, hook triggers match SKILL.md, `.omni`/`.omc` coherence, or platform-matrix behavior. P1 recommendation #8 is explicitly a storage-contract test that fails CI on doc drift `[SYN §10 P1 #8]`.
- **Entry criteria.** WS9 framework exists; WS3/WS5/WS6/WS7/WS8 at least in shape.
- **Deliverables.**
  - `tests/test_contract.py` — drives `scripts/verify_plugin_contract.py --all` from pytest so failures surface in the same report.
  - `tests/test_router.py` (owned by WS3) — the 40+ prompt regression harness.
  - `tests/test_pipeline_e2e.py` (owned by WS5) — gated behind `pytest -m e2e` with a mock-copilot driver.
  - `tests/test_team.py` (owned by WS6) — state machine + handoff doc tests.
  - `tests/test_hooks_kill_switch.py` (owned by WS7).
  - `tests/test_mcp_schema.py` (owned by WS8).
  - `tests/test_windows_launcher.py` — runs `scripts/launch_python.py` on a Windows CI job.
  - Coverage: aim for ≥70% line coverage in `mcp/server.py`, `hooks/*.py`, `scripts/*.py`, and the router module.
  - Hermetic-tests rule: `tests/conftest.py` sets `OMNI_HOME=tmp_path` and `OMNI_ARTIFACT_ROOT=tmp_path/runs` for every test so the repo is never dirtied (closes `[codex-internal §2 Low-1]`).
- **Acceptance criteria.**
  - `pytest -q` on Linux, macOS, Windows CI jobs all green.
  - `pytest -m e2e` runs nightly (not per-PR) and green.
  - Coverage threshold enforced in CI.
  - No test leaves files in the working tree after completion; `git status --porcelain` is empty after `pytest`.
- **Risks + mitigations.**
  - *Risk:* e2e flakiness blocks PRs. *Mitigation:* `-m e2e` separation; PRs only require unit + contract + integration; e2e is nightly.
- **Size.** L.
- **Dependencies.** WS3, WS5, WS6, WS7, WS8, WS9.

### WS11 — Docs + CHANGELOG + README alignment

- **Goal.** Rewrite every user-facing document to match post-Phase-B reality. Delete stale counts, stale command names, stale directories. Add ADRs for every load-bearing decision.
- **Rationale.** Session banner is stale today (29/28/17 vs 30/37/19) `[SYN §6 bug 9]`; README still mentions legacy `.omc/` migration paths; `docs/MIGRATION.md` addresses "v0.1.0 Go runtime" but not the real migration ahead of users (v1.0.0 `.omc` → v2.0.0 `.omni` + renamed commands). Docs drift is a known upstream anti-pattern the synthesis warns against `[SYN §1.4]`.
- **Entry criteria.** WS1 complete (rename stable). WS3/WS5/WS6 complete (commands stable). Runs in parallel with WS10.
- **Deliverables.**
  - `README.md` rewrite: new version badge v2.0.0, correct counts (regenerated from `scripts/verify_plugin_contract.py --counts`), new install paths, new quickstart that uses `/omni-do` and `/omni-next`.
  - `AGENTS.md` + `CLAUDE.md` merged; `CLAUDE.md` becomes a one-line redirect to `AGENTS.md` (or is deleted outright, user preference — default: delete).
  - `docs/ARCHITECTURE.md` update with the new router, category resolver, team orchestrator, and MCP state API.
  - `docs/MIGRATION.md`: new top section "Upgrading from v1.0.0 to v2.0.0" with the `.omc → .omni` migration, the bypass syntax change, the kill-switch rename.
  - `docs/CONTRACT.md` (owned by WS9).
  - `docs/MODELS.md` (owned by WS4).
  - `docs/ROUTER.md` (owned by WS3) with the precedence table + vagueness rubric.
  - `docs/HOOK_CONTRACT.md` (owned by WS7) with env var contract.
  - New `docs/ADR/` directory: ADR-0001 (host = Copilot CLI only), ADR-0002 (skill deletions), ADR-0003 (semantic model categories), ADR-0004 (team = tmux+worktrees+state machine), ADR-0005 (router = structured decision with vagueness gate).
  - `CHANGELOG.md` v2.0.0 section with breaking changes called out.
- **Acceptance criteria.**
  - All doc counts match reality; `scripts/verify_plugin_contract.py --check-doc-counts` (new sub-check) passes.
  - No doc references `.omc/` or `oh-my-claudecode:` (except the redirect note in `docs/RENAMES.md`).
  - Every ADR has: Context, Decision, Alternatives considered, Consequences.
- **Risks + mitigations.**
  - *Risk:* doc rewrite gets behind code. *Mitigation:* docs land with the PR that owns each change; Wave 5 sweep catches residue.
- **Size.** M.
- **Dependencies.** WS1, WS3, WS4, WS5, WS6, WS7, WS8, WS9.

### WS12 — CI / release (green gate + v2.0.0 tag)

- **Goal.** Wire every check from WS1–WS10 into a CI gate, tag v2.0.0, publish release notes.
- **Rationale.** Without a mandatory CI gate, Phase-B outcomes erode. Every upstream that shipped this kind of revamp kept CI green at every step `[SYN §1.1 on OMC CI]`.
- **Entry criteria.** WS1–WS11 complete.
- **Deliverables.**
  - `.github/workflows/ci.yml` matrix across Linux/macOS/Windows, Python 3.9/3.10/3.11/3.12, running:
    1. `scripts/check_stdlib_only.py`
    2. `scripts/discovery_smoke.py`
    3. `scripts/validate_plugin.py`
    4. `scripts/verify_plugin_contract.py --all`
    5. `pytest -q`
    6. (nightly only) `pytest -m e2e`
  - `RELEASE.md` checklist (smoke on a clean machine; docs counts verify; banner verify; tag).
  - Pre-commit hook doc (optional, user-run) that runs the validator.
  - `CHANGELOG.md` pointer in the release.
- **Acceptance criteria.**
  - CI green on `main` at tag time.
  - `git tag v2.0.0` succeeds; release notes published.
  - `copilot plugin install Jurel89/copilot-omni` works on a clean RHEL/macOS/Windows laptop (smoke runbook in RELEASE.md).
- **Risks + mitigations.**
  - *Risk:* Windows flake. *Mitigation:* matrix runs; tolerate `pytest -m e2e` being Linux-only.
- **Size.** M.
- **Dependencies.** Everything else.

## 3. Dependency graph (ASCII DAG)

```
          WS1 (rename)
            │
   ┌────────┼──────────┬──────────┬──────────┐
   ▼        ▼          ▼          ▼          ▼
  WS2      WS3        WS4        WS8        WS9
 (decon)  (router)  (models)   (MCP)     (validator)
   │        │          │          │
   └───┬────┼──────────┘          │
       ▼    ▼                     │
         WS5 (pipeline)           │
              │                   │
              ▼                   │
            WS6 (team) ───────────┘
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
  WS7       WS10        WS11
 (hooks)  (tests)     (docs)
              │
              ▼
             WS12 (CI/release)
```

Critical path: WS1 → WS2/WS3/WS4/WS8/WS9 in parallel → WS5 → WS6 → WS7/WS10/WS11 → WS12.

## 4. Execution waves

### Wave 0 — Baseline snapshot (S, half a day)

- **Entry.** Phase-A synthesis approved; user's 8 locked decisions in this plan.
- **Parallelism plan.** None; single actor.
- **Work.**
  - Create long-lived branch `phase-b/main` off `main`; every wave branches off and merges back here.
  - Tag `v1.0.0-pre-phase-b` on `main` so we can diff.
  - Snapshot `.omni/research/` and add a `.omni/plans/phase-b-master-plan.md` (this file).
  - Write `docs/ADR/ADR-0000-phase-b-charter.md` capturing the 8 locked decisions verbatim.
  - Scaffold `scripts/verify_plugin_contract.py` skeleton with `--check-rename` stub so later waves can append checks.
- **Exit.** Tag + branch exist; charter ADR committed; validator skeleton merges to `phase-b/main`.

### Wave 1 — Foundation (M, 3–5 days)

- **Entry.** Wave 0 exit criteria met.
- **Parallelism plan.** WS1, WS2, WS9 in parallel. WS9 needs WS1's rename targets to scan against, but its skeleton is independent; coordinate via a shared `docs/CONTRACT.md` draft.
- **Work.** WS1 rename + rebrand. WS2 Claude decontamination. WS9 validator skeleton.
- **Exit.** `scripts/verify_plugin_contract.py --check-rename --check-no-claude-primitives` green. `grep` counts at target (0). Wave merge to `phase-b/main`. `main` remains at `v1.0.0` (no user-facing behavior change yet).

### Wave 2 — Core rewrites (L, 7–10 days)

- **Entry.** Wave 1 merged.
- **Parallelism plan.** WS3 (router), WS4 (models), WS8 (MCP) in parallel — they touch disjoint files. WS5 (pipeline) starts when WS3+WS4+WS8 are ~80% done.
- **Work.** WS3 router + `/omni-do` + `/omni-next`. WS4 category resolver. WS8 MCP hardening + state API expansion + trace/session writers. Then WS5 pipeline rewrite.
- **Exit.** Router emits structured decisions; vague prompts redirect to `deep-interview`; bypass works. Category resolver passes unit tests. MCP schema validation active. Autopilot/ralph/ultrawork/ultraqa/ralplan all pass their e2e smoke under `pytest -m e2e`. Merge to `phase-b/main`.

### Wave 3 — Team rebuild (L, 5–7 days)

- **Entry.** Wave 2 merged; ralph works.
- **Parallelism plan.** Single workstream (WS6).
- **Work.** WS6 tmux + worktrees + state machine + handoff docs.
- **Exit.** `omni team plan "..."` smoke green. Zero Claude `Team*`/`Send*` primitives anywhere. Merge to `phase-b/main`.

### Wave 4 — Hardening (M, 3–5 days)

- **Entry.** Wave 3 merged.
- **Parallelism plan.** WS7 (hooks) and remaining WS8 finalization (connection pool, exception sanitization) in parallel.
- **Work.** WS7 kill switches, shlex fix, audit log, banner. WS8 polish.
- **Exit.** `tests/test_hooks_kill_switch.py`, `tests/test_security.py`, `tests/test_mcp_schema.py` green. `OMNI_SKIP_HOOKS=1` proven to no-op hooks. Merge to `phase-b/main`.

### Wave 5 — Tests + docs + release (M, 3–5 days)

- **Entry.** Wave 4 merged.
- **Parallelism plan.** WS10 (tests), WS11 (docs) in parallel. WS12 (CI/release) last.
- **Work.** WS10 full test suite. WS11 docs + ADRs + CHANGELOG. WS12 CI matrix + release.
- **Exit.** `scripts/verify_plugin_contract.py --all` + `pytest -q` green on all three OSes. Tag `v2.0.0`. Publish release notes.

## 5. Atomic PR / commit strategy

- **Branch topology.** Long-lived `phase-b/main` off `main`. Each wave branches off as `phase-b/wave-N-<slug>`; each workstream inside a wave is one PR `phase-b/wave-N/WS<M>-<slug>`. Example: `phase-b/wave-1/WS1-rename-sweep`.
- **PR granularity.** **One PR per workstream**, merged into the wave branch. At wave exit, the wave branch merges into `phase-b/main`. This strikes the balance between WS-scoped reviewability and wave-scoped integration.
- **Commit convention.** Conventional Commits:
  - `refactor(rename): sweep .omc/ → .omni/ (WS1)`
  - `feat(router): intent classifier + vagueness gate (WS3)`
  - `fix(hooks): implement OMNI_SKIP_HOOKS kill switch (WS7)`
  - Scope is always the workstream number so the archaeology story is trivial.
- **Keeping CI green at every step.** Every PR must:
  1. Pass `scripts/verify_plugin_contract.py --all` (grows with each WS).
  2. Pass `pytest -q` on the Linux CI job.
  3. Not break `main`; WS2 deletions must be pre-declared in `docs/ADR-0002-skill-deletions.md` to avoid surprise.
  4. Touch `CHANGELOG.md` with a one-line entry.
- **Merges to `main`.** `main` remains at `v1.0.0` until Wave 5 exits. Final merge `phase-b/main → main` produces `v2.0.0`. No intermediate tags on `main` during Phase B.

## 6. Verification strategy

### Machine-checked

- `scripts/verify_plugin_contract.py --all` as described in WS9.
- `pytest -q` covering unit + integration.
- `pytest -m e2e` nightly on Linux (mock Copilot) and weekly against real Copilot CLI.
- `scripts/check_stdlib_only.py` still enforces zero pip deps.
- Coverage threshold ≥70% on `mcp/`, `hooks/`, `scripts/`, `hooks/router.py`.
- `git status --porcelain` empty after full test run (hermeticity).

### Human-checked (per workstream UAT)

- **WS1.** `grep -r '\.omc/' .` manually on a clean checkout; session banner read in Copilot CLI shows v2.0.0.
- **WS2.** Open three tier-0 SKILL.md files at random; confirm zero Claude primitives in prose.
- **WS3.** Type 5 ad-hoc prompts (from the 40-prompt table) in Copilot CLI; confirm hook output matches expectation.
- **WS4.** Run `omni list models`; confirm categories + resolved models match the subscription menu.
- **WS5.** Run `copilot -p "autopilot build a hello-world CLI in /tmp/hello"`; confirm a spec, a plan, code, and tests are produced.
- **WS6.** Run `omni team plan "3 agents to fix TODOs in docs/"`; open tmux, watch panes, check handoff docs appear.
- **WS7.** `OMNI_SKIP_HOOKS=1 copilot -p "list files"`; no audit log entries created.
- **WS8.** `copilot mcp state_list_active`; returns active modes. Attempt bad input on `state_write`; returns `-32602`.
- **WS9.** Intentionally break one skill; confirm CI fails with the right file:line.
- **WS10.** Full `pytest -q` read-through of the report.
- **WS11.** Open README, AGENTS.md, docs/ARCHITECTURE.md; confirm counts, command names, directory names match reality.
- **WS12.** `copilot plugin install Jurel89/copilot-omni@v2.0.0` on a clean RHEL laptop.

### Adversarial — one cycle per wave

At each wave exit, run three review agents in parallel via `scripts/subagent.py`:

- **`critic`**: is the wave's plan acceptance criteria actually met? Any paper-only claims?
- **`architect`**: are the decisions consistent with Phase-A decisions 1–7?
- **`code-reviewer`**: PR-level review of the wave's diff; flag any Claude primitives, stale `.omc/` references, untested paths.

Any blocker from any of the three reverts the wave merge.

## 7. File-level change inventory

(Not exhaustive; table-of-contents for execution agents. Every line here should become a TODO in the Wave N branch.)

### WS1 — Rename (CREATE / MODIFY / DELETE)

- MODIFY: `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin.json`, `.claude-plugin/plugin.json`, `.mcp.json`, `hooks/hooks.json`, `hooks/*.py`, `scripts/omni.py`, `scripts/omni`, `scripts/omni.cmd`, `scripts/subagent.py`, `scripts/validate_plugin.py`, `scripts/discovery_smoke.py`, `mcp/server.py`, `commands/omni-*.md` (×8), `skills/*/SKILL.md` (×37), `agents/*.md` (×19), `docs/*.md`, `tests/*.py`.
- CREATE: `scripts/verify_plugin_contract.py`, `scripts/omni_migrate.py`, `docs/RENAMES.md`, `docs/ADR/ADR-0000-phase-b-charter.md`, `.omni/plans/phase-b-master-plan.md` (this file).
- RENAME (dirs): `skills/omc-doctor → skills/omni-doctor`, `skills/omc-setup → skills/omni-setup`, `skills/omc-teams → skills/omni-teams`, `skills/omc-reference → skills/omni-reference`.

### WS2 — Decontamination

- CREATE: `docs/CONTRACT.md`, `docs/ADR/ADR-0002-skill-deletions.md`.
- MODIFY: every `skills/*/SKILL.md` and `agents/*.md` that referenced Claude primitives.
- DELETE: skills identified in ADR-0002 (final list after Wave-1 triage; candidates: `skills/self-improve`, `skills/visual-verdict`, `skills/writer-memory`, `skills/project-session-manager`, parts of `skills/deep-dive`, `skills/skillify`, `skills/learner` — final list decided during WS2 execution).

### WS3 — Router

- CREATE: `hooks/router.py`, `scripts/sync_triggers.py`, `commands/omni-do.md`, `commands/omni-next.md`, `tests/test_router.py`, `tests/test_router_handoff.py`, `docs/ROUTER.md`, `docs/ADR/ADR-0005-router-design.md`.
- MODIFY: `hooks/user_prompt_submit.py`, `hooks/session_start.py`, every tier-0 SKILL.md (to consume the decision).

### WS4 — Models

- CREATE: `scripts/omni_models.py`, `docs/MODELS.md`, `commands/omni-models.md`, `tests/test_models.py`, `docs/ADR/ADR-0003-model-categories.md`.
- MODIFY: `scripts/subagent.py` (add `--category`), `scripts/omni.py` (add `omni models` subcommand), every skill/agent referencing raw model names, `.omni/config.json` template created by `omni init`.

### WS5 — Pipeline

- MODIFY: `skills/autopilot/SKILL.md`, `skills/ralph/SKILL.md`, `skills/ultrawork/SKILL.md`, `skills/ultraqa/SKILL.md`, `skills/ralplan/SKILL.md`, `skills/plan/SKILL.md`, `scripts/subagent.py` (add `--background`), `scripts/wait_for_jobs.py` (new).
- CREATE: `tests/test_pipeline_e2e.py`, `docs/PIPELINE.md`.

### WS6 — Team

- CREATE: `scripts/omni_team.py`, `commands/omni-team.md`, `tests/test_team.py`, `docs/ADR/ADR-0004-team-architecture.md`, `docs/TEAM.md`.
- MODIFY: `skills/team/SKILL.md` (full rewrite), `scripts/omni.py` (add `omni team` subcommand).

### WS7 — Hooks

- MODIFY: `hooks/hooks.json`, `hooks/session_start.py`, `hooks/pre_tool_use.py`, `hooks/post_tool_use.py`, `hooks/user_prompt_submit.py` (now thin wrapper over router).
- CREATE: `scripts/launch_python.py`, `docs/HOOK_CONTRACT.md`, `tests/test_hooks_kill_switch.py`, `tests/test_windows_launcher.py`.

### WS8 — MCP

- MODIFY: `mcp/server.py` (schema validation, state API, trace/session writers, connection pool, exception sanitization, schema migration).
- CREATE: `tests/test_mcp_schema.py`, expand `tests/test_mcp_server.py`.
- DELETE (if not implementable): `subtask.route` tool registration and its stub handler.

### WS9 — Validator

- MODIFY: `scripts/verify_plugin_contract.py` (add all `--check-*` subcommands).
- CREATE: `docs/CONTRACT.md`.

### WS10 — Tests

- CREATE: `tests/test_contract.py`, `tests/conftest.py` (hermetic fixtures).
- MODIFY: all existing tests to use hermetic fixtures.

### WS11 — Docs

- MODIFY: `README.md`, `AGENTS.md`, `CLAUDE.md` (delete), `docs/ARCHITECTURE.md`, `docs/MIGRATION.md`, `docs/INSTALL.md`, `docs/SKILLS.md`.
- CREATE: all ADRs listed above; `CHANGELOG.md` v2.0.0 section.

### WS12 — CI/release

- MODIFY: `.github/workflows/ci.yml`.
- CREATE: `RELEASE.md`, `docs/ADR/ADR-9999-v2-release-notes.md` (optional).

## 8. Rollback plan

- **Branch-level.** Every wave merges into `phase-b/main`, not `main`. If Wave N breaks, revert the wave-N merge on `phase-b/main` with `git revert -m 1 <sha>`; re-enter the loop at the wave's entry criteria. `main` is untouched.
- **Tag-level.** `v1.0.0-pre-phase-b` is the last known-good `main`. If the final merge `phase-b/main → main` goes wrong, `git reset --hard v1.0.0-pre-phase-b` restores `main`. The user has locked "no destructive operations without explicit request" as part of the wider contract, so this is a manual step, not automatic.
- **State files.** Users upgrading from v1 run `omni migrate` which moves `.omc/ → .omni/`. If the migration is interrupted, `omni migrate --rollback` moves them back. The migration is idempotent.
- **MCP schema.** Schema migration is forward-only in Phase B (v1 → v2). We ship `scripts/mcp_schema_downgrade.py` as an unsupported rescue script that copies rows into a v1-shaped table; documented in `docs/MIGRATION.md` as "only if you hit an unrecoverable v2 issue".
- **Re-entering the loop.** After a wave revert, the plan does not restart from Wave 0. Rerun the wave's entry-criteria check; if met, retry the wave on a fresh branch.

## 9. Success signals (definition of done for Phase B → v2.0.0)

- `scripts/verify_plugin_contract.py --all` exits 0.
- `pytest -q` green on Linux / macOS / Windows.
- `grep -rE '(\.omc/|oh-my-claudecode|Task\(|Skill\(|AskUserQuestion|TeamCreate|SendMessage|state_list_active)' skills/ agents/ scripts/ hooks/ commands/ docs/` returns 0 hits.
- `OMNI_SKIP_HOOKS=1` verified to no-op all four hooks.
- `omni team plan "..."` smoke green; zero orphan worktrees after cancel.
- `autopilot / ralph / ultrawork / ultraqa / ralplan` e2e smoke green (mock Copilot).
- Session banner reports correct counts (37 skills or revised, 19 agents or revised, 30 MCP tools or revised; exact counts regenerated by the validator and baked into the banner).
- Router regression harness (40+ prompts) green; vague prompts redirect to deep-interview; `!` bypass works.
- Docs: README, AGENTS.md, ARCHITECTURE, MIGRATION, MODELS, ROUTER, HOOK_CONTRACT, CONTRACT, TEAM, PIPELINE exist and are accurate.
- ADR-0000 through ADR-0005 committed.
- `git tag v2.0.0` on `main`; CI badge green; CHANGELOG v2.0.0 published.

## 10. Out of scope for Phase B (explicit non-goals)

- Claude Code support. Plugin runs on Copilot CLI only; Claude Code compat is not tested and not advertised.
- Calls to external AI CLIs (`codex`, `gemini`, `ollama`, etc.). Copilot-only.
- GSD-style phase state machine. Not adopted.
- `deep-interview` redesign (simplification, challenge-agent pruning, ambiguity-scoring rework). Deferred to Phase C.
- New wiki / memory ingestion hooks, knowledge-graph features, LSP tools, ast-grep tools. Deferred to Phase C.
- Multi-language (i18n) SKILL.md variants. Deferred.
- Telemetry / PostHog / any outbound network call from the plugin. Permanently out.

## 11. Open items for human decision before Wave 0 starts (max 3)

The 9 Phase-A open questions are already answered by the user's 8 locked decisions. Only 3 forks remain that deserve a fast user call before Wave 0:

1. **Which skills to delete outright in WS2.** User should confirm the deletion candidate list in `docs/ADR-0002-skill-deletions.md` (drafted during Wave 1). Concretely: keep or drop `skills/self-improve`, `skills/visual-verdict`, `skills/writer-memory`, `skills/project-session-manager`, the Claude-only parts of `skills/deep-dive`? Default recommendation: delete all four; revival is a git-history exercise.
2. **Bypass syntax final choice.** Spec says "`!` prefix OR `--skip-interview` flag, recommend `!`". User to confirm: is `!` good enough, or should we also accept `force:` (OMC's historical syntax)? Default: `!` + `--skip-interview` only.
3. **`CLAUDE.md` — keep as one-line redirect or delete?** Plugin targets Copilot CLI only; `CLAUDE.md` is Claude Code's entrypoint. Default recommendation: delete; keep `AGENTS.md` as the canonical entry. User veto required if they want a stub retained.

## 12. Appendix — mapping from SYNTHESIS P0/P1/P2 → workstreams

| SYNTHESIS item | Priority | Covered by |
|---|---|---|
| P0-1 Collapse `.omc/.omni` split-brain `[SYN §10 P0 #1]` | P0 | WS1 |
| P0-2 Implement kill switches `[SYN §10 P0 #2]` | P0 | WS7 |
| P0-3 Decide runtime contract (Copilot-native port) `[SYN §10 P0 #3]` | P0 | WS2, WS5, WS6 |
| P0-4 Real intent gate `[SYN §10 P0 #4]` | P0 | WS3 |
| P0-5 MCP hardening (schema + state API + dead tools) `[SYN §10 P0 #5]` | P0 | WS8 |
| P1-1 Windows compatibility pass `[SYN §10 P1 #1]` | P1 | WS7 (launch_python + env var rename), WS12 (CI matrix) |
| P1-2 Sync hook trigger table with SKILL.md `[SYN §10 P1 #2]` | P1 | WS3 (sync_triggers.py) |
| P1-3 Fix shlex fallback `[SYN §10 P1 #3]` | P1 | WS7 |
| P1-4 Audit log race `[SYN §10 P1 #4]` | P1 | WS7 |
| P1-5 Upgrade `scripts/subagent.py` `[SYN §10 P1 #5]` | P1 | WS4 (category), WS5 (--background + output capture) |
| P1-6 `/omni-cancel` + `/omni-next` `[SYN §10 P1 #6]` | P1 | WS3 (`omni-next`), WS5 (`omni cancel` refresh), WS6 (team cancel) |
| P1-7 Session-aware banner `[SYN §10 P1 #7]` | P1 | WS7 |
| P1-8 Storage-contract test `[SYN §10 P1 #8]` | P1 | WS9, WS10 |
| P1-9 MCP connection pool `[SYN §10 P1 #9]` | P1 | WS8 |
| P1-10 Policy-file safety `[SYN §10 P1 #10]` | P1 | WS7 |
| P2-1 IntentGate classifier (OMOA) `[SYN §10 P2 #1]` | P2 | WS3 |
| P2-2 `/omni-do` + `/omni-next` (GSD) `[SYN §10 P2 #2]` | P2 | WS3 |
| P2-3 Four-gate taxonomy (GSD) `[SYN §10 P2 #3]` | P2 | **Deferred (Phase C)** — not a decision-7 need |
| P2-4 Artifact-first lifecycle (GSD) `[SYN §10 P2 #4]` | P2 | **Deferred (Phase C)** |
| P2-5 Mode composition grammar (OMC) `[SYN §10 P2 #5]` | P2 | WS5 (documented in `docs/PIPELINE.md`) |
| P2-6 Wisdom accumulation notepads (OMOA) `[SYN §10 P2 #6]` | P2 | **Deferred (Phase C)** |
| P2-7 Category-based delegation (OMOA) `[SYN §10 P2 #7]` | P2 | WS4 |
| P2-8 Read-only reviewer enforcement (OMC) `[SYN §10 P2 #8]` | P2 | WS2 (frontmatter `writable: false` for critic/code-reviewer/security-reviewer; validator checks) |
| P2-9 Ambiguity-scored deep-interview (OMC) `[SYN §10 P2 #9]` | P2 | **Deferred (Phase C)** — user decision 8 |
| P2-10 Session-search + trace writers `[SYN §10 P2 #10]` | P2 | WS8 |

### Internal-audit bug → workstream map (top items)

| Bug (from `int-hooks`, `int-pipeline`, `codex-internal`) | Rank | Workstream |
|---|---|---|
| `OMC_SKIP_HOOKS` unimplemented `[int-hooks §8.1]` | Critical | WS7 |
| Shlex fallback bypass `[int-hooks §2.1]` | Critical | WS7 |
| Audit log race `[int-hooks §3.1]` | Critical | WS7 |
| State API mismatch `[codex-internal §2 Critical-1]` | Critical | WS8 |
| Storage split-brain `[codex-internal §2 Critical-2]` | Critical | WS1 |
| Team primitives absent `[codex-internal §2 Critical-3]` | Critical | WS6 |
| `omc ask codex` undefined `[codex-internal §2 Critical-4]` | Critical | WS2 (removes references) |
| MCP schema not enforced `[codex-internal §2 High-1]` | High | WS8 |
| `scripts/subagent.py` weaker than docs `[codex-internal §2 High-2]` | High | WS5 |
| `python3` hardcoded `[codex-internal §2 High-3]` | High | WS7 (launch_python) |
| `${CLAUDE_PLUGIN_ROOT}` expansion assumed `[int-hooks §1.1]` | High | WS7 |
| Planner → non-existent `/oh-my-claudecode:start-work` `[codex-internal §2 High-4]` | High | WS2 |
| Hook triggers miss SKILL.md declared triggers `[codex-internal §2 High-5]` | High | WS3 (sync_triggers) |
| Hook precedence missing `[int-hooks §5.1]` | High | WS3 |
| Policy file trusted without perms check `[int-hooks §10.2]` | High | WS7 |
| Dead MCP tools (`session_search`, trace, `subtask.route`) `[codex-internal §5]` | Medium | WS8 |
| Raw exception leak `[codex-internal §2 Medium-2]` | Medium | WS8 |
| Stale session banner `[codex-internal §2 Medium-4]` | Medium | WS7 + WS11 |
| Tests dirty the repo `[codex-internal §2 Low-1]` | Low | WS8 + WS10 |
| Connection pool absent `[int-hooks §11.2]` | Medium | WS8 |
| Unicode NFC/NFD not handled `[int-hooks §2.3]` | Medium | WS7 |
| Audit log incomplete schema `[int-hooks §3.3]` | Medium | WS7 |
| Command naming mismatch `/oh-my-claudecode:*` vs `/omni-*` `[codex-internal §4]` | Medium | WS1 + WS2 |

Every Critical/High from the two internal audits is owned. Mediums and Lows roll into WS7/WS8/WS10/WS11 at implementation time.

---

*End of Phase B master plan. Next step: user reviews §11 (3 open items), confirms, Wave 0 starts.*
