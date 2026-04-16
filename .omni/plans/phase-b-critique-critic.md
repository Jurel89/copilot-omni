# Phase B Plan — Adversarial Critique (Critic)

## 0. Verdict

**APPROVE WITH CHANGES** — the plan is directionally correct and unusually rigorous for a v1→v2 rewrite, but it silently drops ~14 skills from WS2's scope, under-sizes WS5 and WS6, and relies on wave-scoped merge topology that will break CI mid-wave. Fix those three classes of issue and it ships.

---

## 1. Top 10 problems, ranked by risk-to-Phase-B success

**P1 — WS2 scope is silently narrower than the actual skill inventory.** §2.WS2 and §11.1 name ~10 deletion candidates (self-improve, visual-verdict, writer-memory, project-session-manager, deep-dive, skillify, learner, plus partial ccg/external-context/mcp-setup). Disk shows **38 skill directories**, including `sciomc`, `skill`, `hud`, `configure-notifications`, `ask`, `trace`, `release`, `debug`, `deepinit`, `remember`, `verify` — none appear in the decontamination candidate list, the ADR-0002 roster, OR the file inventory §7. Grep confirms these skills carry Claude-primitive dependencies (e.g., `skills/sciomc/SKILL.md:29` oh-my-claudecode hits, `skills/skill/SKILL.md:15` hits, `skills/configure-notifications/SKILL.md:25` forbidden-primitive hits). **Minimum fix:** §7 WS2 must list every surviving `skills/<name>/SKILL.md` to be MODIFIED and re-enumerate the DELETE roster against the real 38-skill tree. Without this, WS2 will stall on discovery mid-Wave 1.

**P2 — WS5 is sized "XL" with no lower bound and no decomposition.** §2.WS5 rewrites five flagship skills (autopilot, ralph, ultrawork, ultraqa, ralplan) on top of a `scripts/subagent.py` that is currently 65 lines and must grow a background mode, a run-directory writer, a job-status protocol, category resolution, and wait barriers — AND then become the spine for every tier-0 skill AND WS6's team orchestrator AND the e2e test. Wave 2 budgets 7–10 days for WS3+WS4+WS8+WS5 combined. That is unrealistic; WS5 alone is likely 7–10 days of a senior engineer. **Minimum fix:** split WS5 into WS5a (`subagent.py` primitive upgrade + `wait_for_jobs.py`), WS5b (autopilot/ralph only), WS5c (ultrawork/ultraqa), WS5d (ralplan). Each becomes a PR, the wave-2 budget doubles, and the dependency on `subagent.py` ships before any skill depends on it.

**P3 — Wave merge topology will silently break CI.** §5 says "every PR must pass `scripts/verify_plugin_contract.py --all` (grows with each WS)" AND "every PR must pass `pytest -q` on Linux." But WS2 deletes skills that other workstreams still reference in their intermediate states; WS3 rewrites `hooks/user_prompt_submit.py` that WS7 also rewrites ("now thin wrapper over router" — §7 WS7). Two WSes editing the same file in the same wave = merge conflict. **Minimum fix:** explicit file-ownership table per wave; forbid two WSes from modifying the same file in the same wave, or serialize them.

**P4 — The rename verification is vulnerable to a hole.** §2.WS1 acceptance criteria greps only in `skills/ agents/ scripts/ hooks/ commands/ docs/ tests/`. It omits `.github/`, `templates/`, `.claude-plugin/`, `.mcp.json`, root-level `CHANGELOG.md`, and `plugin.json`. A lazy implementer passes CI with residual `.omc/` in `.github/workflows/ci.yml` or `plugin.json`. **Minimum fix:** strip the directory list; grep the whole tree with an explicit allowlist.

**P5 — WS3's vagueness-gate threshold is completely undefined.** §2.WS3 says "concreteness score < threshold" and "thresholds live in `.omni/config.json` under `router.vagueness_threshold` (default 0.4)". Nothing in the plan explains what signals score what weights, how a prompt accumulates a score, or what the test table calibrates against. The 40-prompt regression table becomes the implicit spec — and whoever writes the table owns the router semantics. **Minimum fix:** ADR-0005 (listed in §7 WS3 DELIVERABLES) must codify the scoring rubric BEFORE the 40-prompt table is authored, not after.

