@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -X utf8 -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -X utf8 -m pip install -r requirements.txt pyinstaller==6.22.3 || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_release.ps1
exit /b %errorlevel%
