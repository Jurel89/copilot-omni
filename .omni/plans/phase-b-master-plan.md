# Phase B — Master Implementation Plan (v2)

*Plan author: Architect/Planner. Plan date: 2026-04-16. Plan type: OMC-style ralplan consensus artifact, revised post-critic+architect review. Companion to `.omni/research/phase-a/SYNTHESIS.md` (reference by section as `[SYN §X]`). Other sources cited as `[int-pipeline §X]`, `[int-hooks §X]`, `[codex-internal §X]`, `[critic §X]`, `[arch §X]`. Sweep PRs will land on a `phase-b/*` branch family; `main` stays buildable every merge. v1 is preserved at `.omni/plans/phase-b-master-plan-v1-backup.md`.*

## 0. Goal statement

Bring `copilot-omni` from a split-brain v1.0.0 "Claude-port with a thin Copilot harness" to a v2.0.0 **Copilot-CLI–native, corporate-safe multi-agent orchestration plugin**. Collapse the `.omc` / `.omni` and `oh-my-claudecode` / `omni` identity split, delete every Claude-only primitive (`Task()`, `Skill()`, `TeamCreate`, `SendMessage`, `AskUserQuestion`), rewrite the tier-0 autonomous pipeline (autopilot / ralph / ultrawork / ultraqa / ralplan / team / plan / cancel / deep-interview entry) around `scripts/subagent.py` + MCP state + Copilot-subscription semantic model categories (`quick` / `deep` / `ultrabrain`), replace the advisory regex intent hook with a real front-door router that auto-redirects vague prompts to `deep-interview` with a documented bypass syntax, rebuild `team` as a tmux+worktree+state-machine Copilot-native feature (with a non-tmux fallback promoted to first-class on all platforms; Windows native is explicitly experimental), harden hooks + MCP against every Critical/High finding in the two internal audits, consolidate the state-source ownership across the on-disk stores under one authoritative matrix, and gate the whole thing behind a machine-checked skill/agent contract validator plus a Wave-0 runtime-contract probe so Phase-B quality cannot regress silently. External AI CLIs (`codex`, `gemini`) are explicitly not called; everything runs through Copilot.

## 1. Locked decisions (user-confirmed, DO NOT revisit)

1. **Host = GitHub Copilot CLI only.** No Claude Code primitives. Where a skill currently relies on `Task()` / `Skill()` / `AskUserQuestion` / `SendMessage` / `TeamCreate`, the skill is rewritten or deleted. Claude Code coexistence is a non-goal.
2. **Architecture = OMC-style composable autonomous modes** (`autopilot`, `ralph`, `ultrawork`, `ralplan`, `team`, `deep-interview`, `plan`, `cancel`). Useful patterns cherry-picked from **oh-my-openagent (OMOA, MIT per user verification)**. GSD's phase state machine is explicitly rejected.
3. **Front-door intent router** must classify every user prompt, auto-trigger `deep-interview` on vague prompts, and expose a bypass syntax. P0 item.
4. **Directory + brand rename** is mandatory: `.omc/ → .omni/` and `OMC / oh-my-claudecode / omc-* → omni / copilot-omni / omni-*` everywhere in skills/, agents/, scripts/, hooks/, commands/, docs/, templates/. A mechanical sweep with a verification script that fails CI on any residual hit.
5. **Team orchestration = real Copilot-native rebuild** (tmux + git worktrees + MCP state machine).
6. **Model selection = OMOA-style semantic categories** (`quick`, `deep`, `ultrabrain`) that resolve to concrete Copilot subscription models (Claude Sonnet / Opus, GPT-5.x, Gemini 2.x). User-overridable via `.omni/config.json`.
7. **External CLIs forbidden** — no `codex`, `gemini`, or other AI CLIs invoked. Stdlib-only, Copilot-only. CI enforces.
8. **deep-interview simplification = follow-up**, not in Phase B scope. Phase B only touches deep-interview for (a) `.omc → .omni` rename, (b) dropping `AskUserQuestion` references, (c) plumbing the router redirect contract, (d) adding turn-based persistence so it can resume across Copilot CLI `-p` turns (ADR-0011).

## 1.5 Changes since v1 (auditable revision log)

Every change below is traceable to a specific reviewer demand. The reviewer column names either the critic (grade B, APPROVE WITH CHANGES) or the architect (structural review).

| # | Change | Demanded by |
|---|---|---|
| 1 | WS2 now enumerates ALL 37 on-disk skills with KEEP-REWRITE / DELETE / DEFER tags (new §2.WS2 table + §7 WS2 full listing) | `[critic §1 P1]`, `[critic §7 #2]` |
| 2 | WS5 split into WS5a (subagent primitive + wait_for_jobs), WS5b (autopilot+ralph), WS5c (ultrawork+ultraqa), WS5d (ralplan); Wave 2 budget expands to 10–14 days | `[critic §1 P2]`, `[critic §7 #6]`, `[arch §4 Cycle 2]` |
| 3 | Wave 1 serialized: WS1 solo first, WS2+WS9 in parallel only after WS1 merges | `[critic §1 P3]`, `[critic §3]`, `[arch §3]` |
| 4 | WS3↔WS8 cycle resolved: WS3 ships with a stub state reader that returns "unknown" until WS8's state API slot `mode="router"` lands | `[arch §1 Decision 3]`, `[arch §4 Cycle 1]` |
| 5 | WS8b "State consolidation" sub-stream added; ADR-0007 codifies state-store ownership matrix across SQLite / runs / plans / specs / state / autopilot / sessions / teams | `[arch §5]`, `[arch §7 #3]` |
| 6 | New §2.5 "Runtime contract verification" names the 6 load-bearing Copilot-CLI assumptions (A1–A6) with Wave-0 probes in `scripts/discovery_smoke.py` that block Wave 0 exit on failure | `[arch §2 A1–A6]`, `[arch §7 #1]` |
| 7 | WS6 rescoped behind `--experimental`; non-tmux fallback tested as first-class on Linux/macOS/Windows; Windows native requires `OMNI_EXPERIMENTAL_TEAM=1` | `[critic §1 P8]`, `[critic §7 #8]`, `[arch §6]`, `[arch §7 #8]` |
| 8 | New WS13 "Plugin migration & lifecycle" bundles ADR-0008 (v1→v2 migrator), ADR-0009 (config.json schema versioning), ADR-0010 (subagent back-pressure), ADR-0011 (deep-interview turn-based resume) | `[critic §6 items 1–6]`, `[arch §8 item 6]` |
| 9 | `!` bypass prefix dropped; `--skip-interview` is the only syntax | `[critic §7 #4]` |
| 10 | Config schema entries defined as `{model: str, fallbacks: [str]}` with fallback exercised by `omni doctor` | `[critic §1 P9]`, `[critic §7 #5]` |
| 11 | `OMC_SKIP_HOOKS` / `DISABLE_OMC` aliases removed in v3.0.0; deprecation documented in `docs/HOOK_CONTRACT.md` and CHANGELOG | `[critic §7 #9]` |
| 12 | MCP schema migrations additive-only through Phase B; ALTER runs only at Wave 5 → main | `[critic §1 P6]`, `[critic §7 #10]` |
| 13 | `wave-N-ownership.yaml` file-ownership manifest per wave forbids two WSes editing the same file in the same wave | `[critic §1 P3]`, `[critic §7 #11]` |
| 14 | Wave 0+1 adversarial reviews run manually; Wave 2+ run in parallel via `subagent.py` | `[critic §1 P10]`, `[critic §7 #12]` |
| 15 | Banned-token validator strips markdown code fences first and parses context (prose allowed, code not) | `[critic §1 P7]`, `[critic §7 #14]` |
| 16 | Coverage targets split per-module: `mcp/` ≥80%, `hooks/` ≥70%, `scripts/` ≥60% | `[critic §7 #15]` |
| 17 | Success signals hard-code expected banner counts; no weasel wording | `[critic §7 #19]` |
| 18 | Every WS PR touches `CHANGELOG.md`; breaking WSes touch `docs/MIGRATION.md` too | `[critic §7 #20]` |
| 19 | ADR-0005 codifies router scoring rubric BEFORE the 40-prompt test table is authored | `[critic §1 P5]`, `[critic §7 #3]` |
| 20 | §12 mapping table gains "Reviewer source" column and covers new sub-workstreams WS5a–d, WS8b, WS13 | user instruction |

## 2. Workstream inventory

Fifteen workstreams after the revision: twelve top-level WSes, with WS5 split 4-ways (WS5a/b/c/d), WS8 gaining WS8b, and WS13 added. For each: Goal, Rationale (with citations), Entry criteria, Deliverables, Acceptance criteria (measurable), Risks + mitigations, Size (S <1d, M 1-3d, L 3-7d, XL >7d), Dependencies.

### WS1 — Rename + rebrand sweep (`.omc → .omni`, `OMC / oh-my-claudecode / omc-* → omni / copilot-omni / omni-*`)

- **Goal.** Produce a single identity and a single storage root. Eliminate the split-brain entirely before any other workstream starts touching the same files.
- **Rationale.** The Phase-A synthesis names split-brain as the single largest correctness problem `[SYN §0 #1, §2 gap "State persistence model"]`; Codex confirms `.omni` is the executable-side contract, `.omc` is only the skill-side contract `[codex-internal §2 Critical-2]`; Grep shows **189 occurrences of `.omc/` across 34 files** and **254 `oh-my-claudecode` hits across 31 skill files** in the current repo (counted this session). This is mechanical, sweeping, and MUST come first so later workstreams don't need a moving target.
- **Entry criteria.** Phase A synthesis approved (done). Wave 0 baseline branch + tag created. No open PRs touching renamed files.
- **Deliverables.**
  - `scripts/verify_plugin_contract.py` — a new CI-executable script with a `--check-rename` mode that greps the **whole tree** (not a directory subset) and fails on any hit of the deprecated tokens. Includes an explicit `ALLOWLISTED_PATHS` array for URL references, upstream quotes, and the rename redirect note — per `[critic §7 #1]`.
  - Repo-wide sed/rename pass across `skills/`, `agents/`, `scripts/`, `hooks/`, `commands/`, `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin.json`, `.claude-plugin/plugin.json`, `.mcp.json`, tests, templates, policy files, `CHANGELOG.md`, `.github/workflows/**`, state-file paths in Python.
  - Rename skill directories that still carry the `omc-` prefix (`skills/omc-doctor`, `skills/omc-setup`, `skills/omc-teams`, `skills/omc-reference`) to `omni-doctor` / `omni-setup` / `omni-teams` / `omni-reference`, with a redirect note in `docs/RENAMES.md`.
  - **Command-namespace rename** `/oh-my-claudecode:X → /omni-X` is promoted from WS2 into WS1 so a user-facing concern does not ride on a decontamination side-effect `[arch §1 Decision 4]`.
  - One-shot data-migration helper `scripts/omni_migrate.py` that moves any existing `.omc/` tree in a user project to `.omni/` on first run of `omni doctor`, emitting a warning if it found anything.
  - Update every command doc under `commands/` to drop stale `/oh-my-claudecode:*` and `.omc/` references.
- **Acceptance criteria (measurable).**
  - `scripts/verify_plugin_contract.py --check-rename` greps the **whole tree** with allowlist; exits 0 from a clean tree. Flipping any file back to `.omc/` makes it exit non-zero. Allowlist covers only `docs/RENAMES.md`, `phase-b-master-plan-v1-backup.md`, and documented upstream quotations.
  - `grep -rE '(\.omc/|oh-my-claudecode|\bomc-)' .` returns 0 hits outside the allowlist — covers `.github/`, `plugin.json`, `CHANGELOG.md` `[critic §1 P4]`.
  - `python3 scripts/omni.py doctor` reports all paths under `.omni/` and no references to `.omc/`.
  - Session banner in `hooks/session_start.py` says "Copilot Omni v2.0.0" and is read from a single version constant reused by the banner and `scripts/omni.py version`.
  - Every `/oh-my-claudecode:*` reference in `commands/` has been replaced by `/omni-*`.
- **Risks + mitigations.**
  - *Risk:* ripgrep false-positive on URLs or external references. *Mitigation:* allowlist in `verify_plugin_contract.py` + inline `# omni-rename-allow` marker.
  - *Risk:* user projects on disk carry old `.omc/` state. *Mitigation:* `scripts/omni_migrate.py` is a no-op if `.omni/` exists; otherwise it moves files and logs to `.omni/audit/migration.log`.
- **Size.** M.
- **Dependencies.** None. WS1 is the foundation.

### WS2 — Claude-Code decontamination (honest skill inventory)

- **Goal.** Remove every Claude-only primitive from skills and agents; for each of the 37 on-disk skills, an explicit KEEP-REWRITE / DELETE / DEFER verdict is committed before Wave 1 WS2 starts editing.
- **Rationale.** The critic's P1 flags the v1 plan as silently under-scoped against the on-disk tree `[critic §1 P1]`. Grep this session shows 31 skills with `oh-my-claudecode` brand contamination and 21 skills with Claude-primitive contamination (`Task(` / `Skill(` / `AskUserQuestion` / `TeamCreate` / `SendMessage` / `state_list_active` / `state_get_status` / `run_in_background`). Every ported skill must either lower itself onto `scripts/subagent.py` + MCP state + existing Copilot primitives, or be cut.
- **Entry criteria.** WS1 complete so that decontamination grep patterns are stable.

#### WS2 skill triage table (all 37 on-disk skills, grep counts from this session)

