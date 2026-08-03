@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
  echo ERROR: venv\Scripts\python.exe was not found.
  pause
  exit /b 1
)
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
"%~dp0venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console --name JuicyCensor AutoCensorLauncher.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
copy /y "%~dp0dist\JuicyCensor.exe" "%~dp0JuicyCensor.exe" >nul
echo.
echo Build complete:
echo %~dp0JuicyCensor.exe
echo.
echo Keep JuicyCensor.exe in this main folder beside venv and autocensor.py.
pause
