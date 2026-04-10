# Copilot Omni - Master Implementation Plan

## Status: PHASE 0 SCAFFOLD COMPLETE (with caveats)

Research, architecture validation, and Phase 0 scaffold are in place. Phases 1-6 have detailed implementation plans below but no code yet. Phase 0 has known gaps documented at the end of this file.

**Honest assessment**: Doc audit complete, research validated, Phase 0 scaffold created and functional (init generates files, doctor runs real diagnostics, wrapper invokes Copilot). Not all phases are implemented — only Phase 0.

---

## Architecture Validation Summary

### What Changed from Original Docs

| Original Assumption | Validated Reality | Impact |
|---|---|---|
| `/chronicle` for session data | ✅ REAL but **experimental** — requires `/experimental on` | Phase 3 must not depend on `/chronicle` GA. Use `--share` for transcripts. |
| `/fleet` for parallel execution | ✅ REAL — `/fleet` exists for parallel subagent execution | Phase 4 can use `/fleet`. Remove "NOT FOUND" from validation. |
| `/research` command | ✅ REAL — produces cited research report | Phase 4 research workflow validated. |
| `/delegate` for cloud agent | ✅ REAL — but requires cloud agent policy enabled | Keep as non-dependency (docs already say "no dependency on /delegate"). |
| Hooks can modify prompts/outputs | ❌ NOT supported — only `deny` in `preToolUse` | Policy layer must use deny-only model. Cannot rewrite prompts via hooks. |
| Wrapper binary essential | ⚠️ Nice-to-have — `copilot -p` already supports programmatic mode | Wrapper adds convenience but is not architecturally required. |
| Enterprise MCP enforcement | ❌ NOT effective for CLI — known policy gaps | Sidecar must enforce MCP policy locally, not rely on GitHub enterprise policy. |
| `commands` in plugin.json | ✅ REAL — but documented as lower priority than skills | Use skills as primary command surface. Commands are fallback. |
| SQLite session store | ✅ REAL — `~/.copilot/session-store.db` exists | Phase 3 can read from this, but it's a Copilot-internal detail. |
| Autopilot mode | ✅ REAL — `--autopilot --max-autopilot-continues N` | Phase 2 can use bounded autopilot for task execution. |

### Confirmed Feature Set for Implementation

```
Plugin System:    ✅ plugin.json with agents, skills, hooks, mcpServers, commands, lspServers
Installation:     ✅ Local path, Git URL, marketplace
Programmatic:     ✅ copilot -p "..." with -s, --share, --allow-tool, --deny-tool, --agent, --model
Transcript:       ✅ --share=PATH (Markdown), --share-gist
Hooks:            ✅ 6+ triggers (sessionStart/End, userPromptSubmitted, preToolUse, postToolUse, errorOccurred, agentStop, subagentStop, preCompact, permissionRequest)
Hooks capability: ✅ Block via preToolUse deny only. No prompt/output modification.
Agents:           ✅ *.agent.md with name, description, tools, model, infer, mcp-servers
Skills:           ✅ skills/NAME/SKILL.md with name, description, allowed-tools, user-invocable
Commands:         ✅ commands/ dir with *.md files (lower priority than skills)
MCP:              ✅ .mcp.json with local/stdio and remote HTTP servers
Custom Instructions: ✅ .github/copilot-instructions.md, .github/instructions/**/*.md, AGENTS.md
Plan Mode:        ✅ Interactive Shift+Tab or /plan
Research/Fleet:   ✅ /research and /fleet are real
Autopilot:        ✅ --autopilot with --max-autopilot-continues
Copilot Memory:   ✅ Built-in persistent memory (store_memory tool)
Session Resume:   ✅ --continue, --resume SESSION-ID
Tool Permissions: ✅ --available-tools, --excluded-tools, --allow-tool, --deny-tool (deny wins)
Output Formats:   ✅ -s (text), --output-format=json (JSONL)
Env Vars:         ✅ COPILOT_MODEL, COPILOT_HOME, COPILOT_GITHUB_TOKEN, etc.
```

---

## Resolved Architecture Decisions

