# Wave 3 Adversarial Review (Codex)

Context reviewed:
- Reports: `.omni/plans/wave-3-WS6-report.md`, `.omni/plans/wave-3-WS7-report.md`, `.omni/plans/wave-3-WS10-report.md`, `.omni/plans/wave-3-WS11-report.md`, `.omni/plans/wave-3-WS12-report.md`
- Plan sections: `.omni/plans/phase-b-master-plan.md` for `WS6`, `WS7`, `WS10`, `WS11`, `WS12`
- Actual code/docs/tests in `git diff 61e4c6a..HEAD`

Verdict: Wave 3 is not merge-ready for `main` and not tag-ready for `v2.0.0`. The code moved the project forward, but several release-facing claims are materially stronger than what the code actually guarantees. The most serious problem is not stylistic drift; it is unsafe migration/testing behavior combined with a weak release gate that can certify a bad ship.

## 1. Top 10 Problems Ranked by Risk to v2.0.0 Merge

1. **The new migration tests can touch the real user home directory.** `migrate()` always processes both `<repo>/.omc` and `~/.omc` via `_locations()` (`scripts/omni_migrate_v1_to_v2.py:122`). The tests call `migrate(tmp_path, dry_run=False)` without monkeypatching `Path.home()` or otherwise isolating the home target (`tests/test_migrate_v1_to_v2.py:28`, `tests/test_migrate_v1_to_v2.py:83`, `tests/test_migrate_v1_to_v2.py:125`, `tests/test_migrate_v1_to_v2.py:191`). On any machine that actually has `~/.omc`, these tests can move real user state. That directly violates the Phase-B hermetic rule (`.omni/plans/phase-b-master-plan.md:495`) and makes the test suite unsafe.

2. **Hook/plugin-root resolution is wrong when the env var is absent.** Both `session_start.py` and `user_prompt_submit.py` do `Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "")) or Path(__file__).resolve().parent.parent` (`hooks/session_start.py:60`, `hooks/session_start.py:61`, `hooks/user_prompt_submit.py:76`). `Path("")` is `.` and is truthy, so the fallback never triggers. In practice these hooks silently bind plugin root to the current working directory, not the plugin directory. That corrupts banner counts, trigger discovery, and any root-relative file access whenever the hook is launched from a different cwd.

3. **`release_preflight.py` does not enforce the release gate described in the plan or release docs.** The plan requires “3 consecutive green runs on `phase-b/main` over >=24h” before merge/tag (`.omni/plans/phase-b-master-plan.md:562`). The release doc tells users to rely on `python3 scripts/release_preflight.py` (`docs/RELEASE-v2.0.0.md:85`, `docs/RELEASE-v2.0.0.md:86`). The script does not check time span, does not verify workflow identity, does not verify `release-gate`, and does not run `mcp-smoke`, `discovery-smoke`, or coverage locally; it just checks branch, cleanliness, validator, pytest, doc existence, and a generic `gh run list --limit 3` summary (`scripts/release_preflight.py:181`). This is the definition of a dishonest ship gate.

4. **The actual CI posture is Ubuntu-only, not cross-OS as planned.** WS12 committed to Linux/macOS/Windows across Python 3.9-3.12 (`.omni/plans/phase-b-master-plan.md:551`). The real workflow runs every job on `ubuntu-latest` (`.github/workflows/ci.yml:12`, `.github/workflows/ci.yml:57`, `.github/workflows/ci.yml:74`, `.github/workflows/ci.yml:85`, `.github/workflows/ci.yml:98`, `.github/workflows/ci.yml:118`, `.github/workflows/ci.yml:132`). That means macOS/Windows claims in docs and release notes are not backed by CI evidence.

5. **The migrator’s blast radius is too large for a default “safe” release tool.** The script always targets both project state and global user state (`scripts/omni_migrate_v1_to_v2.py:129`). It performs direct moves, has no backup, no merge strategy, no logging, and treats “destination exists” as a warning/skip (`scripts/omni_migrate_v1_to_v2.py:79`). That leaves users in split-brain states (`~/.omc` plus `~/.omni`) with no remediation. It also uses `git mv` for repo state (`scripts/omni_migrate_v1_to_v2.py:45`), which means it can fail on dirty repos and modify tracked files as a side effect of “migration.” The docs call this “safe, idempotent” (`CHANGELOG.md:23`, `docs/MIGRATION.md:33`), but the safety story is incomplete.