**P6 — Rollback plan hand-waves the hardest case.** §8 covers branch-level and tag-level rollback but says nothing about **partial wave rollback**. If WS8's schema migration (v1→v2 with `ALTER TABLE ADD COLUMN session_id` — §2.WS8 Risks) ships and then Wave 2 is reverted, user machines that ran migration now have a `session_id` column the code no longer writes. §8 lists `scripts/mcp_schema_downgrade.py` as "unsupported rescue" — that's a v2.0.0 release running unsupported rescue scripts on day one. **Minimum fix:** MCP schema migration must be additive-only AND backward-readable by v1 code for the duration of Phase B; the ALTER runs only at the Wave 5 → `main` merge.

**P7 — Success signals in §9 are gameable.** "`grep -rE '(\.omc/|oh-my-claudecode|Task\(|Skill\(|AskUserQuestion|TeamCreate|SendMessage|state_list_active)' skills/ agents/ scripts/ hooks/ commands/ docs/` returns 0 hits" — this passes if someone replaces `Task(` with `task(` or uses backticks `` `Task()` `` (the regex requires the open paren). It also passes if an implementer moves Claude-primitive references into comments. **Minimum fix:** validator must parse, not grep; or the regex must ignore case and match in code contexts only, not in prose sections.

**P8 — Team orchestrator's tmux fallback is a half-design.** §2.WS6 Risks says "fall back to plain `subprocess.Popen` + per-worker log file when `shutil.which("tmux")` is None." That means two code paths, two state-machine implementations, two cancel protocols — and on Windows the degraded mode becomes the primary mode. But the acceptance criteria in §2.WS6 only exercise the tmux path. **Minimum fix:** `tests/test_team.py` must cover the non-tmux path as the FIRST test, not the fallback.

**P9 — Category resolver does not address per-agent model pinning.** §2.WS4 says "every surviving skill and agent to reference categories, not concrete model names." But SYNTHESIS §10 P2 #7 cites OMOA's design where each *agent* has a `fallback_models` chain AND a category. The plan collapses to categories-only and silently loses the fallback chain. **Minimum fix:** `.omni/config.json` schema must support per-agent override AND a fallback chain per category; otherwise a subscription-menu disappearance of a single model means the agent hard-fails instead of degrading.

**P10 — "Realist check" of the adversarial review gate in §6.3 is self-referential.** §6 says "at each wave exit, run three review agents in parallel via `scripts/subagent.py`" — but WS5 is what *makes* `scripts/subagent.py` capable of parallel invocation. Wave 1's adversarial review cannot actually use the mechanism it's supposed to validate. **Minimum fix:** Wave 0 and Wave 1 adversarial reviews are manual (human + copilot CLI, one at a time); Wave 2+ use the parallel mechanism. State this explicitly.

---

## 2. Per-workstream critique (WS1..WS12)

**WS1 (Rename).** Solid mechanical work. The 189/292 grep counts match the current repo exactly (verified). Risk: §2.WS1 omits root-level files (`CHANGELOG.md`, `plugin.json`, `.github/`) from its acceptance-criteria grep scope — see P4. The `omni-rename-allow` inline marker is a good escape hatch; no note on how to allowlist these without widening the blast radius. Size M is plausible.

**WS2 (Decontamination).** Under-scoped by ~14 skills (P1 above). The "Claude primitive in prose only" exemption marker (`<!-- claude-ref: prose-only -->`) is a good mechanism but no budget is given for how many exemptions are acceptable — a lazy implementer marks everything. Acceptance criteria need a ceiling ("≤ 5 files with prose-only markers"). Size L is plausible IF the deletion list is honest; unbounded if not.

**WS3 (Router).** The strongest-designed workstream in the plan. R1–R6 shape is clear. But (a) scoring rubric is unspecified (P5), (b) the `!` bypass prefix vs. bash history expansion is waved away by offering `--skip-interview` as an "alternative" — that is not a solution, it's a second syntax. Also: no mention of how `router.py` interacts with the hook timeout (5s per §2.WS7's implicit reference); if the classifier grows and crosses 5s, hooks become flaky. Size L is correct but tight.

