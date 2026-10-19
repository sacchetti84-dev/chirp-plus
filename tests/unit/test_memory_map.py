import os
import unittest

from chirp import directory
from chirp import memory_map

IMAGES = os.path.join(os.path.dirname(__file__), '..', 'images')


class TestMemoryMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory.import_drivers()
        cls.radio = directory.get_radio_by_image(
            os.path.join(IMAGES, 'Baofeng_BF-A58S.img'))

    def test_classify(self):
        self.assertEqual(memory_map.CHANNELS, memory_map.classify('memory'))
        self.assertEqual(memory_map.NAMES, memory_map.classify('names'))
        self.assertEqual(memory_map.MESSAGES,
                         memory_map.classify('poweron_msg'))
        self.assertEqual(memory_map.SERVICE, memory_map.classify('squelch'))
        self.assertEqual(memory_map.SERVICE, memory_map.classify('limits'))
        self.assertEqual(memory_map.SETTINGS, memory_map.classify('vfo'))

    def test_driver_regions(self):
        regions = memory_map.driver_regions(self.radio)
        by_name = {r.name: r for r in regions}
        self.assertEqual(0, by_name['memory'].start)
        self.assertEqual(memory_map.CHANNELS, by_name['memory'].kind)
        self.assertEqual(0x1000, by_name['names'].start)
        self.assertEqual([r.start for r in regions],
                         sorted(r.start for r in regions))

    def test_unknown_regions(self):
        data = bytes([0xFF] * 4 + [1, 2, 3] + [0xFF] * 4 + [9] + [0] * 4)
        known = [memory_map.Region(0, 2, 'a', memory_map.SETTINGS),
                 memory_map.Region(11, 12, 'b', memory_map.SETTINGS)]
        found = memory_map.unknown_regions(data, known)
        self.assertEqual([(4, 7)], [(r.start, r.end) for r in found])

    def test_build_map_finds_unknown_data(self):
        data, regions = memory_map.build_map(self.radio)
        self.assertEqual(len(data), len(self.radio.get_mmap()))
        kinds = {r.kind for r in regions}
        self.assertIn(memory_map.CHANNELS, kinds)
        # No two known regions overlap and unknown ones sit in the gaps
        known = [r for r in regions if r.kind != memory_map.UNKNOWN]
        for a, b in zip(known, known[1:]):
            self.assertLessEqual(a.end, b.start)

    def test_byte_kinds_and_rows(self):
        data, regions = memory_map.build_map(self.radio)
        kinds = memory_map.byte_kinds(data, regions)
        self.assertEqual(len(data), len(kinds))
        self.assertEqual(memory_map.CHANNELS, kinds[0])
        rows = list(memory_map.hex_rows(data[:32]))
        self.assertEqual(2, len(rows))
        self.assertEqual(16 * 3 - 1, len(rows[0][1]))
        self.assertEqual(16, len(rows[0][2]))

    def test_every_kind_has_a_tone(self):
        for kind in (memory_map.CHANNELS, memory_map.NAMES,
                     memory_map.SETTINGS, memory_map.MESSAGES,
                     memory_map.SERVICE, memory_map.UNKNOWN,
                     memory_map.EMPTY):
            self.assertIn(kind, memory_map.KIND_TONES)
