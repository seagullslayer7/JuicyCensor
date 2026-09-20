import os
from pathlib import Path
import unittest
from unittest.mock import patch
from bootstrap import Installer, SetupCommandError

ERROR = 'error: Failed to create Python minor version link directory\n  cause: untrusted mount point. (os error 448)'

@unittest.skipUnless(os.name == 'nt', 'Windows setup recovery')
class SetupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.installer = Installer(Path.cwd(), lambda message: None)

    def test_verified_direct_interpreter_after_448(self):
        with patch.object(self.installer, 'command', side_effect=[SetupCommandError(ERROR), None]) as command, patch.object(Path, 'is_file', return_value=True):
            python = self.installer.install_private_python('uv.exe', '3.12.14')
        self.assertEqual(command.call_count, 2)
        self.assertEqual(command.call_args.args[0][0], python)
        self.assertEqual(command.call_args.args[0][1:3], ['-I', '-c'])
        self.assertIn('3.12.14', command.call_args.args[0][3])
        self.assertIn('struct.calcsize', command.call_args.args[0][3])

    def test_unrelated_errors_are_not_recovered(self):
        for message in ['download failed', ERROR.replace('448', '5'), 'unrelated failure (os error 448)']:
            with self.subTest(message=message), patch.object(self.installer, 'command', side_effect=SetupCommandError(message)) as command:
                with self.assertRaises(SetupCommandError):
                    self.installer.install_private_python('uv.exe', '3.12.14')
                self.assertEqual(command.call_count, 1)

    def test_missing_python_stops_recovery(self):
        with patch.object(self.installer, 'command', side_effect=SetupCommandError(ERROR)) as command, patch.object(Path, 'is_file', return_value=False):
            with self.assertRaises(SetupCommandError):
                self.installer.install_private_python('uv.exe', '3.12.14')
            self.assertEqual(command.call_count, 1)

    def test_broken_python_stops_recovery(self):
        with patch.object(self.installer, 'command', side_effect=[SetupCommandError(ERROR), SetupCommandError('Invalid interpreter')]), patch.object(Path, 'is_file', return_value=True):
            with self.assertRaises(SetupCommandError):
                self.installer.install_private_python('uv.exe', '3.12.14')

    def test_cancelled_setup_does_not_continue(self):
        self.installer.cancelled.set()
        with patch.object(self.installer, 'command', side_effect=SetupCommandError(ERROR)) as command:
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                self.installer.install_private_python('uv.exe', '3.12.14')
            self.assertEqual(command.call_count, 1)

    def test_success_does_not_enter_recovery(self):
        with patch.object(self.installer, 'command') as command:
            self.installer.install_private_python('uv.exe', '3.12.14')
            self.assertEqual(command.call_count, 1)

if __name__ == '__main__':
    unittest.main()
