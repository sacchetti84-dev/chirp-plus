# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for a Windows onedir build, laid out like the official
# CHIRP installer (chirpwx.exe + chirp/{share,stock_configs,locale}).
# Build with:  python tools/build_windows.py
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(SPECPATH)


def tree(src, dest, skip=('.xcf', '.pyc')):
    out = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, src)):
        rel = os.path.relpath(dirpath, ROOT)
        for fn in files:
            if fn.endswith(skip) or fn.endswith('~'):
                continue
            out.append((os.path.join(dirpath, fn),
                        os.path.join(dest, os.path.relpath(rel, src))))
    return out


datas = (tree('chirp/share', 'chirp/share') +
         tree('chirp/stock_configs', 'chirp/stock_configs') +
         tree('chirp/locale', 'chirp/locale', skip=('.py', '~')) +
         # Standard wx strings (OK/Cancel buttons and so on)
         collect_data_files('wx', includes=['locale/**/*.mo']))

# Drivers are discovered dynamically, so every module must be bundled
hiddenimports = (collect_submodules(
    'chirp', filter=lambda name: not name.startswith('chirp.cli')) +
    ['serial.tools.list_ports', 'win32api', 'lark',
     # wx.richtext imports these from C code, invisible to the analysis
     'wx._xml', 'wx._html', 'wx._adv'])

a = Analysis(
    ['chirpwx.py'],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['chirp.cli', 'tests', 'tkinter', 'numpy'],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = os.path.join(ROOT, 'chirp', 'share', 'chirp.ico')
console = bool(os.environ.get('CHIRP_CONSOLE'))
# Written by tools/build_windows.py: Windows file properties
version_file = os.environ.get('CHIRP_VERSION_FILE') or None

if os.environ.get('CHIRP_ONEFILE'):
    # One self-contained CHIRP-Plus.exe to share: unpacks itself in a
    # temporary folder at every start (a few seconds)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='CHIRP-Plus',
        console=console,
        icon=icon,
        version=version_file,
        upx=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='chirpwx',
        console=console,
        icon=icon,
        version=version_file,
        contents_directory='.',
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        name='CHIRP-Plus',
    )