6. **WS7’s shlex hardening still fails open instead of denying malformed shell commands.** The plan explicitly required `ValueError -> DENY` (`.omni/plans/phase-b-master-plan.md:369`). The implementation catches `ValueError` and turns the whole malformed command into one opaque token (`hooks/pre_tool_use.py:144`). If the malformed command does not match a configured deny substring, the hook falls through to `allow` (`hooks/pre_tool_use.py:229`). That is better than `.split()`, but it is still not the contract the plan committed to.

7. **Banner/cache behavior does not match the documented invalidation contract and can drift silently.** The plan required cache invalidation against `skills/`, `agents/`, and `mcp/server.py::TOOLS` (`.omni/plans/phase-b-master-plan.md:379`). The implementation hashes only `.claude-plugin/plugin.json`, `AGENTS.md`, and `hooks/hooks.json` (`hooks/session_start.py:91`). A skill add/remove, trigger change, or tool-surface change can leave the banner stale. On top of that, agent count is inferred by regexing `##` headings in `AGENTS.md` (`hooks/session_start.py:145`), which is not a source of truth.

8. **WS11 docs have material truthiness problems, not minor count drift.** README claims 29 skills but lists non-existent `sciomni` and `learner` (`README.md:27`), while those directories do not exist. AGENTS repeats `sciomni` (`AGENTS.md:70`). CHANGELOG and release docs claim `subtask`/`workspace` are removed, but they are still registered MCP tools (`CHANGELOG.md:16`, `docs/RELEASE-v2.0.0.md:24`, `mcp/server.py:943`, `mcp/server.py:955`). This is release-note drift on user-visible compatibility surface.

9. **The `cancel` skill still contains dead, legacy, off-contract instructions.** It references Claude-native team config under `~/.claude`, uses `${CLAUDE_PLUGIN_ROOT}`, and invokes a missing Node script `scripts/cleanup-orphans.mjs` (`skills/cancel/SKILL.md:203`, `skills/cancel/SKILL.md:240`). That directly conflicts with the repo contract of “pure Markdown + Python stdlib” and “no npm beyond the CLI” (`AGENTS.md:3`). It also means Wave 3 shipped with an apparently rewritten skill that still points users at non-existent runtime.

10. **The new integration coverage overstates what is actually tested.** The WS10 report says Wave 3 integration asserts team orchestration and cancel cascade (`.omni/plans/wave-3-WS10-report.md:45`). The actual team smoke creates a run and immediately calls `cancel_team()` without dispatching workers (`tests/test_integration_phase_b.py:197`, `tests/test_integration_phase_b.py:216`). That does not validate live worker cancellation, process teardown, or worktree cleanup under dispatch. The test passes on a much weaker invariant than the report suggests.

## 2. Per-Workstream Critique

### WS6 — Team rebuild

The orchestrator itself is serviceable, but the delivered shape drifted from the plan. The plan promised a staged state machine, handoff docs, first-class subprocess fallback, and cancellation leaving zero orphan worktrees (`.omni/plans/phase-b-master-plan.md:338`, `.omni/plans/phase-b-master-plan.md:345`, `.omni/plans/phase-b-master-plan.md:350`). The current file is a simpler run-dir orchestrator under `.omni/runs/team-*` (`scripts/omni_team.py:7`) rather than the plan’s `.omni/teams/<slug>/...` layout (`.omni/plans/phase-b-master-plan.md:335`). That simplification is fine if explicitly re-scoped, but the docs/reports still speak in larger-contract language.

The bigger issue is evidence: the integration smoke does not dispatch workers before asserting cancel cascade (`tests/test_integration_phase_b.py:197`), and the cancel skill still contains dead Claude/Node-era instructions (`skills/cancel/SKILL.md:203`, `skills/cancel/SKILL.md:240`). So the runtime may be viable, but the user-facing contract around it is not stable.

### WS7 — Hook hardening

This is the strongest Wave 3 engineering area conceptually, but it still has two critical contract misses. First, the env-var migration is incomplete: the hooks still key off `CLAUDE_PLUGIN_ROOT` instead of the plan’s “Copilot first, Claude fallback” requirement (`.omni/plans/phase-b-master-plan.md:370`, `hooks/session_start.py:60`, `hooks/user_prompt_submit.py:76`, `hooks/pre_tool_use.py:103`). Second, malformed shell commands are no longer `.split()`-vulnerable, but they still fall through to allow instead of deny (`hooks/pre_tool_use.py:144`, `hooks/pre_tool_use.py:229`).

