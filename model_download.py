"""Download GGML models from the upstream model repository with SHA-256 checks."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import urllib.request

MODELS = ('base.en', 'small.en', 'medium.en', 'large-v3')


def download_model(name: str, root: Path, progress=print) -> Path:
    if name not in MODELS:
        raise ValueError('Unsupported model')
    request = urllib.request.Request('https://huggingface.co/api/models/ggerganov/whisper.cpp?blobs=true')
    with urllib.request.urlopen(request, timeout=60) as response:
        meta = json.load(response)
    filename = f'ggml-{name}.bin'
    info = next(item for item in meta['siblings'] if item['rfilename'] == filename)
    size, digest = info['size'], info['lfs']['sha256']
    folder = root / 'models'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if target.exists():
        with target.open('rb') as existing:
            if hashlib.file_digest(existing, 'sha256').hexdigest() == digest:
                return target
    temp = target.with_suffix('.bin.partial')
    url = f'https://huggingface.co/ggerganov/whisper.cpp/resolve/{meta["sha"]}/{filename}'
    hasher = hashlib.sha256()
    with temp.open('wb') as output:
        chunk = 16 * 1024 * 1024
        for start in range(0, size, chunk):
            end = min(size - 1, start + chunk - 1)
            req = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(req, timeout=90) as response:
                if response.status != 206 or response.headers.get('Content-Range', '').split('/')[0] != f'bytes {start}-{end}':
                    raise RuntimeError('The model server did not return the requested download range.')
                data = response.read()
            if len(data) != end - start + 1:
                raise RuntimeError('Model download was interrupted. Please retry.')
            output.write(data)
            hasher.update(data)
            progress(f'Downloading {name}: {int((end + 1) * 100 / size)}%')
    if hasher.hexdigest() != digest:
        raise RuntimeError('Model checksum failed. Please retry the download.')
    temp.replace(target)
    return target
