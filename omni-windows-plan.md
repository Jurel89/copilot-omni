# Copilot Omni Windows / Installation Remediation Plan

## Purpose

This document captures the repository-specific remediation scope for Windows runtime, install, plugin, and bundle correctness in Copilot Omni.

## Problem Statement

Historically, the codebase conflated:

- workspace root (where `.omni/` artifacts belong)
- trusted product asset root (where `plugin/`, `templates/`, `policies/`, and metadata belong)
- runtime binary resolution (where `omni` and `omni-sidecar` actually execute from)

That worked in the happy-path source checkout on Unix-like systems, but broke for:

- Windows source builds (`.exe` naming and process management)
- installed/offline layouts (`<prefix>/bin` + `<prefix>/share/copilot-omni`)
- deterministic plugin installation (PATH-dependent sidecar launch)
- trustworthy diagnostics and runtime validation

## End State

After remediation, the product must satisfy all of the following:

1. `omni init` works in source mode and installed mode on Windows and Unix.
2. `omni doctor` reports trusted asset paths, sidecar resolution provenance, sidecar health, and actual MCP launch contract validity.
3. `omni plugin install` is deterministic and does not rely on users manually placing `omni-sidecar` on `PATH`.
4. Sidecar lifecycle uses cross-platform stdin-close semantics rather than Unix-only signal assumptions.
5. Release bundles are platform-correct, hermetic, and complete enough to support installed mode.
6. `omni bundle install` is hermetic/idempotent for managed content and rejects malformed or unexpected bundle contents.
7. CI proves real Windows runtime behavior rather than only cross-compiling.

## Implemented Workstreams

### 1. Trusted asset resolution

- Added trusted asset locators in `wrapper/internal/assets` and `sidecar/internal/assets`.
- Trusted assets now resolve from executable-relative source/install layouts or explicit overrides.
- Runtime code no longer trusts arbitrary workspace-local `plugin/` or `templates/` directories by default.

### 2. Cross-platform sidecar resolution and lifecycle

- Sidecar discovery is platform-aware and supports `.exe` naming on Windows.
- Installed layout prefers same-directory sidecar resolution from `<prefix>/bin`.
- Lifecycle uses stdin-close and process state instead of Unix-only signals.

### 3. Wrapper runtime and workflow correctness

- `omni init`, `omni doctor`, and workflow execution use trusted asset paths.
- `repoRoot()` correctly falls back for non-git source snapshots.
- Generation failures in init abort cleanly instead of partial success.

### 4. Deterministic plugin installation

- Added `omni plugin install` with staging.
- Managed plugin installs generate explicit sidecar command paths.
- Managed install state is persisted and preferred by diagnostics.

### 5. Diagnostics hardening

- Diagnostics validate the full MCP launch contract: `type`, `command`, and required `serve` args.
- Wrapper doctor shows sidecar resolution provenance and fallback diagnostics even when the sidecar cannot start.
- Compat no longer treats “binary exists” as “healthy”.

### 6. Bundle and install correctness

- Bundles include templates and platform-correct metadata.
- Bundle validation rejects missing required runtime binaries and unexpected files.
- `omni bundle install` rejects malformed bundles, stages installs, replaces managed content hermetically, and rolls back managed activations on failure.

### 7. Windows CI/runtime validation

- Added focused Windows source-mode and installed-mode smoke coverage.
- Windows smoke uses real `copilot.cmd` shim behavior rather than only a fake `.exe` path.
- PR CI now proves runtime/install behavior on Windows.

## Verification Matrix

The implemented work is verified by:

- `go test ./...` in `wrapper`
- `go test ./...` in `sidecar`
- `bash test/integration-test.sh`
- `bash test/integration-phase3.sh`
- `bash test/integration-phase4.sh`
- `bash test/integration-phase5.sh`
- PR CI checks:
  - `build`
  - `cross-compile`
  - `windows-runtime`

## Current Delivery Artifact

- PR: `fix/windows-install-remediation` → `main`
- PR URL: `https://github.com/Jurel89/copilot-omni/pull/12`

This document is committed to preserve traceability between the remediation request and the implemented branch state.
