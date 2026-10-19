import importlib.util
import os
import unittest

from chirp import freq_check
from chirp.drivers import generic_csv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
STOCK = os.path.join(ROOT, 'chirp', 'stock_configs')


def load_generator():
    path = os.path.join(ROOT, 'tools', 'make_ham_presets.py')
    spec = importlib.util.spec_from_file_location('make_ham_presets', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestHamPresets(unittest.TestCase):
    def setUp(self):
        self.files = load_generator().presets()

    def memories(self, name):
        radio = generic_csv.CSVRadio(os.path.join(STOCK, name))
        lo, hi = radio.get_features().memory_bounds
        return [m for m in (radio.get_memory(i) for i in range(lo, hi + 1))
                if not m.empty]

    def test_files_match_the_generator(self):
        for name, text in self.files.items():
            with open(os.path.join(STOCK, name), encoding='utf-8',
                      newline='') as f:
                self.assertEqual(text, f.read(),
                                 '%s is stale: run make_ham_presets.py' % name)

    def test_all_in_one_fits_a_baofeng(self):
        # UV-5R and UV-9R family: 128 memories, 7 character names
        mems = self.memories('IT Radioamatori tutto in uno.csv')
        self.assertLessEqual(len(mems), 128)
        for m in mems:
            self.assertLessEqual(len(m.name), 7, m.name)
        names = [m.name for m in mems]
        self.assertEqual(len(names), len(set(names)))

    def test_repeaters(self):
        mems = self.memories('IT Ponti ripetitori 2 m.csv')
        self.assertEqual((145600000, '-', 600000),
                         (mems[0].freq, mems[0].duplex, mems[0].offset))
        self.assertEqual(145787500, mems[-1].freq)
        mems = self.memories('IT Ponti ripetitori 70 cm.csv')
        self.assertEqual((431600000, '-', 1600000),
                         (mems[0].freq, mems[0].duplex, mems[0].offset))
        self.assertEqual(431975000, mems[-1].freq)

    def test_satellites_split_with_doppler(self):
        mems = {m.name: m for m in
                self.memories('IT Satelliti FM radioamatori.csv')}
        so50 = [mems['SO50 A'], mems['SO50 C'], mems['SO50 F']]
        self.assertEqual([436805000, 436795000, 436785000],
                         [m.freq for m in so50])
        self.assertTrue(all(m.duplex == 'split' and m.offset == 145850000
                            and m.tmode == 'Tone' and m.rtone == 67.0
                            for m in so50))
        self.assertEqual(74.4, mems['SO50ARM'].rtone)
        # UHF uplink: lower at the start of the pass, higher at the end
        self.assertEqual([437490000, 437500000, 437510000],
                         [mems['PO101 %s' % s].offset for s in 'ACF'])

    def test_presets_transmit_only_in_amateur_bands(self):
        for name in self.files:
            for m in self.memories(name):
                if freq_check.tx_freq(m) is None:
                    continue        # receive only
                tx = freq_check.band_for(freq_check.tx_freq(m))
                self.assertIn(tx.use, (freq_check.LICENSE, freq_check.FREE),
                              '%s %s' % (name, m.name))
