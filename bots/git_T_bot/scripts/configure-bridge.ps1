$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\katzm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Codex에 포함된 Python 실행 파일을 찾을 수 없습니다: $python"
}

Push-Location $projectRoot
try {
    & $python ".\scripts\configure-bridge.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Discord 브리지 설정 생성에 실패했습니다."
    }
}
finally {
    Pop-Location
}