| Skill | Brand hits | Primitive hits | Verdict | Rationale |
|---|---|---|---|---|
| `ai-slop-cleaner` | 4 | 0 | KEEP-REWRITE | Runbook-style, no Claude primitives. Rewrite only removes brand. |
| `ask` | 4 | 0 | KEEP-REWRITE | Advisor router; Copilot-native once brand is stripped. |
| `autopilot` | 6 | 3 | KEEP-REWRITE | Tier-0 pipeline; rewrite owned by WS5b. |
| `cancel` | 7 | 19 | KEEP-REWRITE | Heavy state-API consumer; rewrite after WS8a exposes real `state_list_active`/`state_get_status`. |
| `ccg` | 2 | 0 | DELETE | "Claude-Codex-Gemini" tri-model orchestration explicitly violates decision 7 (no external CLIs). ADR-0002. |
| `configure-notifications` | 10 | 25 | DEFER-TO-PHASE-C | Works on Copilot shape in principle but is heavily Claude-Code-task-based; carve-out avoids scope creep. |
| `debug` | 0 | 0 | KEEP-REWRITE | Already clean. Frontmatter + runtime field only. |
| `deep-dive` | 7 | 11 | KEEP-REWRITE | Refactored around `scripts/subagent.py` trace + deep-interview handoff. |
| `deep-interview` | 5 | 12 | KEEP-REWRITE | See ADR-0011; Phase B only adds turn-based persistence, drops `AskUserQuestion`. |
| `deepinit` | 0 | 1 | KEEP-REWRITE | One stray `run_in_background`; otherwise OK. |
| `external-context` | 6 | 2 | KEEP-REWRITE | Parallel document-specialist fan-out becomes `scripts/subagent.py --background`. |
| `hud` | 12 | 0 | KEEP-REWRITE | Display skill; brand strip only. |
| `learner` | 2 | 0 | DELETE | Paper-only; no Copilot surface. Git history retains. ADR-0002. |
| `mcp-setup` | 2 | 1 | KEEP-REWRITE | Claude-only in parts; keep the Copilot MCP setup bits, drop Claude sections. |
| `omc-doctor` → `omni-doctor` | 9 | 0 | KEEP-REWRITE | Health-check runbook; rename + brand strip. |
| `omc-reference` → `omni-reference` | 2 | 2 | KEEP-REWRITE | Agent catalog; rewrite as `omni-reference` pointing at new contract. |
| `omc-setup` → `omni-setup` | 18 | 2 | KEEP-REWRITE | Install flow; brand-heavy but mechanical. |
| `omc-teams` → `omni-teams` | 5 | 1 | KEEP-REWRITE | Becomes the new Copilot-native team runbook wrapping `scripts/omni_team.py` (WS6). |
| `plan` | 12 | 21 | KEEP-REWRITE | Strategic planning; WS5d caretaker for ralplan integration, WS5b for basic plan mode. |
| `project-session-manager` | 5 | 0 | DELETE | Claude-Code-worktree-specific; superseded by WS6. ADR-0002. |
| `ralph` | 11 | 14 | KEEP-REWRITE | Tier-0; rewrite owned by WS5b. |
| `ralplan` | 5 | 3 | KEEP-REWRITE | Tier-0 consensus; rewrite owned by WS5d. |
| `release` | 1 | 0 | KEEP-REWRITE | Generic release assistant; brand strip only. |
| `remember` | 0 | 0 | KEEP-REWRITE | Already clean. Frontmatter + runtime field only. |
| `sciomc` | 29 | 11 | DELETE | Claude-specific scientist orchestrator, deepest brand contamination. ADR-0002. |
| `self-improve` | 12 | 1 | DELETE | Evolutionary code loop with Claude tournament selection; no Copilot surface. ADR-0002. |
| `setup` | 13 | 0 | KEEP-REWRITE | OMC install routing; becomes `omni-setup` follow-on. |
| `skill` | 15 | 1 | KEEP-REWRITE | Local skill manager; brand strip + frontmatter validator hook. |
| `skillify` | 0 | 0 | KEEP-REWRITE | Already clean. Minor rewrite for frontmatter compliance. |
| `team` | 10 | 49 | KEEP-REWRITE | Full rewrite owned by WS6. Highest primitive load in the tree. |
| `trace` | 1 | 0 | KEEP-REWRITE | Evidence tracer; brand strip + `trace_write` integration (WS8a). |
| `ultraqa` | 9 | 3 | KEEP-REWRITE | Tier-0 QA loop; rewrite owned by WS5c. |
| `ultrawork` | 9 | 15 | KEEP-REWRITE | Tier-0 parallel fan-out; rewrite owned by WS5c. |
| `verify` | 0 | 0 | KEEP-REWRITE | Already clean. Frontmatter + runtime field only. |
| `visual-verdict` | 1 | 0 | DELETE | Screenshot-compare skill with no Copilot-CLI surface (no vision primitive available). ADR-0002. |
| `wiki` | 0 | 0 | KEEP-REWRITE | Markdown knowledge base; already clean. |
| `writer-memory` | 20 | 1 | DELETE | Niche writer tooling, deep brand contamination, no Phase-B ROI. ADR-0002. |

**Delete roster (7 skills):** `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory`. **Defer roster (1 skill):** `configure-notifications`. **Keep-rewrite roster (29 skills).** Full triage committed as `docs/ADR-0002-skill-deletions.md` before Wave 1 WS2 opens a single PR.

- **Deliverables.**
  - `docs/ADR-0002-skill-deletions.md` pre-seeded with the table above. User may veto individual deletions in §11; default is ship as-tagged.
  - **Forbidden-primitive map** in `docs/CONTRACT.md` listing the banned Claude tokens (`Task(`, `Skill("`, `AskUserQuestion`, `TeamCreate`, `SendMessage`, `TaskCreate`, `TaskUpdate`, `TeamDelete`, `state_list_active`, `state_get_status`, `run_in_background: true`, `lsp_diagnostics`, `ast_grep_search`, `WebSearch`, `WebFetch`) and the Copilot-native replacement pattern for each.
  - Rewrite of every KEEP-REWRITE skill body so it uses only: `scripts/subagent.py` (wrapped via a single markdown recipe), `/omni-*` commands, MCP tool calls via the usual stdio interface, the router `/omni-next` + `/omni-do` described in WS3, and plain shell.
  - Deletion of the 7 DELETE-tagged skills (git history preserves).
  - Skill contract validator step (added to `scripts/verify_plugin_contract.py --check-no-claude-primitives`) that scans every `skills/**/SKILL.md` and `agents/*.md` for the forbidden-primitive set. The validator **strips markdown code fences first, then parses context** (`[critic §7 #14]`): prose references allowed (tagged `<!-- claude-ref: prose-only -->`, **capped at ≤5 files** per `[critic §4 WS2]`); executable code references banned.
  - Read-only reviewer enforcement (P2-8): `critic` / `code-reviewer` / `security-reviewer` agent frontmatter gains `writable: false`; validator checks `[critic §7 #17]`.
- **Acceptance criteria.**
  - `scripts/verify_plugin_contract.py --check-no-claude-primitives` finds 0 code-context hits of any banned token in `skills/` and `agents/`.
  - Exemption count (`<!-- claude-ref: prose-only -->` markers) ≤5 files; validator reports count on every run.
  - Every surviving skill frontmatter has `runtime: copilot`; validator asserts.
  - `docs/ADR-0002-skill-deletions.md` lists every deleted skill with rationale.
  - No skill/agent references `/oh-my-claudecode:*` commands.
  - `writable: false` is present on critic/code-reviewer/security-reviewer frontmatter.
- **Risks + mitigations.**
  - *Risk:* deleting a skill users depend on. *Mitigation:* Wave-0 baseline tag preserves them; deletions are discoverable in git history; `docs/ADR-0002-skill-deletions.md` names each with revival instructions.
  - *Risk:* a skill body uses a Claude primitive only in prose. *Mitigation:* inline marker `<!-- claude-ref: prose-only -->` scopes the check; capped at ≤5 files.
- **Size.** L.
- **Dependencies.** WS1.

### WS3 — Front-door intent router with vague-detection + auto-redirect to deep-interview

- **Goal.** Replace the advisory regex hint in `hooks/user_prompt_submit.py` with a two-stage classifier → resolver that emits a **structured decision**, auto-redirects vague "implement" prompts to `deep-interview`, honors a bypass syntax, and is covered by a regression table of sample prompts → expected decisions.
- **Rationale.** The synthesis names front-door intent routing as **"the single most important gap"** `[SYN §5]`; the hook today returns all regex matches comma-joined with no precedence or handoff `[int-hooks §5.1 Critical]` `[codex-internal §3]`. The architect flagged a WS3↔WS8 cycle: WS3 emits into a state slot whose semantics are owned by WS8 `[arch §4 Cycle 1]`.
- **Entry criteria.** WS1 complete (so the router emits `copilot-omni: …` not `.omc`/`oh-my-claudecode`).
- **Cycle resolution (per `[arch §1 Decision 3, §4 Cycle 1]`).** WS3 ships with a **stub state reader** that returns `{"status": "unknown"}` for `state_read(mode="router")` until WS8a lands the real slot. Downstream skills detect `"unknown"` and proceed without router awareness (preserving v1 behavior). Once WS8a ships `mode="router"` with defined TTL and cancel semantics, WS3 swaps the stub for the live reader in a follow-up PR inside Wave 2. Documented in `docs/ROUTER.md` and ADR-0005.
- **Deliverables.**
  - `hooks/router.py` — stdlib module that (a) classifies prompts into `{cancel, deep-interview, ralplan, autopilot, ralph, team, ultrawork, plan, verify, debug, wiki, remember, ship, research, ops, none}`, (b) scores concreteness via the ADR-0005 rubric (see below), (c) applies the precedence table `cancel > deep-interview > ralplan > autopilot > ralph > team > ultrawork > plan > verify > debug > wiki > remember > ship`, (d) applies the vagueness gate: if `class ∈ {implement, build, autopilot, ralph, team}` and concreteness score < `router.vagueness_threshold` (default 0.4), redirect to `deep-interview`, (e) emits `{"omni.router.decision": {"skill": "...", "confidence": float, "runner_up": "... | null", "redirect": "deep-interview | null", "reasoning": "short", "bypass": bool}}`.
  - **ADR-0005 scoring rubric (codified BEFORE the test table is authored)** per `[critic §7 #3]`:

    | Signal | Weight | Notes |
    |---|---|---|
    | File path present (regex match on `\./|[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+\.[a-z]+`) | +0.30 | One shot, capped |
    | Symbol with CamelCase or snake_case identifier | +0.15 | Up to 2 matches |
    | Markdown code fence | +0.25 | One shot |
    | Issue/PR number (`#\d+`) | +0.20 | |
    | Error string token (`Error`, `Traceback`, `Exception`) | +0.15 | |
    | Numbered steps (`^\d+\.` prose) ≥2 | +0.15 | |
    | Explicit acceptance criteria phrase | +0.15 | |
    | Verb + object concreteness (`fix the TypeError`, `add a CLI flag`) | +0.10 | |
    | Vagueness penalty (prompt length <5 words and no above signal) | -0.20 | |

    Score clamped to [0, 1]. Threshold 0.4 documented as tunable in `.omni/config.json`. The test table in `tests/test_router.py` is authored AFTER this rubric is merged.

  - Rewrite of `hooks/user_prompt_submit.py` to consume `router.py`.
  - **Bypass syntax.** Only `--skip-interview` flag (for skill/command callers). The `!` prefix from v1 is dropped per `[critic §7 #4]`. When bypass is seen, `router.decision.redirect=null` unconditionally; `bypass=true` logged to audit.
  - `commands/omni-do.md` + `commands/omni-next.md` — two new commands modeled on GSD's router shape. `omni-do` takes freeform input and runs the router deterministically. `omni-next` reads MCP state + on-disk artifacts to pick the next action.

    **Note on `omni-next` determinism** `[critic §6 #7]`: the command doc is a runbook. Its "determinism" comes from its bash/python recipe: `python3 scripts/omni_next.py` reads MCP state and emits a JSON decision; the LLM quotes the decision back. The LLM does not invent state. Documented in `docs/ROUTER.md`.
  - Trigger-table generator: `scripts/sync_triggers.py` regenerates `hooks/router.py`'s keyword table from each surviving `skills/*/SKILL.md` frontmatter's declared triggers; fails if the hook file is stale vs. frontmatter.
  - Regression harness `tests/test_router.py` with ≥40 sample prompts → expected `skill`, expected `redirect`, expected `bypass`. **≥8 of those must be adversarial/near-threshold** per `[critic §4 WS3]`.
  - **Deep-interview on Copilot CLI `-p` mode** (ADR-0011): turn-based, not blocking. When router redirects to deep-interview, the skill emits questions in its response and returns control. The NEXT user turn must contain answers. Skill state is persisted to `.omni/specs/deep-interview-<slug>.md` and resumed on next turn. Documented in `docs/ROUTER.md`.
- **Acceptance criteria.**
  - `tests/test_router.py` passes 100%, ≥40 cases, ≥8 adversarial.
  - "autopilot plan and verify" → `autopilot`, runner_up `plan`, redirect null.
  - "build me something cool" → `deep-interview`, redirect `deep-interview`.
  - "build me something cool --skip-interview" → `autopilot`, redirect null, bypass logged.
  - "ralph fix the TypeError in api/user.py line 42" → `ralph`, redirect null, confidence ≥0.7.
  - `scripts/sync_triggers.py --check` returns 0 from clean tree; flipping a SKILL.md trigger without updating the hook table fails CI.
  - Hook emits the `omni.router.decision` payload; downstream skills read it OR tolerate `{"status": "unknown"}` while the WS8a slot is not yet live.
  - `router.py` hook round-trip ≤100ms on a 2024 laptop; integrated into `tests/test_hooks_budget.py` (addresses `[critic §2 WS3]` 5s hook timeout concern).
