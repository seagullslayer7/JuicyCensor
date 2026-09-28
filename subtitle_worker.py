"""Subtitle jobs run outside the GUI; cancellation uses the existing worker Job Object."""
from __future__ import annotations
import array
from contextlib import contextmanager
import json
import math
import os
import re
import subprocess
import shutil
import wave
from pathlib import Path
from uuid import uuid4

from subtitle_document import cue, new_document, validate_document, export_text
from languages import validate_language_model

ROOT = Path(__file__).resolve().parent
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


@contextmanager
def scratch_directory():
    parent = (ROOT/'cache'/'subtitle-temp').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent/uuid4().hex
    folder.mkdir()
    try:
        yield str(folder)
    finally:
        resolved = folder.resolve()
        if resolved.parent != parent or folder.is_symlink():
            raise RuntimeError('Unexpected subtitle temporary directory path.')
        shutil.rmtree(folder)


def run(command, **kw):
    return subprocess.run(command, check=True, creationflags=FLAGS, **kw)


def audio_for(video, emit):
    import autocensor as core
    folder = core.ensure_directories()['audio_cache']
    fingerprint = core.video_fingerprint(video)
    audio = folder / (fingerprint + '.wav')
    if not audio.is_file():
        temporary = audio.with_name(fingerprint + '-' + uuid4().hex + '.partial.wav')
        try:
            emit('stage', message='Preparing audio', phase='prepare', percent=1)
            core.extract_audio(video, temporary)
            temporary.replace(audio)
        finally:
            temporary.unlink(missing_ok=True)
    return audio


def speech_backend(config):
    import torch
    from transcription import select_backend, vulkan_devices
    requested = config.get('backend', 'auto')
    return select_backend(requested, torch.cuda.is_available(), vulkan_devices() if requested in ('auto', 'vulkan') else [])


def cpp_transcribe(audio, config, model_name, language, task, progress):
    from transcription import CLI, ggml_model_path, parse_cpp_result, select_device, vulkan_devices
    model_path = ggml_model_path(model_name)
    if not model_path.is_file():
        raise FileNotFoundError(f'Download the {model_name} Vulkan model in Settings first.')
    device = select_device(config.get('vulkan_device', 'auto'), vulkan_devices())
    with scratch_directory() as scratch:
        prefix = Path(scratch) / 'result'
        command = [str(CLI), '-m', str(model_path), '-f', str(audio), '-l', language,
                   '-dev', str(device['id']), '-pp', '-oj', '-of', str(prefix)]
        if task == 'translate': command.append('-tr')
        else: command += ['-ml', '72', '-sow']
        # VAD is deliberately not enabled in whisper.cpp for quiet dialogue.
        lines = []
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace', creationflags=FLAGS) as process:
            for line in process.stdout:
                lines.append(line)
                match = re.search(r'progress\s*=\s*(\d+(?:\.\d+)?)%', line, re.I)
                if match: progress(float(match[1]))
            process.wait()
        output = ''.join(lines)
        if process.returncode: raise RuntimeError('Vulkan speech recognition failed. Try a smaller model or CPU.')
        if not re.search(r'(using\s+Vulkan\d+\s+backend|Vulkan\d+.*buffer size)', output, re.I):
            raise RuntimeError('The speech runtime did not confirm Vulkan inference.')
        return parse_cpp_result(json.loads(prefix.with_suffix('.json').read_text(encoding='utf-8')))


def load_whisper(model_name, backend, config):
    from faster_whisper import WhisperModel
    return WhisperModel(model_name, device=backend,
                        compute_type='int8' if backend == 'cpu' else config.get('compute_type', 'float16'))


def recognition_options(config, language):
    return dict(language=None if language == 'auto' else language, beam_size=5,
                vad_filter=not config.get('subtitle_quiet', False),
                condition_on_previous_text=False, word_timestamps=True)


def caption_segments(segments):
    """Split long captions only at measured word boundaries, never guessed times."""
    result = []
    for segment in segments:
        words = segment.get('words', [])
        if not words:
            result.append(segment)
            continue
        group = []
        for word in words:
            if not word['text'].strip() or word['end'] <= word['start']:
                continue
            text = ''.join(w['text'] for w in group)
            if group and (len(text + word['text']) > 72 or word['end'] - group[0]['start'] > 6 or
                          (len(text) > 28 and re.search(r'[.!?。！？]$', text.strip()))):
                result.append(dict(start=group[0]['start'], end=group[-1]['end'], text=text.strip()))
                group = []
            group.append(word)
        if group:
            result.append(dict(start=group[0]['start'], end=group[-1]['end'], text=''.join(w['text'] for w in group).strip()))
    return result


