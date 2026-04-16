# Phase-B Wave 3 — Adversarial Critique (Critic)

## 0. Verdict

**APPROVE WITH CHANGES.** Wave 3 is structurally sound. Two items must be fixed before `phase-b/main → main`: (1) shell-injection vector in `_TmuxWorkerHost.launch`; (2) README lists 31 skill names while claiming 29 (includes deleted `sciomni` + `learner`). Plus: `measure_coverage.py` 100%/0-statements bug + kill-switch duplication across hooks.

## 1. Top 10 Problems (risk to v2.0.0)

1. **Shell injection in `_TmuxWorkerHost.launch`** — `omni_team.py:364-374` f-string interpolates `prompt` into shell command via `tmux send-keys`. `json.dumps` does NOT escape shell metachars. **Blocker.** Fix: `shlex.quote()` on every interpolation.
2. **README skill list mismatch** — lists 31 names incl. `sciomni`+`learner` (both deleted per ADR-0002), text claims 29. **Major.** `README.md:27`.
3. **`measure_coverage.py` silent 100% on 0 statements** — `measure_coverage.py:182-183` reports `pct=100.0` when `total==0`. Coverage gate becomes rubber stamp when instrumentation breaks. **Major.**
4. **Hooks duplicate kill-switch logic** — each hook has its own `_quick_disabled()` copy; `_hook_lib._hook_disabled` is dead code for kill-switch. **Major** (maintenance risk + WS7 report claim is inaccurate).
5. **Migrator touches `~/.omc/` without confirmation** — `omni_migrate_v1_to_v2.py:130-131` moves HOME state on `--apply` with no interactive warning. **Major.**
6. **`release_preflight.py` accepts "neutral" CI conclusion** — line 160. Skipped required jobs could pass preflight. **Minor.**
7. **Banner cache doesn't invalidate on skill add/delete** — `session_start.py:91-97` hashes only 3 files. New skills produce stale counts. **Minor.**
8. **`check_worktree_hygiene` passes trivially on clean CI** — zero signal unless `.omni/runs/` exists. **Minor.**
9. **`_TmuxWorkerHost.launch` returns PID=0** — `omni_team.py:378` always returns 0; caller at line 586 marks tmux workers as "failed" immediately. **Major** (tmux mode functionally broken for status tracking).
10. **Phase-C: MCP multi-process migration race deferred** — honest deferral, bounded risk. **Minor.**

## 2. Per-Workstream

- **WS6 Team.** Clean layering, thorough cancel cascade, first-class subprocess fallback. **But**: shell injection (#1), PID=0 bug (#9), `cleanup_team` doesn't kill subprocess workers, 16/18 tests mock Popen/worktree.
- **WS7 Hooks.** Comprehensive kill-switch matrix, 22 subprocess-driven tests. **But**: kill-switch duplication (#4), dead imports in Windows `_atomic_append`, banner cache gap (#7).
- **WS10 Tests.** Real coverage gate, 12 genuine integration smokes. **But**: 100%/0 bug (#3), team tests write to real `.omni/runs/`.
- **WS11 Docs.** Comprehensive CHANGELOG, clear MIGRATION. **But**: README mismatch (#2), migrator consent gap (#5), WS11 report acknowledges stale-signals pre-existing.
- **WS12 Release.** Real release-gate job, sensible preflight. **But**: "neutral" accepted (#6), largely duplicates existing matrix, `gh` undeclared dep.

## 3. Release-Gate: genuine or decorative?

Partial gate. Re-runs checks already in matrix. Unique contribution = 2 file-existence checks (CHANGELOG section, RELEASE doc). Does NOT add cross-platform, real-Copilot integration, v1.x regression, or performance checks. Honest about what it checks — sufficient for v2.0.0 given Windows-experimental posture.

## 4. Cross-WS Integration Risks

- **Team cancel × hook kill-switch:** `OMNI_SKIP_HOOKS=1` in parent shell silently disables worker audit. Undocumented.
- **Migrator × active runtime:** No check for processes reading from `.omc/`. `shutil.move` during active write = corruption.
- **Coverage × behavior coverage:** Gate gameable by misconfiguring `--source` path (real risk per WS10 report).

## 5. Acceptance-Criteria Gaming

- WS6 "18 tests" ✓ accurate.
- WS7 "+48 tests" claim — actual count 22+14+14=50, not 48 (minor discrepancy).
- WS10 "~517 tests" — honest "~".
- WS10 "exercise real production code" — partially true; Wave 2 pipeline test mocks `shutil.which`.
- `team-modes-declared`, `worktree-hygiene` — pass trivially on clean CI trees.

## 6. Hidden Technical Risks

- Shell injection in tmux host (Linux/macOS only — Windows subprocess host safe).
- `_write_json_atomic` Windows race (no retry on `os.replace` failure).
- SIGKILL-ed orchestrator = orphan tmux + subprocess workers; no watchdog.
- `_TmuxWorkerHost` can't detect crash before first `status.json` write.

## 7. Merge-to-Main Readiness

Yes, after the 2 blockers+majors. Architecture coherent, tests substantial, limitations honest. README liability must be fixed. Install instructions reference `copilot plugin install` which is assumed-but-unverified.

## 8. Tightening Recommendations

1. `omni_team.py:360-375` — shell-quote all tmux interpolations.
2. `omni_team.py:378` — return non-falsy sentinel from `_TmuxWorkerHost.launch`.
3. `omni_team.py:586` — change `"running" if pid else "failed"` to `pid is not None`.
4. `README.md:27` — drop `sciomni`, `learner`; verify count.
5. `measure_coverage.py:182-183` — when `total==0`, set `status="warn"` or `"fail"`.
6. `hooks/_hook_lib.py:179` — remove dead `import ctypes`, `import struct`.
7. `omni_migrate_v1_to_v2.py:131` — stderr warn before moving `~/.omc/`.
8. `hooks/session_start.py:91-97` — include `skills/` mtime in tree hash.
9. WS7 report — correct the claim about `_hook_disabled` usage.
10. `tests/test_integration_phase_b.py:218-232` — redirect `_OMNI_RUNS` to `tmp_path`.
11. `release_preflight.py:160` — remove `"neutral"` or document.
12. `omni_team.py:786-795` — `cleanup_team` terminate subprocess workers.

## 9. Grade: B+

Wave 3 delivers a coherent, well-documented, well-tested set of features. Tmux path has 2 bugs (injection + PID=0); README has a mismatch; coverage gate has silent-pass bug. All fixable in minutes. Subprocess fallback path is production-viable.
