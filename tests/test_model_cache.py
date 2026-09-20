"""Exercise the real Hub cache when Windows denies symbolic-link privileges."""
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4
from runtime_paths import configure_model_cache

@unittest.skipUnless(os.name == 'nt', 'Windows cache behavior')
class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        from huggingface_hub import file_download
        self.hub = file_download
        self.probe = self.hub.are_symlinks_supported
        self.root = Path.cwd() / ('cache-test-' + uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        self.hub.are_symlinks_supported = self.probe
        assert self.root.resolve().parent == Path.cwd().resolve()
        shutil.rmtree(self.root)

    def test_reuse_existing_blob_without_symlink_privilege(self):
        source, destination = self.root/'blob', self.root/'config.json'
        source.write_text('{"model":"test"}')
        self.hub.are_symlinks_supported = lambda *a, **kw: True
        configure_model_cache()
        with patch('os.symlink', side_effect=OSError(1314, 'Privilege missing')) as symlink:
            self.hub._create_symlink(str(source), str(destination), new_blob=False)
            self.assertFalse(symlink.called)
        self.assertEqual(source.read_bytes(), destination.read_bytes())
        self.assertFalse(destination.is_symlink())
        self.assertTrue(source.exists())

    def test_new_download_moves_into_snapshot_without_symlink(self):
        source, destination = self.root/'new-blob', self.root/'model.bin'
        source.write_bytes(b'model payload')
        configure_model_cache()
        configure_model_cache()
        with patch('os.symlink', side_effect=OSError(1314, 'Privilege missing')) as symlink:
            self.hub._create_symlink(str(source), str(destination), new_blob=True)
            self.assertFalse(symlink.called)
        self.assertEqual(destination.read_bytes(), b'model payload')
        self.assertFalse(source.exists())

    def test_missing_source_is_not_silently_ignored(self):
        configure_model_cache()
        with self.assertRaises(FileNotFoundError):
            self.hub._create_symlink(str(self.root/'missing'), str(self.root/'target'))

if __name__ == '__main__':
    unittest.main()
