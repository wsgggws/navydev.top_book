# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: self-contained lector with an installed private runtime.

The bundle carries the Python interpreter, Textual and Rich inside itself,
so installing it needs no Python at all. COLLECT expands the runtime once at
installation; the bootloader never unpacks it again on each launch.
"""

from pathlib import Path

PROJECT = Path(SPECPATH).parent
ENTRY = PROJECT / "packaging" / "entry.py"

analysis = Analysis(
    [str(ENTRY)],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "lector_tui",
        "lector_tui.screens.library",
        "lector_tui.screens.listen",
        "lector_tui.screens.reader",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data", "test"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="lector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="lector",
)
