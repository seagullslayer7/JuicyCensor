from __future__ import annotations
import shutil, sys
from pathlib import Path
project = Path(__file__).resolve().parent
errors=[]
print('JuicyCensor v1.0.0 Setup Check')
print('='*35)
print('Python:', sys.version.split()[0])
if sys.version_info[:2] != (3,12): errors.append('Use the Python 3.12 venv.')
for cmd in ('ffmpeg','ffprobe','nvcc'):
    loc=shutil.which(cmd); print(f'{cmd}: {loc or "NOT FOUND"}')
    if cmd in ('ffmpeg','ffprobe') and not loc: errors.append(f'{cmd} missing from PATH.')
try:
    import torch
    print('PyTorch:', torch.__version__)
    print('CUDA runtime:', torch.version.cuda)
    print('CUDA available:', torch.cuda.is_available())
    if torch.cuda.is_available(): print('GPU:', torch.cuda.get_device_name(0))
    else: errors.append('PyTorch cannot access CUDA.')
except Exception as exc: errors.append(f'PyTorch failed: {exc}')
try:
    import whisperx
    print('WhisperX: OK')
except Exception as exc: errors.append(f'WhisperX failed: {exc}')
for name in ('beep.mp3','banned_words.txt','banned_phrases.txt','config.json'):
    ok=(project/name).exists(); print(f'{name}: {"OK" if ok else "MISSING"}')
    if not ok: errors.append(f'Missing {name}')
print()
if errors:
    print('CHECK FAILED')
    for err in errors: print('-',err)
    raise SystemExit(1)
print('JuicyCensor is ready to use.')
