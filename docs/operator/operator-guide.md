# Copilot Omni Operator Guide

## Overview

This guide is for operators who need to deploy, monitor, and troubleshoot Copilot Omni in production environments.

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Monitoring](#monitoring)
4. [Troubleshooting](#troubleshooting)
5. [Support Bundles](#support-bundles)
6. [Migrations](#migrations)
7. [Performance Tuning](#performance-tuning)

## Installation

### Prerequisites

- Git 2.40+
- GitHub Copilot CLI 1.0+
- macOS, Linux, or Windows

### Standard Installation

```bash
# Install from marketplace
copilot plugin install github.com/copilot-omni/copilot-omni

# Or install from local build
copilot plugin install ./plugin
```

### Offline Installation

For air-gapped environments:

```bash
# Download offline bundle from release
curl -L -o copilot-omni-offline.tar.gz https://github.com/copilot-omni/releases/download/v1.0.0/copilot-omni-offline.tar.gz

# Extract and run installer
tar -xzf copilot-omni-offline.tar.gz
cd copilot-omni-offline
./scripts/install-offline.sh
```

## Configuration

### Configuration Files

Copilot Omni uses a layered configuration system:

1. **System defaults** - Built-in defaults
2. **User config** - `~/.copilot-omni/config.json`
3. **Repository config** - `.omni/config.json`
4. **Environment variables** - `OMNI_*`

### Key Settings

```json
{
  "profile": "standard",
  "policy": {
    "protected_paths": [
      ".env",
      "*.key",
      "*.pem"
    ],
    "blocked_commands": [
      "rm -rf /",
      "mkfs.*"
    ]
  },
  "memory": {
    "enabled": true,
    "db_path": ".omni/memory.db",
    "retention_days": 90
  },
  "enterprise": {
    "offline_mode": false,
    "audit_retention": 365,
    "signing_enabled": false
  }
}
```

### Profile Settings

Three profiles are available:

- **permissive** - Minimal restrictions, suitable for development
- **standard** - Balanced security and convenience (default)
- **strict** - Maximum security, requires explicit approvals

## Monitoring

### Health Checks

Check system health:

```bash
omni doctor
```

### Benchmarking

Run performance benchmarks:

```bash
# Run all benchmarks
omni benchmark run

# Run specific category
omni benchmark run --category startup

# Generate report
omni benchmark report --format markdown
```

### Audit Logs

Export audit logs for compliance:

```bash
omni audit export --run-id <run-id>
```

## Troubleshooting

### Common Issues

#### Issue: Slow cold start

**Symptoms**: First command takes >5 seconds

**Diagnosis**:
```bash
omni benchmark run --category startup
```

**Resolution**:
- Check disk I/O performance
- Verify sidecar binary is cached
- Consider warming the sidecar on boot

#### Issue: Memory search timeout

**Symptoms**: Memory queries hang or timeout

**Diagnosis**:
```bash
omni doctor --check memory
```

**Resolution**:
- Check database file size: `ls -lh .omni/memory.db`
- Rebuild indexes: `omni memory reindex`
- Prune old records: `omni memory prune --max-age-days 30`

#### Issue: Policy violations blocking work

**Symptoms**: Commands rejected unexpectedly

**Diagnosis**:
```bash
omni policy check --operation command --value "<command>"
```

**Resolution**:
- Review blocked command in audit log
- Update policy pack if needed
- Use `permissive` profile temporarily for debugging

## Support Bundles

### Creating a Support Bundle

Generate a support bundle for troubleshooting:

```bash
# Basic bundle
omni support-bundle create

# Include logs (larger bundle)
omni support-bundle create --include-logs

# Maximum redaction
omni support-bundle create --redaction-level aggressive
```

### Bundle Contents

A support bundle includes:
- System information (OS, version, arch)
- Configuration files (sanitized)
- Recent logs
- Run artifacts (last 10 runs)
- Memory statistics
- Policy audit trail

### Redaction Levels

- **minimal** - Remove only secrets and tokens
- **standard** - Also remove file paths and usernames
- **aggressive** - Remove all potentially identifying information

## Migrations

### Checking Migration Status

```bash
omni migrate status
```

### Running Migrations

```bash
# Migrate to latest
omni migrate up

# Dry-run (no changes)
omni migrate up --dry-run

# Migrate to specific version
omni migrate up --target-version 1.2.0
```

### Rollback

```bash
# Rollback one version
omni migrate down

# Rollback to specific version
omni migrate down --target-version 1.1.0
```

### Migration Safety

- Always backup before migrating
- Test migrations in staging first
- Migrations are reversible within version window
- Use `--dry-run` to preview changes

## Performance Tuning

### Performance Budgets

Phase 6 defines these performance budgets:

| Operation | Target p95 |
|-----------|------------|
| Cold start | 1.5s |
| Memory search | 150ms |
| Policy check | 50ms |
| Artifact load | 100ms |
| Plan parse | 200ms |

### Optimization Tips

1. **SSD Storage**: Use SSD for `.omni/` directory
2. **Adequate RAM**: Ensure 4GB+ available
3. **Exclude Large Directories**: Add to `.gitignore`
4. **Regular Pruning**: Set up automated memory pruning
5. **Profile Selection**: Use `standard` profile for best balance

### Benchmarking Your Environment

```bash
# Run benchmarks
omni benchmark run

# Compare to budgets
omni benchmark report

# Save for comparison
omni benchmark run --save-results
```

## Enterprise Deployment

### Policy Packs

Deploy organization-wide policy:

```bash
# Validate policy pack
omni policy-pack validate --path policies/strict.json

# Deploy to organization
# (See enterprise documentation)
```

### Offline Mode

For air-gapped environments:

```json
{
  "enterprise": {
    "offline_mode": true,
    "audit_retention": 365
  }
}
```

### Audit Retention

Configure audit log retention:

```json
{
  "enterprise": {
    "audit_retention": 90
  }
}
```

## Emergency Procedures

### Complete Reset

**Warning**: This deletes all data

```bash
# Stop all omni processes
pkill -f omni

# Backup first
cp -r .omni .omni.backup.$(date +%Y%m%d)

# Reset
rm -rf .omni/memory.db
omni init
```

### Recovery from Corruption

If database is corrupted:

```bash
# Rebuild from artifacts
omni memory rebuild --from-artifacts

# Restore from backup
cp .omni.backup.*/memory.db .omni/memory.db
```

## Getting Help

### Support Channels

- **Issues**: https://github.com/copilot-omni/issues
- **Documentation**: https://docs.copilot-omni.io
- **Enterprise Support**: Contact your account manager

### Required Information

When reporting issues, include:
1. Support bundle
2. Steps to reproduce
3. Expected vs actual behavior
4. Environment details (OS, version)

---

**Version**: 1.0.0  
**Last Updated**: 2024-04-11
