@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: run_ocr.bat image.jpg
  exit /b 2
)
".venv\Scripts\python.exe" run_ocr.py "%~1"
