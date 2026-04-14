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

Build and install both binaries together; the wrapper alone is not sufficient.

```bash
# Build from source checkout
cd sidecar && go build -o omni-sidecar ./cmd/omni-sidecar/ && cd ..
cd wrapper && go build -o omni ./cmd/omni/ && cd ..

# Verify runtime
./wrapper/omni doctor

# Bootstrap a target repository
./wrapper/omni init

# Install the Copilot plugin with a generated MCP config
./wrapper/omni plugin install
```

Windows PowerShell:

```powershell
Set-Location sidecar
go build -o omni-sidecar.exe ./cmd/omni-sidecar
Set-Location ..

Set-Location wrapper
go build -o omni.exe ./cmd/omni
Set-Location ..

.\wrapper\omni.exe doctor
.\wrapper\omni.exe init
.\wrapper\omni.exe plugin install
```

### Offline Installation

For air-gapped environments:

```bash
# Download offline bundle from release
curl -L -o copilot-omni-offline.tar.gz https://github.com/Jurel89/copilot-omni/releases/download/v0.1.0/copilot-omni-offline.tar.gz

# Extract and install using the bundled wrapper
tar -xzf copilot-omni-offline.tar.gz
cd copilot-omni-offline
./omni bundle install --bundle-dir . --target /usr/local
```

Windows PowerShell:

```powershell
Expand-Archive .\copilot-omni-offline.zip -DestinationPath .\copilot-omni-offline
Set-Location .\copilot-omni-offline
$installDir = "$env:LOCALAPPDATA\copilot-omni"
.\omni.exe bundle install --bundle-dir . --target $installDir
```

> **Note for Windows users:** The default install path uses your user-local app data directory so no Administrator rights are required.

Installed layout:

- binaries: `<prefix>/bin`
- trusted product assets: `<prefix>/share/copilot-omni`

After installation, add the bin directory to your user PATH so `omni` is available from any terminal:

```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:LOCALAPPDATA\copilot-omni\bin", "User")
```

Then verify the installation:

```powershell
omni doctor
omni init
omni plugin install
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
omni benchmark

# Run specific category
omni benchmark --category startup

# Run specific benchmark
omni benchmark --benchmark cold_start

# List available benchmarks
omni benchmark --list
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
omni benchmark --category startup
```

**Resolution**:
- Check disk I/O performance
- Verify sidecar binary is cached
- Consider warming the sidecar on boot

#### Issue: Memory search timeout

**Symptoms**: Memory queries hang or timeout

**Diagnosis**:
```bash
omni doctor
```

**Resolution**:
- Check database file size:
  - Linux/macOS: `ls -lh .omni/memory.db`
  - Windows PowerShell: `Get-Item .omni/memory.db | Select-Object Name,Length`
- Prune old records by configuring retention in `.omni/config.json`:
  ```json
  {
    "memory": {
      "retention_days": 30
    }
  }
  ```

#### Issue: Policy violations blocking work

**Symptoms**: Commands rejected unexpectedly

**Diagnosis**:
- Review blocked command in audit log: `omni audit <run-id>`
- Check policy configuration in `.omni/config.json`

**Resolution**:
- Update policy pack if needed
- Use `permissive` profile temporarily for debugging

## Support Bundles

### Creating a Support Bundle

Generate a support bundle for troubleshooting:

```bash
# Basic bundle
omni support-bundle

# Include logs (larger bundle)
omni support-bundle --include-logs

# Maximum redaction
omni support-bundle --redaction aggressive

# Include specific run
omni support-bundle --run-id <run-id>
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
omni migrate up --target-version 2
```

### Rollback

```bash
# Rollback one version
omni migrate down

# Rollback to specific version
omni migrate down --target-version 1
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
omni benchmark

# Run specific category
omni benchmark --category startup

# List available benchmarks
omni benchmark --list
```

## Enterprise Deployment

### Policy Packs

Deploy organization-wide policy by distributing configuration files:

```json
{
  "policy": {
    "protected_paths": [".env", "*.key", "*.pem"],
    "blocked_commands": ["rm -rf /", "mkfs.*"]
  }
}
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

Linux/macOS:

```bash
# Stop all omni processes
pkill -f omni

# Backup first
cp -r .omni .omni.backup.$(date +%Y%m%d)

# Reset
rm -rf .omni/memory.db
omni init
```

Windows PowerShell:

```powershell
Get-Process omni, omni-sidecar -ErrorAction SilentlyContinue | Stop-Process -Force
Copy-Item .omni ".omni.backup.$((Get-Date).ToString('yyyyMMdd'))" -Recurse
Remove-Item .omni\memory.db -Force
omni init
```

### Recovery from Corruption

If database is corrupted:

Linux/macOS:

```bash
# Restore from backup
cp .omni.backup.*/memory.db .omni/memory.db

# Or start fresh (will lose memory data)
rm .omni/memory.db
```

Windows PowerShell:

```powershell
Copy-Item .omni.backup.*\memory.db .omni\memory.db

# Or start fresh (will lose memory data)
Remove-Item .omni\memory.db -Force
```

## Getting Help

### Support Channels

- **Issues**: https://github.com/Jurel89/copilot-omni/issues
- **Documentation**: https://github.com/Jurel89/copilot-omni#readme
- **Enterprise Support**: Contact your account manager

### Required Information

When reporting issues, include:
1. Support bundle
2. Steps to reproduce
3. Expected vs actual behavior
4. Environment details (OS, version)

---

**Version**: 0.1.0  
**Last Updated**: 2025-04-11
