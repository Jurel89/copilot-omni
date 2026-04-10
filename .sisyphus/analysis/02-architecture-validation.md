# Copilot Omni - Architecture Validation Report

## Executive Summary

After thorough research of GitHub Copilot CLI official documentation, Context7 SDK docs, and external sources, the overall architecture is **largely sound** but contains several **critical inaccuracies** and **missing decisions** that must be addressed before implementation begins.

**Overall Assessment: VALID WITH MODIFICATIONS NEEDED**

---

## Feature Validation Matrix

### ✅ VALIDATED - Features that exist and work as documented

| Feature | Status | Evidence |
|---|---|---|
| **Plugin manifest (plugin.json)** | ✅ REAL | Official docs show exact format with `name`, `description`, `version`, `author`, `license`, `keywords`, `agents`, `skills`, `hooks`, `mcpServers`, `commands`, `lspServers` |
| **Plugin from local path** | ✅ REAL | `copilot plugin install ./my-plugin` works |
| **Plugin from Git URL** | ✅ REAL | `copilot plugin install OWNER/REPO` works |
| **Plugin marketplace** | ✅ REAL | `marketplace.json` format documented, `copilot plugin marketplace add/browse/list` commands exist |
| **Agents (*.agent.md)** | ✅ REAL | YAML frontmatter with `name`, `description`, `tools`, `model`. Can be in `agents/` dir |
| **Skills (SKILL.md)** | ✅ REAL | Directories in `skills/` with `SKILL.md`, supports `allowed-tools` in frontmatter |
| **Hooks (hooks.json)** | ✅ REAL | 6 triggers: `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred` |
| **Hooks can block execution** | ✅ REAL | `preToolUse` hook can exit non-zero to block, and can return JSON to deny |
| **MCP server definitions** | ✅ REAL | `.mcp.json` in plugin root, `mcpServers` field in plugin.json |
| **Custom instructions** | ✅ REAL | `.github/copilot-instructions.md`, `.github/instructions/**/*.instructions.md`, `AGENTS.md` all documented |
| **Programmatic mode (-p flag)** | ✅ REAL | `copilot -p "prompt"` works, `-s` for silent, `--allow-tool`, `--allow-all` |
| **Transcript export (--share)** | ✅ REAL | `--share='./report.md'` and `--share-gist` documented |
| **Tool allow/deny** | ✅ REAL | `--allow-tool='shell(git)'`, `--deny-tool`, patterns like `shell(command:pattern)` |
| **Agent selection** | ✅ REAL | `copilot --agent=my-agent -p "prompt"` |
| **Namespaced loading** | ✅ REAL | First-found-wins precedence for agents/skills |
| **Copilot Memory** | ✅ REAL | "Copilot Memory allows Copilot to build a persistent understanding of your repository" |

### ⚠️ PARTIAL - Features that exist but with caveats

| Feature | Status | Caveat |
|---|---|---|
| **/chronicle** | ⚠️ PARTIAL | Session data exists via `--share` and session history in `~/.copilot/`, but `/chronicle` as a specific command is NOT confirmed in current docs. The source-alignment doc references it but official docs use `--share` for transcripts. |
| **Plan mode** | ⚠️ PARTIAL | Official docs say "there is also a plan mode" but it's interactive-only, NOT programmatically controllable via `-p`. The SDK has `session.rpc.plan.read/write` but that's SDK (preview), not CLI plugin. |
| **/research command** | ⚠️ PARTIAL | Built-in agents include `explore`, `task`, `research`, `code-review` but `/research` as a dedicated workflow is not fully documented. The `--agent=research` flag exists. |
| **/fleet command** | ❌ NOT FOUND | No evidence of a `/fleet` slash command in any official docs. This appears aspirational. |
| **/delegate command** | ⚠️ PARTIAL | `/delegate` is mentioned for cloud agent delegation, but it's NOT for local plugin workflows. Docs explicitly say "No dependency on /delegate." |
| **Autopilot mode** | ⚠️ PARTIAL | "Autopilot" as a named feature is referenced but not clearly documented as a distinct mode. The concept maps to `--allow-all` in programmatic mode. |
| **Copilot SDK** | ⚠️ PREVIEW | The Copilot SDK (`@github/copilot-sdk`) exists and provides hooks programmatically, but is "currently in public preview." |

### ❌ INVALID - Features that don't exist as documented

