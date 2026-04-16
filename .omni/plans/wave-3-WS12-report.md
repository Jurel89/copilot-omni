# WS12 Completion Report — Release Gate + v2.0.0 Prep

**Branch:** `phase-b/wave-3/WS11-12-docs-release`
**Date:** 2026-04-16
**Status:** Complete

---

## Deliverables

| # | Artifact | File | Notes |
|---|---------|------|-------|
| 1 | CI release-gate job | `.github/workflows/ci.yml` | `release-gate` job on `phase-b/main` push |
| 2 | Release artifact | `docs/RELEASE-v2.0.0.md` | Summary, breaking, features, upgrade path, CI requirements, post-tag checklist |
| 3 | Release preflight script | `scripts/release_preflight.py` | 7 checks, exit 0 = ready, exit 1 = checklist |
| 4 | Phase-C backlog | `docs/PHASE-C-BACKLOG.md` | All deferred items from wave reports, grouped by category |
| 5 | WS12 report | `.omni/plans/wave-3-WS12-report.md` | This file |

---

## CI changes

### New job: `release-gate`

Added to `.github/workflows/ci.yml`:
- **Trigger**: `phase-b/main` push only (`if: github.ref == 'refs/heads/phase-b/main'`)
- **Needs**: `lint, unit-tests, mcp-smoke, discovery-smoke, coverage` (runs after all other jobs)
- **Steps**:
  1. Run plugin contract validator `--all`
  2. Run full pytest suite
  3. Run coverage gate (`measure_coverage.py --check`)
  4. MCP stdio smoke
  5. Plugin discovery smoke (all probes, offline)
  6. Assert CHANGELOG.md has `## [2.0.0]` section
  7. Assert `docs/RELEASE-v2.0.0.md` exists

### Required status checks (document only — admin UI required)

The following checks must be required in GitHub branch protection for `main`:
`lint (3.9)`, `lint (3.10)`, `lint (3.11)`, `lint (3.12)`,
`unit-tests (3.9)`, `unit-tests (3.10)`, `unit-tests (3.11)`, `unit-tests (3.12)`,
`mcp-smoke`, `discovery-smoke`, `coverage`, `release-gate`.

---

## Release preflight script

`scripts/release_preflight.py` — 7 checks:

| # | Check | Exit condition |
|---|-------|---------------|
| 1 | On branch `phase-b/main` | Fail if different branch |
| 2 | No uncommitted changes | Fail if `git status --porcelain` non-empty |
| 3 | Validator `--all` green | Fail if exit code non-zero |
| 4 | Full pytest green | Fail if exit code non-zero |
| 5 | CHANGELOG.md has `[2.0.0]` | Fail if section absent |
| 6 | `docs/RELEASE-v2.0.0.md` exists | Fail if file absent |
| 7 | Last 3 CI runs on `phase-b/main` green | Fail if `gh run list` shows non-success; warns if `gh` not installed |

Exit 0 = all pass (ready to tag). Exit 1 = checklist of failures printed.

Expected exit on current branch (`phase-b/wave-3/WS11-12-docs-release`): **exit 1**
because check #1 (branch = `phase-b/main`) and check #7 (CI runs) will fail.
This is correct and expected — the user must merge to `phase-b/main` first.

---

## Release artifact

`docs/RELEASE-v2.0.0.md` contains:
- 1-paragraph summary of v2.0.0
- 5 breaking-change highlights (from CHANGELOG Breaking section)
- 10 feature highlights (from CHANGELOG Added section)
- Upgrade path (links to MIGRATION.md)
- Known limitations (Windows experimental, real-Copilot nightly, Phase-C backlog)
- Required CI checks table (9 required + 1 best-effort)
- Post-tag checklist (7 items)

---

## Phase-C backlog

`docs/PHASE-C-BACKLOG.md` collects all deferred items from wave reports:

| Category | Items |
|---------|-------|
| Hardening | 10 items (router 16-class, Windows back-pressure, exemption-cap schedule, etc.) |
| Portability | 4 items (Windows CI lane, tmux gate removal, deep-interview UX verify) |
| Features | 14 items (configure-notifications, deep-interview redesign, wiki/memory hooks, etc.) |
| Tests | 6 items (real-Copilot nightly, mutation testing, MCP race, etc.) |

Source WS references: wave-2.x-patch-report, wave-2-WS3-report, wave-2-WS8-report,
wave-3-WS10-report, wave-3-WS6-report, wave-3-WS7-report, phase-b-master-plan.

---

## Acceptance gate

- [x] `.github/workflows/ci.yml` has `release-gate` job
- [x] `docs/RELEASE-v2.0.0.md` present with all required sections
- [x] `scripts/release_preflight.py` present, exits with precise checklist
- [x] `docs/PHASE-C-BACKLOG.md` present with 34 tracked items
- [x] `python3 scripts/release_preflight.py` exits non-zero on current branch (expected: branch check fails)
- [x] No tag pushed. No merge to main.

---

## Pre-tag instructions for user

When ready to release:

```bash
# 1. Merge phase-b/wave-3/WS11-12-docs-release into phase-b/main
git checkout phase-b/main
git merge --ff-only phase-b/wave-3/WS11-12-docs-release

# 2. Verify all 7 preflight checks pass
python3 scripts/release_preflight.py

# 3. Tag (user approval required)
git tag -s v2.0.0 -m 'v2.0.0 release'
git push origin v2.0.0

# 4. Merge phase-b/main to main (user approval required)
git checkout main
git merge --ff-only phase-b/main
git push origin main
```
