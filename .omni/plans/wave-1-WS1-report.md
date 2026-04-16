# Wave 1 — WS1 Rename Sweep Report

**Branch:** `phase-b/wave-1/WS1-rename-sweep`
**Date:** 2026-04-16
**Executor:** Claude Sonnet 4.6 (oh-my-claudecode:executor)

---

## 1. Inventory Counts

### Before (git grep across non-allowlisted paths)
- Total banned-token hits: **698** lines across **60 files**
- Breakdown by token:
  - `oh-my-claudecode`: ~120 hits
  - `.omc/`: ~180 hits
  - `omc-`: ~280 hits
  - `\bOMC\b`: ~118 hits

### After
- Residual hits (post-rename): **8** lines, all covered by `omni-rename-allow` markers or self-allowlisted
- Verifier result: `[ok] rename` — **0 residual banned tokens**, 7 exemptions (cap ≤10)

---

## 2. Files Renamed (Filesystem)

| Old path | New path |
|----------|----------|
| `skills/omc-doctor/` | `skills/omni-doctor/` |
| `skills/omc-reference/` | `skills/omni-reference/` |
| `skills/omc-setup/` | `skills/omni-setup/` |
| `skills/omc-teams/` | `skills/omni-teams/` |
| `skills/sciomc/` | `skills/sciomni/` |

All renames done via `git mv` (history preserved).

---

## 3. Content Edits by Category

### Skills (56 files)
- All `oh-my-claudecode:*` → `copilot-omni:*` (slash command namespace)
- All `.omc/plans`, `.omc/specs`, `.omc/state`, `.omc/autopilot`, etc. → `.omni/*`
- `omc-doctor`, `omc-reference`, `omc-setup`, `omc-teams` → `omni-*` everywhere
- `sciomc` skill name → `sciomni` (frontmatter + all invocation examples)
- `\bOMC\b` in prose → `copilot-omni`
- PSM example aliases updated from `omc`/`Yeachan-Heo/oh-my-claudecode` → `omni`/`Jurel89/copilot-omni`
- `skills/self-improve/scripts/`: `.omc/self-improve` → `.omni/self-improve`

### Agents (9 files)
- All `Task(subagent_type="oh-my-claudecode:*")` → `Task(subagent_type="copilot-omni:*")`
- `.omc/plans/*.md` → `.omni/plans/*.md` path references
- `AGENTS.md`: removed upstream `oh-my-claudecode` name from How-skills-invoke-subagents section

### Commands (8 files)
- All `/oh-my-claudecode:*` → `/copilot-omni:*`

### Hooks (4 files)
- Added `OMNI_SKIP_HOOKS` / `DISABLE_OMNI` kill-switches as primary env vars
- Added `OMC_SKIP_HOOKS` / `DISABLE_OMC` as backward-compat aliases (removed in v3.0.0)
- Kill-switch inserted at module level after docstring in each hook

### Scripts (2 files)
- `scripts/discovery_smoke.py`: removed `.omc/` from exclusion prefix list (`.omni/` remains)
- `scripts/verify_plugin_contract.py`: full implementation of `--check-rename` (see §6); self-allowlisted; extended ALLOW_MARKER_RE to support `#`-style markers in addition to HTML comments

### Docs (1 file)
- `docs/SKILLS.md`: `omc-setup/doctor/reference/teams` → `omni-*`, `OMC agent` → `copilot-omni agent`

### Root-level files
- `AGENTS.md`: removed `oh-my-claudecode` upstream citation from subagent docs
- `README.md`: `sciomc` → `sciomni`, `omc-doctor` → `omni-doctor`; added upstream-reference allow marker for lineage paragraph
- `CHANGELOG.md`: updated v1.0.0 skill list; prepended v1.1.0 entry with changelog-entry allow markers
- `.gitignore`: added `# omni-rename-allow: historical-citation` marker above `.omc/` entry

---

## 4. Exemptions Added

| File | Line | Reason | Token |
|------|------|--------|-------|
| `.gitignore` | 16 | `historical-citation` | `.omc/` (legacy ignore entry) |
| `CHANGELOG.md` | 6 | `changelog-entry` | `omc-*` in heading |
| `CHANGELOG.md` | 8 | `changelog-entry` | `oh-my-claudecode`, `omc-*`, `.omc/` |
| `CHANGELOG.md` | 10 | `changelog-entry` | `omc-*` renamed skill list |
| `CHANGELOG.md` | 11 | `changelog-entry` | `oh-my-claudecode:omc-*` slash-cmd ref |
| `CHANGELOG.md` | 12 | `changelog-entry` | `.omc/` path migration note |
| `README.md` | 47 | `upstream-reference` | `oh-my-claudecode` lineage attribution |

