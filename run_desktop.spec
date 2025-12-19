# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Deck Builder Desktop Application
Packages the Flask app with pywebview into a standalone Windows executable
"""

block_cipher = None

a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),  # Flask templates
        # Add any other static resources if needed
    ],
    hiddenimports=[
        # Application modules
        'api',
        'main',
        'edhrec_provider',

        # Core dependencies
        'flask',
        'webview',
        'requests',
        'unidecode',
        'pyedhrec',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'tkinter',
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
    name='DeckBuilder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for windowed app (no console), True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add path to .ico file if you have an icon
)
