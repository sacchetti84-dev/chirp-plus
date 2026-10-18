"""Build CHIRP-Plus for Windows (PyInstaller onedir) plus a ZIP of it.

Usage:  .venv\\Scripts\\python tools\\build_windows.py [version]

The program goes to %LOCALAPPDATA%\\Programs\\CHIRP-Plus (outside any synced
folder: OneDrive locks files mid-build) and a copy is zipped into
dist/CHIRP-Plus-<version>.zip. The version defaults to next-20261016-plus
(the upstream build this fork is based on). chirp/__init__.py is restored
after the build.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, 'chirp', '__init__.py')
DISTPATH = os.path.join(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()),
                        'Programs')


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else 'next-20261016-plus'
    subprocess.check_call([sys.executable,
                           os.path.join(ROOT, 'tools', 'compile_locales.py')])
    with open(INIT, 'rb') as f:
        original = f.read()
    try:
        with open(INIT, 'wb') as f:
            f.write(original.replace(
                b'CHIRP_VERSION = "py3dev"',
                b'CHIRP_VERSION = "%s"' % version.encode()))
        workpath = os.path.join(tempfile.gettempdir(), 'chirp-plus-build')
        subprocess.check_call([sys.executable, '-m', 'PyInstaller',
                               '--noconfirm', '--clean',
                               '--workpath', workpath,
                               '--distpath', DISTPATH,
                               os.path.join(ROOT, 'chirp-plus.spec')],
                              cwd=ROOT)
    finally:
        with open(INIT, 'wb') as f:
            f.write(original)
    app = os.path.join(DISTPATH, 'CHIRP-Plus')
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    archive = shutil.make_archive(
        os.path.join(ROOT, 'dist', 'CHIRP-Plus-%s' % version), 'zip',
        DISTPATH, 'CHIRP-Plus')
    print('Built %s\nArchive %s' % (app, archive))


if __name__ == '__main__':
    main()