Total: **7 exemptions** (cap ≤10: PASS)

`scripts/verify_plugin_contract.py` is **self-allowlisted** in `ALLOWLIST_PATHS` (not counted as exemption — it defines the banned patterns as regex literals).

---

## 5. Test Results

```
41 passed in 1.17s
```

All 41 existing tests pass on final commit.

```
[ok] rename      — 0 residual hits, 7 exemptions (≤10 cap)
[ok] rename-stub — harness alive
layout probe     — pass: skills=37 agents=19 cmds=8
```

---

## 6. Verifier Implementation (`--check-rename`)

`scripts/verify_plugin_contract.py` now exposes:

- `--check-rename`: walks whole tree, strips markdown code fences, skips 5 hard-allowlisted path prefixes + `.omc/` runtime dir + `.git/` + self, scans for 4 banned patterns, checks `omni-rename-allow` markers within ±3 lines (supports both `<!-- -->` HTML and `# comment` shell formats), fails if any residual hit lacks a marker or exemption count exceeds 10.
- `--list-rename-exemptions`: prints the full exemption map.
- `--all`: runs all registered checks (rename + rename-stub).

---

## 7. Commit SHAs (in order)

| # | SHA | Scope |
|---|-----|-------|
| 1 | `8c382a2` | Verifier implementation (`--check-rename`) |
| 2 | `bb78ea2` | Filesystem path renames (`git mv`) |
| 3 | `152855d` | Skills/agents/commands content rewrites |
| 4 | `f6b7263` | Scripts/hooks/mcp content rewrites |
| 5 | `93ac460` | Docs/root files + verifier marker pattern fix |
| 6 | `c387def` | Env-var kill-switch shim + CHANGELOG entry |

---

## 8. Gotchas Discovered

1. **`from __future__ import annotations` placement.** The patcher inserted the kill-switch block between the docstring and the `from __future__` import in `pre_tool_use.py`. Python requires `__future__` imports to be the first statement after the docstring — fixed by moving `from __future__` before the kill-switch block.

2. **`# omni-rename-allow` vs `<!-- omni-rename-allow -->` in non-HTML files.** The original marker regex only matched HTML comments; `.gitignore` uses `#` comments. Extended `ALLOW_MARKER_RE` to support both forms.

3. **CHANGELOG exemption window.** The 3-line marker window meant a single marker at the top of the changelog block did not cover all 6 affected lines. Added a second marker mid-block to keep all hits within window.

4. **`sciomc` skill name vs directory name.** The directory was renamed to `sciomni/` but the SKILL.md frontmatter `name: sciomc` was the original OMC identifier. Updated both the directory and the frontmatter to `sciomni`.

5. **`scripts/verify_plugin_contract.py` self-reference.** The verifier defines the banned tokens as raw Python string literals — it would flag itself. Added `scripts/verify_plugin_contract.py` to `ALLOWLIST_PATHS` to self-allowlist.

6. **PSM example aliases.** `skills/project-session-manager/templates/projects.json` and `lib/config.sh` contained example `"omc"` alias pointing to `Yeachan-Heo/oh-my-claudecode`. Updated to `"omni"` pointing to `Jurel89/copilot-omni`.

---

## 9. Next-Step Handoff Notes

### WS2 (Decontamination)
- Skill bodies may still reference `oh-my-claudecode` **inside markdown code fences** — the verifier intentionally strips fences before scanning so code-fence content does not trigger. WS2 should decide whether LLM-imitation risk from fenced examples warrants further cleanup.
- `skills/omni-doctor/SKILL.md` contains Node.js `node -e "..."` inline commands referencing old npm package paths (`cache/omc/copilot-omni`). These were not renamed here (the Node path segment `copilot-omni` is the package name, correct). Review if the `omc` directory path within the Node cache logic needs updating.
- `skills/cancel/SKILL.md` references `ToolSearch(query="select:mcp__plugin_copilot-omni_t__...")` — these MCP tool names include `copilot-omni` which is the new name; verify MCP server tool registration matches.

### WS9 (Validator Extension)
- The verifier's `SCAN_EXTENSIONS` set covers common text formats. Add `.tf`, `.hcl`, `.proto`, `.graphql` if the project grows into those.
- Consider adding a `--fix` flag that auto-applies replacements (careful: currently read-only by design).
- The exemption cap of 10 is hardcoded as `MAX_EXEMPTIONS`. If legitimate exemptions grow, make it configurable via CLI flag.
- The 3-line window for marker proximity (`window=3`) is conservative; consider raising to 5 for changelog-style blocks.
