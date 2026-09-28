"""Verified GGML downloads and recovery for truncated English alignment downloads."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import urllib.request
import http.client
import re
import zipfile
from uuid import uuid4

from languages import MODELS

ALIGNMENT_URL = 'https://download.pytorch.org/torchaudio/models/wav2vec2_fairseq_base_ls960_asr_ls960.pth'
ALIGNMENT_CHUNK = 16 * 1024 * 1024


def _checkpoint_complete(path):
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.endswith('/data.pkl') for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def ensure_alignment_checkpoint(target: Path, progress=print):
    """Fetch the pinned TorchAudio English checkpoint in bounded HTTP ranges.

    Torch's downloader can cache an early EOF as a finished download when no
    hash is supplied. Check its ZIP directory before reuse, and never replace
    an existing file until every range and the new ZIP's CRCs are verified.
    """
    if _checkpoint_complete(target):
        return target
    if target.exists():
        progress('Repairing an incomplete English word-alignment download…')
    request = urllib.request.Request(ALIGNMENT_URL, headers={'Range': 'bytes=0-0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        match = re.fullmatch(r'bytes 0-0/(\d+)', response.headers.get('Content-Range', ''))
        if response.status != 206 or not match or response.read(2) != b'P':
            raise RuntimeError('The alignment model server did not return a valid download range. Please retry.')
        size = int(match.group(1))
        etag = response.headers.get('ETag')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.' + uuid4().hex + '.partial')
    try:
        with temp.open('xb') as output:
            for start in range(0, size, ALIGNMENT_CHUNK):
                end = min(size - 1, start + ALIGNMENT_CHUNK - 1)
                headers = {'Range': f'bytes={start}-{end}'}
                if etag:
                    headers['If-Match'] = etag
                for attempt in range(3):
                    try:
                        req = urllib.request.Request(ALIGNMENT_URL, headers=headers)
                        with urllib.request.urlopen(req, timeout=90) as response:
                            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                                raise RuntimeError('The alignment model server returned an unexpected download range.')
                            data = response.read(end - start + 2)
                        if len(data) != end - start + 1:
                            raise RuntimeError('The alignment model download was interrupted.')
                        break
                    except (OSError, http.client.HTTPException, RuntimeError) as exc:
                        if attempt == 2:
                            raise RuntimeError('The alignment model download could not finish. Please retry setup or analysis.') from exc
                        progress('Retrying an interrupted alignment model download…')
                output.write(data)
                progress(f'Downloading English word-alignment model: {int((end + 1) * 100 / size)}%')
        if not _checkpoint_complete(temp):
            raise RuntimeError('The downloaded alignment model is incomplete. Please retry.')
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('The downloaded alignment model failed its integrity check. Please retry.')
        temp.replace(target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def load_alignment_model(language_code, device):
    import whisperx
    if language_code == 'en':
        import torch
        target = Path(torch.hub.get_dir()) / 'checkpoints' / ALIGNMENT_URL.rsplit('/', 1)[-1]
        ensure_alignment_checkpoint(target)
    return whisperx.load_align_model(language_code=language_code, device=device)


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
