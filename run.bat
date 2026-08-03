@echo off
setlocal
cd /d "%~dp0"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
if "%~1"=="" (
  echo Drag a video file onto run.bat.
  pause
  exit /b 1
)
"%~dp0venv\Scripts\python.exe" "%~dp0autocensor.py" "%~1"
echo.
pause
