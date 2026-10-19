"""Build CHIRP-Plus for Windows with PyInstaller.

Usage:
  .venv\\Scripts\\python tools\\build_windows.py [version]
      Folder build in %LOCALAPPDATA%\\Programs\\CHIRP-Plus plus a ZIP of it
      in dist/ (to install on this PC).
  .venv\\Scripts\\python tools\\build_windows.py --onefile [version]
      One CHIRP-Plus.exe to share, in dist/condivisione/ together with
      LEGGIMI.txt and the source code (CHIRP is GPLv3: whoever receives
      the program must be able to get its source).

Builds happen outside the source tree: OneDrive locks files mid-build. The
version defaults to next-20261016-plus (the upstream build this fork is
based on). chirp/__init__.py and chirp/drivers/__init__.py are restored
after the build.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, 'chirp', '__init__.py')
DRIVERS_INIT = os.path.join(ROOT, 'chirp', 'drivers', '__init__.py')
DISTPATH = os.path.join(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()),
                        'Programs')
SHARE_DIR = os.path.join(ROOT, 'dist', 'condivisione')

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(nums)s, prodvers=%(nums)s, mask=0x3f,
                    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[StringFileInfo([StringTable('041004B0', [
      StringStruct('CompanyName', 'CHIRP Plus'),
      StringStruct('FileDescription', 'CHIRP Plus - programmazione radio'),
      StringStruct('FileVersion', '%(version)s'),
      StringStruct('InternalName', 'CHIRP-Plus'),
      StringStruct('LegalCopyright', 'GPLv3 - CHIRP contributors'),
      StringStruct('OriginalFilename', 'CHIRP-Plus.exe'),
      StringStruct('ProductName', 'CHIRP Plus'),
      StringStruct('ProductVersion', '%(version)s')])]),
        VarFileInfo([VarStruct('Translation', [0x0410, 1200])])]
)
"""

README = """CHIRP Plus %(version)s
=========================

Programma per leggere e scrivere le memorie delle radio (Baofeng e molte
altre), basato su CHIRP (https://chirpmyradio.com).

AVVIO
- Doppio clic su CHIRP-Plus.exe. Non serve installarlo.
- Il primo avvio richiede qualche secondo in piu': il programma si
  prepara in una cartella temporanea.
- Windows potrebbe mostrare "Windows ha protetto il PC" perche' il file
  non e' firmato: clic su "Ulteriori informazioni" > "Esegui comunque".

PRIMO USO
1. Collega il cavo di programmazione al PC e alla radio, poi accendi la
   radio. Il cavo viene riconosciuto da solo (in alto a destra
   compare "[ OK ] cavo: COMx").
2. Premi 3 (o Radio > Rileva radio e scarica): il programma riconosce la
   radio e ne scarica le memorie.
3. Modifica i canali e usa "carica sulla radio". Prima di scrivere
   mostra cosa cambiera'; dopo, rilegge la radio e verifica.
Se il cavo non viene trovato serve il suo driver (CH340, PL2303, FTDI o
CP210x, dal sito del produttore).

COLORI
verde = ok, giallo = attenzione, rosso = errore, blu = legge la radio,
arancio = scrive la radio, bianco = file, magenta = toni.

PRUDENZA
- Prima di ogni scrittura il programma salva una copia della radio
  (File > Backup).
- Trasmetti solo dove sei autorizzato: Radio > Controlla frequenze
  segnala licenze e limiti di potenza (regole italiane).

LICENZA
Software libero GPLv3, senza garanzia. Il codice sorgente di questa
versione e' in CHIRP-Plus-sorgente.zip, accanto a questo file.
"""


def version_numbers(version):
    m = re.search(r'(\d{4})(\d{2})(\d{2})', version)
    if not m:
        return (0, 0, 0, 1)
    return tuple(int(x) for x in m.groups()) + (1,)


def build(version, onefile):
    subprocess.check_call([sys.executable,
                           os.path.join(ROOT, 'tools', 'compile_locales.py')])
    workpath = os.path.join(tempfile.gettempdir(), 'chirp-plus-build')
    distpath = (os.path.join(tempfile.gettempdir(), 'chirp-plus-onefile')
                if onefile else DISTPATH)
    os.makedirs(workpath, exist_ok=True)
    version_file = os.path.join(workpath, 'version_info.txt')
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(VERSION_INFO % {'nums': version_numbers(version),
                                'version': version})
    env = dict(os.environ, CHIRP_VERSION_FILE=version_file)
    if onefile:
        env['CHIRP_ONEFILE'] = '1'

    with open(INIT, 'rb') as f:
        original = f.read()
    with open(DRIVERS_INIT, 'rb') as f:
        original_drivers = f.read()
    try:
        with open(INIT, 'wb') as f:
            f.write(original.replace(
                b'CHIRP_VERSION = "py3dev"',
                b'CHIRP_VERSION = "%s"' % version.encode()))
        # chirp/drivers/__init__.py globs *.py to build __all__, which finds
        # nothing in a frozen app (directory.import_drivers() relies on it).
        # Like the official build, freeze it into a static list.
        drivers = sorted(
            os.path.splitext(fn)[0]
            for fn in os.listdir(os.path.dirname(DRIVERS_INIT))
            if fn.endswith('.py') and not fn.startswith('__'))
        with open(DRIVERS_INIT, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# Generated by tools/build_windows.py\n'
                    '__all__ = %r\n' % drivers)
        print('Frozen driver list: %i drivers' % len(drivers))
        subprocess.check_call([sys.executable, '-m', 'PyInstaller',
                               '--noconfirm', '--clean',
                               '--workpath', workpath,
                               '--distpath', distpath,
                               os.path.join(ROOT, 'chirp-plus.spec')],
                              cwd=ROOT, env=env)
    finally:
        with open(INIT, 'wb') as f:
            f.write(original)
        with open(DRIVERS_INIT, 'wb') as f:
            f.write(original_drivers)
    return distpath


def share_package(distpath, version):
    os.makedirs(SHARE_DIR, exist_ok=True)
    exe = os.path.join(SHARE_DIR, 'CHIRP-Plus.exe')
    shutil.copy2(os.path.join(distpath, 'CHIRP-Plus.exe'), exe)
    with open(os.path.join(SHARE_DIR, 'LEGGIMI.txt'), 'w',
              encoding='utf-8', newline='\r\n') as f:
        f.write(README % {'version': version})
    source = os.path.join(SHARE_DIR, 'CHIRP-Plus-sorgente.zip')
    subprocess.check_call(['git', 'archive', '--format=zip',
                           '--prefix=chirp-plus/', '-o', source, 'HEAD'],
                          cwd=ROOT)
    archive = shutil.make_archive(
        os.path.join(ROOT, 'dist', 'CHIRP-Plus-%s-condivisione' % version),
        'zip', SHARE_DIR)
    print('Shareable exe %s\nPackage %s' % (exe, archive))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('version', nargs='?', default='next-20261016-plus')
    parser.add_argument('--onefile', action='store_true',
                        help='one shareable CHIRP-Plus.exe')
    args = parser.parse_args()
    distpath = build(args.version, args.onefile)
    if args.onefile:
        share_package(distpath, args.version)
        return
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    archive = shutil.make_archive(
        os.path.join(ROOT, 'dist', 'CHIRP-Plus-%s' % args.version), 'zip',
        DISTPATH, 'CHIRP-Plus')
    app = os.path.join(DISTPATH, 'CHIRP-Plus')
    print('Built %s\nArchive %s' % (app, archive))


if __name__ == '__main__':
    main()
