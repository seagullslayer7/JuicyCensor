"""Small, cached audio envelopes, decoded without blocking the editor."""
from __future__ import annotations
import array
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

from PySide6.QtCore import QObject, QThread, Signal


class WaveformTask(QThread):
    result = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, root, video, parent):
        super().__init__(parent)
        self.root, self.video = Path(root), video
        self.cancelled = threading.Event()
        self.child = None

    def cancel(self):
        self.cancelled.set()
        if self.child and self.child.poll() is None:
            try: self.child.kill()
            except OSError: pass

    def run(self):
        try:
            stat = Path(self.video).stat()
            key = hashlib.sha256(f'v2|{self.video}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest()
            cache = self.root/'cache'/'waveforms'/(key+'.json.gz')
            if cache.exists():
                try:
                    with gzip.open(cache, 'rt', encoding='utf-8') as stream: data = json.load(stream)
                    if data['rate'] != 100 or not isinstance(data['peaks'], list): raise ValueError('Invalid envelope')
                    if not self.cancelled.is_set(): self.result.emit(self.video, data)
                    return
                except (OSError, EOFError, ValueError, KeyError, TypeError): pass
            local = self.root/'runtime.local.json'
            config = json.loads(local.read_text(encoding='utf-8')) if local.exists() else {}
            ffmpeg = Path(config.get('ffmpeg_dir', str(self.root/'tools/ffmpeg-shared/bin')))/'ffmpeg.exe'
            if not ffmpeg.is_file(): raise FileNotFoundError('FFmpeg is missing. Finish Runtime setup, then reopen the video.')
            # 10 ms bins retain timing detail even in long videos. Never store a full PCM file.
            peaks, frames, pending = [], 0, b''
            with tempfile.TemporaryFile() as errors:
                self.child = subprocess.Popen([str(ffmpeg), '-nostdin', '-v', 'error', '-threads', '1',
                    '-i', self.video, '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '8000',
                    '-f', 's16le', 'pipe:1'], stdout=subprocess.PIPE, stderr=errors,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if self.cancelled.is_set(): self.cancel()
                with self.child.stdout as stream:
                    while not self.cancelled.is_set():
                        chunk = stream.read(32000)
                        if not chunk: break
                        pending += chunk
                        length = len(pending)//160*160
                        samples = array.array('h', pending[:length]); pending = pending[length:]
                        frames += len(samples)
                        peaks.extend(round(max(abs(v) for v in samples[i:i+80])/32768, 5)
                                     for i in range(0, len(samples), 80))
                if self.cancelled.is_set(): self.cancel()
                code = self.child.wait()
                if self.cancelled.is_set(): return
                if code:
                    errors.seek(0)
                    detail = errors.read(2048).decode('utf-8', errors='replace')
                    raise ValueError('No audio track available.' if 'matches no streams' in detail else 'Audio could not be read. Reopen the video to retry.')
            if pending:
                samples = array.array('h', pending[:len(pending)//2*2]); frames += len(samples)
                if samples: peaks.append(round(max(abs(v) for v in samples)/32768, 5))
            data = dict(rate=100, peaks=peaks, duration=frames/8000)
            if self.cancelled.is_set(): return
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix(f'.{id(self)}.tmp')
                with gzip.open(temporary, 'wt', encoding='utf-8') as stream: json.dump(data, stream)
                temporary.replace(cache)
            except OSError: pass  # A read-only cache must not prevent playback or editing.
            self.result.emit(self.video, data)
        except Exception as exc:
            if not self.cancelled.is_set(): self.failed.emit(self.video, str(exc))


class WaveformLoader(QObject):
    ready = Signal(str, dict)
    status = Signal(str, str)

    def __init__(self, root, parent):
        super().__init__(parent)
        self.root, self.path, self.tasks = root, '', []

    def load(self, path):
        self.cancel()
        self.path = path
        if not path: return
        self.status.emit(path, 'Reading audio…')
        task = WaveformTask(self.root, path, self)
        self.tasks.append(task)
        task.result.connect(lambda video, data: self.ready.emit(video, data) if self.path == video and not task.cancelled.is_set() else None)
        task.failed.connect(lambda video, message: self.status.emit(video, message) if self.path == video and not task.cancelled.is_set() else None)
        task.finished.connect(lambda: self.release(task))
        task.start()

    def release(self, task):
        if task in self.tasks: self.tasks.remove(task)
        task.deleteLater()

    def cancel(self):
        self.path = ''
        for task in self.tasks: task.cancel()

    def close(self):
        self.cancel()
        for task in list(self.tasks): task.wait()
