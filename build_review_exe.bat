@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0venv\Scripts\python.exe" (
  echo ERROR: venv\Scripts\python.exe was not found.
  pause
  exit /b 1
)

echo Building corrected JuicyCensor Review.exe...

"%~dp0venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name JuicyCensorReview ^
  AutoCensorReviewLauncher.py

if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

copy /y "%~dp0dist\AutoCensorReview.exe" "%~dp0JuicyCensorReview.exe" >nul

echo.
echo Build complete:
echo %~dp0JuicyCensorReview.exe
echo.
pause