- **Risks + mitigations.**
  - *Risk:* threshold is arbitrary. *Mitigation:* rubric in ADR-0005; thresholds in `.omni/config.json` under `router.vagueness_threshold`; tuned during Wave 5.
  - *Risk:* LLM ignores the decision. *Mitigation:* downstream skills consult `state_read(mode="router")` in their opening step; canonical 3-line router-consumption preamble enforced by `--check-pipeline` lint `[arch §6, §7 #11]`.
  - *Risk:* hook crosses the 5s budget. *Mitigation:* `tests/test_hooks_budget.py` asserts <100ms; classifier is pure regex + numeric scoring, no LLM call.
- **Size.** L.
- **Dependencies.** WS1. Stub-reads from WS8a state API; lives parallel in Wave 2 until WS8a's `mode="router"` slot merges.

### WS4 — Model-category resolver (`quick` / `deep` / `ultrabrain`) + Copilot subscription menu

- **Goal.** Stop hardcoding `haiku` / `sonnet` / `opus` in skills and agents. Introduce OMOA-style semantic categories with explicit fallback chains and a resolver that maps each to a concrete Copilot-subscription model, with per-project overrides.
- **Rationale.** The synthesis recommends category-based delegation as a P2 "upstream parity feature worth stealing" `[SYN §10 P2 #7]`. The critic's P9 flags that the v1 collapse-to-categories lost OMOA's per-category fallback chain `[critic §1 P9]`. The architect flagged WS4 + WS5 co-editing `scripts/subagent.py` in Wave 2 `[arch §1 Decision 6]`.
- **Entry criteria.** WS1 complete.
- **Deliverables.**
  - `scripts/omni_models.py` — resolver: `resolve(category, override_config) -> concrete_model_name`, with fallback: if primary fails auth or availability, try `fallbacks[0]`, then `fallbacks[1]`.
  - **Config schema (ADR-0003, updated per `[critic §7 #5]`):**

    ```json
    {
      "models": {
        "quick":      {"model": "claude-haiku-4",    "fallbacks": ["gpt-5-mini", "gemini-2-flash"]},
        "deep":       {"model": "claude-sonnet-4-6", "fallbacks": ["gpt-5", "gemini-2-pro"]},
        "ultrabrain": {"model": "claude-opus-4-6",   "fallbacks": ["gpt-5-1-thinking", "gemini-2-pro-thinking"]}
      },
      "agents": {
        "critic": {"category": "deep", "model_override": null}
      }
    }
    ```

    Both category-level and per-agent overrides supported.
  - Update `scripts/subagent.py` to accept `--category quick|deep|ultrabrain` and resolve locally; keep raw `--model` as an escape hatch. WS4 PR lands BEFORE WS5a's `--background` edits to `subagent.py` (serialized merge order documented in `wave-2-ownership.yaml`).
  - New `/omni-models` command doc.
  - Edit every surviving skill and agent to reference categories, not concrete model names. **Split acceptance** per `[arch §7 #12]`: "resolver works" in Wave 2; "grep-0 raw model names in skills/agents" enforced by validator at end of Wave 3.
  - `tests/test_models.py` — unit tests for resolver; override-config test; **fallback exercise test** (primary unavailable → resolver picks fallback[0]).
  - `omni doctor` runs a best-effort `copilot models` check and cross-references the config, warning (not failing) when a configured model is not in the menu.
- **Acceptance criteria.**
  - `grep -rE '\b(haiku|sonnet|opus)\b' skills/ agents/` returns 0 hits outside `docs/MODELS.md` — enforced END OF WAVE 3, not end of Wave 2.
  - `scripts/subagent.py executor "hello" --category quick` resolves and invokes Copilot (mock subprocess in CI).
  - `.omni/config.json` is single source of truth; tests prove overrides take precedence; tests prove fallback triggers on primary failure.
  - `omni doctor` warns on config drift vs. `copilot models` output (best-effort).
- **Risks + mitigations.**
  - *Risk:* Copilot menu changes. *Mitigation:* mapping is data; `docs/MODELS.md` documents update procedure; fallback chain absorbs single-model disappearance.
  - *Risk:* hard-coded model in a new skill. *Mitigation:* `--check-no-raw-model-names` fails CI on banned regex; AST-level match, not naive word-regex `[critic §4 WS4]`.
- **Size.** M.
- **Dependencies.** WS1. Serialized-merge with WS5a in Wave 2.

## 2.5 Runtime contract verification (NEW — Wave-0 blocker)

**The six load-bearing Copilot-CLI assumptions** `[arch §2 A1–A6]`. Each gets a Wave-0 probe in `scripts/discovery_smoke.py`; any probe failure blocks Wave 0 exit.

| # | Assumption | Probe | Failure consequence |
|---|---|---|---|
| A1 | `copilot -p --agent <name>` is stable, non-interactive, and supports parallel invocation without auth interference | `discovery_smoke.py --probe parallel-agents` fires 3 `copilot -p` jobs concurrently, asserts all 3 exit 0 within 60s, no auth prompt | WS5c (ultrawork), WS6 (team) degrade to sequential execution |
| A2 | Hook event JSON shape on Copilot CLI matches the fields used by v1 hooks (`event_name`, `tool_name`, `tool_input`, `tool_response`, `prompt`, `cwd`, `session_id`) | `discovery_smoke.py --probe hook-shapes` emits a no-op from each hook, captures stdin, writes `.omni/audit/hook-shapes.jsonl`, diff-checks against expected fields | WS3 (router), WS7 (hook hardening) retarget based on actual shape |
| A3 | Copilot reads `triggers: [...]` in skill frontmatter | `discovery_smoke.py --probe frontmatter-triggers` installs a test skill with a unique trigger word, emits the word in a prompt, checks skill loads | `sync_triggers.py` becomes lint-only; auto-dispatch falls back to router-only |
| A4 | `copilot --agent <name>` supports one-turn dispatch (fresh conversation, no history leak); multi-turn needs explicit session id | `discovery_smoke.py --probe agent-turns` fires twice with the same agent, asserts second call has no memory of the first | WS6 tmux architecture confirmed safe; if multi-turn leaks, ralph reviewer logic changes |
| A5 | `grep -r <token>` over the tree is sufficient to prove rename semantics (no hidden paths, no build artifacts) | `discovery_smoke.py --probe grep-coverage` lists files not covered by the standard grep (`.gitignore` survey) | Allowlist in `verify_plugin_contract.py` expands |
| A6 | Background `subagent.py &` retains Copilot auth tokens across spawns (no per-PID re-auth) | `discovery_smoke.py --probe bg-auth` fires 3 `subagent.py --background`, waits, asserts all authenticated without user interaction | WS5a (background mode) redesigned to serialize auth OR to re-auth via env var |

Wave 0 exit gate = all six probes green on Linux + macOS (Windows optional for A1/A4/A6, mandatory for A2/A3/A5). Probe output persisted to `.omni/audit/runtime-contract.jsonl` for later archaeology.

### WS5 — Autonomous pipeline rewrite (SPLIT into WS5a/b/c/d)

The v1 WS5 was sized XL with no decomposition `[critic §1 P2]`. It is now four workstreams, each sized M, each owning its own PR, its own file set, and its own acceptance criteria. A micro-WS "subagent background protocol" (WS5a) `[arch §7 #4]` lands first so both WS5c (ultrawork) and WS6 (team) consume the same run-directory layout.

#### WS5a — `scripts/subagent.py` primitive upgrade + `wait_for_jobs.py`

- **Goal.** Grow `scripts/subagent.py` (65 LOC today) into the spine: `--category` (from WS4 contract), `--background`, `--session-id`, per-job run-directory layout, JSON status file. Add `scripts/wait_for_jobs.py` poller. Add back-pressure.
- **Rationale.** Every tier-0 skill in WS5b/c/d and every team worker in WS6 depends on this. Has to land first.
- **Entry criteria.** WS1 complete. Wave-0 A6 probe green.
- **Deliverables.**
  - `scripts/subagent.py` gains `--background` writing `.omni/runs/<run-id>/<job-id>/{status.json, stdout.log, stderr.log, spec.json}`. `status.json` schema: `{job_id, run_id, agent, category, state: "pending|running|done|failed", started_at, ended_at, exit_code, error}`.
  - `scripts/subagent.py` gains `--session-id` passed through to MCP state writes.
  - **Back-pressure (ADR-0010, per `[critic §6 #3]`):** semaphore-limited. Default cap = `min(8, os.cpu_count())`. Overridable via `.omni/config.json > runtime.max_parallel_subagents`. When cap reached, new spawns BLOCK (not fail). Per-subagent memory not policed in Phase B — follow-up in Phase C.
  - `scripts/wait_for_jobs.py` — polls a set of status files; returns when all are terminal OR timeout; emits one-line summary per job.
  - `tests/test_subagent_background.py` — 3 parallel background jobs, wait, all succeed.
  - `tests/test_subagent_backpressure.py` — spawn 12 jobs with cap=4, asserts ≤4 concurrent.
- **Acceptance criteria.**
  - 3-way parallel background invocation round-trip <90s in CI.
  - Back-pressure cap enforced; 12 jobs cap 4 shows 3 waves of 4.
  - `wait_for_jobs.py` emits JSONL summary parseable by downstream skills.
- **Size.** M.
- **Dependencies.** WS1. Serialized-merge with WS4 in Wave 2 (both edit `subagent.py`).

#### WS5b — `autopilot` + `ralph` rewrite

- **Goal.** Rewrite the two most-used tier-0 skills on top of WS5a primitives + WS3 router + WS8a state API.
- **Entry criteria.** WS5a merged. WS3 router stub live. WS8a state API live (or stub for `mode="router"`).
- **Deliverables.**
  - `skills/autopilot/SKILL.md` rewritten: 5-phase pipeline as numbered bash/python recipes, invoking `scripts/subagent.py <agent> --category <cat>`, writing state via `state_write(mode="autopilot", session_id=..., body={...})`, reading MCP state on resume. Every `Task()` / `Skill()` reference gone.
  - `skills/ralph/SKILL.md` rewritten: PRD at `.omni/runs/<run-id>/prd.json`, progress at `.omni/runs/<run-id>/progress.txt`, reviewer lane uses `agents/critic.md` (+ new `security-reviewer-lite.md` if missing) via `subagent.py`. Deslop step invokes `skills/ai-slop-cleaner` runbook inline.
  - **Canonical 3-line router-consumption preamble** at the top of each `SKILL.md` body, per `[arch §7 #11]`:

    ```
    # Router preamble
    1. Read MCP state: state_read(mode="router")
    2. If decision.redirect == "deep-interview", defer to deep-interview skill.
    3. Otherwise, proceed with decision.skill == <this-skill-name>.
    ```

  - **Mode composition contract (ADR-0006)** per `[arch §7 #6]`: autopilot Phase 2 calls ralph as SUBPROCESS via `subagent.py ralph --session-id <autopilot-session-id>`; state is NESTED under autopilot (`mode="autopilot.ralph"`); cancel at the outer level cascades to inner subagent via `state_clear(mode="autopilot", session_id=..., reason="cancel")` which sets a signal file the inner ralph loop polls.
- **Acceptance criteria.**
  - `tests/test_pipeline_e2e.py::test_autopilot_hello_cli` completes without `Task()`/`Skill()` references (asserted by log scan, positive evidence: spec file + plan file + code diff all present `[critic §4 WS5]`).
  - `tests/test_pipeline_e2e.py::test_ralph_one_iteration` completes one full iteration.
  - Grep `Task\(|Skill\(|AskUserQuestion|SendMessage|TeamCreate` in `skills/autopilot/` and `skills/ralph/` returns 0.
- **Size.** M.
- **Dependencies.** WS5a, WS3, WS4, WS8a.

#### WS5c — `ultrawork` + `ultraqa` rewrite

- **Goal.** Parallel fan-out and QA cycling on Copilot primitives.
- **Entry criteria.** WS5a merged.
- **Deliverables.**
  - `skills/ultrawork/SKILL.md` rewritten: parallel work fans out via background `scripts/subagent.py &` spawns, capped by WS5a back-pressure, synchronized by `scripts/wait_for_jobs.py`. Run directory = `.omni/runs/<run-id>/ultrawork/<job-id>/`.
  - `skills/ultraqa/SKILL.md` rewritten: 5-cycle loop using `subagent.py` for architect/executor round-trips, state under `mode="ultraqa"`, session_id threaded.
  - Resume + Cleanup sections enforced by `--check-pipeline` linter.
- **Acceptance criteria.**
  - `tests/test_pipeline_e2e.py::test_ultrawork_3_parallel_lint` fires three background jobs and waits.
  - `tests/test_pipeline_e2e.py::test_ultraqa_cycles` converges or stops at 5 cycles.
  - Grep banned primitives in `skills/ultrawork/` and `skills/ultraqa/` returns 0.
- **Size.** M.
- **Dependencies.** WS5a.

#### WS5d — `ralplan` rewrite

- **Goal.** Consensus loop (Planner → Architect → Critic) on Copilot primitives; no `AskUserQuestion`.
- **Entry criteria.** WS5a merged.
- **Deliverables.**
  - `skills/ralplan/SKILL.md` rewritten: consensus loop uses `subagent.py` for the 3 agents. "Interactive" mode falls through to the router's turn-based persistence pattern (see ADR-0011): the skill asks questions in chat; the user answers on the NEXT turn; the skill resumes. Writes to `.omni/plans/ralplan-*.md`.
  - Resume + Cleanup sections; canonical router preamble.
