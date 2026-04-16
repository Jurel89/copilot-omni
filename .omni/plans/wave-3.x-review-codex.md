# Wave 3.x Re-Review (Codex)

Context reviewed:
- Branch/head: `phase-b/wave-3.x/critical-fixes` at `ed59024`
- Original REJECT review: `.omni/plans/wave-3-review-codex.md`
- Patch report: `.omni/plans/wave-3.x-patch-report.md`
- Diff base: `phase-b/main..HEAD`

Method: I re-walked each of the 13 claimed fixes against the committed code and the added regression coverage. I reviewed `HEAD` content, not the current dirty worktree file in `scripts/omni_team.py`, because the request scoped this review to the completed patch wave at `ed59024`.

## Per-fix Re-Verification

| Item | Status | Re-verification |
|---|---|---|
| C1 hermetic migration tests | FIXED | The original issue was that migration tests could touch the real home directory. Every migration test now monkeypatches `Path.home()` before calling `migrate()`, including the CLI cases, and there is an explicit adversarial guard asserting that real `~/.omc` / `~/.omni` state is unchanged (`tests/test_migrate_v1_to_v2.py:47`, `tests/test_migrate_v1_to_v2.py:53`, `tests/test_migrate_v1_to_v2.py:86`, `tests/test_migrate_v1_to_v2.py:138`, `tests/test_migrate_v1_to_v2.py:176`, `tests/test_migrate_v1_to_v2.py:197`, `tests/test_migrate_v1_to_v2.py:228`). The broader migration blast-radius concern from the original review still exists as product behavior, but the specific test-hermeticity bug is resolved. |
| C2 `_PLUGIN_ROOT` falsy-Path bug | FIXED | `session_start.py` and `user_prompt_submit.py` now use explicit truthy-env checks instead of `Path(os.environ.get(..., "")) or ...`, so `Path("") == Path('.')` no longer hijacks root resolution (`hooks/session_start.py:60`, `hooks/session_start.py:62`, `hooks/user_prompt_submit.py:76`, `hooks/user_prompt_submit.py:78`). `pre_tool_use.py` also now prefers `OMNI_PLUGIN_ROOT` over the legacy variable (`hooks/pre_tool_use.py:103`). The banner tests include precedence and empty-string fallthrough coverage (`tests/test_hooks_banner.py:243`, `tests/test_hooks_banner.py:287`, `tests/test_hooks_banner.py:295`). |
| C3 shell injection in `_TmuxWorkerHost.launch` | FIXED | The tmux launch path now shell-quotes every user-controlled interpolation, including `run_id`, `PARENT_RUN_DIR`, `skill`, `prompt`, log paths, and other arguments (`scripts/omni_team.py:365`, `scripts/omni_team.py:368`). The added regression test captures the generated command and asserts an adversarial `$(touch ...)` payload is quoted rather than executable (`tests/test_omni_team.py:741`, `tests/test_omni_team.py:785`, `tests/test_omni_team.py:792`). This addresses the original injection vector directly. |
| C4 `_TmuxWorkerHost.launch` PID sentinel | FIXED | The tmux host now returns `-1` as a success sentinel instead of `0`, the subprocess host returns `None` on failure, and the dispatch loop now keys on `pid is not None` instead of truthiness (`scripts/omni_team.py:294`, `scripts/omni_team.py:345`, `scripts/omni_team.py:382`, `scripts/omni_team.py:589`, `scripts/omni_team.py:593`). The regression test specifically checks that `-1` is treated as `running` rather than `failed` (`tests/test_omni_team.py:803`, `tests/test_omni_team.py:826`, `tests/test_omni_team.py:844`). |
| C5 `shlex ValueError -> DENY` | FIXED | The hook now immediately denies malformed shell input instead of converting it to a token list and falling through to allow (`hooks/pre_tool_use.py:145`, `hooks/pre_tool_use.py:148`, `hooks/pre_tool_use.py:153`). The new tests cover both `shell` and `bash` tool names with unterminated quotes (`tests/test_hooks.py:59`, `tests/test_hooks.py:75`). This matches the original contract and resolves the fail-open path. |
| C6 skill catalog consistency | FIXED | README and the AGENTS skill table no longer list the nonexistent `sciomni` / `learner` skills (`README.md:27`, `AGENTS.md:49`). More importantly, a validator check now compares README and AGENTS skill enumerations to the `skills/*/SKILL.md` filesystem ground truth (`scripts/verify_plugin_contract.py:1788`, `scripts/verify_plugin_contract.py:1802`, `scripts/verify_plugin_contract.py:1853`). That fixes the original skill-catalog drift finding. |
| C7 subtask + workspace MCP tools removed | PARTIAL | The code change itself is real: the `subtask` / `workspace` handlers and tool registrations are gone from `mcp/server.py`, and the file now carries an explicit removal note (`mcp/server.py:901`). That resolves the behavioral surface mismatch. However, the docs cleanup is incomplete: the top inventory table in `AGENTS.md` still says `22` MCP tools (`AGENTS.md:8`, `AGENTS.md:13`) while the later MCP section says `20` (`AGENTS.md:83`). Because the patch claim explicitly included “update doc counts 30→20,” this item is only partial. |
| C8 `cancel/SKILL.md` Node/Claude legacy cleanup | PARTIAL | The missing Node script reference appears removed, which is an improvement. But the file still contains substantial Claude-era runtime instructions: it describes deferred tools “by Claude Code” (`skills/cancel/SKILL.md:41`), still resolves `CLAUDE_PLUGIN_ROOT` as a fallback (`skills/cancel/SKILL.md:67`), still references `~/.claude` cleanup (`skills/cancel/SKILL.md:135`), and still instructs native-team detection via `${CLAUDE_CONFIG_DIR:-$HOME/.claude}` (`skills/cancel/SKILL.md:197`, `skills/cancel/SKILL.md:201`). That means the original “legacy cleanup” goal was only partially met. |
| C9 `measure_coverage` zero-statements -> unmeasured | FIXED | `parse_coverage_json()` now treats zero-statement modules as `status="unmeasured"` with `0.0%` coverage instead of a false `100.0%`, and both reporting and `--check` treat `unmeasured` as failing (`scripts/measure_coverage.py:182`, `scripts/measure_coverage.py:187`, `scripts/measure_coverage.py:224`). The new unit tests cover the no-files case, the “not 100%” regression, and the `any_fail` path (`tests/test_measure_coverage.py:73`, `tests/test_measure_coverage.py:89`, `tests/test_measure_coverage.py:100`). |
| C10 `release_preflight` 24h + workflow filter + no-neutral | NOT FIXED | The patch added workflow filtering, success-only filtering, and an age check (`scripts/release_preflight.py:138`, `scripts/release_preflight.py:156`, `scripts/release_preflight.py:173`). But it still does **not** enforce the documented “3 consecutive green runs” contract. The implementation filters all successful runs first and then takes the first three successes (`scripts/release_preflight.py:157`, `scripts/release_preflight.py:170`), which means failed completed runs between greens are ignored. The docstring says “consecutive” (`scripts/release_preflight.py:118`), but the code does not implement that rule. No regression test was added for this logic, so the release gate can still certify a bad ship. |
| C11 CI macOS + Windows matrix | FIXED | The workflow now runs `unit-tests` across `ubuntu-latest`, `macos-latest`, and `windows-latest`, with Windows-specific `not tmux` handling (`.github/workflows/ci.yml:55`, `.github/workflows/ci.yml:60`, `.github/workflows/ci.yml:65`, `.github/workflows/ci.yml:77`). The release docs and test strategy now explicitly document that macOS/Windows are best-effort rather than gating (`docs/RELEASE-v2.0.0.md:74`, `docs/TEST_STRATEGY.md:87`). The original “Ubuntu-only while docs claim cross-OS” finding is resolved. |
| C12 banner cache hashes skills + agents + `mcp/server.py` | FIXED | The banner tree hash now includes every `SKILL.md`, every `agents/*.md`, and `mcp/server.py` (`hooks/session_start.py:89`, `hooks/session_start.py:100`, `hooks/session_start.py:110`, `hooks/session_start.py:120`). Banner counts also now come from the filesystem rather than AGENTS.md regexes (`hooks/session_start.py:170`, `hooks/session_start.py:173`). The banner tests explicitly assert invalidation when a new skill is added (`tests/test_hooks_banner.py:92`, `tests/test_hooks_banner.py:104`, `tests/test_hooks_banner.py:111`). |
| C13 team integration test dispatches workers | FIXED | The integration test now dispatches workers first, verifies they are `running`, then calls `cancel_team()` and asserts each worker becomes `cancelled` (`tests/test_integration_phase_b.py:234`, `tests/test_integration_phase_b.py:289`, `tests/test_integration_phase_b.py:303`, `tests/test_integration_phase_b.py:307`). That closes the exact weakness identified in the original review. |

