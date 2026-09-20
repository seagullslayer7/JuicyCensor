"""Build versioned Windows installer, portable ZIP, source ZIP and checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
PAYLOAD_FILES = ['JuicyCensorApp.py', 'autocensor.py', 'worker.py', 'transcription.py',
    'runtime_paths.py', 'bootstrap.py', 'setup_wizard.py', 'setup_verify.py',
    'install_runtime.py', 'model_download.py', 'config.json', 'banned_words.txt',
    'banned_phrases.txt', 'beep.mp3', 'release-manifest.json', 'requirements-cpu.lock',
    'requirements-cuda.lock', 'LICENSE', 'README.md', 'THIRD-PARTY.md', 'VALIDATION.md',
    'BUILDING.md', 'RELEASE-NOTES.md']
PAYLOAD_DIRS = ['assets', 'licenses', 'vendor_wheels', 'bootstrap-tools']
SOURCE_EXTRA = ['JuicyCensor.spec', 'build_release.py', 'requirements-ui.txt',
    'requirements-dev.txt', 'requirements-runtime.in', 'requirements-cpu.in',
    'requirements-cuda.in', '.gitignore']


def zip_folder(folder, output, prefix):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(folder.rglob('*')):
            if item.is_file():
                archive.write(item, str(Path(prefix) / item.relative_to(folder)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiled', type=Path, help='Existing PyInstaller output folder; omit to build')
    parser.add_argument('--iscc', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    compiled = args.compiled
    if not compiled:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT/'JuicyCensor.spec')], cwd=ROOT, check=True)
        compiled = ROOT / 'dist/JuicyCensor'
    payload = output / 'JuicyCensor-2.0.1-Windows-x64'
    if payload.exists():
        raise SystemExit('Use an empty release output folder to avoid carrying stale files into a release.')
    shutil.copytree(compiled, payload)
    for name in PAYLOAD_FILES:
        shutil.copy2(ROOT / name, payload / name)
    for name in PAYLOAD_DIRS:
        shutil.copytree(ROOT / name, payload / name)
    # This allowlist intentionally excludes environments, models, caches, local
    # overrides, personal exports, Git metadata and build files.
    zip_folder(payload, output/'JuicyCensor-2.0.1-Windows-x64-Portable.zip', payload.name)
    source = output / 'JuicyCensor-2.0.1-Source'
    source.mkdir()
    for name in PAYLOAD_FILES + SOURCE_EXTRA:
        shutil.copy2(ROOT/name, source/name)
    for name in PAYLOAD_DIRS + ['installer', 'tests', '.github']:
        shutil.copytree(ROOT/name, source/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    zip_folder(source, output/'JuicyCensor-2.0.1-Source.zip', source.name)
    subprocess.run([str(args.iscc.resolve()), f'/DPayloadDir={payload}', f'/DReleaseDir={output}',
                    str(ROOT/'installer/JuicyCensor.iss')], check=True, cwd=ROOT)
    files = sorted([*output.glob('*.zip'), *output.glob('*Setup.exe')])
    lines = []
    for file in files:
        with file.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        lines.append(f'{digest}  {file.name}')
    (output/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Release files created in', output)


if __name__ == '__main__':
    main()
