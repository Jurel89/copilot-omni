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

    $fakeCopilot = Join-Path $fakeBin 'copilot.bat'
    Set-Content -Path $fakeCopilot -Value @"
@echo off
if "%1"=="plugin" if "%2"=="install" (
  > "%FAKE_COPILOT_PLUGIN_INSTALL_RECORD%" <nul set /p =%3
  copy /Y "%3\.mcp.json" "%FAKE_COPILOT_PLUGIN_MCP_SNAPSHOT%" >nul
  exit /b 0
)

>> "%FAKE_COPILOT_WORKFLOW_ARGS_RECORD%" echo %*
echo %* | findstr /C:"--agent=omni-planner" >nul
if not errorlevel 1 (
  echo {"version":"1","run_id":"fake-run","tasks":[{"id":"task-1","title":"verify installed workflow","description":"ensure installed workflow can use trusted plugin assets","dependencies":[],"file_targets":[],"verification_cmd":"echo ok","rollback_note":"none"}]}
  exit /b 0
)

echo %* | findstr /C:"--agent=omni-reviewer" >nul
if not errorlevel 1 (
  echo REVIEW OK
  exit /b 0
)

echo DISCUSS OR SPEC OK
exit /b 0
"@
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
