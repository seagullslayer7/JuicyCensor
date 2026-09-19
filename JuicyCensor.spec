from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / 'JuicyCensorApp.py')], pathex=[str(root / 'vendor')],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
# Qt uses the unversioned ICU API supplied by Windows 10/11. A third-party
# icuuc.dll on PATH (for example Poppler's versioned ICU) is incompatible.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JuicyCensor',
          debug=False, strip=False, upx=False, console=False, icon=str(root / 'assets' / 'orange.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='JuicyCensor')
