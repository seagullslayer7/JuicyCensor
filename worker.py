"""Isolated processing process; @@ lines are structured UI messages."""
from __future__ import annotations
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
from dataclasses import asdict
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
_job_handle = None


def contain_process_tree():
    """Children terminate with this worker, including on UI cancellation/crash."""
    global _job_handle
    if os.name != 'nt':
        return
    from ctypes import wintypes as w
    class BASIC(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                    ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD),
                    ('scheduling', w.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ('read', 'write', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]
    class EXT(ctypes.Structure):
        _fields_ = [('basic', BASIC), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    _job_handle = kernel.CreateJobObjectW(None, None)
    limits = EXT()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _job_handle or not kernel.SetInformationJobObject(_job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())


def emit(kind: str, **values):
    print('@@' + json.dumps({'type': kind, **values}, ensure_ascii=False), flush=True)


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def validate_events(raw: list, duration: float):
    import autocensor as app
    events = []
    for item in raw:
        start, end = float(item['start']), float(item['end'])
        if not math.isfinite(start + end) or not 0 <= start < end <= duration + 0.05:
            raise ValueError('Each censor region must be within the video, with its end after its start.')
        events.append(app.Event(start, min(end, duration), str(item.get('matched', 'Manual')),
                                str(item.get('kind', 'manual')), str(item.get('source', 'manual'))))
    return app.merge_events(events, 0)


def run_job(job: dict):
    import autocensor as app
    from transcription import vulkan_devices
    action = job['action']
    if action == 'download':
        from model_download import download_model
        path = download_model(job['model'], ROOT, lambda message: emit('stage', message=message))
        emit('downloaded', model=job['model'], path=str(path))
        return
    if action == 'probe':
        import torch
        emit('hardware', cuda=torch.cuda.is_available(),
             cuda_name=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
             vulkan=vulkan_devices())
        return
    video = Path(job['video']).resolve()
    if not video.is_file():
        raise FileNotFoundError(f'Video not found: {video}')
    config = job['config']
    paths = app.ensure_directories()
    fingerprint = app.video_fingerprint(video)
    if action == 'analyze':
        import torch
        from transcription import select_backend
        config = dict(config)
        requested = config.get('backend', 'auto')
        config['backend'] = select_backend(requested, torch.cuda.is_available(),
            vulkan_devices() if requested in ('auto', 'vulkan') else [])
        emit('stage', message='Reading video', percent=5)
        duration = app.probe_duration(video)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Video has no valid duration.')
        lists = [app.read_entries(ROOT / 'banned_words.txt'), app.read_entries(ROOT / 'banned_phrases.txt')]
        analysis_config = {key: value for key, value in config.items() if not key.startswith('export_') and key not in ('censor_mode', 'beep_volume', 'beep_frequency', 'beep_file')}
        analysis_key = hashlib.sha256(json.dumps([analysis_config, lists], sort_keys=True).encode()).hexdigest()[:16]
        state_path = ROOT / 'cache' / 'reviews' / f'{fingerprint}_{analysis_key}.json'
        if state_path.exists():
            saved = json.loads(state_path.read_text(encoding='utf-8'))
            validate_events(saved['events'], duration)
            emit('review', state=saved, state_path=str(state_path))
            return
        audio = paths['audio_cache'] / f'{fingerprint}.wav'
        # Stage extraction so cancellation cannot turn a partial WAV into a cache hit.
        if not audio.exists():
            emit('stage', message='Extracting audio', percent=10)
            temp_audio = audio.with_name(f'{fingerprint}-{uuid4().hex}.partial.wav')
            try:
                app.extract_audio(video, temp_audio)
                temp_audio.replace(audio)
            finally:
                temp_audio.unlink(missing_ok=True)
        emit('stage', message='Transcribing and aligning words', percent=20)
        alignment_path = paths['aligned_cache'] / f'{fingerprint}.json'
        aligned = app.transcribe_and_align(audio, config, alignment_path)
        emit('stage', message='Finding censor regions', percent=95)
        words = app.flatten_words(aligned)
        events = app.find_events(words, *lists, config)
        # Padding at the end of the last word may exceed the media duration.
        events = [app.Event(e.start, min(e.end, duration), e.matched, e.kind, e.source)
                  for e in events if e.start < duration]
        state = {'video': str(video), 'fingerprint': fingerprint, 'duration': duration,
                 'events': [asdict(e) for e in events], 'word_count': len(words),
                 'backend': aligned['_backend'], 'alignment_device': aligned['_alignment_device'],
                 'config': config, 'schema': 2}
        atomic_json(state_path, state)
        emit('review', state=state, state_path=str(state_path))
    elif action == 'render':
        state = job['state']
        if state['fingerprint'] != fingerprint:
            raise ValueError('The original video changed. Analyze it again before rendering.')
        duration = app.probe_duration(video)
        events = validate_events(state['events'], duration)
        if not events:
            raise ValueError('There are no censor regions to render.')
        name = f'{app.safe_stem(video)}_{fingerprint[:6]}_{uuid4().hex[:6]}'
        if config.get('export_no_spaces'):
            name = '_'.join(name.split())
        container = config.get('export_format', 'mp4')
        if container not in ('mp4', 'mkv'):
            raise ValueError('Unsupported export format')
        folder = Path(config.get('export_path') or paths['censored_outputs']).expanduser()
        if not folder.is_absolute():
            raise ValueError('Export folder must be an absolute path')
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f'{name}_censored.{container}'
        temporary = output.with_name(output.stem + '.partial' + output.suffix)
        emit('stage', message='Rendering censored video', percent=1)
        try:
            app.create_censored_video(video, ROOT / config.get('beep_file', 'beep.mp3'), temporary, events, config,
                progress=lambda percent: emit('stage', message='Rendering censored video', percent=percent))
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        report = paths['reports'] / f'{name}_report.txt'
        app.write_report(report, video, events, Path('reviewed regions'))
        atomic_json(paths['reports'] / f'{name}_events.json', [asdict(e) for e in events])
        emit('rendered', output=str(output), report=str(report))
    else:
        raise ValueError(f'Unknown action: {action}')


if __name__ == '__main__':
    try:
        contain_process_tree()
        run_job(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    except Exception as exc:
        traceback.print_exc()
        emit('error', message=str(exc))
        raise SystemExit(1)