## Remaining Codex-REJECT-Level Issues

1. `release_preflight.py` still does not implement the ship gate it claims to enforce. The remaining bug is not cosmetic. The code says it requires three consecutive green CI runs, but it actually accepts any three recent green CI runs after filtering out failures and neutrals (`scripts/release_preflight.py:118`, `scripts/release_preflight.py:157`, `scripts/release_preflight.py:170`). That preserves the original failure mode: a failing recent CI run can be silently skipped, and the tool can still print a green release verdict. Because this script is explicitly positioned as the local release gate, I still treat this as REJECT-level.

I do **not** see a second remaining REJECT-level issue from the original 13. The other misses are real, but they are documentation / completeness issues rather than merge-blocking safety failures.

## New Bugs or Regressions Introduced by the Patch Wave

1. `tests/test_measure_coverage.py` contains a weak assertion path: it looks up `report.get("scripts/")`, but `measure_coverage.py` reports module keys as `"scripts"`, `"hooks"`, and `"mcp"` (`scripts/measure_coverage.py:44`, `tests/test_measure_coverage.py:117`). Because the test guards the assertions with `if scripts_info is not None`, that branch never runs. The core C9 fix looks correct on code inspection, but one of the new tests does not actually validate what it claims.

2. Documentation drift remains in `AGENTS.md`. The top inventory table still says `22` MCP tools (`AGENTS.md:8`, `AGENTS.md:13`), while the later MCP section and the server registry reflect the post-C7 `20`-tool surface (`AGENTS.md:83`, `mcp/server.py:901`). This is not REJECT-level by itself, but it directly contradicts the patch report’s claim that the doc counts were fully reconciled.