def transcribe(video, config, emit):
    import autocensor as core
    backend = speech_backend(config)
    model_name = config.get('subtitle_vulkan_model' if backend == 'vulkan' else 'subtitle_model', 'large-v3')
    language = config.get('subtitle_language', 'auto')
    validate_language_model(language, model_name)
    duration = core.probe_duration(video)
    emit('estimate', duration=duration, backend=backend)
    audio = audio_for(video, emit)
    emit('stage', message=f'Loading {model_name} · {backend.upper()}', phase='load', percent=8)
    def progress(percent):
        emit('stage', message='Transcribing subtitles', phase='transcribe', phase_percent=percent, percent=10+percent*.88)
    if backend == 'vulkan':
        result = cpp_transcribe(audio, config, model_name, language, 'transcribe', progress)
        segments, detected = result['segments'], result.get('language') or language
    else:
        model = load_whisper(model_name, backend, config)
        segments_iter, info = model.transcribe(str(audio), **recognition_options(config, language))
        segments = []
        for s in segments_iter:
            segments.append(dict(start=s.start, end=s.end, text=s.text.strip(),
                                 words=[dict(start=w.start,end=w.end,text=w.word) for w in (s.words or [])]))
            progress(min(99, s.end / duration * 100))
        detected = info.language
    doc = new_document(video, detected)
    doc['cues'] = [cue(max(0, s['start']), min(duration, s['end']), s['text'].strip())
                   for s in caption_segments(segments) if s['text'].strip() and min(duration, s['end']) > max(0, s['start'])]
    doc['recognition'] = dict(model=model_name, backend=backend, quiet=bool(config.get('subtitle_quiet')))
    validate_document(doc)
    emit('subtitle_document', document=doc)


def translate_audio(video, doc, ids, config, emit):
    """Translate selected clips to English, retaining exact edited cue boundaries."""
    from faster_whisper.audio import decode_audio
    backend = speech_backend(config)
    model_name = config.get('subtitle_vulkan_model' if backend == 'vulkan' else 'subtitle_model', 'large-v3')
    language = doc.get('language', 'auto')
    validate_language_model(language, model_name, 'translate')
    if doc.get('target_language', 'en') != 'en':
        raise ValueError('Whisper audio translation produces English. Choose English or use Smart translate for another target language.')
    rows = [row for row in doc['cues'] if row['id'] in ids]
    if len(rows) != len(set(ids)) or not rows:
        raise ValueError('Select subtitle lines to translate.')
    audio = audio_for(video, emit)
    duration = sum(row['end'] - row['start'] for row in rows)
    emit('estimate', duration=duration, backend=backend)
    emit('stage', message=f'Loading {model_name}', percent=5, phase='load')
    result = {}
    if backend != 'vulkan':
        decoded = decode_audio(str(audio), sampling_rate=16000)
        model = load_whisper(model_name, backend, config)
    for index, row in enumerate(rows):
        emit('stage', message=f'Translating line {index+1} of {len(rows)}', percent=10+index/len(rows)*88,
             phase='transcribe', phase_percent=index/len(rows)*100)
        if backend == 'vulkan':
            with scratch_directory() as scratch:
                clip = Path(scratch)/'clip.wav'
                run(['ffmpeg', '-v', 'error', '-i', str(audio), '-ss', str(row['start']), '-t', str(row['end']-row['start']),
                     '-ac', '1', '-ar', '16000', str(clip)])
                translated = cpp_transcribe(clip, config, model_name, language, 'translate', lambda p: None)
                value = ' '.join(s['text'].strip() for s in translated['segments'])
        else:
            clip = decoded[round(row['start']*16000):round(row['end']*16000)]
            options = recognition_options(config, language)
            options.update(task='translate', word_timestamps=False, vad_filter=False)
            segments, _ = model.transcribe(clip, **options)
            value = ' '.join(s.text.strip() for s in segments)
        if value.strip(): result[row['id']] = value.strip()
    emit('subtitle_suggestions', suggestions=result)


def waveform(video, emit):
    audio = audio_for(video, emit)
    peaks = []
    with wave.open(str(audio), 'rb') as stream:
        frames = stream.getnframes()
        block = max(1, math.ceil(frames/6000))
        while data := stream.readframes(block):
            samples = array.array('h', data)
            peaks.append(max((abs(v) for v in samples), default=0)/32768)
        duration = frames/stream.getframerate()
    emit('subtitle_waveform', peaks=peaks, duration=duration)


