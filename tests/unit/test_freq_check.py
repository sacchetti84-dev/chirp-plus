import unittest

from chirp import chirp_common
from chirp import freq_check


def mem(freq_mhz, duplex='', offset=0, watts=5.0, number=1):
    m = chirp_common.Memory(number)
    m.freq = int(freq_mhz * 1000000)
    m.duplex = duplex
    m.offset = int(offset * 1000000)
    m.power = chirp_common.PowerLevel('P', watts=watts)
    return m


class TestFreqCheck(unittest.TestCase):
    def levels(self, m):
        return [f.level for f in freq_check.check_memory(m)]

    def test_lpd_at_5w_is_too_much(self):
        found = freq_check.check_memory(mem(433.075, watts=5))
        self.assertEqual([freq_check.WARN], [f.level for f in found])
        self.assertEqual('LPD', found[0].band)
        self.assertIn('0.01 W', found[0].message())

    def test_lpd_at_10mw_is_fine(self):
        self.assertEqual([], self.levels(mem(433.075, watts=0.01)))

    def test_pmr_power_and_note(self):
        found = freq_check.check_memory(mem(446.00625, watts=5))
        self.assertEqual([freq_check.WARN], [f.level for f in found])
        self.assertIn('approved PMR446', found[0].message())
        low = freq_check.check_memory(mem(446.00625, watts=0.5))
        self.assertEqual([freq_check.INFO], [f.level for f in low])

    def test_amateur_needs_license(self):
        found = freq_check.check_memory(mem(145.500))
        self.assertEqual([freq_check.INFO], [f.level for f in found])
        self.assertEqual('amateur 2 m', found[0].band)
        # Inside 70 cm but outside LPD
        found = freq_check.check_memory(mem(432.5))
        self.assertEqual('amateur 70 cm', found[0].band)

    def test_receive_only_bands(self):
        self.assertEqual([freq_check.BAD], self.levels(mem(98.0)))
        self.assertEqual([freq_check.BAD], self.levels(mem(121.5)))
        # Duplex off means receive only: nothing to report
        self.assertEqual([], self.levels(mem(98.0, duplex='off')))

    def test_outside_known_bands(self):
        self.assertEqual([freq_check.WARN], self.levels(mem(470.0)))

    def test_repeater_offset_is_checked_on_tx(self):
        # RX in band, TX shifted out of the 2 m band
        found = freq_check.check_memory(mem(145.700, '+', 2.0))
        self.assertEqual([freq_check.WARN], [f.level for f in found])
        self.assertIn('147.70000', found[0].message())
        found = freq_check.check_memory(mem(433.0, 'split', 446.00625,
                                            watts=0.5))
        self.assertEqual('PMR446', found[0].band)

    def test_empty_memory(self):
        m = chirp_common.Memory(1, empty=True)
        self.assertEqual([], freq_check.check_memory(m))

    def test_translate_hook(self):
        found = freq_check.check_memory(mem(98.0))
        text = found[0].message(
            lambda s: 'radio FM' if s == 'FM broadcast' else s)
        self.assertIn('(radio FM)', text)

    def test_summary(self):
        findings = (freq_check.check_memory(mem(98.0)) +
                    freq_check.check_memory(mem(145.5)))
        self.assertEqual({'info': 1, 'warn': 0, 'bad': 1},
                         freq_check.summary(findings))
