# Dong goi ung dung thanh thu muc chay duoc tren Windows 64-bit + file zip phat hanh.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Ket qua: dist\NovelTranslator\ (chay NovelTranslator.exe) va
#          dist\NovelTranslator-<phien ban>-win64.zip
# Can: Python 3.8+ (khuyen dung 3.11) co trong PATH hoac lenh `py`. Tao venv sach trong build\venv
# de ban dong goi khong lan thu vien thua (numpy, onnxruntime...) cua .venv phat trien.

param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Python {
    if ($Python) { return $Python }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $found = & py -3.11 -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { return $found.Trim() }
    }
    return (Get-Command python -ErrorAction Stop).Source
}

$basePython = Find-Python
Write-Host "Python goc: $basePython"

$venv = Join-Path $root "build\venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $basePython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Khong tao duoc venv" }
}

& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Cai thu vien that bai" }

$version = (& $venvPython -c "from version import __version__; print(__version__)").Trim()
Write-Host "Phien ban: $version"

$appDir = Join-Path $root "dist\NovelTranslator"
$preservedData = Join-Path $root "build\preserved_data"
$hadData = Test-Path (Join-Path $appDir "DuLieu")
if ($hadData) {
    if (Test-Path $preservedData) {
        throw "Da ton tai ban sao tam cua DuLieu: $preservedData. Kiem tra truoc khi build lai."
    }
    Write-Host "Bao ve DuLieu hien co trong luc PyInstaller tao lai dist..."
    Copy-Item -LiteralPath (Join-Path $appDir "DuLieu") -Destination $preservedData -Recurse
}

try {
    & $venvPython -m PyInstaller packaging\novel_translator.spec --noconfirm --clean `
        --distpath dist --workpath build\pyi
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller that bai" }

    $guide = (Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "HUONG_DAN_WINDOWS.md")).Replace("{{VERSION}}", $version)
    Set-Content -Path (Join-Path $appDir "HUONG_DAN.txt") -Value $guide -Encoding UTF8

    Write-Host "Chay kiem tra goi cai (selftest)..."
    $env:NOVEL_DATA_DIR = Join-Path $root "build\selftest_data"
    & (Join-Path $appDir "NovelTranslator.exe") --selftest
    $selftestExit = $LASTEXITCODE
    Remove-Item Env:\NOVEL_DATA_DIR
    if ($selftestExit -ne 0) { throw "Selftest that bai (ma $selftestExit), khong tao zip." }

    $zip = Join-Path $root "dist\NovelTranslator-$version-win64.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path $appDir -DestinationPath $zip -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    Write-Host "Xong: $zip ($sizeMb MB, DuLieu ca nhan khong dong goi)"
}
finally {
    if ($hadData -and (Test-Path $preservedData)) {
        $targetData = Join-Path $appDir "DuLieu"
        if (-not (Test-Path $targetData)) {
            New-Item -ItemType Directory -Path $targetData | Out-Null
        }
        Copy-Item -Path (Join-Path $preservedData "*") -Destination $targetData -Recurse -Force
        Remove-Item -LiteralPath $preservedData -Recurse -Force
        Write-Host "Da khoi phuc DuLieu sau build."
    }
}
