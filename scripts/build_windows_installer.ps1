<#
.SYNOPSIS
  Windows 로컬 머신에서 KR Stock Screener 인스톨러를 빌드합니다.

.DESCRIPTION
  - 프론트엔드 정적 빌드 → PyInstaller 데스크톱 번들 → Inno Setup 인스톨러 컴파일 순서로 수행합니다.
  - 사전 조건: Python 3.12, Node.js 20, Inno Setup 6 설치
  - 산출물: dist\KRStockScreener-Setup-<version>.exe

.PARAMETER Version
  인스톨러에 박힐 버전 문자열. 비우면 "0.0.0-dev".

.PARAMETER SkipFrontend
  frontend\dist 가 이미 빌드되어 있을 때 npm 단계를 건너뜀.

.EXAMPLE
  .\scripts\build_windows_installer.ps1 -Version "0.1.0"

.EXAMPLE
  .\scripts\build_windows_installer.ps1 -SkipFrontend
#>

[CmdletBinding()]
param(
    [string]$Version = "0.0.0-dev",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

# 저장소 루트로 이동 (스크립트가 어디서 실행되든 동작하도록)
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
Write-Host "[build] 저장소 루트: $RepoRoot"
Write-Host "[build] 버전: $Version"

# 1) 프론트엔드 빌드
if (-not $SkipFrontend) {
    Write-Host "`n[1/4] 프론트엔드 빌드 (npm ci && npm run build) ..."
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci 실패" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build 실패" }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[1/4] 프론트엔드 빌드 건너뜀 (-SkipFrontend)"
    if (-not (Test-Path "frontend\dist\index.html")) {
        throw "frontend\dist 가 없습니다. -SkipFrontend 를 빼고 다시 실행하세요."
    }
}

# 2) 파이썬 의존성 설치
Write-Host "`n[2/4] 파이썬 의존성 설치 ..."
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade 실패" }
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "requirements.txt 설치 실패" }
pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "requirements-build.txt 설치 실패" }

# 3) PyInstaller 번들
Write-Host "`n[3/4] PyInstaller 빌드 ..."
python -m PyInstaller --noconfirm desktop/app.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 빌드 실패" }

$builtExe = Join-Path $RepoRoot "dist\KRStockScreener\KRStockScreener.exe"
if (-not (Test-Path $builtExe)) {
    throw "산출물 누락: $builtExe"
}

# 4) Inno Setup 컴파일
Write-Host "`n[4/4] Inno Setup 인스톨러 컴파일 ..."
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    $iscc = "C:\Program Files\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc)) {
    throw "Inno Setup 6 (ISCC.exe) 을 찾을 수 없습니다. https://jrsoftware.org/isinfo.php 에서 설치하세요."
}

$env:KR_APP_VERSION = $Version
& $iscc "installer\windows\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC 컴파일 실패 (exit $LASTEXITCODE)" }

$setup = Get-ChildItem "dist\KRStockScreener-Setup-$Version.exe" -ErrorAction SilentlyContinue
if (-not $setup) {
    throw "인스톨러 결과를 찾을 수 없습니다: dist\KRStockScreener-Setup-$Version.exe"
}

Write-Host "`n빌드 완료" -ForegroundColor Green
Write-Host "  산출물: $($setup.FullName)"
Write-Host "  크기  : $([math]::Round($setup.Length / 1MB, 1)) MB"
