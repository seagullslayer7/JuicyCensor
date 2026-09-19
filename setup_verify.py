"""Executed by the private interpreter, never by the frozen GUI interpreter."""
from pathlib import Path
import subprocess
import sys
from runtime_paths import configure_runtime

configure_runtime()
root = Path(__file__).resolve().parent
import torch
import torchaudio
import whisperx
import ctranslate2
from transcription import vulkan_devices
subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.DEVNULL)
print(f'Python {sys.version.split()[0]}; torch {torch.__version__}; CUDA available: {torch.cuda.is_available()}', flush=True)
print('Vulkan devices: ' + str(vulkan_devices()), flush=True)
if '--models' in sys.argv:
    import nltk
    from model_download import download_model
    print('Downloading starter English models and word alignment data…', flush=True)
    download_model('base.en', root)
    nltk.download('punkt_tab', download_dir=str(root / 'cache/nltk'), raise_on_error=True)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = whisperx.load_model('base.en', device, compute_type='float16' if device == 'cuda' else 'int8', language='en')
    del model
    whisperx.load_align_model(language_code='en', device='cpu')
print('Processing environment verified.', flush=True)
