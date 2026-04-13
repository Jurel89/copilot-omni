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
    $fakeCopilot = Join-Path $fakeBin 'copilot.bat'

    if (-not (Test-Path $sidecarExe)) { throw "Missing sidecar binary: $sidecarExe" }
    if (-not (Test-Path $wrapperExe)) { throw "Missing wrapper binary: $wrapperExe" }

    Set-Content -Path $fakeCopilot -Value @"
@echo off
if "%1"=="plugin" if "%2"=="install" (
  > "%FAKE_COPILOT_PLUGIN_INSTALL_RECORD%" <nul set /p =%3
  copy /Y "%3\.mcp.json" "%FAKE_COPILOT_PLUGIN_MCP_SNAPSHOT%" >nul
  exit /b 0
)
echo unexpected fake copilot invocation %* 1>&2
exit /b 1
"@
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
