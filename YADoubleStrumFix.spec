from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("vgamepad")
datas.append(("icon.ico", "."))
binaries = collect_dynamic_libs("vgamepad")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=["vgamepad", "pygame"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="YADoubleStrumFix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico',
)