- **Acceptance criteria.**
  - `tests/test_pipeline_e2e.py::test_ralplan_auth_refactor` produces a `.omni/plans/ralplan-*.md` with the RALPLAN-DR structure (Principles / Drivers / Options / ADR).
  - Skill handles a mid-flow "user hasn't answered yet" state gracefully (test mocks two turns).
  - Grep `AskUserQuestion` in `skills/ralplan/` returns 0.
- **Size.** M.
- **Dependencies.** WS5a.

**Shared WS5 acceptance criteria (spans WS5a–d):**
- `scripts/verify_plugin_contract.py --check-pipeline` validates every tier-0 skill has Resume, Cleanup, and Router-preamble sections.
- Wave 2 budget expands to **10–14 days** to reflect WS3 + WS4 + WS5a + WS5b + WS5c + WS5d + WS7a + WS8a + WS8b parallelism (critic P2 fix).
- E2e gated behind `pytest -m e2e` with a mock-copilot stub; a periodic **nightly real-Copilot job** is explicitly wired in `.github/workflows/ci.yml` per `[critic §7 #7]`.

### WS6 — Team orchestration (Copilot-native rebuild, rescoped `--experimental`)

- **Goal.** Rebuild `skills/team` (and the KEEP-REWRITE `omni-teams`) as a real Copilot-native feature: tmux panes + git worktrees + MCP state machine + explicit handoff docs, with composable pipelines (`team-plan → team-prd → team-exec → team-verify → team-fix`). **Non-tmux subprocess fallback is first-class** on Linux/macOS/Windows. **Windows native** is gated behind `OMNI_EXPERIMENTAL_TEAM=1` in v2.0.0.
- **Rationale.** User decision 5 (locked). The critic's P8 flagged v1's tmux fallback as a "half-design" where acceptance criteria only exercised tmux `[critic §1 P8]`. The architect's §6 called out WS6 as "first to break" on Windows `[arch §6]`.
- **Entry criteria.** WS1, WS2, WS3, WS4 complete. WS5a merged so background run-directory layout is locked. WS5b done so ralph can be composed (optional). Wave-0 A1, A4, A6 probes green.
- **Deliverables.**
  - `scripts/omni_team.py` — stdlib Python orchestrator:
    - Creates team dir `.omni/teams/<team-slug>/`.
    - One git worktree per worker under `.omni/teams/<slug>/workers/<worker-id>/`.
    - Worker execution mode = `tmux` (default when `shutil.which("tmux")`) OR `subprocess` (fallback, first-class). The protocol is identical; only the process-host differs.
    - State machine `{plan, prd, exec, verify, fix, done, failed}` in MCP under `mode="team"` with `session_id`.
    - Per-stage handoff docs to `.omni/teams/<slug>/handoffs/<stage>.md`.
    - `team cancel` op: kills tmux session OR subprocess group, `git worktree remove` each worker, `state_clear` with session scope.
    - **Ralph composition protocol** (`[critic §2 WS6]`): `omni team plan "..." --ralph` sets a `ralph_compose: true` flag in the team state; per-worker, the team orchestrator wraps the worker's verify+fix stage in a `subagent.py ralph --session-id <team.worker-id>` call (fresh ralph session per worker).
  - Rewrite `skills/team/SKILL.md` as a runbook on top of `scripts/omni_team.py`. Claude primitives gone.
  - Rewrite `skills/omni-teams/SKILL.md` (was `omc-teams`) as the user-facing entry point pointing at the same script.
  - New command `commands/omni-team.md`.
  - `tests/test_team.py` — **non-tmux subprocess path tested as the FIRST-class smoke test** (`[critic §7 #8]`); tmux path tested second. Both paths create 3 worktrees, reach `done`, cancel cleanly.
  - **Windows experimental gate (ADR-0007):** `OMNI_EXPERIMENTAL_TEAM=1` env var required on Windows; `omni team` without the gate exits 2 with a pointer to `docs/TEAM.md`.
- **Acceptance criteria.**
  - `omni team plan "3 agents to fix lint in src/**" --agents 3` (subprocess mode) creates 3 worktrees, 3 subprocess workers, 1 handoff doc per stage, reaches `done`. On Linux/macOS tmux mode runs the same assertion.
  - `grep -rE 'TeamCreate|TaskCreate|TaskUpdate|SendMessage|TeamDelete' skills/ agents/ scripts/` returns 0.
  - Cancellation leaves no orphan worktrees (assertion: 3 worktrees created first, then cancel, then `git worktree list` shows 0) per `[critic §4 WS6]`.
  - Team composes with ralph via `omni team plan "..." --ralph` (ralph wraps verify/fix).
  - Windows CI job with `OMNI_EXPERIMENTAL_TEAM=1` runs subprocess-mode smoke; without the flag, exits 2.
- **Risks + mitigations.**
  - *Risk:* tmux not installed. *Mitigation:* first-class subprocess fallback tested on every PR.
  - *Risk:* git worktree quota. *Mitigation:* configurable team root.
  - *Risk:* Windows divergence. *Mitigation:* `--experimental` gate; ADR-0007 explains the posture.
  - *Risk:* half-killed tmux sessions with detached `copilot` children `[arch §6]`. *Mitigation:* cleanup uses PID-tracked kill, not session-scoped; PIDs recorded in state machine at worker spawn.
- **Size.** L (rescoped from XL: MVP is tmux + subprocess, no multi-stage sophistication beyond the 5 handoffs).
- **Dependencies.** WS1, WS2, WS3, WS4, WS5a; soft dependency on WS5b (ralph compose).

### WS7 — Hooks & triggers hardening (SPLIT into WS7a schema + WS7b content)

- **Goal.** Close every Critical and High finding in `[int-hooks]`. **Schema-level items (kill switches, env var rename, shlex fix, launch_python) land in EARLY Wave 2 next to WS8a** per `[arch §3, §7 #5]`; content items (banner, audit schema, NFC, policy perms) land in Wave 4.
- **Rationale.** The audit lists 3 Critical + 4 High `[int-hooks §12]`. Splitting schema-level from content-level unblocks WS3 and makes kill switches a Wave-2 deliverable rather than a Wave-4 deferral for a P0 item.
- **Entry criteria.** WS1 complete. Schema-level sub-stream (WS7a) enters Wave 2; content-level (WS7b) enters Wave 4.

#### WS7a (schema, Wave 2)
- Kill switches `OMNI_SKIP_HOOKS` / `DISABLE_OMNI` at the top of every hook; `OMC_SKIP_HOOKS` / `DISABLE_OMC` kept as back-compat aliases with deprecation warning; **removed in v3.0.0** per `[critic §7 #9]`.
- `shlex.split(posix=True)` ValueError → DENY with reason "malformed shell command"; no `.split()` fallback.
- `${CLAUDE_PLUGIN_ROOT}` → `${COPILOT_PLUGIN_ROOT}` rename with `CLAUDE_PLUGIN_ROOT` fallback read (Copilot first).
- `scripts/launch_python.py` bootstrap: tries `python3`, `python`, `py -3` in order; replaces every hardcoded `python3` in hook/mcp configs.

#### WS7b (content, Wave 4)
- Audit log hardening: `fcntl.flock` POSIX, per-pid logfile Windows, fsync after append; schema `{ts, tool, status, args_digest, session_id, bypass, router_decision}`.
- Session-aware banner: direct SQLite read, not MCP stdio. **Expected counts hard-coded to post-Phase-B reality** per `[critic §7 #19]`:
  - Skills: **29** (= 37 on-disk - 7 DELETE - 1 DEFER).
  - Agents: TBD at Wave 4; locked count committed to banner, validated by `--check-doc-counts`.
  - MCP tools: TBD at Wave 4 after WS8a's tool churn (drops `subtask.route`, adds `trace_write` + `session_record` → net count locked).
- **Banner cache invalidation** `[critic §2 WS7]`: `.omni/cache/banner.json` includes `tree_hash` of `skills/` + `agents/` + `mcp/server.py::TOOLS`; refresh on mismatch at session start.
- Unicode NFC normalization in `pre_tool_use.py`.
- Policy-file permission check: reject world-writable, warn on non-0600.
- Hook precedence contract moved into router (WS3); hook becomes thin wrapper.

- **Acceptance criteria (combined).**
  - `tests/test_hooks.py::KillSwitchTests` sets `OMNI_SKIP_HOOKS=1` and asserts **all four** hooks no-op (empty JSON, exit 0) — per `[critic §4 WS7]`.
  - `tests/test_security.py` regression for `rm'-rf /` returns DENY.
  - Parallel stress 100 log lines / 10 processes → all 100 parse as valid JSONL.
  - `scripts/launch_python.py doctor` on Windows CI with Python as `py -3` only → green.
  - `--check-env-vars` finds no bare `CLAUDE_PLUGIN_ROOT` in `hooks/hooks.json`, `.mcp.json`, or command docs (fallback reads allowed).
  - Banner counts match ADR-committed values; `--check-doc-counts` green.
- **Size.** L (split across Wave 2 and Wave 4).
- **Dependencies.** WS1, WS3.

### WS8 — MCP server hardening + state API + dead-code removal (with WS8b sub-stream)

- **Goal.** Close every Critical/High in `[codex-internal §5]` and `[int-hooks §11]`. Give skills the API they need (state listing, session scoping, router slot) and delete tools that are readers without writers. WS8b consolidates state-source ownership across the on-disk stores into ADR-0007's canonical matrix.
- **Rationale.** Skills expect `state_list_active`, `state_get_status`, session scoping, router slot; the server exposes only `state_write/read/clear` with `mode` + `body` `[codex-internal §5]`. Schemas published but unenforced `[int-hooks §11.1]`. `session_search`, `trace_*` readers with no writers. `subtask.route` stub. The architect flagged dual-state consolidation as the unaddressed half of P0-1 `[arch §5]`.
- **Entry criteria.** WS1 complete.

#### WS8a — Schema + API expansion
- **Schema enforcement.** In `mcp/server.py::_handle()`, validate `arguments` against tool's `inputSchema` using a stdlib JSON Schema subset (types, required, enum, additionalProperties:false). Return `-32602 invalid params`. Acknowledge YAGNI risk `[critic §2 WS8]`: restrict the grammar used across all tool schemas upfront to the subset the validator supports; document in `docs/CONTRACT.md`.
- **Expanded state API.**
  - `state_list_active` — modes where `body.active == true`, optional `session_id` filter.
  - `state_get_status` — `{mode, active, session_id, updated_at, summary}` for a mode.
  - `state_write` gains optional `session_id`.
  - `state_clear` gains optional `session_id` and `reason` (stored in audit).
- **Router slot (`mode="router"`) is a named WS8a deliverable** per `[arch §4 Cycle 1, §7 #7]`: TTL=600s, concurrent-writer = last-write-wins, session-scoped, cancel semantics = `state_clear(mode="router", session_id=<x>)` invalidates.
- **Writers for readers.**
  - `trace_write` (span_id, parent_id, actor, action, detail, duration_ms); wired into `subagent.py` entry/exit.
  - `session_record` (session_id, prompt, decision, outcome); called from `user_prompt_submit.py` after router decision + from tier-0 skills on entry.
- **Drop dead tools.** If `subtask.route` cannot be made non-stub within Phase B, remove. session_search + trace writers now delivered.
- **Exception leak fix.** `_handle()` returns sanitized message for unexpected exceptions; traceback to `.omni/support/mcp.log`.
- **Connection pool.** 4-connection thread-safe pool behind `_Conn` wrapper.
- **Policy-profile robustness.** Malformed policy JSON → loud stderr warning, fallback to default.
- **Artifact mirror sandbox.** `_tool_artifact_write` gains `OMNI_ARTIFACT_ROOT` override.
- **Schema migrations additive-only through Phase B** per `[critic §1 P6, §7 #10]`: `ALTER TABLE ADD COLUMN session_id` runs ONLY at Wave 5 → main merge, not during Phase B waves. Wave 2+3+4 code tolerates `session_id = NULL` rows. Downgrade path = drop column (reversible).

#### WS8b — State consolidation (NEW)

- **Goal.** Answer "which store is authoritative for which data class" across the on-disk stores.
- **Rationale.** `[arch §5]` flags this as the unaddressed half of P0-1: the rename collapses directory names but leaves parallel stores with overlapping responsibilities.
- **Deliverables.**
  - **ADR-0007 "State store ownership matrix"** in `docs/CONTRACT.md`:

    | Store | Path | Data class | Authority |
    |---|---|---|---|
    | MCP SQLite | `$OMNI_HOME/omni.db` | mode state, session records, traces, artifact mirrors | **AUTHORITATIVE** for machine-readable state |
    | Runs markdown | `.omni/runs/<run-id>/` | specs, PRD, progress logs, stdout/stderr/status per job | **AUTHORITATIVE** for artifact content; MCP mirrors metadata |
    | Plans markdown | `.omni/plans/*.md` | ralplan outputs, phase plans | **AUTHORITATIVE** for plan content; MCP stores pointer + status |
    | Specs markdown | `.omni/specs/*.md` | deep-interview outputs, feature specs | **AUTHORITATIVE** for spec content; MCP stores pointer |
    | Autopilot state | `.omni/autopilot/` | legacy, v1 | **DEPRECATED** in v2; migrated by `omni_migrate.py` into `runs/` + MCP; read-only mirror for 1 minor release |
    | Sessions state | `.omni/sessions/` | legacy, v1 | **DEPRECATED** in v2; migrated into MCP `session_record` table |
    | Flat state | `.omni/state/*-state.json` | legacy, v1 | **RETIRED** in v2; `omni_migrate.py` drains into MCP; no read path in v2 code |
    | Teams | `.omni/teams/<slug>/` | team orchestrator workers, handoffs | **AUTHORITATIVE** for team artifacts; MCP mirrors state machine |
  - `scripts/verify_plugin_contract.py --check-storage` — asserts no skill writes to more than one store per data class. Scans skill bodies for store write patterns.
