# Phase-B Wave 3.x — Re-Review (Claude code-reviewer)

## 0. Verdict

**APPROVE WITH CONDITIONS** — approve the merge of the 13 commits into `phase-b/main` conditional on fixing one HIGH-severity regression introduced by the C4 patch (subprocess failure path misclassified as "running"). Remaining findings are MEDIUM/LOW and can ship. *(Conditions since fixed in commits `15c9329` + `ee1c820` + `31f6157`.)*

## 1. Per-item verification (C1..C13)

- **C1 hermetic migration tests** (`838c8dc`) — Every test monkeypatches `Path.home()`. Thorough, correct. ✓
- **C2 `_PLUGIN_ROOT` falsy-Path** (`838c8dc`) — Explicit `if os.environ.get(...)` in 3 hook files; `OMNI_PLUGIN_ROOT` primary + `CLAUDE_PLUGIN_ROOT` legacy. 5 precedence tests. ✓
- **C3 Shell injection** (`f80677f`) — `shlex.quote()` on every tmux interpolation. Adversarial test with `$(touch /tmp/pwned-wave-3x)` asserts no sentinel created. ✓
- **C4 Tmux PID sentinel** (`f80677f`) — `_TmuxWorkerHost.launch` returns -1; dispatch uses `pid is not None`. **REGRESSION**: `_SubprocessWorkerHost.launch` still returns 0 on failure → `0 is not None` True → failed subprocess workers marked "running". Fixed post-review in `15c9329` (return None on failure).
- **C5 `shlex` ValueError → DENY** (`727bd65`) — Catches ValueError, returns `deny` with reason `malformed-shell-command`. 2 tests. ✓
- **C6 Skill catalog consistency** (`659bb8b`) — README + AGENTS.md match filesystem (29 skills). Validator check added. ✓
- **C7 Remove subtask/workspace tools** (`f5c1bc4` + `ed59024`) — Deleted handlers + registry; smoke reports 20 tools. **MEDIUM**: CHANGELOG claims `run_status` removed but still registered as UNUSED-OUTSIDE-TESTS. Fixed in `15c9329`.
- **C8 cancel/SKILL.md legacy refs** (`51312cb`) — All `.omc`/`OMC_STATE_DIR`/`CLAUDE_SESSION_ID`/`cleanup-orphans.mjs`/`TeamDelete` replaced. ✓
- **C9 measure_coverage zero-statements** (`51148d7`) — `status="unmeasured"` + `pct=0.0`; both `any_fail` checks updated. 4 tests. ✓
- **C10 release_preflight 24h + workflow filter** (`1a49666`) — Workflow=CI filter, success-only, --skip-ci-age-check flag. Logic sound. ✓
- **C11 macOS+Windows CI matrix** (`f3aa261`) — Pragmatic best-effort for non-Linux; Windows skips tmux tests. ✓
- **C12 Banner cache tree-hash** (`87a7ac0`) — Hashes `skills/*/SKILL.md` + `agents/*.md` + `mcp/server.py`; filesystem counts. Test adds new SKILL and asserts invalidation. ✓
- **C13 Dispatch-then-cancel** (`3c7118e`) — Dispatches 3 FAKE workers, verifies running, cancels, asserts all cancelled. Well-structured. ✓

## 2. Cascading regressions introduced

- **[HIGH] C4 subprocess failure misclassified as running** — see C4 above. Fixed in follow-up commit.

No other cascading regressions. The C7 test cleanup in `ed59024` correctly addressed the 4 orphaned schema-validation tests.

## 3. Style + consistency

All fixes consistent with repo conventions: stdlib-only, test-structure parity (unittest vs pytest mix is transitional), `# Cn:` comment prefixes link back to findings.

## 4. New defects

- **[HIGH]** `_SubprocessWorkerHost.launch` returns 0 on failure, breaks C4's `pid is not None` check. → Fixed.
- **[MEDIUM]** CHANGELOG `run_status` removal claim inaccurate. → Fixed.
- **[LOW]** Redundant `target` assignment in `measure_coverage.py:194`. Dead code, same value; deferred.

## 5. Deferred items verification

Patch report §"Items deferred" lists 5 Phase-C deferrals:
1. Full blocking cross-OS CI — best-effort, documented.
2. Coverage gate on macOS/Windows — Linux-only, documented.
3. `copilot-smoke` real-integration — continue-on-error.
4. `measure_coverage` PEP 668 workaround — documented.
5. Real-Copilot adversarial cancel-cascade test — Phase-C.

All 5 reasonable, properly documented. No items silently dropped.

## 6. Overall grade: B+

Disciplined remediation of 13 convergent findings with regression tests per fix, new structural validator check, consistent doc updates. C3 shell-injection + C5 shlex-DENY materially improve security. C1/C2 close real correctness bugs. Grade not A because the C4 fix introduced a regression caught only by re-review (subprocess failure path not exercised by the C4 test). The regression + CHANGELOG debt are fixed post-review.
