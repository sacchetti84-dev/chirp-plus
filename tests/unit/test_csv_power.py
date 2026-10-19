import os
import tempfile
import unittest

from chirp import chirp_common
from chirp.drivers import generic_csv

HEADER = 'Location,Name,Frequency,Duplex,Offset,Power\n'


class TestCSVLowPower(unittest.TestCase):
    """LPD (10 mW) and PMR446 (0.5 W) powers must survive a CSV round trip.

    They used to be shown as "0.0W", saved as "0.0W" and read back as no
    power at all, which the CSV driver replaces with its 50 W default.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'lpd.csv')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(HEADER)
            f.write('1,LPD 01,433.075000,,0.000000,0.01W\n')
            f.write('2,PMR 01,446.006250,,0.000000,0.5W\n')
            f.write('3,R0,145.600000,-,0.600000,5.0W\n')

    def test_label_keeps_milliwatts(self):
        radio = generic_csv.CSVRadio(self.path)
        self.assertEqual('0.01W', str(radio.get_memory(1).power))
        self.assertEqual('0.5W', str(radio.get_memory(2).power))
        self.assertEqual('5.0W', str(radio.get_memory(3).power))

    def test_save_and_reopen_keeps_the_power(self):
        radio = generic_csv.CSVRadio(self.path)
        for number in (1, 2, 3):
            # What the grid does after an edit: the memory goes back in
            radio.set_memory(radio.get_memory(number))
        copy = os.path.join(self.dir, 'copy.csv')
        radio.save(copy)
        back = generic_csv.CSVRadio(copy)
        self.assertEqual(['0.01W', '0.5W', '5.0W'],
                         [str(back.get_memory(n).power) for n in (1, 2, 3)])
        self.assertAlmostEqual(10.0, float(back.get_memory(1).power))

    def test_grid_text_parses_back(self):
        # The grid shows str(power) and parses what it shows
        power = chirp_common.parse_power(str(
            generic_csv.CSVRadio(self.path).get_memory(1).power))
        self.assertTrue(power)
        self.assertAlmostEqual(10.0, float(power))
