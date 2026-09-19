"""Install the pinned Windows inference runtime and the default Vulkan model."""
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request
import zipfile
from model_download import download_model

ROOT = Path(__file__).resolve().parent
VULKAN_URL = 'https://github.com/lemonade-sdk/whisper.cpp-builds/releases/download/v1.8.4/whisper-bin-x64-vulkan.zip'
VULKAN_SHA = 'e31ca33a055162f49f1460edfb0c2134025816b6fb44a3a77854242df28e55f9'
FFMPEG_URL = 'https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build-shared.zip'
FFMPEG_SHA = '9f28727e8b472a04c1d2e520aaa425dca82721b995139b35710091130ea6e699'


def install_zip(url, digest, destination, flatten_bin=False):
    download = ROOT / 'cache' / 'downloads' / (destination.name + '.zip')
    download.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, download)
    with download.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise RuntimeError(f'Checksum failed for {download.name}')
    with zipfile.ZipFile(download) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            relative = Path(item.filename)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe archive member')
            if flatten_bin:
                if '/bin/' not in item.filename:
                    continue
                relative = Path('bin') / relative.name
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
    download.unlink()


if __name__ == '__main__':
    install_zip(VULKAN_URL, VULKAN_SHA, ROOT / 'tools' / 'whisper-vulkan')
    install_zip(FFMPEG_URL, FFMPEG_SHA, ROOT / 'tools' / 'ffmpeg-shared', True)
    download_model('base.en', ROOT)
    print('Runtime and base.en model installed and verified.')
