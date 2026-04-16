# Phase-B Wave 2 — Adversarial Critique (Critic)

## 0. Verdict

**REVISE — DO NOT FAST-FORWARD WAVE 2 INTO `phase-b/main`.** The implementation contains at least one Critical defect (subagent.py treats SKILLS as AGENTS in autopilot Phase 2/3 and team Phase 5), one architectural defect (the WS3 stub state reader was supposed to be replaced by WS5b but wasn't, breaking autopilot resume), and several Major contract violations (validator allowlist undermines its own canonical-store guarantee; `OMNI_SUBAGENT_FAKE_*` env vars are activated by single-byte set without any production guardrail; ADR-0006's "outer skill writes cancel.signal" cascade is documented but not implemented in any place that calls inner skills).

## 1. Top 10 problems, ranked by risk-to-Phase-B-success

### 1. CRITICAL — `subagent.py` invokes skills as agents; no skill named in `agents/` will resolve

- **Workstream:** WS5b (autopilot), WS5c (ultrawork → autopilot recipe), WS5d (ralplan via autopilot)
- **Evidence:** `scripts/subagent.py:411` builds `[copilot, "-p", prompt, "--agent", agent]`. `agents/` contains 19 agents (analyst, architect, code-reviewer, code-simplifier, critic, debugger, designer, document-specialist, executor, explore, git-master, planner, qa-tester, scientist, security-reviewer, test-engineer, tracer, verifier, writer). Yet `skills/autopilot/SKILL.md:166` runs `python3 scripts/subagent.py ralplan ...` and `skills/autopilot/SKILL.md:295-300` selects `agent = "ralph" if use_ralph else "executor"`. Neither `ralplan` nor `ralph` exists in `agents/`. ADR-0006 §2 mandates "Subprocess-only invocation … via `python3 scripts/subagent.py <skill-name>`" — but the helper has no skill-vs-agent dispatcher.
- **Why it matters:** ADR-0006 composition (autopilot → ralplan → critic, autopilot → ralph) is structurally non-functional outside `OMNI_SUBAGENT_FAKE=1`. `OMNI_SUBAGENT_FAKE=1` short-circuits the copilot invocation to `python -c "...print('OK')"` — so e2e tests prove only that bash blocks run, not that the architecture is wired correctly.
- **Severity:** Blocker.
- **Minimum fix:** `subagent.py` gains a skill-vs-agent dispatcher: if name in `{"ralplan","ralph","ultrawork","ultraqa","autopilot","team"}`, build `copilot -p <prompt> /copilot-omni:<name>` instead of `--agent <name>`. Or split into `subagent.py` (agents) and `subskill.py` (skills).

### 2. CRITICAL — WS5b never replaced the WS3 stub; autopilot resume is permanently broken

- **Evidence:** `scripts/router_state.py:28-38` hard-codes `_PIPELINE_MODES_WS5 = {autopilot, ralph, ultrawork, team}` and returns `_WS5_STUB = {"status": "unknown", "reason": "WS5 not yet shipped"}` for every one of those. WS5b's report does not list a `router_state.py` change.
- `skills/autopilot/SKILL.md:62-72` reads via `router_state.py --read --mode autopilot` then `LAST_PHASE = d.get('phase', 0)`. The stub never carries `phase`, so `LAST_PHASE` is always `0`, so EVERY autopilot resume re-runs all 5 phases from scratch.
- **Severity:** Blocker (silent data loss on resume).
- **Minimum fix:** Update `router_state.py` to read MCP for `mode in {autopilot,ralph,ultrawork,team}` instead of stubbing. Update `tests/test_router_state.py` in lockstep.

### 3. MAJOR — Validator's `state-store-canonical` check is undermined by allowlisting `subagent.py` then SKILL.md recipes do raw SQL too

