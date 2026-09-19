"""Make project-local FFmpeg and CUDA runtime DLLs discoverable."""
import json
import os
import sys
from pathlib import Path

_dll_handles = []

def configure_runtime():
    root = Path(__file__).resolve().parent
    local_path = root / "runtime.local.json"
    local = json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {}
    for key, variable in (("torch_cache", "TORCH_HOME"), ("hf_cache", "HF_HOME"), ("nltk_data", "NLTK_DATA")):
        if local.get(key):
            os.environ.setdefault(variable, local[key])
    for variable, folder in (("HF_HOME", "huggingface"), ("TORCH_HOME", "torch"), ("MPLCONFIGDIR", "matplotlib"), ("NLTK_DATA", "nltk")):
        location = root / "cache" / folder
        location.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault(variable, str(location))
    paths = [root / "tools" / "ffmpeg-shared" / "bin",
             Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"]
    for path in reversed(paths):
        if path.is_dir():
            value = str(path)
            if value not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")
            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                _dll_handles.append(os.add_dll_directory(value))
    if os.name == 'nt':
        # Some restricted Windows folders reject the Hub's temporary symlink
        # probe itself. Use its supported file-copy path in that case.
        try:
            from huggingface_hub import file_download
            if not getattr(file_download.are_symlinks_supported, '_juicy_safe', False):
                probe = file_download.are_symlinks_supported
                def safe_probe(cache_dir=None):
                    try:
                        return probe(cache_dir)
                    except OSError:
                        location = str(Path(cache_dir or file_download.constants.HF_HUB_CACHE).expanduser().resolve())
                        file_download._are_symlinks_supported_in_dir[location] = False
                        return False
                safe_probe._juicy_safe = True
                file_download.are_symlinks_supported = safe_probe
        except ImportError:
            pass
