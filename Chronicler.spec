# -*- mode: python ; coding: utf-8 -*-
#
# Regenerate with scripts/pack.sh, which runs `flet pack` with the data files and hidden
# imports below. Anything hand-edited here must be mirrored into that script, or the next
# regen silently drops it. See docs/packaging.md.

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
    # Windowed, which is what `flet pack` emits unless --debug-console is passed. Setup
    # therefore happens in the Flet window (chronicler/desktop/views/wizard.py) rather than
    # on stdin, and `chronicler server` borrows the calling terminal's console at startup -
    # see attach_windows_console() in chronicler/__main__.py and docs/packaging.md.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.png'],
)