- **Evidence:** `scripts/verify_plugin_contract.py:1102-1110` allowlists `scripts/subagent.py` from "no direct SQL writes". But `scripts/subagent.py:163-201` does an UPSERT directly into `state` table — and every Phase-B SKILL.md (`skills/autopilot/SKILL.md:140-145, 213-218, 365`, `skills/ralplan/SKILL.md:317-348, 482-509, 597-628`) embeds inline `python3 -c "...sqlite3.connect(... INSERT INTO state ...)"`. Validator only scans `scripts/`, `hooks/`, `mcp/` for `*.py` — markdown files out of scope.
- **Severity:** Major.
- **Minimum fix:** Push inline SQL into a single `_state_write` helper on a single allowlisted file, OR scan markdown for `INSERT INTO state` patterns inside python heredocs.

### 4. MAJOR — `OMNI_SUBAGENT_FAKE` activates on any non-empty value; production-leak risk is real

- **Evidence:** `scripts/subagent.py:79-83` defines `_env_bool` truthy. Set `OMNI_SUBAGENT_FAKE=true` in `.bashrc` and forget → all autopilot/ralph runs silently fake. No banner, no warning.
- **Severity:** Major.
- **Minimum fix:** Refuse FAKE unless `PYTEST_CURRENT_TEST` env-var is also set OR add `OMNI_TEST_MODE=1` requirement.

### 5. MAJOR — ADR-0006 cancel cascade is documented but the "outer writes signal" half is missing in code

- **Evidence:** ADR-0006 §4 says outer skill creates `.omni/runs/<run-id>/cancel.signal`. Inspection: `skills/autopilot/SKILL.md` only READS cancel.signal; never WRITES it as part of cascading. Inner ralplan run-dir is `.omni/runs/ralplan-<session-id>/` (sibling, not nested). Cancel signal at `.omni/runs/autopilot-<id>/cancel.signal` will NEVER be seen by inner ralplan loop.
- **Severity:** Major.
- **Minimum fix:** Either nest run-dirs (`.omni/runs/autopilot-<id>/inner/ralplan-<id>/cancel.signal`) and update inner-skill cancel checks to walk upward, or have outer skill write cancel.signal into BOTH its own and every spawned inner run-dir.

### 6. MAJOR — `parse_critic_verdict.py` last-line-wins is brittle to LLM output; no contextual gating

- **Evidence:** `scripts/parse_critic_verdict.py:25` uses `^VERDICT:\s*(APPROVE|REVISE|REJECT)\s*$`, last match wins. No fence-stripping. A critic emitting `VERDICT: REJECT` inside a fenced code block at end of file is misread as REJECT. REJECT is TERMINAL (`skills/ralplan/SKILL.md:48`).
- **Severity:** Major.
- **Minimum fix:** Strip code fences first, OR require the verdict to be the LAST non-empty line of the file (not just match anywhere).

### 7. MAJOR — Exemption cap raised 15→25 in WS3 with no formal recovery plan; current 17/25 leaves only 8 slots for Wave 3+

- **Evidence:** `bc6e9dc` raised cap to 25. Wave 2 at 17/25. Wave 3 includes WS6 team rebuild ("highest primitive load in the tree"). With 8 slots remaining, Wave 3 will hit the cap.
- **Severity:** Major.
- **Minimum fix:** Set falling cap schedule (Wave 3 ≤22, Wave 4 ≤18, Wave 5 ≤12) tied to PR template.

### 8. MAJOR — WS3 router classifier ignores intent classification; only does concreteness scoring

- **Evidence:** Master plan §2 WS3 said router must classify into `{cancel, deep-interview, ralplan, autopilot, ralph, team, ultrawork, plan, verify, debug, wiki, remember, ship, research, ops, none}`. `scripts/router.py::classify` does ONLY concreteness scoring + binary vague/no-vague. Output dict has NO `skill`, NO `confidence`, NO `runner_up`.
- **Severity:** Major (functional regression vs. master-plan intent).
- **Minimum fix:** Either ship the missing skill classifier in WS3 follow-up before merging Wave 2, or amend master plan §2 WS3 acceptance criteria to drop skill-classification requirement.