**WS4 (Models).** The plan does not include `omni-doctor` actually checking Copilot's subscription menu against the config — §2.WS4 says "best-effort check by running `copilot models` if available, else no-op", but there is no mapping between that output and the category table, so `omni doctor` can report "healthy" while the config references a model Copilot dropped. Size M is optimistic; category refactor hits every skill and agent file.

**WS5 (Pipeline).** See P2 — too large and undecomposed. Also: the e2e test `tests/test_pipeline_e2e.py` is gated behind `pytest -m e2e` with a mock-copilot. But a mock copilot cannot verify that Copilot CLI's `-p` mode actually behaves as assumed (subprocess semantics, stdout flushing, model-flag acceptance). The "nightly real-Copilot job" is named once and never specified — no CI infra for nightly jobs is declared in WS12 (§2.WS12 only mentions `(nightly only) pytest -m e2e` with no scheduler config).

**WS6 (Team).** Size XL is defensible; tmux + worktrees + state machine + handoff docs + cancel semantics is a real 5–7 day job for one person. But "team composes with ralph" in the acceptance criteria is asserted without specifying the composition protocol — how does `--ralph` flag cross the orchestrator/worker boundary? Where does ralph's state slot live relative to team's? Undefined. The Windows story ("team mode requires WSL on Windows") silently walks away from the WS7/WS12 cross-platform promises — this should be a locked decision, not a buried mitigation.

**WS7 (Hooks).** The kill-switch retrofit is good. The `fcntl.flock` POSIX path + per-pid logfile Windows path is the right trade-off. But the banner's "computed at install time and cached in `.omni/cache/banner.json`" creates a cache-invalidation problem: when a new skill lands, does the cache refresh? §2.WS7 does not say. Deprecation aliases for `OMC_SKIP_HOOKS` / `DISABLE_OMC` are fine, but neither the deprecation timeline nor the removal milestone is named. Size L is correct.

**WS8 (MCP).** The stdlib-only JSON Schema validator at ~120 LOC is a YAGNI trap — it will accumulate edge cases across the 30 tools. Plan should acknowledge this and either (a) restrict the subset used across all tool schemas to a known-tiny grammar upfront, or (b) concede and ship a vendored single-file validator. The schema migration path is forward-only (P6) which is a quiet bug waiting for a wave-revert.

**WS9 (Validator).** Sound design. The per-file `<!-- omni-contract-exempt: <reason> -->` escape hatch needs a budget (see WS2). `--check-references` can only assert that command/tool names exist as files — not that they are actually wired through. Mechanical, not semantic. Plan should say so explicitly so reviewers don't over-trust a green validator.

**WS10 (Tests).** "Coverage ≥70% line coverage in `mcp/server.py`" against a 1219-line file with 30 MCP tools is a real 3–5 day engineering job that the plan rolls into Wave 5 alongside docs and release. That's overloaded.

**WS11 (Docs).** Cross-cuts everything. Size M is unrealistic if WS11 waits until Wave 5 — by that point it's rewriting 9 major docs + 6 ADRs + the CHANGELOG with no sequencing plan. Splitting doc work into "land with the PR that owns each change" (§2.WS11 mitigation) is the right principle but not operationalized: no WS1/WS3/WS5/WS6 PR lists the doc file it must update.

**WS12 (CI/release).** CI matrix is reasonable but Windows Python 3.9 + `fcntl` conditional + tmux-absent path = a matrix cell that is structurally different, and "tolerate `pytest -m e2e` being Linux-only" hides a real gap: e2e on Windows is untested ever. Tagging v2.0.0 with untested Windows e2e is the single most likely cause of a post-release regression. Plan should commit to ≥1 real Copilot CLI smoke on Windows before tag, manually if needed.

---

## 3. Wave partitioning — does it actually work?

