# Building JuicyCensor 2.0

Use Windows x64, Python 3.12.10 for the frozen GUI, PyInstaller 6.21.0, PySide6 6.11.2,
and Inno Setup 7.1.0. The private processing environment uses Python 3.12.14.

```powershell
python -m venv build-env
.\build-env\Scripts\python.exe -m pip install PyInstaller==6.21.0 -r requirements-ui.txt
.\build-env\Scripts\python.exe build_release.py --iscc 'C:\path\to\ISCC.exe' --output release
```

Use a fresh output directory each build. The builder creates Setup.exe, Portable.zip,
Source.zip and SHA256SUMS.txt. PyInstaller's specification deliberately excludes an
incompatible third-party ICU DLL that some developer machines expose through PATH.
Qt uses the Windows ICU API. Do not add another application's DLLs to the bundle.

`bootstrap-tools/uv.exe` must be uv 0.12.17, matching release-manifest.json. The source
ZIP includes it. Git checkout users can obtain the verified binary from the official
uv release; the GitHub workflow automates this step.

## Dependency policy

WhisperX 3.8.6 constrains torch/torchaudio to 2.8.x and torchvision to 0.23.x. Runtime
locks resolve compatible packages for Windows Python 3.12, using CPU or CUDA 12.8
PyTorch wheels. Hashes are required and end-user setup permits wheels only.

The ANTLR runtime 4.9.3 wheel in vendor_wheels was built from its verified PyPI source
using `setup.py bdist_wheel`; its SHA-256 is pinned in both locks. Preserve this wheel
and its hash when regenerating locks (PyPI distributes only its source archive).
To update dependencies, regenerate both locks, verify the wheel hash and remove
machine-specific paths from generated comments, then rerun setup and media tests.

Never package runtime.local.json, venv, runtime, vendor, caches, personal videos,
Git metadata or reports. build_release.py uses an explicit allowlist.

## Publishing on GitHub

1. Commit and push the reviewed source to the project repository.
2. Tag that exact commit `v2.0.0` and push the tag.
3. The release workflow builds artifacts and creates a **draft** GitHub Release.
4. Review its assets, notes and validation results, then publish it. Mark it latest.

Manual alternative: create a draft release for the exact source commit, attach the
three release downloads plus SHA256SUMS.txt, paste RELEASE-NOTES.md, then publish.
The Releases page is where users download Setup.exe or Portable.zip. GitHub's automatic
source archive is not the portable application.

The installer defaults to a per-user folder, lets users choose a destination, and
creates an uninstall entry and optional shortcuts. `/PORTABLE=1` is a documented
extraction mode for verification; it suppresses registry entries and shortcuts.
The portable ZIP is the recommended portable distribution.

For unattended runtime verification, explicitly opt in with
`JuicyCensor.exe --setup-runtime cpu --skip-models` (or `cuda`). Omit `--skip-models`
to fetch the starter models too. This downloads dependencies and logs to
`logs/setup.log`; a zero exit code indicates success. Normal first launch always
presents the consent/setup dialog instead.
