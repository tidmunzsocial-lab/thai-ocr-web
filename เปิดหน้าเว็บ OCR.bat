@echo off
cd /d "%~dp0"
title Unlimited OCR
echo กำลังเปิดหน้าเว็บ Unlimited OCR...
echo กรุณาอย่าปิดหน้าต่างนี้ขณะใช้งาน
".venv\Scripts\python.exe" web_app.py
pause