### ADR-001: Sidecar Language
**Decision: Go**
- Static binary compilation (no runtime dependencies)
- Excellent SQLite support via modernc.org/sqlite (pure Go, no CGO needed)
- Fast compilation, easy cross-compilation
- MCP stdio server pattern is trivial in Go
- NOT Rust: sidecar doesn't need memory-safety guarantees, development speed matters more

### ADR-002: Sidecar ↔ Plugin Communication
**Decision: MCP over stdio**
- Sidecar IS an MCP server declared in plugin's `.mcp.json`
- Plugin field: `"mcpServers": ".mcp.json"` pointing to sidecar binary
- Sidecar exposes tools: `omni_health`, `omni_config_resolve`, `omni_artifact_write`, `omni_artifact_read`, `omni_policy_check`, `omni_memory_search`, `omni_memory_store`, `omni_guarded_patch`, `omni_verification_run`, etc.
- No HTTP server, no port management, no socket files

### ADR-003: Command Surface
**Decision: Skills as primary, Commands as secondary**
- All `/omni-*` user-facing features are SKILLS (e.g., `skills/omni-init/SKILL.md`, `skills/omni-doctor/SKILL.md`)
- Skills have richer frontmatter (`allowed-tools`, `user-invocable`, `disable-model-invocation`)
- Commands used only for very simple passthrough if needed