def export_video(job, emit):
    import autocensor as core
    video, output = Path(job['video']).resolve(), Path(job['output']).resolve()
    if output == video or output.exists(): raise ValueError('Choose a new output filename. Existing files are never replaced.')
    format_name = job['format']
    if format_name not in ('mp4', 'mkv') or output.suffix.lower() != '.'+format_name:
        raise ValueError('Choose MP4 or MKV with the matching file extension.')
    text = export_text(job['document'], 'ass', job.get('track', 'source'))
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = core.probe_duration(video)
    emit('estimate', duration=duration, backend='render')
    token = job.get('partial_token') or uuid4().hex
    if not re.fullmatch(r'[0-9a-f]{32}', token): raise ValueError('Invalid export job identifier.')
    partial = output.with_name(output.stem+'.'+token+'.partial'+output.suffix)
    try:
        with scratch_directory() as scratch:
            subtitle = Path(scratch)/'captions.ass'
            subtitle.write_text(text, encoding='utf-8-sig')
            command = ['ffmpeg', '-hide_banner', '-nostdin', '-n', '-i', str(video)]
            if format_name == 'mkv':
                command += ['-i', str(subtitle), '-map', '0:v:0', '-map', '0:a?', '-map', '1:0', '-c', 'copy',
                            '-metadata:s:s:0', 'title=JuicyCensor subtitles', '-disposition:s:0', 'default']
                font_name = job['document'].get('style', {}).get('font', 'Trebuchet MS')
                font_file = {'Trebuchet MS': 'trebucbd.ttf', 'Segoe UI': 'segoeuib.ttf', 'Arial': 'arialbd.ttf'}.get(font_name)
                font = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/str(font_file)
                if font_file and font.is_file():
                    command += ['-attach', str(font), '-metadata:s:t:0', 'mimetype=application/x-truetype-font']
            else:
                # Filter path is a fixed filename inside the private temporary cwd.
                # Software encoding is available on AMD, NVIDIA, and CPU-only machines.
                config = dict(job.get('config', {}), export_format='mp4')
                # Burn-in always needs an encoder. With the original/copy preset,
                # retain dimensions and use automatic hardware selection at high quality.
                if config.get('export_encoder', 'copy') == 'copy' or config.get('export_quality') == 'original':
                    config.update(export_encoder='auto', export_quality='high', export_video_quality='18',
                                  export_resolution='original', export_fps='original', export_preset='medium')
                encoding = core.export_encoding_args(config, video)
                vf = encoding.index('-vf')
                encoding[vf+1] += ',subtitles=captions.ass'
                # Retain common MP4-compatible audio exactly. Otherwise use the
                # configured audio encode so MKV-only audio cannot break an MP4 export.
                probe = run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=codec_name','-of','json',str(video)], capture_output=True, text=True)
                audio_streams = json.loads(probe.stdout).get('streams', [])
                if all(s.get('codec_name') in ('aac','mp3','ac3','eac3','alac') for s in audio_streams):
                    audio_index=encoding.index('-c:a'); encoding=encoding[:audio_index]+['-c:a','copy']
                command += ['-map', '0:v:0', '-map', '0:a?', *encoding, '-movflags', '+faststart']
            command += ['-progress', 'pipe:1', '-nostats', str(partial)]
            with (Path(scratch)/'export.log').open('w+', encoding='utf-8') as log:
                with subprocess.Popen(command, cwd=scratch, stdout=subprocess.PIPE, stderr=log,
                                      text=True, encoding='utf-8', errors='replace', creationflags=FLAGS) as process:
                    for line in process.stdout:
                        if line.startswith('out_time_us='):
                            try: percent = min(99, int(line.split('=',1)[1])/1e6/duration*100)
                            except ValueError: continue
                            emit('stage', message='Exporting subtitled video', percent=percent, phase='render', phase_percent=percent)
                    process.wait()
                if process.returncode:
                    raise RuntimeError('Subtitle video export failed. Check that the video and subtitle font can be read.')
            # On Windows rename refuses an output created while this job was running.
            partial.rename(output)
    finally:
        partial.unlink(missing_ok=True)
    emit('rendered', output=str(output))


def run_subtitle_job(job, emit):
    from runtime_paths import configure_runtime
    configure_runtime()
    action = job['action']
    if action == 'subtitle_smart':
        from translation import request_suggestions
        suggestions = request_suggestions(validate_document(job['document']), job['ids'], job['settings'],
            os.environ.get('JUICY_TRANSLATION_KEY', ''),
            lambda p: emit('stage', message='Preparing translation suggestions', percent=p, phase='transcribe', phase_percent=p))
        emit('subtitle_suggestions', suggestions=suggestions)
        return
    video = Path(job['video'])
    if not video.is_file(): raise FileNotFoundError('Choose an existing video first.')
    if action == 'subtitle_transcribe': transcribe(video, job['config'], emit)
    elif action == 'subtitle_translate': translate_audio(video, validate_document(job['document']), job['ids'], job['config'], emit)
    elif action == 'subtitle_waveform': waveform(video, emit)
    elif action == 'subtitle_export': export_video(job, emit)
    else: raise ValueError('Unknown subtitle job.')