**Wave 1: WS1 + WS2 + WS9 in parallel.** Breaks. WS2 edits every surviving SKILL.md body; WS1 edits every `.omc/` reference in those same SKILL.md bodies. Two concurrent branches with overlapping file sets on 37+ files → merge conflict on every skill. The plan notes "WS9 needs WS1's rename targets" but ignores that WS2 also needs WS1 complete. **Fix:** WS1 finishes first; WS2 + WS9 run parallel after WS1 merges.

**Wave 2: WS3 + WS4 + WS8 in parallel, then WS5.** Partially works. WS3 and WS7 (later wave) both edit `hooks/user_prompt_submit.py` — but within Wave 2, WS3 does not touch WS4 or WS8 files, so parallel is safe there. But WS4 edits "every skill and agent referencing raw model names" (§7 WS4) — that overlaps heavily with skills WS3 is also modifying to consume the router decision. **Fix:** WS4 updates skill frontmatter only (category field); skill body changes wait for WS5.

**Wave 4: WS7 + remaining WS8 in parallel.** Works — they touch disjoint files.

**Wave 5: WS10 + WS11 parallel, WS12 last.** Works, but WS11 depends on counts that WS10 computes, so ordering within the wave matters. Plan is silent.

---

## 4. Acceptance-criteria gaming (one gameable check per WS, with tightening)

- **WS1:** Grep passes if stale refs are in `CHANGELOG.md` or `plugin.json` (not in the scoped dirs). Tighten: grep whole tree; explicit allowlist.
- **WS2:** "0 occurrences of banned tokens" passes if tokens are moved into markdown code fences or exemption-marked. Tighten: exemption budget ≤ 5 files; validator reports exemption count.
- **WS3:** "`tests/test_router.py` passes 100%" passes if the table only has easy cases. Tighten: require ≥8 adversarial/near-threshold prompts in the table.
- **WS4:** "0 hits of `haiku|sonnet|opus` outside `docs/MODELS.md`" passes if names are split (`'hai' + 'ku'`). Tighten: AST-level (or at least a character-class) validator, not a word-regex.
- **WS5:** "completes without Task()/Skill() references (asserted by log scan)" passes if the skill just doesn't log. Tighten: require positive evidence in logs (spec file written, plan file written, code diff produced).
- **WS6:** "Cancellation leaves no orphan worktrees" passes trivially if no worktrees are created in the smoke. Tighten: assert 3 worktrees ARE created, THEN cancel, THEN 0.
- **WS7:** Kill-switch test passes if only ONE hook is checked. Tighten: all four hooks in one test.
- **WS8:** "schema-validation tests" pass with one bad-input case. Tighten: table of ≥10 bad inputs spanning types, required, enum, additionalProperties.
- **WS9:** "`--all` exits 0 on a clean tree" is tautological. Tighten: add a "break one thing, confirm exit non-zero with correct file:line" regression test.
- **WS10:** "coverage ≥70%" passes with tests that exercise lines without asserting behavior. Tighten: mutation testing or explicit assertion count per module.
- **WS11:** "All doc counts match reality" passes if counts are auto-generated and nobody reads the prose. Tighten: manual read-through in UAT (§6 WS11 does this — good; enforce).
- **WS12:** "CI green on main at tag time" passes the moment CI turns green. Tighten: require 3 consecutive green runs on main over ≥24h before tag.

---

## 5. Hidden risks the plan ignores

