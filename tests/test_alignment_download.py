import io
from pathlib import Path
import re
import sys
import tempfile
import shutil
from uuid import uuid4
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_download as models


class Response(io.BytesIO):
    def __init__(self, data, content_range, status=206):
        super().__init__(data)
        self.status = status
        self.headers = {'Content-Range': content_range, 'ETag': '"model-v1"'}


class AlignmentDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.gettempdir()).resolve()
        self.folder = self.temp_root / ('juicy-alignment-' + uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(self.clean_folder)
        self.target = self.folder / 'model.pth'
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('archive/data.pkl', b'demo checkpoint data' * 10)
        self.data = data.getvalue()
        self.calls = []

    def clean_folder(self):
        assert self.folder.resolve().parent == self.temp_root and not self.folder.is_symlink()
        shutil.rmtree(self.folder)

    def response(self, request, timeout):
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', request.get_header('Range')).groups())
        self.calls.append((start, end))
        if end:
            self.assertEqual(request.get_header('If-match'), '"model-v1"')
        return Response(self.data[start:end+1], f'bytes {start}-{end}/{len(self.data)}')

    def download(self, fetch=None):
        with patch.object(models, 'ALIGNMENT_CHUNK', 64), patch.object(models.urllib.request, 'urlopen', side_effect=fetch or self.response):
            models.ensure_alignment_checkpoint(self.target, progress=lambda message: None)

    def test_completed_cache_is_reused_without_network(self):
        self.target.write_bytes(self.data)
        with patch.object(models.urllib.request, 'urlopen', side_effect=AssertionError('Network not needed')):
            models.ensure_alignment_checkpoint(self.target)
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_truncated_cache_is_replaced_only_after_complete_download(self):
        self.target.write_bytes(self.data[:30])
        self.download()
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertGreater(len(self.calls), 3)
        self.assertFalse(list(self.target.parent.glob('*.partial')))

    def test_short_chunk_retries_same_range(self):
        failed = False
        def fetch(request, timeout):
            nonlocal failed
            response = self.response(request, timeout)
            if request.get_header('Range') == 'bytes=64-127' and not failed:
                failed = True
                return Response(b'x', response.headers['Content-Range'])
            return response
        self.download(fetch)
        self.assertEqual(self.calls.count((64, 127)), 2)
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_failed_download_keeps_old_cache_and_cleans_partial(self):
        self.target.write_bytes(b'old incomplete data')
        def fetch(request, timeout):
            if request.get_header('Range') != 'bytes=0-0':
                raise OSError('connection interrupted')
            return self.response(request, timeout)
        with self.assertRaisesRegex(RuntimeError, 'could not finish'):
            self.download(fetch)
        self.assertEqual(self.target.read_bytes(), b'old incomplete data')
        self.assertFalse(list(self.target.parent.glob('*.partial')))

    def test_server_ignoring_range_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'valid download range'):
            self.download(lambda request, timeout: Response(self.data, '', status=200))
        self.assertFalse(self.target.exists())

    def test_corrupt_archive_is_not_installed(self):
        self.data = self.data.replace(b'demo checkpoint data', b'bad! checkpoint data', 1)
        with self.assertRaisesRegex(RuntimeError, 'integrity check'):
            self.download()
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.target.parent.glob('*.partial')))


if __name__ == '__main__':
    unittest.main()
