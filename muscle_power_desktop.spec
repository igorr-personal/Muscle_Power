# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Muscle Power Desktop.

Build:
    pyinstaller muscle_power_desktop.spec

Output:
    dist/Musclepower.exe  (single-file, no console)
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve source paths
# ---------------------------------------------------------------------------
ROOT = Path(SPECPATH)
SRC = ROOT / "src"

block_cipher = None

a = Analysis(
    [str(SRC / "muscle_power_desktop" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        # Config + data
        (str(ROOT / "config.yaml"), "."),
        # KB directory (may be empty — required for KBConfig)
        (str(ROOT / "kb_data"), "kb_data"),
        # Documents folder
        (str(ROOT / "documents"), "documents"),
    ],
    hiddenimports=[
        # SQLAlchemy dialects
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.pool",
        # scipy / numpy internals
        "scipy.signal",
        "scipy.fft",
        "scipy.linalg",
        "numpy.core._multiarray_umath",
        # pandas
        "pandas",
        # pyqtgraph
        "pyqtgraph",
        "pyqtgraph.graphicsItems",
        "pyqtgraph.Qt",
        # Bluetooth / sensor SDK
        "bleak",
        # FPDF
        "fpdf",
        # Our packages
        "muscle_power",
        "muscle_power.db",
        "muscle_power.services",
        "muscle_power.utils",
        "muscle_power_desktop",
        "muscle_power_desktop.pages",
        "muscle_power_desktop.widgets",
        "muscle_power_desktop.windows",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "streamlit",
        "plotly",
        "sentence_transformers",
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Musclepower",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
