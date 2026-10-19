import os
import unittest
from unittest import mock

from chirp import batch_program
from chirp import directory
from chirp import memmap

IMAGES = os.path.join(os.path.dirname(__file__), '..', 'images')


class FakeRadioFleet:
    """Radios that store what is uploaded; one of them can be faulty."""
    def __init__(self, image, faulty=()):
        self.image = image
        self.faulty = set(faulty)
        self.current = 0
        self.stored = {}
        self.pipes = []

    def open_pipe(self):
        pipe = mock.MagicMock()
        self.pipes.append(pipe)
        return pipe


def make_batch(fleet, verify=True):
    image = directory.get_radio_by_image(fleet.image)
    rclass = type(image)

    def sync_out(radio):
        data = radio.get_mmap().get_byte_compatible().get(0, 0x2000)
        if fleet.current in fleet.faulty:
            # This radio does not keep one byte of the channels
            data = bytearray(data)
            data[0x10] ^= 0xFF
            data = bytes(data)
        fleet.stored[fleet.current] = data

    def sync_in(radio):
        radio._mmap = memmap.MemoryMapBytes(fleet.stored[fleet.current])
        radio.process_mmap()

    patches = [mock.patch.object(rclass, 'sync_out', sync_out),
               mock.patch.object(rclass, 'sync_in', sync_in)]
    for p in patches:
        p.start()
    return batch_program.Batch(image, fleet.open_pipe, verify=verify), \
        patches


class TestBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory.import_drivers()

    def run_fleet(self, count, faulty=(), verify=True):
        fleet = FakeRadioFleet(os.path.join(IMAGES, 'Baofeng_BF-A58S.img'),
                               faulty)
        batch, patches = make_batch(fleet, verify)
        try:
            for i in range(count):
                fleet.current = i
                batch.program_next(sleep=lambda s: None)
        finally:
            for p in patches:
                p.stop()
        return batch, fleet

    def test_all_good(self):
        batch, fleet = self.run_fleet(3)
        self.assertEqual((3, 3, 0), (batch.done, batch.good, batch.failed))
        self.assertTrue(all(r.verified for r in batch.results))
        # Every port opened was closed: upload + readback for each radio
        self.assertEqual(6, len(fleet.pipes))
        for pipe in fleet.pipes:
            pipe.close.assert_called_once_with()

    def test_faulty_radio_is_reported(self):
        batch, fleet = self.run_fleet(3, faulty={1})
        self.assertEqual([True, False, True],
                         [r.ok for r in batch.results])
        self.assertFalse(batch.results[1].verified)
        self.assertEqual(1, batch.results[1].problems)

    def test_without_verify(self):
        batch, fleet = self.run_fleet(2, faulty={0}, verify=False)
        self.assertEqual([None, None],
                         [r.verified for r in batch.results])
        self.assertEqual(2, batch.good)
        self.assertEqual(2, len(fleet.pipes))

    def test_upload_error(self):
        image = directory.get_radio_by_image(
            os.path.join(IMAGES, 'Baofeng_BF-A58S.img'))
        pipe = mock.MagicMock()
        batch = batch_program.Batch(image, lambda: pipe)
        with mock.patch.object(type(image), 'sync_out',
                               side_effect=Exception('Radio did not ack')):
            result = batch.program_next(sleep=lambda s: None)
        self.assertFalse(result.ok)
        self.assertFalse(result.uploaded)
        self.assertEqual('Radio did not ack', result.error)
        pipe.close.assert_called_once_with()
        self.assertEqual(1, batch.failed)