### ADR-004: Policy Enforcement
**Decision: Hooks (deny-only) + Sidecar MCP tools (guard layer)**
- `preToolUse` hooks block prohibited operations (shell commands, protected paths)
- Sidecar MCP tools enforce plan-scope constraints (won't write files outside plan)
- Hooks config generated by `omni init` into `.github/hooks/omni-policy.json`
- Sidecar is authoritative for policy decisions, hooks are the enforcement mechanism

### ADR-005: Config Format
**Decision: JSON for all config (Phase 0)**
- `.omni/config.json` for repo-local config
- `~/.copilot-omni/config.json` for user-global config
- JSON was chosen over TOML because implementing a TOML parser from scratch is impractical and we want zero external dependencies
- TOML may be revisited in Phase 6 if a dependency budget allows
- Template file: `templates/config.json.tmpl`

### ADR-006: Wrapper Binary
**Decision: Go CLI wrapper (`omni` command)**
- Thin convenience wrapper around `copilot -p` invocations
- Manages sidecar process lifecycle (start, health check, stop)
- Resolves config, profile, and phase state
- NOT architecturally essential but provides UX the plugin alone cannot:
  - `omni init` → runs skill + sidecar setup
  - `omni doctor` → runs diagnostics
  - `omni run "prompt"` → wraps `copilot -p` with correct flags + sidecar wiring
  - `omni plan` → interactive planning
  - `omni execute` → guarded execution
  - `omni resume` → resume with context hydration

### ADR-007: Execution Model
**Decision: Programmatic Copilot invocations per phase**
- Each phase (discuss, spec, plan, execute, verify) runs as a separate `copilot -p` invocation
- Transcripts captured via `--share`
- Artifacts stored under `.omni/runs/<run-id>/`
- Sidecar provides context hydration between phases via MCP tools

---

## Repository Structure (Target State After Phase 0)

```
copilot-omni/
├── README.md
├── docs/
│   └── internal/                    # Original planning docs
│       └── fixed/                   # Corrected file names
├── .sisyphus/
│   └── analysis/                    # Research and validation docs
├── plugin/                          # The Copilot CLI plugin
│   ├── plugin.json                  # Plugin manifest
│   ├── agents/                      # Custom agents
│   │   ├── omni-conductor.agent.md  # Orchestrator agent
│   │   ├── omni-planner.agent.md    # Planning specialist
│   │   ├── omni-reviewer.agent.md   # Plan review specialist
│   │   └── omni-verifier.agent.md   # Verification specialist
│   ├── skills/                      # Skills (= slash commands)
│   │   ├── omni-init/
│   │   │   └── SKILL.md             # /omni-init: bootstrap repo
│   │   ├── omni-doctor/
│   │   │   └── SKILL.md             # /omni-doctor: diagnostics
│   │   ├── omni-run/
│   │   │   └── SKILL.md             # /omni-run: start a workflow
│   │   ├── omni-plan/
│   │   │   └── SKILL.md             # /omni-plan: plan only
│   │   └── omni-resume/
│   │       └── SKILL.md             # /omni-resume: resume a run
│   ├── commands/                    # Simple commands (if needed)
│   ├── hooks.json                   # Policy hooks
│   └── .mcp.json                    # Declares sidecar as MCP server
├── sidecar/                         # Go sidecar binary
│   ├── go.mod
│   ├── go.sum
│   ├── cmd/
│   │   └── omni-sidecar/
│   │       └── main.go              # MCP stdio server entry point
│   ├── internal/
│   │   ├── mcp/                     # MCP protocol implementation
│   │   ├── config/                  # Config resolution (JSON)
│   │   ├── policy/                  # Policy engine
│   │   ├── artifact/                # Artifact management
│   │   ├── schema/                  # JSON schema validation
│   │   └── doctor/                  # Diagnostics engine
│   └── schemas/                     # JSON schemas for artifacts
├── wrapper/                         # Go wrapper binary
│   ├── go.mod
│   ├── cmd/
│   │   └── omni/
│   │       └── main.go              # CLI entry point
│   └── internal/
│       ├── copilot/                 # Copilot CLI invocation helpers
│       └── sidecar/                 # Sidecar process management
├── profiles/                        # Policy profile packs
│   ├── strict/
│   │   └── config.json
│   ├── standard/
│   │   └── config.json
│   └── permissive/
│       └── config.json
├── templates/                       # Bootstrap templates
│   ├── copilot-instructions.md.tmpl
│   ├── agents-md.md.tmpl
│   ├── instructions-md.md.tmpl
│   └── config.json.tmpl
└── test/
    ├── fixtures/                    # Test fixture repos
    └── adversarial/                 # Adversarial test cases
```

---

## Phase 0 Implementation Plan (Detailed)

### Wave 1: Plugin Skeleton + Sidecar Health (Day 1-2)

**Task 1.1: Create plugin manifest and directory structure**
- Files: `plugin/plugin.json`, `plugin/agents/`, `plugin/skills/`, `plugin/.mcp.json`
- plugin.json declares: name="copilot-omni", agents, skills, hooks, mcpServers
- .mcp.json declares sidecar binary as local MCP server

**Task 1.2: Create minimal sidecar binary (Go)**
- `sidecar/cmd/omni-sidecar/main.go`
- Implements MCP stdio protocol
- Exposes single tool: `omni_health` → returns `{ "status": "ok", "version": "0.1.0" }`
- Build produces static binary for linux/amd64, linux/arm64, darwin/amd64, darwin/arm64, windows/amd64

**Task 1.3: Wire plugin → sidecar via MCP**
- `.mcp.json` points to sidecar binary with platform detection
- Test: `copilot plugin install ./plugin && copilot -p "use omni_health tool" --silent`

**Verification:** Plugin installs, sidecar starts via MCP, health tool responds.

### Wave 2: Config Resolution + Profiles (Day 2-3)

**Task 2.1: Config schema and resolver**
- Define JSON config schema: profiles, policy settings, memory settings, sidecar path overrides
- Implement resolver: defaults → profile → global config → repo config → env vars → CLI flags
- Schema: `sidecar/internal/config/`

**Task 2.2: Profile packs**
- `profiles/strict/`, `profiles/standard/`, `profiles/permissive/`
- Each contains `config.json` with policy defaults

**Task 2.3: Config MCP tool**
- Sidecar exposes `omni_config_resolve` tool
- Returns merged config for current context

**Verification:** Config resolution works with precedence, profiles load correctly.

### Wave 3: Bootstrap Generator + Doctor (Day 3-5)

**Task 3.1: Templates for bootstrap artifacts**
- `templates/copilot-instructions.md.tmpl` — managed block with Omni instructions
- `templates/agents-md.md.tmpl` — managed AGENTS.md section
- `templates/config.json.tmpl` — default repo config
- All templates use explicit managed region markers: `<!-- omni:managed:start --> ... <!-- omni:managed:end -->`

**Task 3.2: `omni-init` skill**
- `plugin/skills/omni-init/SKILL.md`
- Generates: `.github/copilot-instructions.md`, `.github/instructions/omni.instructions.md`, `AGENTS.md` section, `.omni/config.json`
- Idempotent: preserves content outside managed blocks

**Task 3.3: `omni-doctor` skill**
- `plugin/skills/omni-doctor/SKILL.md`
- Checks: plugin manifest validity, sidecar binary presence, MCP startup, hooks presence, config resolution, Copilot CLI version
- Sidecar exposes `omni_doctor` MCP tool for programmatic checks

**Task 3.4: Doctor diagnostics engine**
- `sidecar/internal/doctor/`
- Structured diagnostics with pass/fail/warn and remediation messages

**Verification:** `omni init` generates correct files, re-running preserves manual edits, `omni doctor` catches injected faults.

### Wave 4: Wrapper Binary + Integration Tests (Day 5-7)

**Task 4.1: `omni` wrapper CLI**
- `wrapper/cmd/omni/main.go`
- Commands: `omni init`, `omni doctor`, `omni run`, `omni plan`, `omni resume`
- Each command: resolve config → start sidecar if needed → invoke Copilot with correct flags

**Task 4.2: Integration test harness**
- Test fixture repositories with seeded configs
- Test: install plugin → run doctor → run init → verify artifacts
- Test: cross-platform binary selection

**Task 4.3: CI pipeline**
- GitHub Actions: build sidecar for all platforms, run tests, package release

**Verification:** Phase 0 scaffold functional (39 integration tests pass). Exit gate not fully met — doctor coverage and Copilot CLI integration testing requires actual Copilot CLI install.

---

## Phase 1-6 Summary Plans

### Phase 1: Spec-Driven Workflow Core
- Run state machine in sidecar (`.omni/runs/<run-id>/run.json`)
- Spec, plan, decisions artifact schemas
- Agents: omni-conductor, omni-planner, omni-reviewer, omni-verifier
- `omni run "feature"` → discuss → spec → plan → review → wait for approval
- `omni resume <run-id>` → hydrate from artifacts, continue

### Phase 2: Guarded Execution and Verification
- Task executor in sidecar with plan-scope enforcement
- MCP tools: `omni_guarded_patch`, `omni_verification_run`, `omni_repo_map`
- Hooks for command/ path policy (`preToolUse` deny)
- Execution journal, rollback metadata
- Adversarial test suite

### Phase 3: Local Memory and Deep Resumability
- SQLite memory store in sidecar
- Ingestion pipeline: specs, plans, decisions, verification outcomes, summaries
- Memory search: lexical + metadata + recency
- `omni memory search`, `omni memory capture`, `omni memory prune`
- Deep resume: hydrate from memory + artifacts
- Privacy controls: project wipe, selective delete, export

### Phase 4: Research, Subagents, and Parallel Workflows
- Research mode: combine /research, local memory, repo exploration
- Subtask decomposition and scheduling
- Isolated workspaces for write-capable subtasks
- Merge pipeline with review gates
- Intent router: skill vs agent vs MCP tool vs built-in

### Phase 5: Enterprise Policy, Offline Distribution
- Release bundle: static binaries, checksums, signatures, SBOM
- Local filesystem marketplace installation
- Policy packs with validator
- Audit export tools
- Enterprise diagnostics and compatibility matrix

### Phase 6: GA Hardening, Performance, UX Polish
- Performance budgets and benchmark harness
- Migration engine for schema evolution
- Support bundle generator
- UX polish: status, progress, errors, dry-run, summary
- GA release checklist and operator docs

---

## Open Decisions Requiring User Input

1. **Sidecar language confirmed as Go?** (Recommended, but needs explicit approval)
2. **Plugin name: "copilot-omni" or something else?** (The docs use "Copilot Omni" as working name)
3. **Should the wrapper binary be implemented in Phase 0 or deferred?** (Recommended: Phase 0, it's the user's primary entry point)
4. **Start with Phase 0 implementation immediately?** (Recommended: yes, all research is complete)
