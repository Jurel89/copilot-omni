# Phase 5 Plan — Enterprise Policy, Offline Distribution, and Operability

## 1. Summary
Phase 5 makes Copilot Omni deployable in conservative enterprise environments by hardening packaging, policy packs, offline installation, diagnostics, and audit export. The goal is not more workflow capability; it is predictable installation, explicit governance, and supportable operation when registries, networks, or GitHub capabilities are restricted.

## 2. Dependencies
- Phases 1-4 are feature-complete enough to package and govern.
- Sidecar policy decisions, memory controls, run journals, and verification reports are already machine-readable.
- Wrapper and plugin assets can already run locally without cloud dependencies beyond Copilot itself.
- Existing profile packs in `profiles/` are the baseline for enterprise policy-pack evolution.

## 3. Implementation Waves

### Wave 1 — Release bundle and policy-pack contracts
Parallel tasks: bundle manifest, policy-pack schema, compatibility report schema.

### Wave 2 — Release/build pipeline and offline installation tooling
Parallel tasks: static binary packaging, checksums/signatures/SBOM, marketplace/install assets.

### Wave 3 — Enterprise validation, audit export, and diagnostics
Parallel tasks: policy validator, audit export tools, enterprise diagnostics, relocatable path support.

### Wave 4 — Air-gapped and cross-platform acceptance matrix
Parallel tasks: offline install tests, strict-profile compatibility tests, support workflows.

## 4. Task Specifications

### Task 1.1 — Define release and policy-pack schemas
- **File paths**:
  - `sidecar/internal/release/manifest.go`
  - `sidecar/internal/policy/pack_schema.go`
  - `sidecar/internal/audit/schema.go`
  - `sidecar/schemas/release-manifest.schema.json`
  - `sidecar/schemas/policy-pack.schema.json`
  - `sidecar/schemas/audit-export.schema.json`
- **What to implement**:
  - Release manifest fields for version, target platform, checksums, signatures, SBOM location, and provenance metadata.
  - Policy-pack schema covering commands, tools, protected paths, network posture, memory retention, and update behavior.
  - Audit export schema for run status, policy decisions, verification outcomes, and packaging metadata.
- **Success criteria**:
  - Schemas validate deterministic bundle metadata and policy packs in CI.
  - Audit export shape is stable enough for support tooling.
- **Constraints**:
  - Do not let enterprise governance live only in docs.
  - Do not store secrets inside bundle metadata or audit exports.

### Task 1.2 — Upgrade config/profile model for enterprise defaults and relocatable paths
- **File paths**:
  - `sidecar/internal/config/config.go`
  - `sidecar/internal/config/resolver.go`
  - `profiles/strict/config.json`
  - `profiles/standard/config.json`
  - `profiles/permissive/config.json`
  - `templates/config.json.tmpl`
- **What to implement**:
  - Profile fields for update behavior, marketplace roots, network posture, audit defaults, export redaction, and relocatable cache/config directories.
  - Resolver support for portable installations and explicit path overrides.
  - Strict-profile defaults that disable or warn on weakly enforced enterprise controls.
- **Success criteria**:
  - Resolved config reflects offline/portable operation paths correctly.
  - Profile validation tests catch unknown or inconsistent enterprise settings.
- **Constraints**:
  - Do not make online registry access a hard requirement.
  - Do not assume GitHub enterprise settings fully enforce local policy.

### Task 2.1 — Build release bundle pipeline
- **File paths**:
  - `scripts/release/build-bundles.sh`
  - `scripts/release/generate-sbom.sh`
  - `scripts/release/sign-release.sh`
  - `plugin/marketplace.json`
  - `wrapper/internal/version/version.go`
  - `sidecar/internal/version/version.go`
  - `docs/offline-install.md`
- **What to implement**:
  - Cross-platform bundle generation with static binaries, plugin assets, checksums, signatures, SBOMs, and provenance metadata.
  - Local filesystem marketplace metadata and install instructions.
  - Version injection so plugin, wrapper, and sidecar report a consistent release version.
- **Success criteria**:
  - Release output contains all required artifacts for Linux, macOS, and Windows targets.
  - A local marketplace root can serve the packaged plugin bundle.
- **Constraints**:
  - Do not rely on npm, PyPI, or package-manager installation steps for the plugin itself.
  - Do not publish unsigned or unchecksummed release bundles.

### Task 2.2 — Add offline install and bootstrap tooling
- **File paths**:
  - `scripts/install/install-local-marketplace.sh`
  - `scripts/install/install-from-bundle.sh`
  - `docs/operator/install-from-marketplace.md`
  - `docs/operator/install-from-local-path.md`
  - `docs/operator/portable-operation.md`
- **What to implement**:
  - Repeatable installation flows for local filesystem marketplace roots, direct local paths, and internal Git URLs.
  - Portable operation guidance for relocatable config/cache directories.
  - Operator docs that spell out prerequisites, trust steps, and verification commands.
- **Success criteria**:
  - Installation succeeds in air-gapped test environments using only shipped artifacts.
  - Docs are sufficient for a fresh operator to install without reading source code.
- **Constraints**:
  - Do not assume internet access during install.
  - Do not make operator instructions wrapper-source-code dependent.

