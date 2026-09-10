# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['chronicler/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('chronicler/migrations', 'chronicler/migrations'), ('chronicler/webclient/src', 'chronicler/webclient/src')],
    hiddenimports=['aiosqlite', 're._parser', 'logging.config'],
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
    name='Chronicler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.png'],
)