- **Acceptance criteria.**
  - `--check-storage` passes on a clean tree.
  - All v1 `.omni/state/*-state.json` / `.omni/autopilot/` / `.omni/sessions/` artifacts drained by `omni_migrate.py` smoke test.
  - Every KEEP-REWRITE skill body lists its authoritative store in a `## Storage` section.

- **WS8 combined acceptance.**
  - `tests/test_mcp_server.py` grows: schema-validation table of **≥10 bad inputs** spanning types, required, enum, additionalProperties `[critic §4 WS8]`; state API (`state_list_active` round-trip, `state_get_status` for unknown mode returns `{active: false}`), trace writer smoke, session_record smoke, connection-pool 5-parallel-writers test.
  - No `_tool_*` function instantiates raw `sqlite3.connect()`; all via `_Conn`.
  - `tests/test_security.py` no longer creates `.omni/runs/run-2/spec.md` in the repo.
  - Storage matrix (ADR-0007) committed before any Wave 3 PR opens.
- **Size.** L (WS8a) + M (WS8b).
- **Dependencies.** WS1.

### WS9 — Skill/agent contract audit — machine-checked contract (promoted skeleton to Wave 0)

- **Goal.** Make the skill/agent contract enforceable. Every surviving `skills/*/SKILL.md` and `agents/*.md` must have valid frontmatter, exist on disk, reference only real commands/tools/agents, and pass the validator. Paper-only claims cannot merge.
- **Rationale.** The architect's §3 recommendation #2 promotes the WS9 skeleton to Wave 0 so Wave-1 WS1/WS2 cannot green-merge without it.
- **Entry criteria.** Wave 0 starts; skeleton lands during Wave 0 alongside WS1 scaffolding.
- **Deliverables.**
  - `scripts/verify_plugin_contract.py` with subcommands:
    - `--check-rename` (WS1)
    - `--check-no-claude-primitives` (WS2) — strips code fences first, context-aware `[critic §7 #14]`
    - `--check-no-raw-model-names` (WS4) — AST-level match, not naive word-regex `[critic §4 WS4]`
    - `--check-pipeline` (WS5: Resume + Cleanup + Router-preamble sections)
    - `--check-env-vars` (WS7a)
    - `--check-storage` (WS8b)
    - `--check-references` — for every `/omni-*` command reference, assert command file exists; for every `agents/<name>` reference, assert agent file exists; for every MCP tool name, assert tool registered in `mcp/server.py::TOOLS`. **Explicitly documented as MECHANICAL, not SEMANTIC** per `[critic §2 WS9]`.
    - `--check-frontmatter` — validates `name`, `description`, `runtime: copilot`, and (skills only) `triggers: [...]`; (reviewer agents only) `writable: false`.
    - `--check-doc-counts` — asserts banner counts + README counts match reality.
    - `--all` — runs every check; used by CI.
  - `docs/CONTRACT.md` — frontmatter schema, banned primitives, allowed Copilot primitives, router decision payload shape, state API, model category resolver, expected skill sections (Setup / Resume / Cleanup / Acceptance / Storage / Router-preamble), storage ownership matrix.
  - CI wiring (WS12) invokes `--all`.
  - Final deletion pass on paper-only skills at the end of WS2.
- **Acceptance criteria.**
  - `scripts/verify_plugin_contract.py --all` exits 0 on clean tree.
  - 100% of skills pass `--check-frontmatter` and `--check-references`.
  - Intentionally breaking one skill (`/omni-nonexistent`) makes `--all` exit non-zero with precise file:line.
  - Regression test: `tests/test_validator_fail_precision.py` flips one file, asserts exit != 0 with correct file:line `[critic §4 WS9]`.
- **Size.** M.
- **Dependencies.** Skeleton in Wave 0; full per-subcommand growth tracks each WS.

### WS10 — Test strategy (real tests, not stubs)

- **Goal.** Transition from "tests validate the small executable core" to "tests validate the behavioral contract" `[SYN §0 #10]`.
- **Rationale.** P1-8 "Storage-contract test that fails CI on doc drift" `[SYN §10 P1 #8]`.
- **Entry criteria.** WS9 skeleton exists; WS3/WS5*/WS6/WS7*/WS8* at least in shape.
- **Deliverables.**
  - `tests/test_contract.py` — drives `--all` from pytest.
  - `tests/test_router.py` (owned by WS3) — 40+ prompt regression, ≥8 adversarial.
  - `tests/test_pipeline_e2e.py` (owned by WS5b/c/d) — `pytest -m e2e`, mock-copilot driver; nightly real-Copilot job.
  - `tests/test_team.py` (owned by WS6) — non-tmux first, tmux second, state machine + handoff docs.
  - `tests/test_hooks_kill_switch.py` (owned by WS7a).
  - `tests/test_hooks_budget.py` — asserts router <100ms (addresses `[critic §2 WS3]`).
  - `tests/test_mcp_schema.py` (owned by WS8a) — table of ≥10 bad inputs per `[critic §4 WS8]`.
  - `tests/test_storage_matrix.py` (owned by WS8b).
  - `tests/test_windows_launcher.py` — `scripts/launch_python.py` on Windows CI.
  - `tests/test_subagent_background.py` + `tests/test_subagent_backpressure.py` (owned by WS5a).
  - `tests/test_omni_team_py.py` — unit tests for `scripts/omni_team.py` (per `[critic §7 #18]`).
  - **Per-module coverage targets per `[critic §7 #15]`:** `mcp/` ≥80%, `hooks/` ≥70%, `scripts/` ≥60%. CI enforces via `.coveragerc`.
  - Hermetic rule: `tests/conftest.py` sets `OMNI_HOME=tmp_path` and `OMNI_ARTIFACT_ROOT=tmp_path/runs` for every test; repo never dirtied.
- **Acceptance criteria.**
  - `pytest -q` on Linux / macOS / Windows CI jobs all green.
  - `pytest -m e2e` nightly on Linux (mock Copilot) and weekly against real Copilot CLI.
  - Per-module coverage thresholds enforced.
  - `git status --porcelain` empty after full test run.
- **Risks + mitigations.**
  - *Risk:* e2e flakiness blocks PRs. *Mitigation:* `-m e2e` separation; PRs only require unit + contract + integration; e2e nightly.
- **Size.** L.
- **Dependencies.** WS3, WS5*, WS6, WS7*, WS8*, WS9.

### WS11 — Docs + CHANGELOG + README alignment

- **Goal.** Rewrite every user-facing document to match post-Phase-B reality. Delete stale counts, stale command names, stale directories. Add ADRs for every load-bearing decision.
- **Rationale.** Session banner stale today `[SYN §6 bug 9]`; README still mentions legacy `.omc/`; `docs/MIGRATION.md` addresses "v0.1.0 Go runtime" but not v1.0.0 `.omc` → v2.0.0 `.omni`.
- **Entry criteria.** WS1 complete. WS3/WS5*/WS6 complete (commands stable). Parallel with WS10.
- **Deliverables per `[critic §7 #20]`:** every WS's PR touches `CHANGELOG.md` with one line; every BREAKING WS (WS1, WS7a, WS8a, WS8b, WS13) touches `docs/MIGRATION.md`.
  - `README.md` rewrite: v2.0.0 badge, correct counts (regenerated by `--check-doc-counts`), new install paths, new quickstart using `/omni-do` + `/omni-next`.
  - `AGENTS.md` + `CLAUDE.md` merge; `CLAUDE.md` deleted (user default per §11).
  - `docs/ARCHITECTURE.md` update with router, category resolver, team orchestrator, MCP state API, storage matrix.
  - `docs/MIGRATION.md` "Upgrading from v1.0.0 to v2.0.0": `.omc → .omni`, command namespace, kill-switch rename, breaking surface enumerated.
  - `docs/CONTRACT.md` (WS9 + WS8b).
  - `docs/MODELS.md` (WS4).
  - `docs/ROUTER.md` (WS3) — precedence, vagueness rubric (ADR-0005 table), bypass syntax, `omni-next` determinism note, deep-interview turn-based resume.
  - `docs/HOOK_CONTRACT.md` (WS7) — env var contract, kill-switch deprecation timeline.
  - `docs/TEAM.md` (WS6) — tmux vs subprocess, Windows `--experimental` posture.
  - `docs/PIPELINE.md` (WS5) — mode composition: autopilot→ralph subprocess nesting, session_id threading, cancel cascading.
  - `docs/RENAMES.md` (WS1) — redirect list.
  - New `docs/ADR/` directory:
    - ADR-0000 Phase-B charter
    - ADR-0001 host = Copilot CLI only
    - ADR-0002 skill deletions
    - ADR-0003 semantic model categories + fallback chains
    - ADR-0004 team = tmux + worktrees + state machine (with subprocess fallback)
    - ADR-0005 router scoring rubric
    - ADR-0006 mode composition (autopilot→ralph)
    - ADR-0007 state store ownership matrix + team Windows `--experimental` posture
    - ADR-0008 plugin-distribution migration
    - ADR-0009 `.omni/config.json` schema versioning
    - ADR-0010 subagent back-pressure
    - ADR-0011 deep-interview turn-based resume on Copilot CLI `-p`
  - `CHANGELOG.md` v2.0.0 section with full breaking surface.
- **Acceptance criteria.**
  - `--check-doc-counts` passes.
  - No doc references `.omc/` or `oh-my-claudecode:` except `docs/RENAMES.md`.
  - Every ADR has Context, Decision, Alternatives considered, Consequences.
  - Manual UAT read-through per WS11 in §6.
- **Size.** M (operationalized via "land doc with the PR that owns each change" principle, explicitly enforced by `wave-N-ownership.yaml` doc-file ownership).
- **Dependencies.** WS1, WS3, WS4, WS5*, WS6, WS7*, WS8*, WS9, WS13.

### WS12 — CI / release (green gate + v2.0.0 tag)

- **Goal.** Wire every check from WS1–WS11 + WS13 into a CI gate, tag v2.0.0, publish release notes.
- **Rationale.** Without a mandatory CI gate, Phase-B outcomes erode `[SYN §1.1]`.
- **Entry criteria.** WS1–WS11, WS13 complete.
- **Deliverables.**
  - `.github/workflows/ci.yml` matrix across Linux / macOS / Windows, Python 3.9 / 3.10 / 3.11 / 3.12:
    1. `scripts/check_stdlib_only.py`
    2. `scripts/discovery_smoke.py --all` (runs A1–A6 probes on supported OSes)
    3. `scripts/validate_plugin.py`
    4. `scripts/verify_plugin_contract.py --all`
    5. `pytest -q` with per-module coverage thresholds
    6. Nightly: `pytest -m e2e` (Linux mock + Linux real Copilot)
    7. Weekly: `pytest -m e2e` against real Copilot on all three OSes
  - **Named nightly job** `phase-b-e2e-nightly` with cron `0 2 * * *`, Linux runner, `COPILOT_TOKEN` secret-gated per `[critic §7 #7]`.
  - `RELEASE.md` checklist (smoke on clean machine; docs counts verify; banner verify; tag).
  - Pre-commit hook doc (optional, user-run).
  - **Release gate per `[critic §4 WS12]`:** 3 consecutive green runs on `phase-b/main` over ≥24h before the final merge to `main`.
  - **Windows real-Copilot manual smoke** before tag, tracked in `RELEASE.md` checklist `[critic §2 WS12]`.
- **Acceptance criteria.**
  - CI green on `main` at tag time.
  - `git tag v2.0.0` succeeds; release notes published.
  - `copilot plugin install Jurel89/copilot-omni` works on clean RHEL/macOS/Windows laptop (smoke runbook in `RELEASE.md`).
  - Windows manual smoke signed off.
- **Size.** M.
- **Dependencies.** All other WSes.

### WS13 — Plugin migration & lifecycle (NEW)

