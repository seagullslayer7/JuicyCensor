"""WhisperX CUDA/CPU and whisper.cpp Vulkan with CPU forced alignment."""
from __future__ import annotations
import gc
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
CLI = ROOT / 'tools' / 'whisper-vulkan' / 'Release' / 'whisper-cli.exe'
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def vulkan_devices(cli: Path = CLI) -> list[dict]:
    if not cli.is_file():
        return []
    try:
        result = subprocess.run([str(cli), '--help'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=20,
                                creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return []
    devices = []
    for match in re.finditer(r'ggml_vulkan:\s*(\d+) = (.*?)\s*\|', result.stdout + result.stderr):
        name = match[2].strip()
        devices.append({'id': int(match[1]), 'name': name,
                        'amd': bool(re.search(r'AMD|Radeon', name, re.I))})
    return devices


def select_backend(requested: str, cuda: bool, devices: list[dict]) -> str:
    if requested not in ('auto', 'cuda', 'vulkan', 'cpu'):
        raise ValueError(f'Unknown acceleration option: {requested}')
    if requested == 'auto':
        return 'cuda' if cuda else ('vulkan' if devices else 'cpu')
    if requested == 'cuda' and not cuda:
        raise RuntimeError('NVIDIA CUDA is unavailable. Choose Auto, AMD / Vulkan, or CPU.')
    if requested == 'vulkan' and not devices:
        raise RuntimeError('No Vulkan GPU was detected. Install the GPU vendor driver or choose CPU.')
    return requested


def select_device(requested, devices: list[dict]) -> dict:
    if not devices:
        raise RuntimeError('No Vulkan GPU is available.')
    if requested in (None, 'auto'):
        return next((d for d in devices if d['amd']), devices[0])
    try:
        return next(d for d in devices if d['id'] == int(requested))
    except (ValueError, StopIteration):
        raise ValueError(f'Vulkan device {requested!r} is unavailable. Refresh the GPU list.') from None


def parse_cpp_result(document: dict) -> dict:
    segments = []
    for raw in document.get('transcription', []):
        offsets = raw['offsets']
        start, end = float(offsets['from']) / 1000, float(offsets['to']) / 1000
        if not math.isfinite(start + end) or start < 0 or end <= start:
            raise ValueError('Vulkan transcription returned invalid segment timestamps.')
        if segments and start < segments[-1]['start']:
            raise ValueError('Vulkan transcription segments are out of order.')
        text = str(raw['text']).strip()
        if text:
            segments.append({'start': start, 'end': end, 'text': text})
    return {'segments': segments, 'language': document.get('result', {}).get('language')}


def cache_signature(audio: Path, config: dict, backend: str) -> str:
    stat = audio.stat()
    model = config.get('vulkan_model', 'base.en') if backend == 'vulkan' else config.get('model', 'large-v3')
    details = {'schema': 2, 'audio': [str(audio.resolve()), stat.st_size, stat.st_mtime_ns],
               'backend': backend, 'model': model, 'language': config.get('language', 'en'),
               'alignment': 'cpu' if backend == 'vulkan' else backend,
               'compute_type': config.get('compute_type', 'float16')}
    if backend == 'vulkan':
        path = ROOT / 'models' / f'ggml-{model}.bin'
        if path.exists():
            details['model_file'] = [path.stat().st_size, path.stat().st_mtime_ns]
    return hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()


def transcribe_and_align(audio_path: Path, config: dict, cache_path: Path, progress=None) -> dict:
    def report(phase, percent, message):
        if progress:
            progress(phase, percent, message)
    report('load', 0, 'Loading speech model')
    import torch
    import whisperx
    requested = config.get('backend', config.get('device', 'auto'))
    devices = vulkan_devices() if requested in ('auto', 'vulkan') else []
    backend = select_backend(requested, torch.cuda.is_available(), devices)
    signature = cache_signature(audio_path, config, backend)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        if cached.get('_cache_signature') == signature:
            print('Using matching word-alignment cache.', flush=True)
            return cached
    language = config.get('language') or 'en'
    audio = whisperx.load_audio(str(audio_path))
    duration = len(audio) / 16000
    if backend == 'vulkan':
        device = select_device(config.get('vulkan_device', 'auto'), devices)
        model_name = config.get('vulkan_model', 'base.en')
        if model_name not in ('base.en', 'small.en', 'medium.en', 'large-v3'):
            raise ValueError('Unsupported Vulkan model. Choose base.en, small.en, medium.en, or large-v3.')
        model_path = ROOT / 'models' / f'ggml-{model_name}.bin'
        if not model_path.is_file():
            raise FileNotFoundError(f'Download the {model_name} Vulkan model in Settings first.')
        if model_name.endswith('.en') and language not in ('en', 'auto'):
            raise ValueError('This Vulkan model supports English only. Choose large-v3 for other languages.')
        print(f'Transcribing on Vulkan GPU {device["id"]}: {device["name"]}; model {model_name}.', flush=True)
        scratch = ROOT / 'cache' / 'transcripts'
        scratch.mkdir(parents=True, exist_ok=True)
        prefix = scratch / uuid4().hex
        command = [str(CLI), '-m', str(model_path), '-f', str(audio_path),
                   '-l', language, '-dev', str(device['id']), '-pp', '-oj', '-of', str(prefix)]
        lines = []
        report('transcribe', 0, 'Transcribing on Vulkan GPU')
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace',
                              creationflags=CREATE_NO_WINDOW) as process:
            for line in process.stdout:
                lines.append(line)
                print(line.rstrip(), flush=True)
                match = re.search(r'progress\s*=\s*(\d+(?:\.\d+)?)%', line, re.I)
                if match:
                    report('transcribe', float(match[1]), 'Transcribing on Vulkan GPU')
            process.wait()
        output = ''.join(lines)
        (scratch / 'last-vulkan.log').write_text(output, encoding='utf-8')
        json_path = prefix.with_suffix('.json')
        try:
            if process.returncode:
                raise RuntimeError('Vulkan transcription failed. Check cache/transcripts/last-vulkan.log. '
                                   'Try a smaller model or CPU.\n' + output[-1800:])
            # Require positive evidence that inference used a Vulkan backend.
            if not re.search(r'(using\s+Vulkan\d+\s+backend|Vulkan\d+.*buffer size)', output, re.I):
                raise RuntimeError('The runtime did not confirm Vulkan inference; refusing to report GPU success.')
            result = parse_cpp_result(json.loads(json_path.read_text(encoding='utf-8')))
        finally:
            json_path.unlink(missing_ok=True)
        alignment_device = 'cpu'
    else:
        alignment_device = backend
        precision = 'int8' if backend == 'cpu' else config.get('compute_type', 'float16')
        print(f'Transcribing with WhisperX on {backend}.', flush=True)
        model = whisperx.load_model(config.get('model', 'large-v3'), backend,
                                   compute_type=precision, language=None if language == 'auto' else language)
        try:
            report('transcribe', 0, 'Transcribing speech')
            result = model.transcribe(audio, batch_size=int(config.get('batch_size', 8)),
                                      language=None if language == 'auto' else language, print_progress=True,
                                      progress_callback=lambda percent: report('transcribe', percent, 'Transcribing speech'))
        finally:
            del model
            gc.collect()
            if backend == 'cuda':
                torch.cuda.empty_cache()
    report('transcribe', 100, 'Transcription complete')
    report('align_load', 0, 'Loading word-alignment model')
    detected = result.get('language') or language
    if detected == 'auto':
        raise RuntimeError('The transcription backend did not identify a language.')
    if result['segments']:
        print(f'Aligning words on {alignment_device} ({detected}).', flush=True)
        align_model, metadata = whisperx.load_align_model(language_code=detected, device=alignment_device)
        try:
            report('align', 0, 'Aligning words')
            aligned = whisperx.align(result['segments'], align_model, metadata, audio,
                                     alignment_device, return_char_alignments=False, print_progress=True,
                                     progress_callback=lambda percent: report('align', percent, 'Aligning words'))
        finally:
            del align_model
            gc.collect()
            if alignment_device == 'cuda':
                torch.cuda.empty_cache()
    else:
        aligned = {'segments': [], 'word_segments': []}
    report('align', 100, 'Word alignment complete')
    for segment in aligned['segments']:
        for word in segment.get('words', []):
            if 'start' in word and 'end' in word:
                start, end = float(word['start']), float(word['end'])
                if not math.isfinite(start + end) or not 0 <= start <= end <= duration + 0.1:
                    raise ValueError('Forced alignment produced an invalid word boundary.')
    aligned.update(language=detected, _cache_signature=signature,
                   _backend=backend, _alignment_device=alignment_device)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(cache_path.name + '.tmp')
    temporary.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(cache_path)
    return aligned
