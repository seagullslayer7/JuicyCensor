"""Make project-local FFmpeg and CUDA runtime DLLs discoverable."""
import json
import os
import sys
from pathlib import Path

_dll_handles = []

def configure_model_cache():
    """Use the Hub's regular-file cache on Windows without symlink privileges."""
    if os.name != 'nt':
        return
    try:
        from huggingface_hub import file_download
    except ImportError:
        return  # The frozen GUI does not include processing dependencies.
    # A successful probe does not guarantee later link creation. WinError 1314
    # is an OSError missed by the Hub's PermissionError fallback. Select its
    # existing copy/move path; do not modify the library on disk or Windows.
    def regular_files_only(cache_dir=None):
        return False
    file_download.are_symlinks_supported = regular_files_only


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
    configure_model_cache()