### 9. MAJOR — Subagent pool back-pressure has fail-open hole on Windows that may silently disable cap

- **Evidence:** `scripts/subagent_pool.py:26-44` Windows uses `msvcrt.locking(fd, LK_NBLCK, 1)` (non-blocking, fails immediately if locked). `_FLOCK_AVAILABLE = False` fallback returns silently from `acquire()` (line 182-184) — if `msvcrt` import fails, cap silently goes to infinity. ADR-0010 makes Windows "best-effort" but no telemetry on whether lock succeeded.
- **Severity:** Major.
- **Minimum fix:** Add `pool.is_enforcing_cap()` boolean and log WARN when in best-effort mode.

### 10. MAJOR — Critic-verdict and clarifying-question parse paths in `ralplan/SKILL.md` are syntactically buggy

- **Evidence:** `skills/ralplan/SKILL.md:351-384` has `if python3 - <<PYEOF` then `then exit 0` — exit code semantics inverted relative to clear intent; dead variable `raw =`; coupling between bash control-flow and python heredoc never tested in real bash 5 (only via FAKE mode).
- **Severity:** Major.
- **Minimum fix:** Refactor heredoc to write a sentinel file and have bash test for file presence.

## 2. Per-workstream critique

(Detailed per-WS findings in agent output; key verdicts)
- **WS8:** `_sanitize_error` heuristic misses `KeyError: 'TOKEN_VALUE'` shape; canonical-writer guarantee defeated by allowlist.
- **WS3:** Concrete-scoring-only; intent classification missing; URL false-positive in `_RE_FILE_PATH`.
- **WS4:** Resolver fails open correctly; production `copilot models` shell path never end-to-end verified.
- **WS5a:** Wrapper script regenerated per spawn (TOCTOU smell); double-release path; Windows pid-alive check silently treats every PID as alive.
- **WS5b:** Suffers findings #1, #2, #5. Phase 2/3 architecturally broken outside FAKE mode.
- **WS5c:** Cap-enforcement test verifies spec sanity guard, NOT actual cap behavior (admitted in WS5c §9).
- **WS5d:** Findings #6 + #10. 723 lines of bash-with-embedded-python validated only via FAKE mode.

## 3. Cross-workstream integration risks

- **Router state thread to autopilot resume: BROKEN.** Finding #2.
- **WS5a pool back-pressure × WS5b/c/d parallel spawns:** No tests for "pool starvation across phases".
- **WS8 schema validator × WS5b/c/d state writes:** mode dotted pattern not regex-constrained — typo `"autopilt.ralplan"` silently passes.
- **`state` table UNIQUE constraint on `mode` only:** Two concurrent autopilot sessions COLLIDE on `mode="autopilot"` and overwrite each other's state. Master plan §1.5 row 4 added column for this — but no UNIQUE INDEX on `(mode, session_id)`.

## 4. Acceptance-criteria gaming

- **WS8:** `run_status` and `artifact_write` marked `# UNUSED-OUTSIDE-TESTS` rather than deleted — tests pin handlers, dead code paths ship.
- **WS3:** Router emits `decision="redirect|proceed|bypass"` only — not the master-plan-promised 16-class skill choice.
- **WS4:** "Fallback chain exercised" satisfied with custom callable, never via production `copilot models` shell-out.
- **WS5b:** "Claude primitives gone" test is regex-grep on SKILL.md outside fences — lazy implementer can move forbidden primitives INTO a fence to pass.
- **WS5c:** Ultrawork "cap enforcement" verifies spec sanity guard, NOT actual cap behavior.

## 5. Hidden technical risks

