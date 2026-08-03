@echo off
setlocal
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
"%~dp0venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --console --name JuicyCensor --collect-all whisperx --collect-all faster_whisper --collect-all ctranslate2 --collect-all torch --collect-all torchaudio --collect-all transformers --collect-all pyannote.audio --add-data "config.json;." --add-data "banned_words.txt;." --add-data "banned_phrases.txt;." --add-data "beep.mp3;." autocensor.py
echo.
echo Build output: %~dp0dist\JuicyCensor\
pause
