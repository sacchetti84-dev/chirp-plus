# Copyright 2026 CHIRP Plus contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Licenses of the third-party software frozen into the Windows build.

The executable carries Python, wxPython, requests and other libraries.
Their licenses (MIT, BSD, Apache, PSF, MPL, LGPL...) ask that their
notices travel with every binary copy, and the LGPL and MPL ones that
their source stays available. chirp-plus.spec calls notices() on the
exact list of files PyInstaller bundles, so nothing is forgotten when a
version changes; a bundled file that belongs to no known package stops
the build.
"""
import os
import re
import sys
import zipfile
from importlib import metadata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ICONS_LICENSE = os.path.join(ROOT, 'chirp', 'share', 'icons', 'LICENSE')
FALLBACK = os.path.join(HERE, 'third_party_licenses')
LICENSE_FILE = re.compile(r'(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$',
                          re.I)
# Copyleft licenses that want their source next to the binary
SOURCE_NEEDED = re.compile(r'LGPL|Lesser|MPL|Mozilla', re.I)
# wxPython is LGPL with the wxWindows exception, which lets binaries go
# without the source; it is still listed, with its license
SOURCE_EXEMPT = {'wxpython'}


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _site_packages():
    return [_norm(p) for p in sys.path if p.endswith('site-packages')]


def _owners():
    """{normalized file path: distribution} for every installed file"""
    owners = {}
    for dist in metadata.distributions():
        for f in dist.files or []:
            owners[_norm(dist.locate_file(f))] = dist
    return owners


def bundled(toc):
    """Distributions behind the (name, path, typecode) entries of a TOC.

    Returns ({name: distribution}, uses_python) and raises if a file from
    site-packages belongs to no distribution.
    """
    owners = _owners()
    sites = _site_packages()
    base = _norm(sys.base_prefix)
    found, unknown, python = {}, [], False
    for entry in toc:
        path = entry[1]
        if not path or not os.path.isabs(path):
            continue
        key = _norm(path)
        dist = owners.get(key)
        if dist is not None:
            found[dist.metadata['Name'].lower()] = dist
        elif any(key.startswith(s) for s in sites):
            unknown.append(path)
        elif key.startswith(base):
            python = True
    if unknown:
        raise RuntimeError('Bundled files of unknown license, add them to '
                           'tools/third_party.py: %s' % unknown[:5])
    # The bootloader at the start of the executable comes from PyInstaller
    # (GPL with an exception that allows any license for the program)
    found['pyinstaller'] = metadata.distribution('pyinstaller')
    return found, python


def license_name(dist):
    meta = dist.metadata
    if meta['Name'].lower() == 'pyinstaller':
        return 'GPL-2.0-or-later with the bootloader exception'
    name = meta.get('License-Expression') or ''
    if not name:
        lic = (meta.get('License') or '').strip()
        if 'classifiers' in lic or len(lic) > 80 or '\n' in lic:
            lic = ''    # "(specified using classifiers)" or a whole text
        name = lic
    if not name:
        name = ', '.join(c.split(' :: ')[-1]
                         for c in meta.get_all('Classifier') or []
                         if c.startswith('License ::'))
    return name or 'see below'


def license_texts(dist):
    texts = []
    for f in sorted(dist.files or [], key=str):
        if LICENSE_FILE.search(str(f).replace('\\', '/')):
            try:
                texts.append((str(f), dist.locate_file(f).read_text(
                    encoding='utf-8', errors='replace')))
            except OSError:
                pass
    fallback = os.path.join(FALLBACK, '%s.txt' %
                            dist.metadata['Name'].lower())
    if not texts and os.path.exists(fallback):
        with open(fallback, encoding='utf-8') as f:
            texts.append(('license (from the source package)', f.read()))
    if not texts:
        raise RuntimeError('No license text for %s: add one to %s' % (
            dist.metadata['Name'], FALLBACK))
    return texts


def needs_source(dist):
    return (dist.metadata['Name'].lower() not in SOURCE_EXEMPT and
            bool(SOURCE_NEEDED.search(license_name(dist))))


def notices(toc, path):
    """Write the notices of everything in @toc to @path"""
    dists, python = bundled(toc)
    rule = '=' * 78
    out = ['Third-party software in CHIRP Plus',
           rule, '',
           'CHIRP Plus itself is free software under the GNU GPL version 3',
           'or later (see COPYING in the source). The program bundles the',
           'components below; each keeps its own license, reproduced here.',
           'The source of the LGPL and MPL components is in',
           'CHIRP-Plus-librerie-sorgente.zip, next to the program.', '']
    for dist in sorted(dists.values(), key=lambda d: d.metadata['Name']):
        out.append('- %s %s: %s' % (dist.metadata['Name'], dist.version,
                                    license_name(dist)))
    if python:
        out.append('- Python %s: PSF License Agreement (with the licenses '
                   'of its own components)' % sys.version.split()[0])
    out.append('- Microsoft Visual C++ runtime (vcruntime140*.dll): '
               'redistributable under the Visual Studio license terms')
    out.append('- Tabler Icons (chirp/share/icons): MIT')
    out.append('')
    for dist in sorted(dists.values(), key=lambda d: d.metadata['Name']):
        out += [rule, '%s %s - %s' % (
            dist.metadata['Name'], dist.version, license_name(dist))]
        home = dist.metadata.get('Home-page') or ''
        if home:
            out.append(home)
        out.append(rule)
        for name, text in license_texts(dist):
            out += ['', '--- %s' % name, '', text.strip(), '']
    out += [rule, 'Tabler Icons - MIT', 'https://tabler.io/icons', rule, '']
    with open(ICONS_LICENSE, encoding='utf-8') as f:
        out += [f.read().strip(), '']
    if python:
        out += [rule, 'Python %s' % sys.version.split()[0], rule, '']
        with open(os.path.join(sys.base_prefix, 'LICENSE.txt'),
                  encoding='utf-8', errors='replace') as f:
            out.append(f.read().strip())
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
    return path


def sources(toc, path):
    """Zip the installed source of the LGPL/MPL components to @path"""
    dists, _python = bundled(toc)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for dist in dists.values():
            if not needs_source(dist):
                continue
            prefix = '%s-%s' % (dist.metadata['Name'], dist.version)
            for f in dist.files or []:
                name = str(f).replace('\\', '/')
                if name.endswith(('.pyc', 'RECORD', 'INSTALLER')):
                    continue
                full = dist.locate_file(f)
                if os.path.isfile(full):
                    z.write(full, '%s/%s' % (prefix, name))
            for name, text in license_texts(dist):
                if not os.path.isfile(dist.locate_file(name)):
                    z.writestr('%s/LICENSE.txt' % prefix, text)
    return path
