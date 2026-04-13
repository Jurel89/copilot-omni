$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$wrapperExe = Join-Path $repoRoot 'wrapper/omni.exe'
$bundleDir = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-bundle-" + [System.Guid]::NewGuid().ToString('N'))
$installPrefix = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-install-" + [System.Guid]::NewGuid().ToString('N'))
$projectDir = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-project-" + [System.Guid]::NewGuid().ToString('N'))

New-Item -ItemType Directory -Path $bundleDir | Out-Null
New-Item -ItemType Directory -Path $installPrefix | Out-Null
New-Item -ItemType Directory -Path $projectDir | Out-Null

try {
    if (-not (Test-Path $wrapperExe)) { throw "Missing wrapper binary: $wrapperExe" }

    & $wrapperExe bundle create $bundleDir | Out-Host
    & $wrapperExe bundle install --bundle-dir $bundleDir --target $installPrefix | Out-Host

    $installedWrapper = Join-Path $installPrefix 'bin/omni.exe'
    if (-not (Test-Path $installedWrapper)) {
        throw "Installed wrapper missing: $installedWrapper"
    }

    & $installedWrapper doctor | Out-Host

    Push-Location $projectDir
    try {
        & $installedWrapper init | Out-Host
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
}
finally {
    foreach ($path in @($bundleDir, $installPrefix, $projectDir)) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }
}
