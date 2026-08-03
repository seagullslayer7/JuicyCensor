@echo off
setlocal
cd /d "%~dp0"

echo This removes only PyInstaller build artifacts.
echo It does not remove your EXEs, source files, cache, reports, or videos.
echo.
choice /c YN /m "Remove build artifacts"
if errorlevel 2 exit /b 0

if exist "%~dp0build" rmdir /s /q "%~dp0build"
if exist "%~dp0dist" rmdir /s /q "%~dp0dist"
if exist "%~dp0AutoCensor.spec" del /q "%~dp0JuicyCensor.spec"
if exist "%~dp0AutoCensorReview.spec" del /q "%~dp0JuicyCensor Review.spec"

echo Build artifacts removed.
pause
