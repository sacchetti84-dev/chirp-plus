import os
import unittest

from chirp import directory
from chirp import radio_compare

IMAGES = os.path.join(os.path.dirname(__file__), '..', 'images')


def load(name):
    return directory.get_radio_by_image(os.path.join(IMAGES, name))


class TestCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory.import_drivers()

    def setUp(self):
        self.old = load('Baofeng_BF-A58S.img')
        self.new = load('Baofeng_BF-A58S.img')

    def first_used(self):
        lo, hi = self.new.get_features().memory_bounds
        for n in range(lo, hi + 1):
            if not self.new.get_memory(n).empty:
                return n
        self.fail('no used memory in test image')

    def test_same_image_has_no_changes(self):
        self.assertEqual([], radio_compare.diff_radios(self.old, self.new))

    def test_changed_memory(self):
        n = self.first_used()
        mem = self.new.get_memory(n)
        mem.name = 'TEST'
        self.new.set_memory(mem)
        changes = radio_compare.diff_memories(self.old, self.new)
        self.assertEqual(1, len(changes))
        self.assertEqual(radio_compare.CHANGED, changes[0].kind)
        self.assertEqual(str(n), changes[0].where)
        self.assertIn('TEST', changes[0].after)

    def test_added_and_removed(self):
        n = self.first_used()
        self.new.erase_memory(n)
        changes = radio_compare.diff_memories(self.old, self.new)
        self.assertEqual([radio_compare.REMOVED], [c.kind for c in changes])
        changes = radio_compare.diff_memories(self.new, self.old)
        self.assertEqual([radio_compare.ADDED], [c.kind for c in changes])

    def test_settings_diff(self):
        values = radio_compare.setting_values(self.old)
        self.assertTrue(values)
        settings = self.new.get_settings()
        # Flip the first boolean setting we can find
        for group in settings:
            for element in group:
                if hasattr(element, 'value') and \
                        isinstance(element.value.get_value(), bool):
                    element.value = not element.value.get_value()
                    self.new.set_settings(settings)
                    changes = radio_compare.diff_settings(self.old, self.new)
                    self.assertEqual(1, len(changes))
                    self.assertEqual('setting', changes[0].what)
                    return
        self.skipTest('no boolean setting')

    def test_summary(self):
        n = self.first_used()
        self.new.erase_memory(n)
        counts = radio_compare.summary(
            radio_compare.diff_radios(self.old, self.new))
        self.assertEqual({'memory': 1, 'setting': 0}, counts)

    def test_verify_upload_bytes(self):
        method, problems = radio_compare.verify_upload(self.old, self.new)
        self.assertEqual('bytes', method)
        self.assertEqual([], problems)
        n = self.first_used()
        mem = self.new.get_memory(n)
        mem.freq += 12500
        self.new.set_memory(mem)
        method, problems = radio_compare.verify_upload(self.old, self.new)
        self.assertEqual(1, len(problems))

    def test_verify_upload_ignores_unwritten_areas(self):
        # Bytes outside the upload ranges (e.g. calibration) may differ
        ranges = radio_compare.written_ranges(self.new)
        self.assertTrue(ranges)
        outside = next(a for a in range(0, 0x2000)
                       if not any(s <= a < e for s, e in ranges))
        mmap = self.new.get_mmap()
        mmap[outside] = (mmap.get_byte_compatible()[outside][0] ^ 0xFF)
        self.assertEqual([], radio_compare.verify_upload(self.old,
                                                         self.new)[1])

    def test_verify_upload_memories_fallback(self):
        csv = directory.get_radio('Generic_CSV')(None)
        method, problems = radio_compare.verify_upload(csv, csv)
        self.assertEqual('memories', method)
        self.assertEqual([], problems)
