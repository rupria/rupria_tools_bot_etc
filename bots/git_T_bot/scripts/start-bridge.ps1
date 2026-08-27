$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$nodeBin = "C:\Users\katzm\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"
$python = "C:\Users\katzm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$cdc = Join-Path $projectRoot "node_modules\.bin\cdc.cmd"
$configureScript = Join-Path $projectRoot "scripts\configure-bridge.py"
$completionAlertScript = Join-Path $projectRoot "scripts\completion_alert.py"

function Import-DotEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        $separator = $line.IndexOf("=")
        if ($separator -lt 0) {
            continue
        }
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim().Trim("'`"")
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

Import-DotEnv -Path (Join-Path $projectRoot ".env")

$completionAlertRoutes = @()
if ($env:DISCORD_COMPLETION_ALERT_ROUTES) {
    $completionAlertRoutes = @(
        $env:DISCORD_COMPLETION_ALERT_ROUTES -split "[,\r\n]+" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim() }
    )
}

if (-not (Test-Path -LiteralPath $cdc)) {
    throw "커넥터가 설치되지 않았습니다. 먼저 scripts\install-bridge.ps1을 실행하세요."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Codex에 포함된 Python 실행 파일을 찾을 수 없습니다: $python"
}
if (-not (Test-Path -LiteralPath $configureScript)) {
    throw "설정 생성 스크립트를 찾을 수 없습니다: $configureScript"
}
if (-not (Test-Path -LiteralPath $completionAlertScript)) {
    throw "완료 알림 스크립트를 찾을 수 없습니다: $completionAlertScript"
}

$codexCandidates = Get-ChildItem -Path "$env:LOCALAPPDATA\OpenAI\Codex\bin\*\codex.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
if (-not $codexCandidates) {
    throw "Codex CLI 실행 파일을 찾을 수 없습니다. Codex Desktop 설치 상태를 확인하세요."
}

$codexBin = Split-Path -Parent $codexCandidates[0].FullName
$env:Path = "$nodeBin;$codexBin;$env:Path"

Push-Location $projectRoot
try {
    & $python $configureScript
    if ($LASTEXITCODE -ne 0) {
        throw "Discord 브리지 설정 생성에 실패했습니다."
    }

    $env:CONNECT_CONFIG_PATH = Join-Path $projectRoot ".connect\config.json"
    $env:CONNECT_STATE_PATH = Join-Path $projectRoot ".connect\state.json"

    $completionAlertProcess = $null
    if ($completionAlertRoutes.Count -gt 0) {
        $alertStdout = Join-Path $projectRoot ".connect\completion-alert.stdout.log"
        $alertStderr = Join-Path $projectRoot ".connect\completion-alert.stderr.log"
        $completionAlertArguments = @(
            $completionAlertScript,
            "--project-root", $projectRoot
        )
        foreach ($route in $completionAlertRoutes) {
            $completionAlertArguments += @("--route", $route)
        }

        $completionAlertProcess = Start-Process `
            -FilePath $python `
            -ArgumentList $completionAlertArguments `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $alertStdout `
            -RedirectStandardError $alertStderr `
            -PassThru

        Start-Sleep -Milliseconds 500
        $completionAlertProcess.Refresh()
        if ($completionAlertProcess.HasExited -and $completionAlertProcess.ExitCode -ne 0) {
            $errorText = if (Test-Path -LiteralPath $alertStderr) {
                Get-Content -Raw -LiteralPath $alertStderr
            }
            else {
                "알림 로그가 없습니다."
            }
            throw "완료 알림 모니터 시작에 실패했습니다. $errorText"
        }
    }
    else {
        Write-Host "DISCORD_COMPLETION_ALERT_ROUTES가 비어 있어 완료 알림 모니터는 시작하지 않습니다."
    }

    & $cdc start --direct
}
finally {
    if ($completionAlertProcess -and -not $completionAlertProcess.HasExited) {
        Stop-Process -Id $completionAlertProcess.Id -Force
    }
    Pop-Location
}
