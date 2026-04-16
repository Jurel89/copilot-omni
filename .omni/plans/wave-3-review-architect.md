# Phase-B Wave 3 — Architectural Review

## 0. Architectural verdict

**Merge to `main`: yes, with two mandatory fixes.** Structure is sound: team orchestration cleanly layered, hook-lib factoring tight, migrator idempotent, release gate real. Must fix before tag: (1) `skills/cancel/SKILL.md` contains 3 un-allowlisted `.omc` path refs + stale `OMC_STATE_DIR`/`CLAUDE_SESSION_ID` env vars; (2) `README.md:27` lists `learner` in 29-skill catalog (deleted per ADR-0002). Everything else merge-ready.

## 1. Team architecture: layering

Clean 4-layer decomposition in `omni_team.py`:
1. Public lifecycle API (create/dispatch/collect/cancel/cleanup/status)
2. Host adapter layer (`_TmuxSession` / `_TmuxWorkerHost` / `_SubprocessWorkerHost`)
3. Worktree manager (delegated to `omni_worktree.py`)
4. Subagent consumer (delegated to `subagent.py` + `subagent_pool.py`)

One smell: worker hosts share no formal Protocol class — interface is implicit. Fine for 2 implementations; needs formalizing if Phase C adds container host.

`omni_worktree.py` is thin: 317 lines, 4 public functions, `_sanitize_name` prevents branch-name injection, `remove` prunes before removing (robust to deleted dirs).

## 2. Hook-lib factoring

`hooks/_hook_lib.py` well-scoped at 252 lines. Four public APIs: `_hook_disabled`, `_deprecation_warn`, `_append_audit`, `_write_metric`. Abstractions don't leak: audit + metrics share private `_atomic_append` but expose separate schemas. File-locking handles 3 platforms with 1s budget and drop-on-timeout. Clean.

## 3. Migration surface: blast radius

Genuinely idempotent: rerunning is safe, no data loss.

TOCTOU window during `shutil.move` if another process writes to `.omc/` concurrently — caught by broad exception, reported as `ERR`, exit 1. Never silently corrupts.

Worst case: partial move between `.omc/` and `.omni/`. Manual recovery, not silent loss. Uses `git mv` in git repos (preserves history) and `shutil.move` outside. Never modifies dotfiles.

Does NOT update config.json schema, rename env vars, or touch slash-command refs — documented as manual steps in MIGRATION.md §2-3. Right call.

## 4. Release gate: genuine or decorative?

Genuine. 7 checks: branch, uncommitted, validator, pytest, CHANGELOG section, release doc, last-3-CI runs. Checks 3+4 execute real code; #7 queries real CI state. Exits 1 with detailed checklist on failure.

Cannot catch: runtime behavior differences, Copilot CLI plugin discovery correctness, migration on real v1 installs, doc content accuracy. CI workflow adds `release-gate` job on push to `phase-b/main` — real pipeline gate, not local-only.

## 5. Documentation coherence

Tells consistent story across 8 docs. One contradiction: `README.md:27` lists `learner` (deleted) in 29-skill catalog; lists 31 names total. Rest is aligned. `HOOK_CONTRACT.md` matches `_hook_lib.py` exactly. `ADR/README.md` indexes 12 ADRs accurately. `PHASE-C-BACKLOG.md` items cite origin.

## 6. Phase-C deferral audit

29 items organized Hardening(10)/Portability(4)/Features(13)/Tests(6). Each cites source.

Genuinely post-v2.0.0:
- Windows team mode, full Windows CI, cross-OS audit — platform hardening
- Router 16-class chooser, wiki/memory, LSP tools — feature expansion
- Mutation testing, real-Copilot nightly — test maturity

Borderline load-bearing:
- "Pipeline e2e test guards — explicit asserts" — means some integration tests aren't asserting. Weakens pipeline-mode confidence, but not blocking.
- "Audit log `0700` perms" — security tightening; current uses umask default.
- "Router: enforce `<router-decision>` at transport layer" — known limitation.

**Verdict: honest deferrals. No load-bearing debt disguised.**

## 7. Merge-to-main readiness

New assumptions:
- `.omni/` directory exists. External tooling referencing `.omc/` breaks.
- `AGENTS.md` is sole agent entrypoint. CLAUDE.md references 404.
- ADRs are reference only — no runtime code reads them. Safe to merge.
- 17-check validator is CI gate — main branch protection must be configured (documented but not scripted).

Reverse-compat:
- `OMC_SKIP_HOOKS`/`DISABLE_OMC` correctly handled — `_hook_lib.py:85-88` warns + honors. Sentinel prevents spam. Clean removal in v3.0.0.

Could break: users with `.omc/` state who skip migrator get fresh `.omni/` with no history. Doctor should detect + prompt.

## 8. Dead-code / end-state drift

Zero `# TODO`/`# FIXME` in production Python. Clean.

Stale refs:
1. **`skills/cancel/SKILL.md:65,78,81`** — bash fallback references `.omc`, `OMC_STATE_DIR`, `CLAUDE_SESSION_ID`/`CLAUDECODE_SESSION_ID`.
2. **`README.md:27`** — `learner` in skill catalog; counts 31 names, claims 29.
3. **`AGENTS.md:98`** — lists `run_status`, `resume_context` under MCP tools; CHANGELOG says `run_status` is "still callable but not documented".
4. **`cancel/SKILL.md:28`** — summary references `TeamDelete` (Claude primitive); the body was correctly rewritten but summary not updated.

## 9. Architectural recommendations

1. **Fix cancel SKILL.md v1/Claude residue** (lines 28,64-81). Update to `.omni`, `OMNI_STATE_DIR`, `COPILOT_SESSION_ID`, `omni_team.py cancel`.
2. **Fix README skill list** — remove `learner`; verify count=29.
3. **Formalize worker-host interface** — add `typing.Protocol` `WorkerHost` class.
4. **Add `--verify-migration` to `omni doctor`** — detect un-migrated `.omc/`.
5. **Tighten audit dir perms** — explicit `chmod 0o700` in `_ensure_dir`.
6. **De-duplicate kill-switch fast-path** — extract `fast_disabled(hook_name)` into `_hook_lib`.
7. **TOCTOU guard on migrator** — acquire `.omc/.migrate.lock` before moving.
8. **Wire branch-protection via `gh api`** or document with screenshots.
9. **Add `--rollback` to migrator** — `.omni → .omc` safety net.
10. **Validate manifest.json schema in `dispatch_workers`** — `_validate_manifest` helper.

## 10. Items for user decision before v2.0.0

1. **Cancel SKILL.md cleanup scope** — update in-place, or strip entire bash fallback since `omni_team.py cancel` is canonical?
2. **README skill count** — verify canonical 29; does `hud` still ship or was it folded into banner?
3. **`run_status`/`resume_context` MCP tools** — remove from AGENTS.md to match CHANGELOG, or keep as documented?
4. **Branch protection** — script via `gh api` in preflight, or manual UI acceptable?
5. **Audit dir `0700` perms** — ship in v2.0.0 or defer?
6. **`copilot-smoke` CI continue-on-error** — accept for v2.0.0 or add explicit note in release doc?
