@echo off
setlocal
cd /d "%~dp0"
echo This deletes cached WAV files and aligned transcript JSON files.
echo It does NOT delete models, reports, censored videos, or your source videos.
echo.
choice /c YN /m "Delete JuicyCensor cache"
if errorlevel 2 exit /b 0
if exist "%~dp0cache\audio" rmdir /s /q "%~dp0cache\audio"
if exist "%~dp0cache\alignments" rmdir /s /q "%~dp0cache\alignments"
mkdir "%~dp0cache\audio" 2>nul
mkdir "%~dp0cache\alignments" 2>nul
echo Cache cleared.
pause
