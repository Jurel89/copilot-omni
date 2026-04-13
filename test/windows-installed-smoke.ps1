$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$wrapperExe = Join-Path $repoRoot 'wrapper/omni.exe'
$bundleDir = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-bundle-" + [System.Guid]::NewGuid().ToString('N'))
$installPrefix = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-install-" + [System.Guid]::NewGuid().ToString('N'))
$projectDir = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-project-" + [System.Guid]::NewGuid().ToString('N'))
$fakeBin = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-fake-bin-" + [System.Guid]::NewGuid().ToString('N'))
$pluginInstallRecord = Join-Path $projectDir 'plugin-install-path.txt'
$pluginInstallMcpSnapshot = Join-Path $projectDir 'plugin-install-mcp.json'
$workflowArgsRecord = Join-Path $projectDir 'workflow-args.txt'

New-Item -ItemType Directory -Path $bundleDir | Out-Null
New-Item -ItemType Directory -Path $installPrefix | Out-Null
New-Item -ItemType Directory -Path $projectDir | Out-Null
New-Item -ItemType Directory -Path $fakeBin | Out-Null

try {
    if (-not (Test-Path $wrapperExe)) { throw "Missing wrapper binary: $wrapperExe" }

    $fakeCopilotSource = Join-Path $fakeBin 'copilot.go'
    $fakeCopilot = Join-Path $fakeBin 'copilot.exe'
    Set-Content -Path $fakeCopilotSource -Value @"
package main

import (
    "fmt"
    "io"
    "os"
    "path/filepath"
    "strings"
)

func main() {
    args := os.Args[1:]
    joined := strings.Join(args, " ")
    if record := os.Getenv("FAKE_COPILOT_WORKFLOW_ARGS_RECORD"); record != "" {
        _ = os.WriteFile(record, []byte(joined), 0o644)
    }

    if len(args) >= 3 && args[0] == "plugin" && args[1] == "install" {
        target := args[2]
        if err := os.WriteFile(os.Getenv("FAKE_COPILOT_PLUGIN_INSTALL_RECORD"), []byte(target), 0o644); err != nil {
            fmt.Fprintln(os.Stderr, err)
            os.Exit(1)
        }
        src, err := os.Open(filepath.Join(target, ".mcp.json"))
        if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
        defer src.Close()
        dst, err := os.Create(os.Getenv("FAKE_COPILOT_PLUGIN_MCP_SNAPSHOT"))
        if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
        defer dst.Close()
        if _, err := io.Copy(dst, src); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
        return
    }

    if strings.Contains(joined, "--agent=omni-planner") {
        fmt.Print(`{"version":"1","run_id":"fake-run","tasks":[{"id":"task-1","title":"verify installed workflow","description":"ensure installed workflow can use trusted plugin assets","dependencies":[],"file_targets":[],"verification_cmd":"echo ok","rollback_note":"none"}]}`)
        return
    }
    if strings.Contains(joined, "--agent=omni-reviewer") {
        fmt.Print("REVIEW OK")
        return
    }
    if len(args) > 0 && args[0] == "-p" {
        fmt.Print("DISCUSS OK")
        return
    }

    fmt.Print("DISCUSS OR SPEC OK")
}
"@
    & go build -o $fakeCopilot $fakeCopilotSource | Out-Host
    $env:PATH = "$fakeBin;$env:PATH"
    $env:FAKE_COPILOT_PLUGIN_INSTALL_RECORD = $pluginInstallRecord
    $env:FAKE_COPILOT_PLUGIN_MCP_SNAPSHOT = $pluginInstallMcpSnapshot
    $env:FAKE_COPILOT_WORKFLOW_ARGS_RECORD = $workflowArgsRecord

    & $wrapperExe bundle create $bundleDir | Out-Host
    & $wrapperExe bundle install --bundle-dir $bundleDir --target $installPrefix | Out-Host

    $installedWrapper = Join-Path $installPrefix 'bin/omni.exe'
    if (-not (Test-Path $installedWrapper)) {
        throw "Installed wrapper missing: $installedWrapper"
    }

    & $installedWrapper doctor | Out-Host
    & $installedWrapper plugin install | Out-Host

    Push-Location $projectDir
    try {
        & $installedWrapper init | Out-Host
        & $installedWrapper plan "Validate installed workflow" | Out-Host
    }
    finally {
        Pop-Location
    }

    $shareRoot = Join-Path $installPrefix 'share/copilot-omni'
    foreach ($requiredPath in @('plugin', 'templates', 'policies', 'marketplace.json', 'release-manifest.json')) {
        $fullPath = Join-Path $shareRoot $requiredPath
        if (-not (Test-Path $fullPath)) {
            throw "Installed asset missing: $fullPath"
        }
    }

    if (-not (Test-Path $pluginInstallRecord)) {
        throw "Installed plugin install did not invoke fake copilot"
    }
    $mcp = Get-Content $pluginInstallMcpSnapshot -Raw | ConvertFrom-Json
    $installedSidecar = Join-Path $installPrefix 'bin/omni-sidecar.exe'
    if ($mcp.mcpServers.'copilot-omni-sidecar'.command -ne $installedSidecar) {
        throw "Expected installed staged sidecar command $installedSidecar"
    }

    if (-not (Test-Path $workflowArgsRecord)) {
        throw "Installed workflow did not invoke fake copilot"
    }
    $workflowArgs = Get-Content $workflowArgsRecord -Raw
    $expectedAddDir = "--add-dir=$shareRoot\plugin"
    if ($workflowArgs -notmatch [regex]::Escape($expectedAddDir)) {
        throw "Expected workflow copilot args to include $expectedAddDir`nActual: $workflowArgs"
    }
    if (-not (Get-ChildItem -Path (Join-Path $projectDir '.omni/plans') -Filter '*.json' -ErrorAction SilentlyContinue)) {
        throw "Installed workflow did not create a plan artifact"
    }
}
finally {
    foreach ($path in @($bundleDir, $installPrefix, $projectDir, $fakeBin)) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }
}