3. The new validator check for C6 is narrowly scoped to the skill catalog only (`scripts/verify_plugin_contract.py:1788`). It will not catch the still-wrong MCP tool count in the AGENTS inventory table. That is not a regression in product behavior, but it does mean the new “consistency” guard is materially narrower than the patch report implies.

## Verdict

**Verdict: REMAIN REJECT**

Twelve of the thirteen items are either fixed or close enough to count as substantially addressed. The exception is C10, and C10 is the one item that still directly affects release safety. A release gate that claims “three consecutive green CI runs over at least 24 hours” but actually ignores interleaved failed runs is still too weak for merge-to-main / tag-readiness.

The patch wave is therefore not a cosmetic near-miss; it still leaves one of the original REJECT grounds unresolved.

## Merge-to-Main Readiness

The 13 commits should **not** go to `main` via PR yet. A short Wave 3.y is warranted.

Required Wave 3.y scope:
- Fix C10 properly by enforcing **the last three completed `CI` runs** on `phase-b/main` are all `success`, rather than filtering to successes first.
- Add regression tests around that logic. Right now the release-gate behavior is untested.
- Finish the cleanup debt already claimed in the patch report: remove the remaining Claude-era instructions from `skills/cancel/SKILL.md` or explicitly narrow the claim, and fix the lingering `AGENTS.md` MCP tool count drift.

If those changes land cleanly, I would expect the branch to upgrade to at least **APPROVE WITH CHANGES**, and likely **APPROVE** if the release-preflight test coverage is solid.

Completion summary: Re-verified all 13 claimed fixes against `phase-b/main..ed59024`. Statuses: 9 FIXED, 3 PARTIAL, 1 NOT FIXED. The remaining merge blocker is C10: `release_preflight.py` still does not enforce three consecutive green CI runs. Secondary drift remains in `skills/cancel/SKILL.md`, `AGENTS.md`, and one new C9 regression test.


## Review Notes

I did not treat the current uncommitted `scripts/omni_team.py` worktree change as part of this verdict, and I did not re-run the full suite locally because the request was for a read-only adversarial verification of the completed patch wave. The statuses above therefore reflect code inspection plus the committed regression evidence present on the branch, with extra weight given to places where the implementation claim and the actual condition being checked still diverge.
