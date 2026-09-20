"""Private, pinned runtime setup. No administrator or system Python required."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request
import zipfile

# Runtime compatibility version; unchanged for the 2.0.2 cache fix.
VERSION = '2.0.0'


def ready(root):
    try:
        marker = json.loads((root / 'runtime' / 'ready.json').read_text())
        return (marker['version'] == VERSION and
                (root / 'venv/Scripts/python.exe').is_file() and
                (root / 'tools/ffmpeg-shared/bin/ffmpeg.exe').is_file())
    except (OSError, ValueError, KeyError):
        return False


class Installer:
    def __init__(self, root, progress=print):
        self.root = Path(root).resolve()
        self.progress = progress
        self.cancelled = threading.Event()
        self.process = None
        self.env = os.environ.copy()
        for key in ('PYTHONPATH', 'PYTHONHOME', '_MEIPASS2', 'HF_HOME', 'TORCH_HOME', 'NLTK_DATA'):
            self.env.pop(key, None)
        self.env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
                        UV_CACHE_DIR=str(self.root / 'cache/uv'),
                        UV_CREDENTIALS_DIR=str(self.root / 'cache/uv-credentials'),
                        UV_PYTHON_INSTALL_DIR=str(self.root / 'runtime/python'),
                        UV_LINK_MODE='copy', UV_HTTP_TIMEOUT='120')

    def check_cancel(self):
        if self.cancelled.is_set():
            raise RuntimeError('Setup cancelled. Run setup again to resume.')

    def cancel(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            self.process.kill()

    def command(self, args):
        self.check_cancel()
        # A frozen Qt app must not impose its DLL directory on Python/uv.
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            self.process = subprocess.Popen([str(x) for x in args], cwd=self.root, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally:
            if os.name == 'nt' and getattr(sys, 'frozen', False):
                ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
        try:
            for line in self.process.stdout:
                self.progress(line.rstrip())
                self.check_cancel()
            if self.process.wait():
                raise RuntimeError('A setup command failed. See the setup log above.')
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process.stdout.close()
            self.process = None
        self.check_cancel()

    def archive(self, url, digest, name, destination, ffmpeg=False):
        archive = self.root / 'cache/downloads' / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        def valid():
            if not archive.is_file():
                return False
            with archive.open('rb') as f:
                return hashlib.file_digest(f, 'sha256').hexdigest() == digest
        if not valid():
            self.progress('Downloading ' + name)
            partial = archive.with_suffix('.partial')
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as out:
                total, done = int(response.headers.get('Content-Length', 0)), 0
                while data := response.read(1024 * 1024):
                    self.check_cancel()
                    out.write(data)
                    done += len(data)
                    self.progress(f'{name}: {done // 1048576} MB' + (f' / {total // 1048576} MB' if total else ''))
            partial.replace(archive)
        if not valid():
            raise RuntimeError('Download checksum mismatch: ' + name)
        self.progress('Verified ' + name + '; extractingÃ¢â‚¬Â¦')
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                self.check_cancel()
                relative = Path(item.filename)
                if item.is_dir():
                    continue
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe archive entry')
                if ffmpeg:
                    relative = Path(*relative.parts[1:])
                target = destination / relative
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Archive entry leaves runtime folder')
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as src, target.open('wb') as out:
                    while data := src.read(1024 * 1024):
                        self.check_cancel()
                        out.write(data)

    def install(self, profile='cpu', models=True):
        if profile not in ('cpu', 'cuda'):
            raise ValueError('Unknown runtime profile')
        root = self.root
        (root / 'runtime').mkdir(exist_ok=True)
        marker = root / 'runtime/ready.json'
        marker.unlink(missing_ok=True)
        manifest = json.loads((root / 'release-manifest.json').read_text())
        uv = root / 'bootstrap-tools/uv.exe'
        with uv.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['uv_sha256']:
                raise RuntimeError('Bundled installer helper checksum mismatch')
        self.progress('Installing private Python ' + manifest['python'])
        self.command([uv, 'python', 'install', manifest['python'], '--no-bin', '--no-registry'])
        python = root / 'runtime/python' / f"cpython-{manifest['python']}-windows-x86_64-none/python.exe"
        if not (root / 'venv/Scripts/python.exe').exists():
            self.command([uv, 'venv', root / 'venv', '--python', python, '--relocatable'])
        python = root / 'venv/Scripts/python.exe'
        self.progress('Installing verified processing packages. This can take several minutes.')
        index = 'cu128' if profile == 'cuda' else 'cpu'
        self.command([uv, 'pip', 'sync', root / f'requirements-{profile}.lock', '--python', python,
                      '--require-hashes', '--only-binary', ':all:', '--find-links', root / 'vendor_wheels',
                      '--extra-index-url', f'https://download.pytorch.org/whl/{index}',
                      '--index-strategy', 'unsafe-best-match'])
        from install_runtime import VULKAN_URL, VULKAN_SHA, FFMPEG_URL, FFMPEG_SHA
        self.archive(FFMPEG_URL, FFMPEG_SHA, 'ffmpeg-shared.zip', root / 'tools/ffmpeg-shared', True)
        self.archive(VULKAN_URL, VULKAN_SHA, 'whisper-vulkan.zip', root / 'tools/whisper-vulkan')
        self.progress('Checking the new processing environmentÃ¢â‚¬Â¦')
        self.command([python, '-B', root / 'setup_verify.py', *(['--models'] if models else [])])
        self.check_cancel()
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': VERSION, 'profile': profile, 'models': models}, indent=2))
        temporary.replace(marker)
        self.progress('Setup complete. JuicyCensor is ready.')