- **Goal.** Answer the missed items the v1 plan glossed over: how existing v1.0.0 installs migrate to v2.0.0; how user-facing `.omni/config.json` survives future plugin upgrades; how `subagent.py` back-pressure is defaulted; how deep-interview works on Copilot CLI `-p`.
- **Rationale.** All four items raised by critic §6 (items 1–5) and architect §8 (item 6) are "plugin lifecycle" concerns that need defaults + ADRs before shipping. Rather than scatter them, WS13 bundles them.
- **Entry criteria.** WS1 merged (rename stable so migrator knows what to move).
- **Deliverables.**
  - **D1 — Plugin-distribution migration (ADR-0008).** `scripts/omni_migrate_v1_to_v2.py` runs automatically on first plugin load (or first `omni doctor`) when `.omc/` exists: renames directories, rewrites references in user config, prints one-line report. CHANGELOG.md flags v2.0.0 as BREAKING. Idempotent. Rollback path: `omni_migrate_v1_to_v2.py --rollback` documented as last-resort.
  - **D2 — `.omni/config.json` versioning (ADR-0009).** Harness-managed. Top-level `schema_version: 1` (start). `omni doctor` rewrites missing/stale keys, never silently drops unknown keys (warns). Plugin upgrades run a one-shot migrator. Users MAY edit; edits must respect schema. Upgrade path from `schema_version=1` to `=2` is a scripted `migrate_config_v1_to_v2()` shipped with the plugin upgrade that introduces the new schema.
  - **D3 — `subagent.py` back-pressure (ADR-0010).** Semaphore-limited. Default cap = `min(8, os.cpu_count())`. Overridable via `.omni/config.json > runtime.max_parallel_subagents`. When cap reached, new spawns BLOCK (not fail). Per-subagent memory policing deferred to Phase C. (Implementation ships as part of WS5a.)
  - **D4 — deep-interview on Copilot CLI `-p` (ADR-0011).** Turn-based, not blocking. Deep-interview emits questions; skill returns control; NEXT user turn must contain answers. Skill state persists to `.omni/specs/deep-interview-<slug>.md`, resumed on next turn. (Documented in `docs/ROUTER.md`; skill body change owned by WS2's deep-interview rewrite.)
  - **Accepted breakage surface enumeration (ADR in `CHANGELOG.md` v2.0.0)** per `[arch §8 item 6]`:
    - `.omc/ → .omni/` migration mandatory
    - `/oh-my-claudecode:* → /omni-*` breaks user shell aliases
    - `OMC_SKIP_HOOKS → OMNI_SKIP_HOOKS` (with alias for 1 minor version; removed v3.0.0)
    - `CLAUDE_PLUGIN_ROOT → COPILOT_PLUGIN_ROOT` (with fallback read)
    - 7 skills deleted per ADR-0002
    - 1 skill deferred (`configure-notifications`)
    - MCP tool churn: `subtask.route` removed; legacy `.omni/state/*-state.json` writers removed
- **Acceptance criteria.**
  - `scripts/omni_migrate_v1_to_v2.py --smoke` on a fabricated v1 tree converts cleanly; `--rollback` reverses.
  - `.omni/config.json` without `schema_version` triggers migration on `omni doctor`; test asserts unknown keys preserved with warning.
  - `tests/test_config_migration.py` covers v1→v2 config schema upgrade.
  - `tests/test_deep_interview_turns.py` exercises turn-1 → turn-2 resume path on a mock Copilot `-p` loop.
  - CHANGELOG v2.0.0 enumerates the full break list; `docs/MIGRATION.md` links it.
- **Size.** M.
- **Dependencies.** WS1 (naming stable). ADR-0010 ships via WS5a. ADR-0011 skill body ships via WS2/deep-interview rewrite.

## 3. Dependency graph (ASCII DAG, updated)

```
          WS1 (rename + command namespace)
            │
   ┌────────┼──────────┬──────────┬──────────┬──────────┐
   ▼        ▼          ▼          ▼          ▼          ▼
  WS2      WS3        WS4       WS8a       WS9        WS13
 (decon)  (router    (models   (MCP      (validator  (lifecycle,
          + stub     + fallbk)  schema)   skeleton   migrator,
          reader →              + router   in Wave 0) config
          cuts over             slot                  version)
          to WS8a                +
          when slot             WS8b
          live in Wave 2)       ownership
                                matrix
   │        │           │          │          │          │
   │        │           ▼          │          │          │
   │        │         WS5a         │          │          │
   │        │       (subagent      │          │          │
   │        │         primitive)   │          │          │
   │        │           │          │          │          │
   │        └─┬─────────┼──────────┘          │          │
   │          ▼         ▼                     │          │
   │        WS5b      WS5c      WS5d          │          │
   │       (auto+     (ultra+   (ralplan)     │          │
   │        ralph)    ultraqa)                │          │
   │                                          │          │
   └──────────┬──────────────────────┬────────┘          │
              ▼                      ▼                   │
            WS6 (team)             WS7a (hooks schema,   │
              │                         Wave 2)          │
              │                         │                │
              └─────────┬────────────┬──┴────────────────┘
                        ▼            ▼
                      WS7b         WS10       WS11
                      (hooks      (tests)    (docs +
                       content,                ADRs)
                       Wave 4)
                        │            │          │
                        └─────┬──────┴──────────┘
                              ▼
                            WS12 (CI/release)
```

Critical path: **WS1 → WS2 || WS3-stub || WS4 || WS8a || WS8b || WS9 || WS13 → WS5a → WS5b || WS5c || WS5d → WS6 → WS7b || WS10 || WS11 → WS12.**

Cycle previously at WS3↔WS8 resolved by stub reader in WS3 until WS8a's `mode="router"` slot merges inside Wave 2.

## 4. Execution waves

### Wave 0 — Baseline snapshot + runtime contract verification (S+M, 1.5–2 days)

- **Entry.** Phase-A synthesis approved; user's 8 locked decisions in this plan; user sign-off on §11 open items.
- **Parallelism plan.** Single actor for branch/tag scaffolding; runtime-contract probes run serial.
- **Work.**
  - Create long-lived branch `phase-b/main` off `main`; every wave branches off and merges back here.
  - Tag `v1.0.0-pre-phase-b` on `main`.
  - Snapshot `.omni/research/` and commit `.omni/plans/phase-b-master-plan.md` (this file).
  - Write `docs/ADR/ADR-0000-phase-b-charter.md` capturing the 8 locked decisions verbatim.
  - Scaffold `scripts/verify_plugin_contract.py` skeleton with `--check-rename` stub so later waves can append checks. (Architect's "W0-gate" promotion `[arch §7 #2]`.)
  - **Runtime contract probes §2.5 A1–A6 in `scripts/discovery_smoke.py`**; all six green on Linux + macOS (Windows optional for A1/A4/A6, mandatory for A2/A3/A5). Output persisted to `.omni/audit/runtime-contract.jsonl`.
- **Exit.** Tag + branch exist; charter ADR committed; validator skeleton merged; six probes green. **If any mandatory probe fails, Wave 0 blocks.**

### Wave 1 — Foundation, serialized (M, 4–6 days)

- **Entry.** Wave 0 exit criteria met.
- **Parallelism plan.** **Serialized per `[critic §1 P3]`, `[critic §7 #11]`:** WS1 SOLO first (2–3 days); after WS1 merges to `phase-b/main`, WS2 + WS9 run in parallel (2–3 days).
- **Work.** WS1 rename + rebrand + command namespace. Then WS2 Claude decontamination + WS9 validator growth.
- **File ownership.** `wave-1-ownership.yaml` forbids two WSes editing the same file concurrently:
  - WS1-solo: owns every file touched by rename (no other WS edits during this sub-wave).
  - Post-WS1: WS2 owns skill/agent bodies; WS9 owns `verify_plugin_contract.py` + `docs/CONTRACT.md`. Non-overlapping.
- **Exit.** `scripts/verify_plugin_contract.py --check-rename --check-no-claude-primitives --check-frontmatter` green. Grep counts at target (0). Wave merges to `phase-b/main`. `main` remains at v1.0.0.

### Wave 2 — Core rewrites (L, 10–14 days, expanded per `[critic §1 P2]`)

- **Entry.** Wave 1 merged.
- **Parallelism plan.** WS3-router (with stub reader) || WS4-models || WS7a-hooks-schema || WS8a-MCP-schema || WS8b-storage-matrix || WS13-migrator-scaffold in parallel. WS5a (subagent primitive) opens as soon as WS4 merges `--category` (serialized on `subagent.py`). WS5b/c/d start when WS5a merges AND WS8a's `mode="router"` slot lands (so WS3 can cut over from stub to live).
- **File ownership.** `wave-2-ownership.yaml`:
  - WS3 owns `hooks/router.py`, `hooks/user_prompt_submit.py`, `commands/omni-do.md`, `commands/omni-next.md`, `tests/test_router.py`, `docs/ROUTER.md`.
  - WS4 owns `scripts/omni_models.py`, `tests/test_models.py`, `docs/MODELS.md`.
  - WS4 + WS5a both edit `scripts/subagent.py`: **WS4 merges first**, WS5a rebases. No concurrent edits.
  - WS5b/c/d own their respective `skills/<name>/SKILL.md`.
  - WS7a owns `hooks/hooks.json`, `hooks/pre_tool_use.py`, `scripts/launch_python.py`.
  - WS8a owns `mcp/server.py`, `tests/test_mcp_server.py`, `tests/test_mcp_schema.py`.
  - WS8b owns the storage-matrix section of `docs/CONTRACT.md`.
  - WS13 owns `scripts/omni_migrate_v1_to_v2.py`, config schema docs.
- **Work.** As per each WS's deliverables.
- **Exit.** Router emits structured decisions; `mode="router"` slot live in MCP; vague prompts redirect to deep-interview; `--skip-interview` works. Category resolver passes unit tests including fallback. MCP schema validation active; state API expanded; storage matrix committed. Autopilot/ralph/ultrawork/ultraqa/ralplan all pass their e2e smoke under `pytest -m e2e`. WS7a kill switches and shlex fix live. Merge to `phase-b/main`.

### Wave 3 — Team rebuild (L, 5–7 days)

- **Entry.** Wave 2 merged; ralph works.
- **Parallelism plan.** Single workstream (WS6) + WS13 migrator smoke (runs in parallel, touches disjoint files).
- **Work.** WS6 tmux + subprocess fallback + worktrees + state machine + handoff docs. WS13 `omni_migrate_v1_to_v2.py` + config schema versioning completion.
- **Exit.** `omni team plan "..."` smoke green in BOTH modes on Linux+macOS; subprocess-only green on Windows. `OMNI_EXPERIMENTAL_TEAM=1` gate live. Zero Claude `Team*`/`Send*` primitives anywhere. Migrator smoke green. Also: end-of-Wave 3, validator enforces "grep-0 raw model names in skills/agents" per WS4 split-acceptance `[arch §7 #12]`. Merge to `phase-b/main`.

### Wave 4 — Hardening (M, 3–5 days)

- **Entry.** Wave 3 merged.
- **Parallelism plan.** WS7b (hooks content) and final WS8 polish (connection pool, exception sanitization) in parallel.
- **Work.** WS7b audit log + banner + policy checks. WS8 polish. WS13 deep-interview turn-based resume test.
- **Exit.** `tests/test_hooks_kill_switch.py`, `tests/test_security.py`, `tests/test_mcp_schema.py`, `tests/test_deep_interview_turns.py` green. Banner counts match ADR-committed values. Merge to `phase-b/main`.

### Wave 5 — Tests + docs + release (M, 4–6 days)

- **Entry.** Wave 4 merged.
- **Parallelism plan.** WS10 (tests) || WS11 (docs). WS12 (CI/release) last. **WS11 ordering within wave:** docs that depend on counts (README, banner) wait on `--check-doc-counts` to stabilize `[critic §3]`.
- **Work.** WS10 full suite + coverage thresholds. WS11 docs + ADRs + CHANGELOG v2.0.0 full breakage surface. WS12 CI matrix + nightly job + release.
- **Exit.** `scripts/verify_plugin_contract.py --all` + `pytest -q` green on all three OSes. Per-module coverage thresholds met. 3 consecutive green `phase-b/main` runs over ≥24h. Windows real-Copilot manual smoke signed off. Tag `v2.0.0`. Publish release notes.

## 5. Atomic PR / commit strategy

- **Branch topology.** Long-lived `phase-b/main` off `main`. Each wave branches off as `phase-b/wave-N-<slug>`; each workstream inside a wave is one PR `phase-b/wave-N/WS<M>-<slug>`. Example: `phase-b/wave-1/WS1-rename-sweep`, `phase-b/wave-2/WS5a-subagent-primitive`.
- **PR granularity.** One PR per workstream (with WS5 split yielding 4 PRs in Wave 2); merged into the wave branch. At wave exit, wave branch merges into `phase-b/main`.
- **Commit convention.** Conventional Commits:
  - `refactor(rename): sweep .omc/ → .omni/ (WS1)`
  - `feat(router): intent classifier + vagueness gate (WS3)`
  - `feat(subagent): --background + run-directory layout (WS5a)`
  - `fix(hooks): implement OMNI_SKIP_HOOKS kill switch (WS7a)`
  - Scope = workstream number.
- **File-ownership manifest per wave** (`wave-N-ownership.yaml`, `[critic §7 #11]`). YAML enforced by a tiny pre-PR lint `scripts/check_wave_ownership.py`: if a PR modifies a file listed in another WS's ownership set for the same wave, CI fails.
- **Keeping CI green.** Every PR must:
  1. Pass `scripts/verify_plugin_contract.py --all` (grows with each WS).
  2. Pass `pytest -q` on Linux CI.
  3. Not break `main`; WS2 deletions pre-declared in ADR-0002.
  4. Touch `CHANGELOG.md` with one line.
  5. If breaking: touch `docs/MIGRATION.md` too per `[critic §7 #20]`.
  6. Pass `scripts/check_wave_ownership.py`.
- **Merges to `main`.** `main` remains at v1.0.0 until Wave 5 exits. Final merge `phase-b/main → main` produces v2.0.0. No intermediate tags on `main` during Phase B.

## 6. Verification strategy

### Machine-checked

- `scripts/verify_plugin_contract.py --all` as described in WS9.
- `scripts/discovery_smoke.py --all` runs the §2.5 runtime probes on Wave 0 entry + nightly thereafter.
- `pytest -q` covering unit + integration.
- `pytest -m e2e` nightly on Linux (mock Copilot) and weekly against real Copilot CLI on all three OSes.
- `scripts/check_stdlib_only.py` enforces zero pip deps.
- **Per-module coverage** `[critic §7 #15]`: `mcp/` ≥80%, `hooks/` ≥70%, `scripts/` ≥60%. CI enforces.
- `git status --porcelain` empty after full test run.

### Human-checked (per workstream UAT)

- **WS1.** Whole-tree grep manually on clean checkout; session banner in Copilot CLI shows v2.0.0.
- **WS2.** Open five KEEP-REWRITE SKILL.md files at random; confirm zero Claude primitives in executable-code sections.
- **WS3.** Type 5 ad-hoc prompts (from the 40-prompt table); confirm hook output matches expectation; type one adversarial near-threshold.
- **WS4.** Run `omni list models`; confirm categories + resolved models + fallback chains match subscription menu; kill primary network path and confirm fallback triggers.
- **WS5a.** Run `subagent.py --background` × 3; confirm run dirs and status.json.
- **WS5b.** Run `copilot -p "autopilot build a hello-world CLI in /tmp/hello"`; confirm spec + plan + code + tests produced.
- **WS5c.** Run `copilot -p "ultrawork fix three imports in src/*.py"`; confirm 3 background jobs.
- **WS5d.** Run `copilot -p "ralplan refactor the auth module"`; confirm RALPLAN-DR plan produced.
- **WS6.** Run `omni team plan "3 agents to fix TODOs in docs/"` in BOTH modes; open tmux, watch panes, check handoff docs; repeat in subprocess mode. Repeat on Windows with `OMNI_EXPERIMENTAL_TEAM=1`.
- **WS7a.** `OMNI_SKIP_HOOKS=1 copilot -p "list files"`; confirm no audit log entries created.
- **WS7b.** Read banner counts; cross-check `--check-doc-counts`.
- **WS8a.** `copilot mcp state_list_active`; returns active modes. Attempt bad input on `state_write`; returns `-32602`.
- **WS8b.** Open `docs/CONTRACT.md` storage matrix; cross-reference against 3 random skill bodies.
- **WS9.** Intentionally break one skill; confirm CI fails with right file:line.
- **WS10.** Full `pytest -q` read-through.
- **WS11.** Open README, AGENTS.md, ARCHITECTURE, MIGRATION, CONTRACT, all ADRs; confirm counts, command names, directory names.
- **WS12.** `copilot plugin install Jurel89/copilot-omni@v2.0.0` on clean RHEL/macOS/Windows; manual smoke logged.
- **WS13.** Run migrator on a fabricated v1 tree; confirm idempotence; confirm deep-interview turn-based resume.

### Adversarial — one cycle per wave (manual in W0+W1, parallel W2+)

Per `[critic §1 P10, §7 #12]`: the adversarial review gate cannot use a mechanism it is meant to validate. So:
- **Wave 0 + Wave 1 adversarial reviews run manually** — human reviewer runs `critic`, `architect`, `code-reviewer` agents one at a time via `copilot --agent <x>` in the terminal.
- **Wave 2+ adversarial reviews run in parallel** via `scripts/subagent.py --background` (which itself lands mid-Wave 2 via WS5a).

Three review agents at each wave exit:
- `critic`: is the wave's plan acceptance criteria actually met? Any paper-only claims?
- `architect`: are decisions consistent with Phase-A decisions 1–7?
- `code-reviewer`: PR-level review of wave diff; flag Claude primitives, stale `.omc/` refs, untested paths.

Any blocker from any of the three reverts the wave merge.

## 7. File-level change inventory

(Not exhaustive; table-of-contents for execution agents. Every line here should become a TODO in the Wave-N branch.)

### WS1 — Rename (CREATE / MODIFY / DELETE)

- MODIFY: `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin.json`, `.claude-plugin/plugin.json`, `.mcp.json`, `hooks/hooks.json`, `hooks/*.py`, `scripts/omni.py`, `scripts/omni`, `scripts/omni.cmd`, `scripts/subagent.py`, `scripts/validate_plugin.py`, `scripts/discovery_smoke.py`, `mcp/server.py`, `commands/omni-*.md` (×8+), `skills/*/SKILL.md` (KEEP-REWRITE subset = 29), `agents/*.md`, `docs/*.md`, `tests/*.py`, `CHANGELOG.md`, `.github/workflows/*.yml`.
- CREATE: `scripts/verify_plugin_contract.py` (skeleton), `scripts/omni_migrate.py`, `docs/RENAMES.md`, `docs/ADR/ADR-0000-phase-b-charter.md`, `.omni/plans/phase-b-master-plan.md` (this file), `.omni/plans/phase-b-master-plan-v1-backup.md` (v1 preservation).
- RENAME (dirs): `skills/omc-doctor → skills/omni-doctor`, `skills/omc-setup → skills/omni-setup`, `skills/omc-teams → skills/omni-teams`, `skills/omc-reference → skills/omni-reference`.
- RENAME (commands): every `/oh-my-claudecode:X` → `/omni-X`.

### WS2 — Decontamination (full 37-skill listing)

**KEEP-REWRITE (29):** `ai-slop-cleaner`, `ask`, `autopilot`, `cancel`, `debug`, `deep-dive`, `deep-interview`, `deepinit`, `external-context`, `hud`, `mcp-setup`, `omni-doctor` (renamed), `omni-reference` (renamed), `omni-setup` (renamed), `omni-teams` (renamed), `plan`, `ralph`, `ralplan`, `release`, `remember`, `setup`, `skill`, `skillify`, `team`, `trace`, `ultraqa`, `ultrawork`, `verify`, `wiki`.

**DELETE (7):** `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory`.

**DEFER-TO-PHASE-C (1):** `configure-notifications`.

- CREATE: `docs/CONTRACT.md`, `docs/ADR/ADR-0002-skill-deletions.md`.
- MODIFY: every KEEP-REWRITE `skills/*/SKILL.md`, every `agents/*.md` that referenced Claude primitives.
- DELETE (dirs): `skills/ccg/`, `skills/learner/`, `skills/project-session-manager/`, `skills/sciomc/`, `skills/self-improve/`, `skills/visual-verdict/`, `skills/writer-memory/`.
- MOVE: `skills/configure-notifications/` → `phase-c-backlog/configure-notifications/` (out of `skills/` tree, preserved in repo).

### WS3 — Router

- CREATE: `hooks/router.py`, `scripts/sync_triggers.py`, `scripts/omni_next.py`, `commands/omni-do.md`, `commands/omni-next.md`, `tests/test_router.py`, `tests/test_router_handoff.py`, `tests/test_hooks_budget.py`, `docs/ROUTER.md`, `docs/ADR/ADR-0005-router-design.md`.
- MODIFY: `hooks/user_prompt_submit.py`, `hooks/session_start.py`, every KEEP-REWRITE SKILL.md (canonical router-consumption preamble).

### WS4 — Models

- CREATE: `scripts/omni_models.py`, `docs/MODELS.md`, `commands/omni-models.md`, `tests/test_models.py`, `docs/ADR/ADR-0003-model-categories.md`.
- MODIFY: `scripts/subagent.py` (add `--category`; MERGED FIRST before WS5a), `scripts/omni.py` (add `omni models` subcommand), every KEEP-REWRITE skill/agent referencing raw model names, `.omni/config.json` template.

### WS5a — Subagent primitive

- MODIFY: `scripts/subagent.py` (add `--background`, `--session-id`, back-pressure semaphore).
- CREATE: `scripts/wait_for_jobs.py`, `tests/test_subagent_background.py`, `tests/test_subagent_backpressure.py`, `docs/ADR/ADR-0010-subagent-backpressure.md`.

### WS5b — autopilot + ralph

- MODIFY: `skills/autopilot/SKILL.md`, `skills/ralph/SKILL.md`, possibly add `agents/security-reviewer-lite.md`.
- CREATE: `tests/test_pipeline_e2e.py` (initial file; grown by WS5c/d), `docs/PIPELINE.md`, `docs/ADR/ADR-0006-mode-composition.md`.

### WS5c — ultrawork + ultraqa

- MODIFY: `skills/ultrawork/SKILL.md`, `skills/ultraqa/SKILL.md`.
- MODIFY: `tests/test_pipeline_e2e.py` (add ultrawork + ultraqa tests).

### WS5d — ralplan

- MODIFY: `skills/ralplan/SKILL.md`.
- MODIFY: `tests/test_pipeline_e2e.py` (add ralplan test).

### WS6 — Team

- CREATE: `scripts/omni_team.py`, `commands/omni-team.md`, `tests/test_team.py`, `tests/test_omni_team_py.py`, `docs/ADR/ADR-0004-team-architecture.md`, `docs/TEAM.md`.
- MODIFY: `skills/team/SKILL.md` (full rewrite), `skills/omni-teams/SKILL.md` (entry runbook), `scripts/omni.py` (add `omni team` subcommand).

### WS7a — Hooks schema

- MODIFY: `hooks/hooks.json`, `hooks/pre_tool_use.py`, `hooks/user_prompt_submit.py` (kill switches, env-var rename, shlex fix).
- CREATE: `scripts/launch_python.py`, `docs/HOOK_CONTRACT.md`, `tests/test_hooks_kill_switch.py`, `tests/test_windows_launcher.py`.

### WS7b — Hooks content

- MODIFY: `hooks/session_start.py` (dynamic banner, cache tree_hash), `hooks/post_tool_use.py` (audit log), `hooks/pre_tool_use.py` (NFC, policy perms).

### WS8a — MCP schema + API

- MODIFY: `mcp/server.py` (schema validation, state API expansion, router slot, trace_write, session_record, connection pool, exception sanitization, policy-profile robustness, artifact sandbox).
- CREATE: `tests/test_mcp_schema.py`.
- MODIFY: `tests/test_mcp_server.py`.
- DELETE (tool registration): `subtask.route` if not implementable.

### WS8b — Storage consolidation

- CREATE: `docs/ADR/ADR-0007-state-ownership.md`.
- MODIFY: `docs/CONTRACT.md` (storage matrix section).
- MODIFY: `scripts/verify_plugin_contract.py` (`--check-storage`).
- CREATE: `tests/test_storage_matrix.py`.

### WS9 — Validator

- MODIFY: `scripts/verify_plugin_contract.py` (all `--check-*` subcommands).
- CREATE: `docs/CONTRACT.md` (shared with WS2+WS8b), `tests/test_validator_fail_precision.py`.

### WS10 — Tests

- CREATE: `tests/test_contract.py`, `tests/conftest.py` (hermetic fixtures), `.coveragerc` (per-module targets).
- MODIFY: all existing tests to use hermetic fixtures.

### WS11 — Docs

- MODIFY: `README.md`, `AGENTS.md`, delete `CLAUDE.md` (per §11 default), `docs/ARCHITECTURE.md`, `docs/MIGRATION.md`, `docs/INSTALL.md`, `docs/SKILLS.md`.
- CREATE: all ADRs (0000–0011); `CHANGELOG.md` v2.0.0 section.

### WS12 — CI/release

- MODIFY: `.github/workflows/ci.yml` (matrix + nightly job config).
- CREATE: `RELEASE.md`, `docs/ADR/ADR-9999-v2-release-notes.md` (optional).

### WS13 — Plugin lifecycle

- CREATE: `scripts/omni_migrate_v1_to_v2.py`, `tests/test_migrator.py`, `tests/test_config_migration.py`, `tests/test_deep_interview_turns.py`, `docs/ADR/ADR-0008-plugin-migration.md`, `docs/ADR/ADR-0009-config-schema-versioning.md`, `docs/ADR/ADR-0011-deep-interview-turn-based.md`.
- MODIFY: `scripts/omni.py` (wire migrator), `.omni/config.json` template (`schema_version: 1`).

## 8. Rollback plan

- **Branch-level.** Every wave merges into `phase-b/main`, not `main`. If Wave N breaks, revert wave-N merge on `phase-b/main` with `git revert -m 1 <sha>`; re-enter at wave entry criteria. `main` untouched.
- **Tag-level.** `v1.0.0-pre-phase-b` is last known-good `main`. Final merge `phase-b/main → main` tags v2.0.0. If that merge goes wrong, `git reset --hard v1.0.0-pre-phase-b` restores `main` — manual step (user-policy locked).
- **State files.** Users upgrading from v1 run `omni migrate` (implemented by WS13's `omni_migrate_v1_to_v2.py`); idempotent. `--rollback` documented as last-resort.
- **MCP schema.** **Additive-only through Phase B per `[critic §1 P6, §7 #10]`.** Schema migration bumps `schema_version` from 1 → 2 ONLY at Wave 5 → main merge. Inside Phase B waves, `session_id` column either exists with NULL-tolerance OR does not exist (both branches handled). Downgrade `scripts/mcp_schema_downgrade.py` ships as unsupported rescue in `docs/MIGRATION.md`.
- **Partial wave rollback** per `[critic §1 P6, §7 #13]`. Scenario: WS8a's schema ships mid-Wave 2, then Wave 2 is fully reverted. Procedure:
  1. Run `scripts/mcp_schema_downgrade.py --to=1` on local `.omni/omni.db`.
  2. Revert Wave 2 merge commit.
  3. `pytest -q` to confirm v1 schema works.
  4. Re-enter Wave 2 on a fresh branch.

  Because Phase-B schema migrations are additive-only and `session_id=NULL` is tolerated, the downgrade is a column drop, which is reversible.
- **Re-entering the loop.** After a wave revert, plan does NOT restart from Wave 0. Rerun wave's entry-criteria check; if met, retry.

## 9. Success signals (definition of done for Phase B → v2.0.0)

Hard-coded, no weasel wording `[critic §7 #19]`:

- `scripts/verify_plugin_contract.py --all` exits 0.
- `pytest -q` green on Linux / macOS / Windows.
- Per-module coverage met: `mcp/` ≥80%, `hooks/` ≥70%, `scripts/` ≥60%.
- `grep -rE '(\.omc/|oh-my-claudecode|Task\(|Skill\(|AskUserQuestion|TeamCreate|SendMessage|state_list_active)' .` returns 0 hits (whole-tree grep with explicit allowlist).
- `OMNI_SKIP_HOOKS=1` verified to no-op ALL FOUR hooks (not a subset).
- `omni team plan "..."` smoke green in BOTH tmux and subprocess modes on Linux+macOS; subprocess-only on Windows with `OMNI_EXPERIMENTAL_TEAM=1`; zero orphan worktrees after cancel (asserted by `git worktree list` showing 0 after 3 created then cancelled).
- `autopilot / ralph / ultrawork / ultraqa / ralplan` e2e smoke green (mock Copilot); nightly real-Copilot job on Linux green at tag time.
- **Session banner reports EXACTLY: 29 skills, N agents, M MCP tools** (N and M locked at end of WS7b content pass + ADR-committed; `--check-doc-counts` enforces).
- Router regression harness ≥40 prompts, ≥8 adversarial near-threshold, green; vague prompts redirect to deep-interview; `--skip-interview` works.
- Docs: README, AGENTS.md, ARCHITECTURE, MIGRATION, MODELS, ROUTER, HOOK_CONTRACT, CONTRACT (with storage matrix), TEAM, PIPELINE, RENAMES all exist and accurate.
- ADR-0000 through ADR-0011 committed.
- 3 consecutive green `phase-b/main` runs over ≥24h before tag.
- Windows real-Copilot manual smoke signed off in `RELEASE.md`.
- `git tag v2.0.0` on `main`; CI badge green; CHANGELOG v2.0.0 with full breakage surface enumerated.

## 10. Out of scope for Phase B (explicit non-goals)

- Claude Code support. Plugin runs on Copilot CLI only; Claude Code compat is not tested and not advertised.
- Calls to external AI CLIs (`codex`, `gemini`, `ollama`, etc.). Copilot-only.
- GSD-style phase state machine. Not adopted.
- `deep-interview` simplification (challenge-agent pruning, ambiguity-scoring rework). Deferred to Phase C. Phase B only ships turn-based persistence (ADR-0011) and removes `AskUserQuestion` references.
- **Windows native tmux team mode** (full tmux on Windows). `OMNI_EXPERIMENTAL_TEAM=1` gate in v2.0.0; proper Windows team posture decided in Phase C.
- `configure-notifications` skill. Deferred to Phase C (per WS2 triage).
- New wiki / memory ingestion hooks, knowledge-graph features, LSP tools, ast-grep tools. Deferred to Phase C.
- Multi-language (i18n) SKILL.md variants. Deferred.
- Telemetry / PostHog / any outbound network call from the plugin. Permanently out. Note: `omni doctor`'s best-effort `copilot models` check is a Copilot-initiated call, not plugin-initiated `[critic §6 #4]`.
- **Per-subagent memory policing.** Back-pressure caps concurrency, not memory. Memory-level back-pressure deferred to Phase C `[critic §6 #3]`.
- **Test artifact lifetime GC.** `.omni/runs/<run-id>/` auto-cleanup deferred to Phase C `[critic §6 #5]`.

## 11. Open items for human decision before Wave 0 starts — RESOLVED

All three items resolved on 2026-04-16; user accepted defaults. Plan is now fully locked for execution.

1. **Delete roster (ADR-0002).** ACCEPTED AS-TAGGED. WS2 will delete `ccg`, `learner`, `project-session-manager`, `sciomc`, `self-improve`, `visual-verdict`, `writer-memory`. No vetoes.
2. **`configure-notifications`.** DEFER-TO-PHASE-C (moved out of `skills/` into `.omni/deferred/`, retrievable via git history).
3. **`CLAUDE.md` at repo root.** DELETE outright (WS11). No stub retained; `AGENTS.md` is the sole entrypoint.

## 12. Appendix — mapping from SYNTHESIS P0/P1/P2 → workstreams

| SYNTHESIS item | Priority | Covered by | Reviewer source |
|---|---|---|---|
| P0-1 Collapse `.omc/.omni` split-brain `[SYN §10 P0 #1]` | P0 | WS1 + WS8b (storage matrix) | `[arch §5]` |
| P0-2 Implement kill switches `[SYN §10 P0 #2]` | P0 | WS7a (Wave 2, advanced from Wave 4) | `[arch §3, §7 #5]` |
| P0-3 Decide runtime contract (Copilot-native port) `[SYN §10 P0 #3]` | P0 | WS2, WS5a–d, WS6 | v1 |
| P0-4 Real intent gate `[SYN §10 P0 #4]` | P0 | WS3 (with stub reader until WS8a `mode="router"` lands) | `[arch §1 Decision 3, §4 Cycle 1]` |
| P0-5 MCP hardening (schema + state API + dead tools) `[SYN §10 P0 #5]` | P0 | WS8a + WS8b | `[arch §5]` |
| P1-1 Windows compatibility pass `[SYN §10 P1 #1]` | P1 | WS7a (launch_python + env var rename), WS12 (CI matrix), WS6 (Windows experimental gate) | `[critic §2 WS6, §7 #8]` |
| P1-2 Sync hook trigger table with SKILL.md `[SYN §10 P1 #2]` | P1 | WS3 (`sync_triggers.py`) | v1 |
| P1-3 Fix shlex fallback `[SYN §10 P1 #3]` | P1 | WS7a | `[arch §3]` |
| P1-4 Audit log race `[SYN §10 P1 #4]` | P1 | WS7b | v1 |
| P1-5 Upgrade `scripts/subagent.py` `[SYN §10 P1 #5]` | P1 | WS4 (category + fallbacks), WS5a (`--background` + back-pressure + output capture) | `[critic §1 P2, §7 #6]` |
| P1-6 `/omni-cancel` + `/omni-next` `[SYN §10 P1 #6]` | P1 | WS3 (`omni-next` determinism doc), WS5b (`omni cancel` refresh), WS6 (team cancel) | `[critic §6 #7]` |
| P1-7 Session-aware banner `[SYN §10 P1 #7]` | P1 | WS7b (with cache tree_hash) | `[critic §2 WS7]` |
| P1-8 Storage-contract test `[SYN §10 P1 #8]` | P1 | WS9, WS10, WS8b | `[arch §5]` |
| P1-9 MCP connection pool `[SYN §10 P1 #9]` | P1 | WS8a | v1 |
| P1-10 Policy-file safety `[SYN §10 P1 #10]` | P1 | WS7b | v1 |
| P2-1 IntentGate classifier (OMOA) `[SYN §10 P2 #1]` | P2 | WS3 | v1 |
| P2-2 `/omni-do` + `/omni-next` (GSD) `[SYN §10 P2 #2]` | P2 | WS3 | v1 |
| P2-3 Four-gate taxonomy (GSD) `[SYN §10 P2 #3]` | P2 | **Deferred (Phase C)** — not a decision-7 need | v1 |
| P2-4 Artifact-first lifecycle (GSD) `[SYN §10 P2 #4]` | P2 | **Deferred (Phase C)** | v1 |
| P2-5 Mode composition grammar (OMC) `[SYN §10 P2 #5]` | P2 | WS5b (ADR-0006 mode composition contract) + `docs/PIPELINE.md` | `[arch §1 Decision 2, §7 #6]` |
| P2-6 Wisdom accumulation notepads (OMOA) `[SYN §10 P2 #6]` | P2 | **Deferred (Phase C)** | v1 |
| P2-7 Category-based delegation (OMOA) `[SYN §10 P2 #7]` | P2 | WS4 (with `fallbacks: [str]`) | `[critic §1 P9, §7 #5]` |
| P2-8 Read-only reviewer enforcement (OMC) `[SYN §10 P2 #8]` | P2 | WS2 (frontmatter `writable: false` for critic/code-reviewer/security-reviewer; validator checks) | `[critic §7 #17]` |
| P2-9 Ambiguity-scored deep-interview (OMC) `[SYN §10 P2 #9]` | P2 | **Deferred (Phase C)** — user decision 8 | v1 |
| P2-10 Session-search + trace writers `[SYN §10 P2 #10]` | P2 | WS8a (`trace_write`, `session_record`) | v1 |

### Internal-audit bug → workstream map (top items)

| Bug (from `int-hooks`, `int-pipeline`, `codex-internal`) | Rank | Workstream | Reviewer source |
|---|---|---|---|
| `OMC_SKIP_HOOKS` unimplemented `[int-hooks §8.1]` | Critical | WS7a (Wave 2) | `[arch §3]` |
| Shlex fallback bypass `[int-hooks §2.1]` | Critical | WS7a | `[arch §3]` |
| Audit log race `[int-hooks §3.1]` | Critical | WS7b | v1 |
| State API mismatch `[codex-internal §2 Critical-1]` | Critical | WS8a | v1 |
| Storage split-brain `[codex-internal §2 Critical-2]` | Critical | WS1 + WS8b | `[arch §5]` |
| Team primitives absent `[codex-internal §2 Critical-3]` | Critical | WS6 | v1 |
| `omc ask codex` undefined `[codex-internal §2 Critical-4]` | Critical | WS2 (`ccg` DELETE) | `[critic §1 P1]` |
| MCP schema not enforced `[codex-internal §2 High-1]` | High | WS8a | v1 |
| `scripts/subagent.py` weaker than docs `[codex-internal §2 High-2]` | High | WS5a | `[critic §1 P2]` |
| `python3` hardcoded `[codex-internal §2 High-3]` | High | WS7a (`launch_python`) | `[arch §3]` |
| `${CLAUDE_PLUGIN_ROOT}` expansion assumed `[int-hooks §1.1]` | High | WS7a | `[arch §2 A2]` |
| Planner → non-existent `/oh-my-claudecode:start-work` `[codex-internal §2 High-4]` | High | WS1 (command namespace rename) + WS2 | `[arch §1 Decision 4]` |
| Hook triggers miss SKILL.md declared triggers `[codex-internal §2 High-5]` | High | WS3 (`sync_triggers`) | v1 |
| Hook precedence missing `[int-hooks §5.1]` | High | WS3 | v1 |
| Policy file trusted without perms check `[int-hooks §10.2]` | High | WS7b | v1 |
| Dead MCP tools (`session_search`, trace, `subtask.route`) `[codex-internal §5]` | Medium | WS8a | v1 |
| Raw exception leak `[codex-internal §2 Medium-2]` | Medium | WS8a | v1 |
| Stale session banner `[codex-internal §2 Medium-4]` | Medium | WS7b + WS11 | `[critic §7 #19]` |
| Tests dirty the repo `[codex-internal §2 Low-1]` | Low | WS8a + WS10 | v1 |
| Connection pool absent `[int-hooks §11.2]` | Medium | WS8a | v1 |
| Unicode NFC/NFD not handled `[int-hooks §2.3]` | Medium | WS7b | v1 |
| Audit log incomplete schema `[int-hooks §3.3]` | Medium | WS7b | v1 |
| Command naming mismatch `/oh-my-claudecode:*` vs `/omni-*` `[codex-internal §4]` | Medium | WS1 (promoted to WS1 from WS2) | `[arch §1 Decision 4]` |

### Missed-items (from critic + architect) → workstream map

| Item | Source | Workstream | ADR |
|---|---|---|---|
| Honest 37-skill triage table | `[critic §1 P1, §7 #2]` | WS2 (§2.WS2) | ADR-0002 |
| WS5 split into 4 sub-workstreams | `[critic §1 P2, §7 #6]` | WS5a/b/c/d | ADR-0006 (mode composition) |
| Wave 1 serialized | `[critic §1 P3, §3, §7 #11]` | Wave 1 plan (§4) | — |
| WS3↔WS8 cycle stub | `[arch §4 Cycle 1, §7 #7]` | WS3 deliverables | ADR-0005 |
| State consolidation matrix | `[arch §5, §7 #3]` | WS8b | ADR-0007 |
| 6 runtime-contract probes | `[arch §2 A1–A6, §7 #1]` | §2.5 + `discovery_smoke.py` | — |
| WS6 `--experimental` rescope | `[critic §1 P8, §7 #8, arch §6, §7 #8]` | WS6 (§2.WS6) | ADR-0007 |
| Plugin-distribution migrator | `[critic §6 #1]` | WS13 | ADR-0008 |
| Config schema versioning | `[critic §6 #2]` | WS13 | ADR-0009 |
| Subagent back-pressure | `[critic §6 #3]` | WS5a + WS13 | ADR-0010 |
| Deep-interview `-p` turns | `[critic §6 #6, arch §8 #6]` | WS13 + WS2 deep-interview rewrite | ADR-0011 |
| Whole-tree grep + allowlist | `[critic §7 #1]` | WS1 | — |
| Drop `!` bypass | `[critic §7 #4]` | WS3 (§2.WS3) | ADR-0005 |
| Fallback chain in config | `[critic §7 #5]` | WS4 | ADR-0003 |
| ADR-0005 rubric before tests | `[critic §7 #3]` | WS3 deliverables | ADR-0005 |
| `OMC_SKIP_HOOKS` deprecation v3.0.0 | `[critic §7 #9]` | WS7a + `docs/HOOK_CONTRACT.md` | — |
| MCP additive-only migrations | `[critic §7 #10]` | WS8a | — |
| `wave-N-ownership.yaml` | `[critic §7 #11]` | §5 | — |
| Manual W0+W1 adversarial | `[critic §7 #12]` | §6 | — |
| Banned-token parsing pass | `[critic §7 #14]` | WS2 validator | — |
| Per-module coverage | `[critic §7 #15]` | WS10 + `.coveragerc` | — |
| Hard-coded banner counts | `[critic §7 #19]` | WS7b + §9 | — |
| CHANGELOG + MIGRATION per-PR | `[critic §7 #20]` | §5 | — |
| `scripts/omni_team.py` test inventory | `[critic §7 #18]` | WS10 (`tests/test_omni_team_py.py`) | — |

Every Critical/High from the two internal audits is owned. Every convergent reviewer must-fix landed. Mediums and Lows roll into WS7/WS8/WS10/WS11 at implementation time.

---

*End of Phase B master plan (v2). v1 preserved at `.omni/plans/phase-b-master-plan-v1-backup.md`. Next step: user reviews §11 (≤3 open items) + confirms D1–D4 defaults, Wave 0 starts.*
