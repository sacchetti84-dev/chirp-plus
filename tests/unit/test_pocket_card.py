import datetime
import unittest

from chirp import chirp_common
from chirp import pocket_card
from chirp.drivers import generic_csv


def mem(number, mhz, name='', **kw):
    m = chirp_common.Memory(number)
    m.freq = int(mhz * 1000000)
    m.name = name
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestPocketCard(unittest.TestCase):
    def test_tone_text(self):
        self.assertEqual('', pocket_card.tone_text(mem(1, 145.5)))
        self.assertEqual('T88.5', pocket_card.tone_text(
            mem(1, 145.5, tmode='Tone', rtone=88.5)))
        self.assertEqual('TS123.0', pocket_card.tone_text(
            mem(1, 145.5, tmode='TSQL', ctone=123.0)))
        self.assertEqual('D023N', pocket_card.tone_text(
            mem(1, 145.5, tmode='DTCS', dtcs=23, dtcs_polarity='NN')))

    def test_shift_text(self):
        self.assertEqual('-0.600', pocket_card.shift_text(
            mem(1, 145.6, duplex='-', offset=600000)))
        self.assertEqual('RX', pocket_card.shift_text(
            mem(1, 145.8, duplex='off')))
        self.assertEqual('', pocket_card.shift_text(mem(1, 145.5)))

    def build(self, count, per_column=3):
        radio = generic_csv.CSVRadio(None)
        radio.erase_memory(0)
        for i in range(1, count + 1):
            radio.set_memory(mem(i, 433.0 + i * 0.025, 'CH<%i>' % i))
        return pocket_card.build_html(radio, per_column=per_column,
                                      today=datetime.date(2026, 10, 19))

    def test_html(self):
        page = self.build(5)
        self.assertIn('Generic CSV', page)
        self.assertIn('2026-10-19', page)
        self.assertIn('5 ch', page)
        # Names are escaped
        self.assertIn('CH&lt;1&gt;', page)
        self.assertIn('433.0250', page)
        self.assertEqual(1, page.count('<b>Generic CSV</b>'))

    def test_pages(self):
        page = self.build(13, per_column=3)
        # 6 channels per page -> 3 pages
        self.assertEqual(3, page.count('<b>Generic CSV</b>'))
        self.assertEqual(2, page.count('page-break-before'))

    def test_labels(self):
        radio = generic_csv.CSVRadio(None)
        page = pocket_card.build_html(radio, labels={'name': 'Nome'})
        self.assertIn('Nome', page)
