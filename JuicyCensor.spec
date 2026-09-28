from pathlib import Path
import json
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

root = Path(SPECPATH)
version = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))['version']
version_tuple = tuple(int(part) for part in version.split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                     mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', 'JuicyCensor'),
        StringStruct('FileVersion', version),
        StringStruct('ProductName', 'JuicyCensor'),
        StringStruct('ProductVersion', version),
        StringStruct('OriginalFilename', 'JuicyCensor.exe'),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)
a = Analysis([str(root / 'JuicyCensorApp.py')], pathex=[str(root / 'vendor')],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
# Qt uses the unversioned ICU API supplied by Windows 10/11. A third-party
# icuuc.dll on PATH (for example Poppler's versioned ICU) is incompatible.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JuicyCensor',
          debug=False, strip=False, upx=False, console=False,
          version=version_info, icon=str(root / 'assets' / 'orange.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='JuicyCensor')
