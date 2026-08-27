$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pnpm = "C:\Users\katzm\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
$nodeBin = "C:\Users\katzm\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"

if (-not (Test-Path -LiteralPath $pnpm)) {
    throw "Codex에 포함된 pnpm을 찾을 수 없습니다: $pnpm"
}

$env:Path = "$nodeBin;$env:Path"

Push-Location $projectRoot
try {
    $lockFile = Join-Path $projectRoot "pnpm-lock.yaml"
    if (Test-Path -LiteralPath $lockFile) {
        & $pnpm install --frozen-lockfile
    }
    else {
        & $pnpm install
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Discord 커넥터 설치에 실패했습니다."
    }
}
finally {
    Pop-Location
}

Write-Host "프로젝트 전용 Discord 커넥터 설치가 완료되었습니다."
