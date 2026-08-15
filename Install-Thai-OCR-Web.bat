@echo off
setlocal
title Install Thai OCR Web
set "INSTALL_DIR=%USERPROFILE%\Thai-OCR-Web"
echo Downloading Thai OCR Web from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $stage=Join-Path $env:TEMP ('thai-ocr-web-'+[guid]::NewGuid()); $zip=Join-Path $stage 'source.zip'; New-Item -ItemType Directory -Path $stage | Out-Null; Invoke-WebRequest 'https://github.com/tidmunzsocial-lab/thai-ocr-web/archive/refs/tags/v1.3.0.zip' -OutFile $zip; Expand-Archive -LiteralPath $zip -DestinationPath $stage; New-Item -ItemType Directory -Path '%INSTALL_DIR%' -Force | Out-Null; Copy-Item -Path (Join-Path $stage 'thai-ocr-web-1.3.0\*') -Destination '%INSTALL_DIR%' -Recurse -Force; & '%INSTALL_DIR%\install.ps1'"

if errorlevel 1 (
  echo.
  echo Installation failed. Please copy the error above when asking for help.
  pause
  exit /b 1
)
endlocal