The banner/cache path also under-delivers relative to the plan: it hashes too little and derives counts from docs instead of source-of-truth registries (`hooks/session_start.py:84`, `.omni/plans/phase-b-master-plan.md:379`). This will create exactly the sort of stale-banner drift the workstream was supposed to eliminate.

### WS10 — Test strategy

The project gained useful tests, but the test strategy is not yet trustworthy as a release argument. The biggest miss is hermeticity: the plan required test isolation via temp `OMNI_HOME` and a clean repo after full run (`.omni/plans/phase-b-master-plan.md:495`, `.omni/plans/phase-b-master-plan.md:500`), yet the migration tests can operate on the real home directory (`tests/test_migrate_v1_to_v2.py:28`, `scripts/omni_migrate_v1_to_v2.py:129`). That is a serious regression in test safety.

The second miss is behavioral undercoverage disguised as smoke coverage. Team cancellation is asserted without worker dispatch (`tests/test_integration_phase_b.py:197`), and there is no real cross-OS lane despite the docs presenting a release-grade matrix (`docs/TEST_STRATEGY.md:76`, `.github/workflows/ci.yml:55`). The coverage harness is acceptable, but the surrounding narrative is ahead of the actual evidence.

### WS11 — Docs and migration

WS11 is currently the least trustworthy workstream. README and AGENTS advertise skills that do not exist (`README.md:27`, `AGENTS.md:70`), CHANGELOG claims MCP removals that did not happen (`CHANGELOG.md:16`, `mcp/server.py:810`, `mcp/server.py:943`, `mcp/server.py:955`), and MIGRATION/RELEASE present the migrator as safer and more deterministic than it is (`docs/MIGRATION.md:33`, `docs/RELEASE-v2.0.0.md:17`).

A release with this level of documentation drift will create operator confusion even if the code is mostly correct. The docs are currently not suitable as the canonical source for upgrade guidance.

### WS12 — Release prep

This workstream did not meet its own acceptance bar. The plan required a Linux/macOS/Windows matrix plus named nightly/weekly real-Copilot jobs and a 3-green-runs-over-24h gate (`.omni/plans/phase-b-master-plan.md:551`, `.omni/plans/phase-b-master-plan.md:557`, `.omni/plans/phase-b-master-plan.md:562`). The actual workflow is Ubuntu-only, has no nightly or weekly real-Copilot job, and the local preflight approximates history via generic `gh run list` without enforcing age or workflow identity (`.github/workflows/ci.yml:1`, `.github/workflows/ci.yml:96`, `scripts/release_preflight.py:112`).

This is the clearest architectural drift in the wave: the release process described in docs is stronger than the release process encoded in automation.

## 3. Cross-OS Portability Honest Assessment

Linux: plausible for normal use.

macOS: plausible, but not proven in CI. The Unicode path-normalization issue was explicitly deferred (`.omni/plans/wave-3-WS7-report.md:121`), and none of the Wave 3 automation verifies macOS-specific behavior.

Windows: not release-grade. The plan treated Windows as explicitly risky (`.omni/plans/phase-b-master-plan.md:346`, `.omni/plans/phase-b-master-plan.md:352`), but the actual CI never runs there (`.github/workflows/ci.yml:12`). Hooks still use legacy `CLAUDE_PLUGIN_ROOT` reads (`hooks/pre_tool_use.py:103`, `hooks/session_start.py:60`), and `skills/cancel/SKILL.md` still references a missing Node helper (`skills/cancel/SKILL.md:240`). The tests also skip permission semantics on Windows (`tests/test_hooks_banner.py:207`).

Net: the repo currently has Linux evidence, macOS hope, and Windows documentation.

## 4. Migration Safety: Blast Radius of `scripts/omni_migrate_v1_to_v2.py`

Blast radius is larger than the docs admit.

- It touches both local repo state and global user state every time (`scripts/omni_migrate_v1_to_v2.py:129`).
- It can mutate tracked git state via `git mv` (`scripts/omni_migrate_v1_to_v2.py:45`).
- It has no backup, no transaction, no merge plan, and no migration log.
- If `.omni` already exists, it just skips (`scripts/omni_migrate_v1_to_v2.py:79`). That preserves safety against overwrite, but it also strands `.omc` contents with no reconciliation path.
- The release docs tell users to run `--apply` before first use (`docs/RELEASE-v2.0.0.md:17`), but do not describe failure modes on dirty repos, partially migrated homes, or split state.

