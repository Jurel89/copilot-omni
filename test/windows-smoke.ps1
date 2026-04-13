$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tempRepo = Join-Path ([System.IO.Path]::GetTempPath()) ("omni-win-smoke-" + [System.Guid]::NewGuid().ToString('N'))

New-Item -ItemType Directory -Path $tempRepo | Out-Null

try {
    $sidecarExe = Join-Path $repoRoot 'sidecar/omni-sidecar.exe'
    $wrapperExe = Join-Path $repoRoot 'wrapper/omni.exe'

    if (-not (Test-Path $sidecarExe)) { throw "Missing sidecar binary: $sidecarExe" }
    if (-not (Test-Path $wrapperExe)) { throw "Missing wrapper binary: $wrapperExe" }

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
}
finally {
    if (Test-Path $tempRepo) {
        Remove-Item $tempRepo -Recurse -Force
    }
}
