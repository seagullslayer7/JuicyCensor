@echo off
setlocal
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0setup_check.py"
echo.
pause
