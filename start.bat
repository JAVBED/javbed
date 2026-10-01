@echo off
setlocal
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6, javbed" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m javbed.app
exit /b %errorlevel%
