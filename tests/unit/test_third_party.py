import importlib.util
import os
import sys
import tempfile
import unittest
import zipfile

import serial
import yattag

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def load():
    path = os.path.join(ROOT, 'tools', 'third_party.py')
    spec = importlib.util.spec_from_file_location('third_party', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestThirdParty(unittest.TestCase):
    def setUp(self):
        self.tp = load()
        self.tmp = tempfile.mkdtemp()
        self.toc = [('serial', serial.__file__, 'PYMODULE'),
                    ('yattag', yattag.__file__, 'PYMODULE'),
                    ('os', os.__file__, 'PYMODULE')]

    def test_notices_reproduce_every_license(self):
        path = self.tp.notices(self.toc, os.path.join(self.tmp, 'n.txt'))
        with open(path, encoding='utf-8') as f:
            text = f.read()
        # pyserial and yattag install no license file: the fallback texts
        self.assertIn('Chris Liechti', text)
        self.assertIn('GNU LESSER GENERAL PUBLIC LICENSE', text)
        self.assertIn('PYTHON SOFTWARE FOUNDATION LICENSE', text)
        self.assertIn('pyinstaller', text)      # the bootloader
        self.assertIn('Tabler Icons', text)

    def test_lgpl_source_is_zipped(self):
        path = self.tp.sources(self.toc, os.path.join(self.tmp, 's.zip'))
        names = zipfile.ZipFile(path).namelist()
        self.assertTrue(any(n.endswith('yattag/__init__.py') for n in names))
        self.assertFalse(any('serial' in n for n in names))     # BSD

    def test_unknown_bundled_file_stops_the_build(self):
        site = [p for p in sys.path if p.endswith('site-packages')][0]
        toc = [('mystery', os.path.join(site, 'mystery_pkg', 'x.py'),
                'PYMODULE')]
        with self.assertRaises(RuntimeError):
            self.tp.bundled(toc)