### Task 3.1 — Implement policy-pack validator and enterprise diagnostics
- **File paths**:
  - `sidecar/internal/policy/validator.go`
  - `sidecar/internal/doctor/enterprise.go`
  - `sidecar/internal/doctor/compatibility.go`
  - `wrapper/cmd/omni/main.go`
  - `wrapper/internal/workflow/doctor.go`
  - `test/fixtures/phase5/policy-packs/`
- **What to implement**:
  - CI-friendly policy-pack validation with deterministic failure messages.
  - Enterprise diagnostics that warn when GitHub or environment settings limit available capabilities.
  - Compatibility reporting surfaced through `omni doctor` or a dedicated enterprise subcommand.
- **Success criteria**:
  - Invalid policy packs fail fast with precise remediation.
  - Diagnostics clearly separate hard blockers from degraded capability warnings.
- **Constraints**:
  - Do not mask unsupported enterprise controls as enforced.
  - Do not bury environment problems inside generic health output.

### Task 3.2 — Add audit export tools
- **File paths**:
  - `sidecar/internal/audit/export.go`
  - `sidecar/internal/audit/redaction.go`
  - `sidecar/internal/mcp/tools.go`
  - `sidecar/internal/mcp/tool_audit_export.go`
  - `sidecar/internal/mcp/tool_policy_validate.go`
  - `wrapper/internal/workflow/audit.go`
  - `plugin/skills/omni-audit/SKILL.md`
- **What to implement**:
  - Export of run status, policy decisions, verification outcomes, and packaging metadata in a portable schema.
  - Redaction rules for secrets and sensitive memory content.
  - Wrapper and skill entry points for audit collection.
- **Success criteria**:
  - Audit exports let support teams reconstruct run state without exposing secrets.
  - Export contents validate against the audit schema.
- **Constraints**:
  - Do not dump raw secrets or full unredacted transcripts by default.
  - Do not make audit export dependent on network access.

### Task 4.1 — Run the enterprise acceptance matrix
- **File paths**:
  - `test/integration-phase5.sh`
  - `test/offline/airgap-install.sh`
  - `test/offline/portable-paths.sh`
  - `test/fixtures/phase5/local-marketplace/`
  - `docs/operator/compatibility-matrix.md`
- **What to implement**:
  - Air-gapped install checks for macOS, Linux, and Windows images.
  - Strict-profile tests for update disabling, registry blocking, and capability warnings.
  - Compatibility matrix documenting supported and degraded environments.
- **Success criteria**:
  - Offline install success rate meets the phase target on the supported matrix.
  - Strict profile behavior is reproducible and documented.
- **Constraints**:
  - Do not declare success from Linux-only validation.
  - Do not leave known degraded environments undocumented.

## 5. Sidecar MCP Tools to Add

### `omni_policy_validate`
- **Input schema**: `{ repo_root: string, policy_pack_path?: string, profile?: string }`
- **Output format**: JSON `{ valid: boolean, profile, errors: [], warnings: [], normalized_policy?: object }`
- **Behavior description**: Validates a policy pack or resolved profile configuration and returns deterministic errors suitable for CI and operator use.

### `omni_audit_export`
- **Input schema**: `{ repo_root: string, run_id?: string, format?: "json"|"jsonl", output_path?: string, include_packaging?: boolean }`
- **Output format**: JSON `{ exported: true, output_path, record_count, redactions_applied, schema_version }`
- **Behavior description**: Produces a portable audit export containing run, policy, verification, and optional packaging metadata with redaction applied.

### `omni_enterprise_diagnose`
- **Input schema**: `{ repo_root: string, include_environment?: boolean, include_marketplace?: boolean }`
- **Output format**: JSON `{ status, compatibility: { supported, degraded, blockers }, diagnostics: [], recommendations: [] }`
- **Behavior description**: Evaluates active environment constraints, GitHub/Copilot limitations, marketplace configuration, and profile posture for enterprise support scenarios.

## 6. Plugin Components to Add
- Add `plugin/skills/omni-audit/SKILL.md` for operator-facing audit export collection.
- Update `plugin/skills/omni-doctor/SKILL.md` so enterprise compatibility results are visible and actionable.
- Add `plugin/marketplace.json` for local marketplace installation.
- Update `plugin/hooks.json` only where enterprise policy packs change deny behavior and ensure sidecar remains authoritative.
- Keep all components namespaced and installable from local path, internal Git, or marketplace root.

## 7. Verification Checklist
- Release bundle generation produces static binaries, checksums, signatures, SBOMs, and provenance metadata.
- The product installs from a local marketplace root added with `copilot plugin marketplace add /PATH/TO/MARKETPLACE`.
- Strict profile disables or warns on features that depend on weakly enforced enterprise controls.
- Audit exports contain enough data to reconstruct run status, verification state, and policy decisions without exposing secrets.
- Offline installation passes on macOS, Linux, and Windows images without package-manager access.
- Policy-pack validation is deterministic and CI-friendly.

## 8. Risks and Mitigations
- **Risk: release engineering becomes a separate project.** Mitigation: freeze bundle format and signing inputs early and validate them in CI every release.
- **Risk: enterprise users assume GitHub enforces more than it does.** Mitigation: surface compatibility gaps explicitly in diagnostics and strict-profile warnings.
- **Risk: portable installs cause path bugs.** Mitigation: centralize relocatable path resolution in config and test it in offline fixtures.
- **Risk: audit exports leak sensitive data.** Mitigation: require redaction defaults, schema review, and seeded support-bundle privacy tests.
