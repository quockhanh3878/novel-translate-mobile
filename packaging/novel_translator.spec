# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec cho ban Windows (thu muc, khong phai 1 file: khoi dong nhanh, it bi
# antivirus nham, tien trinh con --worker khong phai giai nen lai).
# Build: powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "dictionaries" / "idioms_verified.json"), "dictionaries"),
    (str(ROOT / "dictionaries" / "idioms_curated.json"), "dictionaries"),
    (str(ROOT / "dictionaries" / "hanviet_words.json"), "dictionaries"),
]
for package in ("opencc", "cloudscraper", "holidays", "certifi"):
    datas += collect_data_files(package)

hiddenimports = (
    collect_submodules("holidays.countries")  # holidays nap tung nuoc bang importlib khi chay
    + ["pipeline", "multi_pipeline", "prepare_novel", "build_idiom_dictionary"]
)

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "numpy", "onnxruntime", "pytest", "matplotlib", "scipy", "pandas", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NovelTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # can console: tien trinh con --worker doc log qua pipe, va cua so nay la noi tat app
    icon=str(ROOT / "packaging" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NovelTranslator",
)
