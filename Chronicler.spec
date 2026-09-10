# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['chronicler/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('chronicler/migrations', 'chronicler/migrations'), ('chronicler/webclient/src', 'chronicler/webclient/src')],
    hiddenimports=['aiosqlite'],
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
    [],
    exclude_binaries=True,
    name='Chronicler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Chronicler',
)
