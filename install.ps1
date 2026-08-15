param([switch]$Check)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$winget = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"

if ($Check) {
    foreach ($file in "web_app.py", "requirements.txt", "download_models.py", "เปิดหน้าเว็บ OCR.bat") {
        if (-not (Test-Path (Join-Path $root $file))) { throw "Missing $file" }
    }
    Write-Host "Installer check: OK" -ForegroundColor Green
    exit 0
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows 64-bit is required" }
$driveName = [IO.Path]::GetPathRoot($root).Substring(0, 1)
if ((Get-PSDrive -Name $driveName).Free -lt 35GB) {
    throw "Need at least 35 GB of free disk space"
}
if (-not (Test-Path $winget)) { throw "winget is required. Install App Installer from Microsoft Store." }

Set-Location $root
if (-not (Test-Path $python)) {
    Write-Host "[1/7] Installing Python 3.12..." -ForegroundColor Cyan
    & $winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed" }
}

Write-Host "[2/7] Creating Python environments..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Main environment creation failed" }
}
if (-not (Test-Path ".venv-paddle\Scripts\python.exe")) {
    & $python -m venv .venv-paddle
    if ($LASTEXITCODE -ne 0) { throw "Paddle environment creation failed" }
}
$mainPython = Join-Path $root ".venv\Scripts\python.exe"
$paddlePython = Join-Path $root ".venv-paddle\Scripts\python.exe"

Write-Host "[3/7] Installing NVIDIA PyTorch and web app..." -ForegroundColor Cyan
& $mainPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $mainPython -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu130
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }
& $mainPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Web app dependency installation failed" }

Write-Host "[4/7] Installing PaddleOCR GPU..." -ForegroundColor Cyan
& $paddlePython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Paddle pip upgrade failed" }
& $paddlePython -m pip install paddleocr==3.3.2
if ($LASTEXITCODE -ne 0) { throw "PaddleOCR installation failed" }
& $paddlePython -m pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
if ($LASTEXITCODE -ne 0) { throw "PaddlePaddle GPU installation failed" }

if (-not (Test-Path $ollama)) {
    Write-Host "[5/7] Installing Ollama..." -ForegroundColor Cyan
    & $winget install --id Ollama.Ollama -e --silent --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Ollama installation failed" }
}
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
}
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null
        break
    } catch {
        if ($attempt -eq 59) { throw "Ollama server did not start" }
        Start-Sleep -Seconds 1
    }
}
Write-Host "[6/7] Downloading Typhoon Fast Q4..." -ForegroundColor Cyan
& $ollama pull scb10x/typhoon-ocr1.5-3b
if ($LASTEXITCODE -ne 0) { throw "Typhoon Fast download failed" }

Write-Host "[7/7] Downloading full OCR models (this can take a while)..." -ForegroundColor Cyan
& $mainPython download_models.py
if ($LASTEXITCODE -ne 0) { throw "Full model download failed" }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Thai OCR Web.lnk"))
$shortcut.TargetPath = Join-Path $root "เปิดหน้าเว็บ OCR.bat"
$shortcut.WorkingDirectory = $root
$shortcut.Save()

Write-Host "Installation complete. Opening Thai OCR Web..." -ForegroundColor Green
Start-Process -FilePath (Join-Path $root "เปิดหน้าเว็บ OCR.bat")
