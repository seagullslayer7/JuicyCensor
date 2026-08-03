@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0dist\JuicyCensor.exe" (
  echo JuicyCensor.exe has not been built yet.
  echo Run build_launcher_exe.bat first.
  pause
  exit /b 1
)
start "" "%~dp0dist\JuicyCensor.exe"