1. **Plugin marketplace metadata drift.** `plugin.json` and `.claude-plugin/plugin.json` are both listed in §7 WS1 MODIFY but there is no discussion of distribution — if this plugin is published via Claude Code's marketplace OR Copilot's plugin system, the rename breaks existing install commands for current users. Migration to v2 for existing installs is unaddressed.
2. **Copilot CLI flag drift.** The plan assumes `copilot -p <prompt> --model <x> --agent <y>` is stable. Copilot CLI has changed flags within minor versions. `scripts/subagent.py` depends on this; no compatibility layer is proposed.
3. **MCP schema version pinning.** `mcp/server.py` increments `schema_version` from 1→2 (§2.WS8). If users roll between versions, the DB becomes unusable. No compatibility matrix.
4. **SQLite lock contention under real parallel load.** Plan mentions "5-way concurrent state_write stress" — SQLite WAL mode + parallel writers across processes (`subagent.py &` spawns) will hit lock contention quickly. A 5-writer test proves nothing; real team scenarios can spin 10+ writers.
5. **User-machine variance.** tmux versions across corporate laptops vary wildly (2.6 on RHEL 7, 3.3a on Ubuntu 22, MinTTY on Windows). Plan commits to tmux but only tests one version.
6. **`CLAUDE.md` deletion breaks Claude-Code-as-fallback.** §11.3 defaults to deleting `CLAUDE.md`. Anyone running this plugin in Claude Code (still possible per locked decision "coexistence is a non-goal" — that's a non-goal, not a block) loses entry-point metadata.
7. **No regression budget.** Plan has no guidance on "how many rejections per PR is acceptable" or "what happens when wave-exit adversarial review blocks twice." Unbounded rework risk.
8. **`scripts/launch_python.py` cold-start cost.** Every hook invocation adds a Python-bootstrap Python shim in front of Python — that's 2x interpreter startup on Windows. Hooks already have 5–10s budgets (§2.WS7); this eats into it.

---

## 6. Open items the plan should have surfaced but didn't

The §11 three items (skill deletion list, bypass syntax, `CLAUDE.md` fate) are small forks. The following are bigger:

1. **Does Phase B keep Claude Code installable-but-degraded, or hard-block?** §1 says "coexistence is a non-goal" but the plan keeps `CLAUDE_PLUGIN_ROOT` as fallback (§2.WS7). Pick a side.
2. **Is `.omni/config.json` user-editable or harness-managed?** Category overrides, router thresholds, team root, hook timeouts — all land there. If users edit it freely, future plugin upgrades break on config-schema drift. Needs a config-versioning ADR.
3. **Should `subagent.py` grow a queue / back-pressure mechanism for ultrawork?** Plan says "background spawns + wait barrier" but on a single laptop with 8 workers × Copilot CLI each eating ~500MB, OOM is real. Not addressed.
4. **Telemetry absolutism.** §10 says "no outbound network call from the plugin." But `omni doctor` running `copilot models` IS an outbound call from Copilot CLI, which users may have blocked by corp policy. Plan should distinguish plugin-initiated vs. Copilot-initiated network.
5. **Test artifact lifetime.** `.omni/runs/<run-id>/` is created by ultrawork/ralph. Who deletes these? Unbounded disk growth.
6. **deep-interview's `AskUserQuestion` replacement.** §1.8 defers deep-interview redesign to Phase C. But §2.WS5 ralplan says "interactive mode falls through to the router's bypass/confirm pattern (the skill asks the user a question in chat; the model emits it as plain text, the user answers, the skill continues)." That is a significant UX claim that Phase B must validate — will Copilot CLI's `-p` mode wait for user input mid-prompt? Usually no. Unverified assumption.
7. **The `/omni-next` skill has a dependency inversion.** §2.WS3 says `/omni-next` "reads MCP state + on-disk artifacts to pick the next action." But `omni-next` lives in `commands/`, not `skills/`, and command docs are markdown consumed by the LLM — not executable. How does a command doc "read MCP state"? Through the LLM. Then the "deterministic" claim is hollow.

---

## 7. Specific tightening recommendations (15+ concrete edits)

1. **§2.WS1 acceptance criteria:** change `grep -r '\.omc/' skills/ agents/ scripts/ hooks/ commands/ docs/ tests/` to a whole-tree grep with an `ALLOWLISTED_PATHS` array in `verify_plugin_contract.py`, and include `CHANGELOG.md`, `plugin.json`, `.claude-plugin/**`, `.github/**`, `.mcp.json`.
2. **§2.WS2 deliverables:** enumerate all 38 skills under `skills/` by name and tag each as KEEP-REWRITE / DELETE / DEFER before Wave 1 starts. Do not leave this to "final list decided during WS2 execution" (§7 WS2).
3. **§2.WS3 R1 scoring rubric:** ADR-0005 must specify exact signal weights (e.g., file-path match = +0.3, code block = +0.4, issue # = +0.2, …) BEFORE `tests/test_router.py` is written.
4. **§2.WS3 bypass syntax:** remove `!` prefix OR document that it is posix-sh-only; make `--skip-interview` the only cross-shell option.
5. **§2.WS4 config schema:** define `.omni/config.json` category entries as `{model: str, fallbacks: [str]}` not flat strings; add ADR-0003 test that `omni doctor` exercises fallback.
6. **§2.WS5 split:** decompose into 5a (subagent primitive), 5b (autopilot+ralph), 5c (ultrawork+ultraqa), 5d (ralplan). Size each M, not a single XL.
7. **§2.WS5 e2e:** the "real Copilot CLI nightly" must be explicitly wired in `.github/workflows/ci.yml` (§7 WS12) with a named job and a scheduler config.
8. **§2.WS6 fallback test:** `tests/test_team.py` must exercise the non-tmux path as a first-class smoke test, not a gated `pytest -m team-e2e`.
9. **§2.WS7 deprecation timeline:** name a removal version for `OMC_SKIP_HOOKS`/`DISABLE_OMC` aliases (e.g., "removed in v3.0.0"); document in `docs/HOOK_CONTRACT.md`.
10. **§2.WS8 migration:** mandate additive-only schema migrations through Phase B; forbid column renames/drops until v2.0.0 is cut.
11. **§5 PR rules:** add a file-ownership manifest per wave (a `wave-N-ownership.yaml`) that enforces no two WSes in the same wave edit the same file.
12. **§6 adversarial review:** explicitly state Wave 0 and Wave 1 adversarial reviews run manually (since `subagent.py` parallel mode ships in Wave 2); Wave 2+ use parallel.
13. **§8 rollback:** define a "partial wave revert" procedure for cases where WS8's MCP schema has already shipped but Wave 2 reverts.
14. **§9 success signals:** change the banned-token grep to use a parsing pass (strip code fences first, then grep), and add a CONTEXT check (prose-only markers allowed, in-code uses not).
15. **§9 coverage signal:** split the ≥70% coverage target per-module (`mcp/server.py` ≥80%, `hooks/` ≥70%, `scripts/` ≥60%) so a single easy-to-cover file doesn't prop up the aggregate.
16. **§11 additions:** add open items for (a) plugin-distribution migration, (b) `.omni/config.json` versioning, (c) deep-interview interactive-mode feasibility on Copilot CLI `-p`.
17. **§12 P2 #8 Read-only reviewer enforcement:** the plan assigns this to "WS2 (frontmatter `writable: false`)" — but §2.WS2 does not mention `writable: false` at all. Either add to WS2 deliverables or reassign.
18. **§7 WS6:** add `scripts/omni_team.py` to WS10 test inventory explicitly — currently no test module is named for it beyond `tests/test_team.py`.
19. **§9 signal "session banner reports correct counts":** hard-code the expected counts OR say they are dynamic; the current "37 skills or revised, 19 agents or revised, 30 MCP tools or revised" is weasel wording that a lazy implementer games by reporting whatever ships.
20. **§2.WS11:** require that each WS's PR touches `CHANGELOG.md` with one line AND `docs/MIGRATION.md` if breaking. Currently only CHANGELOG is mentioned (§5).

---

## 8. Overall grade and rationale

**Grade: B.**

This is a serious, structured, cited plan — far above the median for v1→v2 rewrites in my experience, and the ralplan consensus shape shows through (acceptance criteria are mostly measurable, risks are mostly mitigated, dependency DAG is coherent). The synthesis-to-workstream mapping in §12 is unusually complete; the author clearly traced every P0/P1/P2 and most Critical/High bugs to an owner. What drops it from A is a trio of avoidable weaknesses: (1) WS2's deletion list is silently under-specified against the 38-skill inventory on disk — my grep found ~14 skills with oh-my-claudecode / Claude-primitive contamination that are not mentioned in the plan; (2) WS5 is sized XL with no decomposition and no honest time estimate, when the dependent `subagent.py` is 65 lines of today that needs to grow into the spine of five flagship skills; (3) the wave-based merge topology ignores cross-WS file ownership and will produce avoidable merge conflicts in Wave 1 and Wave 2. Fix those three, enforce the scoring rubric and validator tightening in §7 above, and this plan ships a believable v2.0.0.
