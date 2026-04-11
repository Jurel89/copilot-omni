# Copilot Omni GA Release Checklist

This checklist ensures all Phase 6 requirements are met before declaring GA.

## Phase 6 Requirements Verification

### Performance Budgets (PHASE-6-NFR-001, PHASE-6-NFR-002)

- [ ] Cold start p95 <= 1.5 seconds on target dev hardware
  - [ ] Test on macOS (Intel)
  - [ ] Test on macOS (Apple Silicon)
  - [ ] Test on Linux (x64)
  - [ ] Test on Windows (x64)
- [ ] Memory search warm p95 <= 150ms
- [ ] Policy check p95 <= 50ms
- [ ] Artifact load p95 <= 100ms
- [ ] Plan parse p95 <= 200ms

### Functional Requirements

#### PHASE-6-FR-001: Versioned Migrations
- [ ] Migration engine implemented
- [ ] Config schema migrations work
- [ ] Artifact schema migrations work
- [ ] Memory schema migrations work
- [ ] Rollback functionality tested
- [ ] Migration validation works

#### PHASE-6-FR-002: Dry-Run and Summary Modes
- [ ] Dry-run mode for migrations implemented
- [ ] Dry-run mode for execution implemented
- [ ] Summary mode shows planned actions
- [ ] No side effects in dry-run mode

#### PHASE-6-FR-003: Support Bundle Generator
- [ ] Bundle creation works
- [ ] System info collected
- [ ] Config files collected
- [ ] Recent logs collected
- [ ] Run artifacts collected
- [ ] Redaction controls work
  - [ ] Minimal redaction level
  - [ ] Standard redaction level
  - [ ] Aggressive redaction level
- [ ] Bundle validation works

#### PHASE-6-FR-004: Benchmark Results and CI Gates
- [ ] Benchmark harness implemented
- [ ] All Phase 6 benchmarks defined
- [ ] CI integration for benchmarks
- [ ] Regression detection works
- [ ] Benchmark reports generated

#### PHASE-6-FR-005: UX Affordances
- [ ] Current phase displayed
- [ ] Active policy profile shown
- [ ] Run health indicator
- [ ] Pending blockers listed
- [ ] Next recommended command shown

### Non-Functional Requirements

#### PHASE-6-NFR-001: Cold Start Performance
- [ ] p95 cold start measured
- [ ] Performance budget met
- [ ] Regression tests in CI

#### PHASE-6-NFR-002: Latency Budgets
- [ ] Memory retrieval latency measured
- [ ] Policy check latency measured
- [ ] Artifact hydration latency measured
- [ ] All budgets within targets

#### PHASE-6-NFR-003: Upgrade/Downgrade Paths
- [ ] Upgrade path tested (previous -> current)
- [ ] Downgrade path tested (current -> previous)
- [ ] Data integrity verified
- [ ] Rollback procedure documented

### Success Metrics

- [ ] Cold start p95: <= 1.5s ✓
- [ ] Memory search warm p95: <= 150ms ✓
- [ ] Regression escape rate: 0 critical ✓
- [ ] Support bundle usefulness: >= 90% ✓

## Test Matrix

### Platforms
- [ ] macOS 14+ (Intel)
- [ ] macOS 14+ (Apple Silicon)
- [ ] Ubuntu 22.04+ (x64)
- [ ] Windows 11 (x64)

### Copilot CLI Versions
- [ ] Copilot CLI 1.0+
- [ ] Copilot CLI latest stable

### Git Versions
- [ ] Git 2.40+

## Documentation

- [ ] README updated
- [ ] Installation guide complete
- [ ] Quick start guide complete
- [ ] Operator guide complete
- [ ] Migration guide complete
- [ ] Troubleshooting guide complete
- [ ] API documentation complete

## Security Review

- [ ] Security audit passed
- [ ] No critical vulnerabilities
- [ ] Dependency review complete
- [ ] Secrets handling reviewed
- [ ] Policy enforcement verified

## Release Artifacts

- [ ] Version tagged (v0.1.0)
- [ ] Release notes drafted
- [ ] Binaries built for all platforms
- [ ] Checksums generated
- [ ] SBOM generated
- [ ] Signatures created
- [ ] Marketplace metadata updated

## Sign-Off

- [ ] Engineering sign-off
- [ ] QA sign-off
- [ ] Security sign-off
- [ ] Product sign-off
- [ ] Legal sign-off (if applicable)

## Post-Release

- [ ] Monitoring in place
- [ ] Support channels ready
- [ ] Incident response plan updated
- [ ] Rollback plan documented

## Deferred Items

Any items intentionally deferred should be listed here with:
- Item description
- Reason for deferral
- Target version for resolution
- Owner

---

**Release Date**: ___________
**Released By**: ___________
