# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cabinet_status_main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets\\\\app_icon.ico', 'assets'), ('db_config.ini', '.'), ('app_style.qss', '.'), ('assets', 'assets')],
    hiddenimports=['pyodbc'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='cabinet_status',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app_icon.ico'],
)
