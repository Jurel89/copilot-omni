# Phase 5 Deferral: Windows Offline Install

**Deferral ID:** PHASE-5-DEFER-001
**Owner:** Copilot Omni team
**Date:** 2026-04-11
**Status:** Deferred to Phase 6 (GA Hardening)

## Rationale

The PRD exit gate requires offline install tests on macOS, Linux, and Windows. Phase 5 ships a Bash-based installer (`scripts/install-offline.sh`) that supports Linux and macOS with portable checksum verification (sha256sum/shasum/openssl auto-detection).

Windows offline install requires either:
1. A PowerShell installer script (`install-offline.ps1`), or
2. A cross-platform Go-based installer binary

This work is deferred to Phase 6 (GA Hardening, UX, Performance) because:
- Phase 6 explicitly addresses cross-platform packaging and install tests
- The current Bash installer validates the offline distribution architecture end-to-end on Linux/macOS
- Windows CI images and PowerShell testing infrastructure are not yet available
- The core bundle format, validation, and marketplace metadata are platform-agnostic

## Acceptance Criteria for Phase 6

- [ ] `scripts/install-offline.ps1` or equivalent Windows installer
- [ ] CI matrix includes Windows offline install test
- [ ] `sha256` verification uses `Get-FileHash` on Windows
- [ ] marketplace.json paths work on Windows (backslash handling)