| Feature | Status | Reality |
|---|---|---|
| **Commands directory in plugins** | ⚠️ AMBIGUOUS | `commands` field IS documented in `plugin.json` reference, but NO docs explain the command file format or how to create custom slash commands. The `commands` field may be for a different purpose. |
| **Wrapper binary controlling "process-level Copilot flags"** | ⚠️ OVERBUILT | A wrapper binary is unnecessary for controlling flags — `copilot -p --allow-tool=...` already does this. The wrapper may be useful as a convenience CLI but is NOT architecturally required. |
| **SQLite session store** | ❌ NOT CONFIRMED | No evidence of a local SQLite session store in current docs. Session data lives in `~/.copilot/` but format is not documented as SQLite. The SDK uses JSON-RPC, not direct SQLite access. |
| **MCP allowlist enforcement as described** | ⚠️ LIMITED | Official docs confirm: "Copilot CLI can't currently support the following organization-level MCP server policies: MCP servers in Copilot... MCP Registry URL." The enforcement has known gaps. |

---

## Critical Architecture Decisions NOT in Docs

### 1. Sidecar Language — MUST DECIDE
The docs specify a "sidecar binary" but never state what language to use.
- **Options**: Rust (static binary, cross-compile friendly), Go (simpler, also static), TypeScript/Bun (matches plugin patterns)
- **Recommendation**: Go — simpler than Rust, native static binary compilation, excellent SQLite support, fast compilation. The sidecar doesn't need Rust's memory safety guarantees (it's not a systems-level project).

### 2. Sidecar ↔ Plugin Communication — MUST DECIDE
How does the Copilot CLI plugin talk to the sidecar?
- **Option A**: MCP server (sidecar runs as MCP stdio server) — ✅ This is what the docs intend
- **Option B**: HTTP REST API — More flexible but requires port management
- **Option C**: Unix socket — Fast but platform-specific
- **Recommendation**: Option A (MCP stdio) — this is exactly what the plugin `mcpServers` field supports. The sidecar IS an MCP server.

### 3. Commands vs Skills — MUST CLARIFY
The docs reference "slash commands" but Copilot CLI plugins don't have a clear custom slash command mechanism. 
- **Skills** ARE slash-command-like (`/skill-name args`)
- **Commands** field exists in plugin.json but documentation is missing
- **Recommendation**: Use SKILLS for all user-facing commands. Each `/omni-*` command is actually a skill.

### 4. Config Format — RESOLVED (see ADR-005 in 03-implementation-plan.md)
Docs mention `config.toml` but never explain why TOML over JSON or YAML.
- **Original recommendation**: Use TOML for human-edited config (`.omni/config.toml`), JSON for machine-readable schemas.
- **Final decision (ADR-005)**: JSON for all config files. TOML parser would require external dependencies; stdlib `encoding/json` suffices.

---

## Document Naming Issue — RESOLUTION PLAN

All 19 files have a systematic 2-position naming mismatch. The correct content-to-filename mapping is:

| Correct Name | Current File |
|---|---|
| `references.md` | `phase-0-foundation-bootstrap-prd.md` |
| `program-manifest.json` | `phase-0-foundation-bootstrap-architecture.md` |
| `v1-phase-roadmap.md` | `phase-1-spec-driven-workflow-core-prd.md` |
| `phase-gate-checklist.md` | `phase-1-spec-driven-workflow-core-architecture.md` |
| `phase-0-foundation-bootstrap-prd.md` | `phase-2-guarded-execution-verification-prd.md` |
| `phase-0-foundation-bootstrap-architecture.md` | `phase-2-guarded-execution-verification-architecture.md` |
| `phase-1-spec-driven-workflow-core-prd.md` | `phase-3-local-memory-resumability-prd.md` |
| `phase-1-spec-driven-workflow-core-architecture.md` | `phase-3-local-memory-resumability-architecture.md` |
| `phase-2-guarded-execution-verification-prd.md` | `phase-4-research-subagents-parallelism-prd.md` |
| `phase-2-guarded-execution-verification-architecture.md` | `phase-4-research-subagents-parallelism-architecture.md` |
| `phase-3-local-memory-resumability-prd.md` | `phase-5-enterprise-offline-distribution-prd.md` |
| `phase-3-local-memory-resumability-architecture.md` | `phase-5-enterprise-offline-distribution-architecture.md` |
| `phase-4-research-subagents-parallelism-prd.md` | `phase-6-ga-hardening-ux-performance-prd.md` |
| `phase-4-research-subagents-parallelism-architecture.md` | `phase-6-ga-hardening-ux-performance-architecture.md` |
| `phase-5-enterprise-offline-distribution-prd.md` | `architecture-principles.md` |
| `phase-5-enterprise-offline-distribution-architecture.md` | `source-alignment.md` |
| `phase-6-ga-hardening-ux-performance-prd.md` | `initial-architecture-draft.md` |
| `phase-6-ga-hardening-ux-performance-architecture.md` | `target-system-architecture.md` |
| *(keep as-is)* | `phase-gate-checklist.md` (contains program overview) |

---

## Revised Architecture Model

Based on validated features, the architecture should be:

```
┌─────────────────────────────────────────────────┐
│                  USER                            │
│  (types `copilot` or `omni` in terminal)         │
└───────────┬─────────────────┬───────────────────┘
            │                 │
            ▼                 ▼
┌───────────────────┐ ┌──────────────────────────┐
│   Copilot CLI      │ │   `omni` wrapper CLI      │
│   (interactive)    │ │   (convenience shortcuts)  │
│                    │ │   - wraps `copilot -p`      │
│  Plugin provides:  │ │   - manages sidecar proc    │
│  - agents/         │ │   - resolves config         │
│  - skills/         │ │                             │
│  - hooks/          │ └──────────┬──────────────────┘
│  - .mcp.json       │            │
│  - commands/       │            │ spawns
└────────┬───────────┘            ▼
         │              ┌──────────────────────────┐
         │ MCP/stdio    │   Sidecar Binary (Go)     │
         ├─────────────►│   - MCP server (stdio)     │
         │              │   - SQLite memory store     │
         │              │   - Policy engine           │
         │              │   - Artifact management     │
         │              │   - Config resolution       │
         │              │   - Guarded tools           │
         │              │   - Health endpoint         │
         │              └────────────────────────────┘
         │
         │ Tool calls
         ▼
┌───────────────────┐
│   LLM (Claude/GPT) │
│   via Copilot      │
└───────────────────┘
```

### Key Clarifications

1. **Plugin = user-facing** — provides agents, skills, hooks, and MCP wiring
2. **Sidecar = state/policy** — runs as MCP server, owns SQLite, policy, guarded tools
3. **Wrapper = convenience** — thin CLI that wraps `copilot -p` and manages sidecar lifecycle
4. **All `omni` commands are SKILLS** — not "commands" in the plugin.json sense
5. **Hooks = policy enforcement layer** — `preToolUse` hook blocks unauthorized operations
6. **Programmatic mode = execution engine** — `copilot -p` drives all phase transitions

---

## Risk Assessment

### HIGH RISK
1. **Document naming mismatch** — anyone reading files will be 2 phases off. Must fix immediately.
2. **Sidecar language undecided** — blocks Phase 0 implementation.
3. **Commands vs Skills confusion** — docs reference "commands" but plugin commands may not work as expected.

### MEDIUM RISK
4. **Copilot SDK in preview** — hooks via SDK work but are preview; CLI hooks via JSON are GA.
5. **No custom slash command docs** — the `commands` field exists but format is undocumented.
6. **/fleet doesn't exist** — Phase 4 references `/fleet`-style decomposition which is aspirational.
7. **SQLite session store assumption** — docs assume Copilot uses SQLite internally, which is unconfirmed.

### LOW RISK
8. **Config format** — resolved to JSON per ADR-005.
9. **MCP enforcement gaps** — known limitation, docs already acknowledge it.
10. **Programmatic mode limitations** — `--share` is file-based, not structured JSON export.

---

## Recommendations Before Implementation

1. **Fix document naming** — rename all files to match their content
2. **Decide sidecar language** — Go recommended for fastest path to working prototype
3. **Use skills, not commands** — all `/omni-*` entry points should be skills
4. **Use hooks for policy** — `preToolUse` hooks in `.github/hooks/` for enforcement
5. **Use MCP for sidecar** — sidecar is an MCP stdio server, launched via plugin's `.mcp.json`
6. **Use programmatic mode** — `copilot -p` for all phase transitions
7. **Use --share for transcripts** — `--share=./path/transcript.md` for artifact capture
8. **Drop /fleet references** — replace with subagent/parallel patterns that actually exist
9. **Clarify /chronicle** — use `--share` instead, which is the real transcript mechanism
10. **Document all decisions** — create ADRs for language, protocol, config format choices
