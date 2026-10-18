import os
import shutil
import tempfile
import unittest

import openpyxl

from chirp import directory
from chirp.drivers import generic_csv
from chirp.drivers import generic_xlsx

TEST_CSV = os.path.join(os.path.dirname(__file__), '..', 'images',
                        'Generic_CSV.csv')


class TestExcel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.xlsx = os.path.join(self.tmp, 'memories.xlsx')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _csv(self):
        return generic_csv.CSVRadio(TEST_CSV)

    def _export(self, src):
        dst = generic_xlsx.ExcelRadio(None)
        dst.erase_memory(0)
        for mem in src.get_memories():
            if not mem.empty:
                dst.set_memory(mem)
        dst.save(self.xlsx)
        return dst

    def assertSameMemories(self, a, b):
        mems_a = [m for m in a.get_memories() if not m.empty]
        mems_b = [m for m in b.get_memories() if not m.empty]
        self.assertEqual(len(mems_a), len(mems_b))
        for ma, mb in zip(mems_a, mems_b):
            self.assertEqual(ma.to_csv(), mb.to_csv())

    def test_roundtrip(self):
        src = self._csv()
        self._export(src)
        back = generic_xlsx.ExcelRadio(self.xlsx)
        self.assertSameMemories(src, back)

    def test_detected_by_directory(self):
        self._export(self._csv())
        radio = directory.get_radio_by_image(self.xlsx)
        self.assertIsInstance(radio, generic_xlsx.ExcelRadio)
        self.assertNotIsInstance(radio, generic_xlsx.ExcelLegacyRadio)

    def test_csv_is_not_excel(self):
        with open(TEST_CSV, 'rb') as f:
            data = f.read()
        self.assertFalse(generic_xlsx.ExcelRadio.match_model(
            data, 'Generic_CSV.csv'))
        self.assertIsInstance(directory.get_radio_by_image(TEST_CSV),
                              generic_csv.CSVRadio)

    def test_numbers_are_numbers(self):
        self._export(self._csv())
        sheet = openpyxl.load_workbook(self.xlsx).active
        header = [c.value for c in sheet[1]]
        row = [c for c in sheet[2]]
        freq = row[header.index('Frequency')]
        self.assertIsInstance(freq.value, float)
        self.assertEqual('0.000000', freq.number_format)
        self.assertIsInstance(row[header.index('Location')].value, int)
        self.assertIsInstance(row[header.index('Name')].value, str)
        # Header row and Location column stay visible while scrolling
        self.assertEqual('B2', sheet.freeze_panes)

    def test_hand_edited_sheet(self):
        # What a user typing in Excel produces: integers stored as floats,
        # blank rows, a note far to the right, a different sheet name
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = 'Le mie frequenze'
        sheet.append(['Location', 'Name', 'Frequency', 'Mode', None, None,
                      'nota'])
        sheet.append([1.0, 'PMR 1', 446.00625, 'NFM'])
        sheet.append([None, None, None, None])
        sheet.append([2, 'PMR 2', '446.01875', 'NFM', None, None, 'ok'])
        wb.save(self.xlsx)
        radio = generic_xlsx.ExcelRadio(self.xlsx)
        self.assertEqual([], radio.errors)
        self.assertEqual(446006250, radio.get_memory(1).freq)
        self.assertEqual('PMR 2', radio.get_memory(2).name)
        self.assertEqual('NFM', radio.get_memory(2).mode)

    def test_comments_survive(self):
        src = generic_csv.CSVRadio(None)
        src.load_from('# my radio\nLocation,Frequency\n1,146.520\n')
        dst = generic_xlsx.ExcelRadio(None)
        dst._comments = src._comments
        dst.erase_memory(0)
        dst.set_memory(src.get_memory(1))
        dst.save(self.xlsx)
        back = generic_xlsx.ExcelRadio(self.xlsx)
        self.assertEqual([(-1, '# my radio')], back._comments)
        self.assertEqual(146520000, back.get_memory(1).freq)

    def test_xls_is_read_only(self):
        radio = generic_xlsx.ExcelLegacyRadio(None)
        self.assertRaises(Exception, radio.save,
                          os.path.join(self.tmp, 'x.xls'))
        self.assertTrue(generic_xlsx.ExcelLegacyRadio.match_model(
            generic_xlsx.XLS_MAGIC + b'\0' * 8, 'old.XLS'))
        self.assertFalse(generic_xlsx.ExcelRadio.match_model(
            generic_xlsx.XLS_MAGIC, 'old.xls'))

    def test_cell_to_text(self):
        self.assertEqual('', generic_xlsx.cell_to_text(None))
        self.assertEqual('12', generic_xlsx.cell_to_text(12.0))
        self.assertEqual('88.5', generic_xlsx.cell_to_text(88.5))
        self.assertEqual('FM', generic_xlsx.cell_to_text(' FM '))