- **Race condition (background spawn):** Wrapper writes status="running" then runs command. If wrapper dies between os.replace and subprocess.run, status is "running" forever.
- **Atomic-write violations:** Pool's `_write_state` does seek(0)/ftruncate(0)/write under lock; if write interrupted, file is empty — silently freeing every slot.
- **Lock-file corruption on power loss:** No fsync; corrupt JSON treated as empty bucket — fail-open after crash.
- **MCP unavailability:** `_mcp_write_best_effort` falls back to direct sqlite3; if `~/.omni/omni.db` missing, write silently dropped.
- **Copilot CLI flag drift:** `subagent.py:411` builds `--agent` — Wave-0 A1 probe was supposed to validate; no check that `--agent` is the right flag.
- **Copilot `-p` quoting:** Long prompts with shell metacharacters from heredocs reach OS process table — visible in `ps -ef` to other users on shared boxes.

## 6. Merge-readiness for `phase-b/main`

Risks of fast-forwarding 45 commits:
- Finding #1 means autopilot/ralplan/ralph composition is non-functional in production. Wave 3 (WS6 team) cannot start until #1 is fixed.
- Finding #2 means autopilot resume silently re-runs all phases.
- Finding #5 means cancel cascade is broken.
- `state` table missing `UNIQUE(mode, session_id)` index → concurrent autopilot runs corrupt each other's resume state.
- Exemption budget at 17/25 starts Wave 3 with 8 slots, against WS6 alone which baseline-loads 49 banned-primitive hits.
- Validator's `state-store-canonical` check is paper guarantee — allowlisting `subagent.py` and excluding `.md` files together mean it can never fail.
- 273 tests pass in `OMNI_SUBAGENT_FAKE` mode only. No nightly real-Copilot job exists.

## 7. Tightening recommendations (15 concrete edits)

1. `scripts/subagent.py:411` — skill-vs-agent dispatcher.
2. `scripts/router_state.py:28-38` — remove WS5 stub; read real MCP state.
3. `scripts/verify_plugin_contract.py:1102-1110` — remove subagent.py allowlist OR refactor to call MCP via subprocess.
4. `scripts/verify_plugin_contract.py:1138` — extend `_STATE_SCAN_DIRS_PY` to include `skills/**/*.md`.
5. `scripts/subagent.py:79-83 + 392` — add production guard requiring `PYTEST_CURRENT_TEST`.
6. `mcp/server.py:99-103` — add `UNIQUE(mode, session_id)` on state table; schema migration v3.
7. `skills/autopilot/SKILL.md:611` and `skills/ralplan/SKILL.md:60` — unify run-dir layout (nested).
8. `scripts/parse_critic_verdict.py:30-47` — strip code fences before scanning.
9. `scripts/router.py:367-375` — extend dict with `skill: str | None` and `runner_up: str | None`.
10. `scripts/verify_plugin_contract.py:93` — schedule cap back down per wave.
11. `mcp/server.py:321-328 _SENSITIVE_RE` — add `[A-Z_]{3,}\b` (no `=`) to catch leaked uppercase tokens.
12. `scripts/category_resolver.py:114-165` — fixture-driven test for SHELL `copilot models --json` path.
13. `scripts/subagent.py:567-633` wrapper — fsync `status.json` after `os.replace`; explicit cleanup.
14. `skills/ralplan/SKILL.md:351-384` — refactor heredoc-with-shell-if into sentinel-file pattern.
15. `docs/ADR/ADR-0006-mode-composition.md:82-100` — explicitly state run-dir nesting requirement.

## 8. Overall grade: C+

Wave 2 ships impressive scaffolding: 14 KLOC of new Python, 273 passing tests, four new ADRs, four new validator checks, a working JSON-schema validator, a credible cross-process file-lock pool, a refined router classifier, and 5 SKILL.md rewrites that meaningfully reduced Claude-primitive contamination. The team executed at volume. But three structurally broken seams hide behind passing tests: (1) `subagent.py` invokes skills as agents with no dispatcher (FAKE short-circuits this); (2) WS3 stub state reader was supposed to be replaced by WS5b but wasn't (autopilot resume broken); (3) cancel cascade ADR documented but run-dir layout makes it physically impossible. Each only shows up in real production. No nightly real-Copilot job exists. Fix #1 + #2 + #5 in a 1-2 day follow-up PR before fast-forwarding `phase-b/main` and the grade rises to B+.