This is not catastrophic code, but it is not “safe” enough to market as a default upgrade tool without stronger isolation and rollback language.

## 5. Release Gate Honesty: Does `release_preflight.py` Really Block Bad Ships?

No.

What it does block:
- wrong branch (`scripts/release_preflight.py:53`)
- dirty worktree (`scripts/release_preflight.py:61`)
- broken validator (`scripts/release_preflight.py:69`)
- broken pytest (`scripts/release_preflight.py:78`)
- missing changelog/release doc (`scripts/release_preflight.py:91`, `scripts/release_preflight.py:105`)
- obviously red recent CI history if `gh` is available (`scripts/release_preflight.py:112`)

What it does **not** block, despite docs/plan implying otherwise:
- missing coverage pass in the local preflight
- broken `mcp-smoke`
- broken `discovery-smoke`
- absence of a successful `release-gate` workflow specifically
- absence of 3 consecutive green runs over >=24h (`.omni/plans/phase-b-master-plan.md:562`)
- macOS/Windows regressions
- missing nightly/weekly real-Copilot jobs

It is a helpful checklist runner, not a trustworthy release gate.

## 6. Hidden Bugs Claude Missed

1. **The `Path("")` truthiness bug in hook root resolution** is subtle and easy to miss, but it is high impact (`hooks/session_start.py:61`, `hooks/user_prompt_submit.py:76`).
2. **The migration tests are non-hermetic and can move real `~/.omc` state** (`tests/test_migrate_v1_to_v2.py:28`, `scripts/omni_migrate_v1_to_v2.py:129`). This is the single worst hidden bug in the wave.
3. **WS7’s malformed-command path still allows by default**, contrary to the written security contract (`hooks/pre_tool_use.py:144`, `.omni/plans/phase-b-master-plan.md:369`).
4. **The cancel skill references a missing Node script and legacy env/path assumptions** (`skills/cancel/SKILL.md:203`, `skills/cancel/SKILL.md:240`). That is a latent runtime/documentation failure.
5. **The docs claim removed MCP tools that are still present in the server registry** (`docs/RELEASE-v2.0.0.md:24`, `mcp/server.py:943`, `mcp/server.py:955`). That is compatibility drift likely to create unnecessary migration churn.

## 7. Overall Grade + Recommendation

**Grade: C-**

Why not lower: the core direction is sound, the hook hardening work is real, and the repo now has better structure than before.

Why not higher: the release evidence is overstated, the migration/test safety bug is severe, and the docs are not trustworthy enough for a breaking release.

**Recommendation:** Block merge to `main` and do not tag `v2.0.0` until at least these are fixed:
- hermeticize `tests/test_migrate_v1_to_v2.py` and remove real-home blast radius
- fix hook plugin-root resolution and finish `COPILOT_PLUGIN_ROOT` migration with Claude fallback
- make malformed shell parse failures deny, or explicitly downgrade the contract everywhere
- either implement the real release gate or rewrite docs/preflight to match what actually exists
- reconcile README/AGENTS/CHANGELOG/RELEASE claims with the live skill/tool surface
- remove or rewrite the dead Node/Claude path in `skills/cancel/SKILL.md`

If those are corrected, I would re-review quickly. The wave does not look structurally doomed; it looks prematurely declared complete.

---

Completion summary: reviewed WS6/7/10/11/12 against the plan and `61e4c6a..HEAD`; highest-risk findings are unsafe migration tests, broken hook root resolution, a weak release gate, and material documentation drift.

Word count: 2070

## Addendum: What Would Change My Recommendation Quickly

This is not a request for a redesign. A focused remediation pass would materially improve confidence:
- one patch to isolate migration tests from the real home directory and to document/contain global-state migration behavior
- one patch to fix hook root/env-var handling and to remove the dead `cleanup-orphans.mjs` path from the cancel skill
- one patch to align release automation, release docs, and changelog language with the real CI surface
- one patch to either implement or explicitly drop the stronger WS7 malformed-command contract

If those land cleanly, most remaining concerns become normal Phase-C debt rather than v2.0.0 release blockers.
