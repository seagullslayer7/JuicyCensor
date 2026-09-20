"""Integration checks for audible preview and preserved review edits (requires FFmpeg)."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autocensor as core
import worker

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg runtime required')
class ReviewTests(unittest.TestCase):
    def setUp(self):
        parent = Path(tempfile.gettempdir()).resolve()
        self.root = parent / ('juicy-review-' + uuid4().hex)
        self.root.mkdir()
        def cleanup():
            assert self.root.resolve().parent == parent
            shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        for name in ('banned_words.txt', 'banned_phrases.txt'):
            (self.root / name).write_text('hello\n', encoding='utf-8')
        self.video = self.root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=orange:s=160x90:r=25:d=4',
            '-f', 'lavfi', '-i', 'sine=frequency=220:duration=4', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(self.video)], check=True)
        self.beep = self.root / 'beep.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3', str(self.beep)], check=True)
        self.config = {'backend': 'cpu', 'model': 'base.en', 'censor_mode': 'mute', 'beep_file': str(self.beep),
                       'beep_frequency': 1000, 'beep_volume': .8, 'pulse_on': .22, 'pulse_off': .08}
        self.state = {'video': str(self.video), 'fingerprint': core.video_fingerprint(self.video),
                      'events': [{'start': 1., 'end': 2., 'matched': 'test'}]}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(worker, 'ROOT', self.root))
        self.stack.enter_context(patch.object(core, 'PROJECT_DIR', self.root))

    def run_job(self, action, config=None):
        messages = []
        with patch.object(worker, 'emit', lambda kind, **kw: messages.append(dict(type=kind, **kw))), contextlib.redirect_stdout(io.StringIO()):
            worker.run_job(dict(action=action, video=str(self.video), state=self.state, config=config or self.config))
        return messages[-1]

    def audio(self, path):
        import numpy as np
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ar', '16000', '-ac', '1', '-f', 'f32le', '-'])
        return np.frombuffer(raw, dtype=np.float32)

    def test_preview_audio_all_styles_and_copied_video(self):
        import numpy as np
        def rms(a): return float(np.sqrt(np.mean(a * a)))
        def tone(a, hz):
            spectrum = abs(np.fft.rfft(a))
            index = round(hz * len(a) / 16000)
            return max(spectrum[max(0,index-2):index+3])
        for mode in ('mute', 'continuous_beep', 'pulse_beep', 'custom_beep'):
            with self.subTest(mode=mode):
                result = self.run_job('preview', dict(self.config, censor_mode=mode))
                self.assertEqual(result['type'], 'previewed')
                audio = self.audio(result['output'])
                inside, outside = audio[17600:30400], audio[3200:12800]
                self.assertGreater(rms(outside), .03)
                if mode == 'mute': self.assertLess(rms(inside), .002)
                else:
                    self.assertGreater(rms(inside), .01)
                    self.assertGreater(tone(inside, 440 if mode == 'custom_beep' else 1000), tone(inside, 220) * 5)
                def video_hash(path):
                    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-'])
                self.assertEqual(video_hash(self.video), video_hash(result['output']))

    def test_cache_reuse_invalidation_and_rejected_bounds(self):
        first = self.run_job('preview')['output']
        mtime = Path(first).stat().st_mtime_ns
        self.assertEqual(self.run_job('preview')['output'], first)
        self.assertEqual(Path(first).stat().st_mtime_ns, mtime)
        self.state['events'][0]['end'] = 2.5
        self.assertNotEqual(self.run_job('preview')['output'], first)
        self.state['events'][0]['end'] = 40
        with self.assertRaises(ValueError): self.run_job('preview')
        self.assertFalse(list((self.root/'cache/previews').glob('*.partial.mkv')))

    def test_old_review_transcript_upgrade_preserves_manual_edits(self):
        aligned = {'segments': [{'words': [{'word': 'hello', 'start': 1, 'end': 1.5}]}],
                   '_backend': 'cpu', '_alignment_device': 'cpu'}
        with patch.object(core, 'transcribe_and_align', return_value=aligned):
            first = self.run_job('analyze')
            path = Path(first['state_path'])
            old = first['state']; old.pop('words'); old['schema'] = 2
            old['events'] = self.state['events']
            path.write_text(json.dumps(old), encoding='utf-8')
            upgraded = self.run_job('analyze')['state']
        self.assertEqual(upgraded['events'], old['events'])
        self.assertEqual(upgraded['words'][0]['text'], 'hello')
        self.assertEqual(upgraded['schema'], 3)

if __name__ == '__main__': unittest.main()
