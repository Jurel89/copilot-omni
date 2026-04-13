$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tempRepo = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-smoke-" + [System.Guid]::NewGuid().ToString('N'))
$fakeBin = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-fake-bin-" + [System.Guid]::NewGuid().ToString('N'))
$pluginInstallRecord = Join-Path $tempRepo 'plugin-install-path.txt'
$pluginInstallMcpSnapshot = Join-Path $tempRepo 'plugin-install-mcp.json'

New-Item -ItemType Directory -Path $tempRepo | Out-Null
New-Item -ItemType Directory -Path $fakeBin | Out-Null

try {
    $sidecarExe = Join-Path $repoRoot 'sidecar/omni-sidecar.exe'
    $wrapperExe = Join-Path $repoRoot 'wrapper/omni.exe'
    $fakeCopilotSource = Join-Path $fakeBin 'copilot.go'
    $fakeCopilot = Join-Path $fakeBin 'copilot.exe'

    if (-not (Test-Path $sidecarExe)) { throw "Missing sidecar binary: $sidecarExe" }
    if (-not (Test-Path $wrapperExe)) { throw "Missing wrapper binary: $wrapperExe" }

    Set-Content -Path $fakeCopilotSource -Value @"
package main

import (
    "fmt"
    "io"
    "os"
    "path/filepath"
)

func main() {
    args := os.Args[1:]
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
    fmt.Fprintln(os.Stderr, "unexpected fake copilot invocation", args)
    os.Exit(1)
}
"@
    & go build -o $fakeCopilot $fakeCopilotSource | Out-Host
    $env:PATH = "$fakeBin;$env:PATH"
    $env:FAKE_COPILOT_PLUGIN_INSTALL_RECORD = $pluginInstallRecord
    $env:FAKE_COPILOT_PLUGIN_MCP_SNAPSHOT = $pluginInstallMcpSnapshot

    & $wrapperExe doctor | Out-Host
    Push-Location $tempRepo
    try {
        & $wrapperExe init | Out-Host
    }
    finally {
        Pop-Location
    }

    $expected = @(
        '.omni/config.json',
        '.github/copilot-instructions.md',
        '.github/instructions/omni.instructions.md',
        'AGENTS.md'
    )

    foreach ($relativePath in $expected) {
        $fullPath = Join-Path $tempRepo $relativePath
        if (-not (Test-Path $fullPath)) {
            throw "Missing generated file: $fullPath"
        }
    }

    & $wrapperExe plugin install | Out-Host
    if (-not (Test-Path $pluginInstallRecord)) {
        throw "Plugin install did not invoke fake copilot"
    }
    if (-not (Test-Path $pluginInstallMcpSnapshot)) {
        throw "Plugin install did not snapshot staged .mcp.json"
    }

    $mcp = Get-Content $pluginInstallMcpSnapshot -Raw | ConvertFrom-Json
    $command = $mcp.mcpServers.'copilot-omni-sidecar'.command
    if ($command -ne $sidecarExe) {
        throw "Expected staged sidecar command $sidecarExe, got $command"
    }
}
finally {
    foreach ($path in @($tempRepo, $fakeBin)) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }
}
