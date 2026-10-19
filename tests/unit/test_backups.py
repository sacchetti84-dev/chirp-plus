import os
import shutil
import tempfile
import unittest

from chirp.wxui import backups


class TestBackups(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def touch(self, name, size=8345):
        with open(os.path.join(self.dir, name), 'wb') as f:
            f.write(b'\xff' * size)

    def test_lists_newest_first(self):
        self.touch('Baofeng_UV-9R_download_20261018T184935.img')
        self.touch('Baofeng_UV-9R_upload_20261019T005737.img')
        self.touch('Baofeng_UV-5R_download_20261017T090000.img')
        found = backups.list_backups(self.dir)
        self.assertEqual(['upload', 'download', 'download'],
                         [b.kind for b in found])
        self.assertEqual('Baofeng UV-9R', found[0].radio)
        self.assertEqual('Baofeng UV-5R', found[2].radio)
        self.assertEqual(8345, found[0].size)
        self.assertEqual(2026, found[0].when.year)

    def test_vendor_with_underscore_model(self):
        self.touch('Retevis_RT6_download_20261019T010000.img')
        self.touch('BTECH_GMRS-V1_upload_20261019T010000.img')
        self.assertEqual({'Retevis RT6', 'BTECH GMRS-V1'},
                         {b.radio for b in backups.list_backups(self.dir)})

    def test_ignores_other_files(self):
        self.touch('notes.txt')
        self.touch('Baofeng_UV-9R_download_bad-date.img')
        self.touch('Baofeng_UV-9R_something_20261019T010000.img')
        self.assertEqual([], backups.list_backups(self.dir))

    def test_missing_folder(self):
        self.assertEqual([], backups.list_backups(
            os.path.join(self.dir, 'nope')))
