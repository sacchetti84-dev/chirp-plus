import unittest
from unittest import mock

from chirp import directory
from chirp import radio_detect

UV9R_MAGIC = b'\x50\xBB\xFF\x20\x14\x04\x13'
UV9R_IDENT = b'\xAA\x30\x79\x04\x00\x05\x20\xDD'


class FakeBaofeng:
    """Answers the clone handshake for one magic, ignores everything else.

    Records every byte written so tests can check nothing beyond the
    handshake is ever sent.
    """
    def __init__(self, magic=UV9R_MAGIC, ident=UV9R_IDENT):
        self.magic = magic
        self.ident = ident
        self.timeout = 1
        self.written = b''
        self._rx = b''
        self._pending = b''

    def reset_input_buffer(self):
        self._rx = b''

    def write(self, data):
        self.written += data
        self._pending += data
        if self._pending.endswith(self.magic):
            self._rx += b'\x06'
            self._pending = b''
        elif self._pending == b'\x02':
            self._rx += self.ident
            self._pending = b''
        elif self._pending == b'\x06':
            self._rx += b'\x06'
            self._pending = b''
        elif len(self._pending) >= len(self.magic) and \
                not self.magic.startswith(self._pending[-1:]):
            self._pending = b''

    def read(self, n):
        data, self._rx = self._rx[:n], self._rx[n:]
        return data


class TestDetect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory.import_drivers()

    def test_probes_cover_baofeng_families(self):
        probes = radio_detect.build_probes()
        magics = [p.magic for p in probes]
        self.assertEqual(len(magics), len(set(magics)))
        uv9r = [p for p in probes if p.magic == UV9R_MAGIC][0]
        models = [c.MODEL for c in uv9r.classes]
        self.assertIn('UV-9R', models)
        # The BF-F8HP (uv5r family) shares this magic
        self.assertIn('BF-F8HP', models)
        self.assertTrue(any(c.MODEL == 'UV-5R' for p in probes
                            for c in p.classes))

    def test_preferred_goes_first(self):
        uv9r = directory.get_radio('Baofeng_UV-9R')
        probes = radio_detect.build_probes(preferred=uv9r)
        self.assertEqual(UV9R_MAGIC, probes[0].magic)
        self.assertIs(uv9r, probes[0].classes[0])

    def test_identify_uv9r(self):
        radio = FakeBaofeng()
        uv9r = directory.get_radio('Baofeng_UV-9R')
        probes = radio_detect.build_probes()
        seen = []
        result = radio_detect.identify(
            radio, probes, status=lambda i, n, p: seen.append(i), pause=0)
        self.assertIsNotNone(result)
        self.assertEqual(UV9R_IDENT, result.ident)
        self.assertIn(uv9r, result.classes)
        self.assertEqual(list(range(len(seen))), seen)

    def test_only_handshake_bytes_are_sent(self):
        radio = FakeBaofeng()
        uv9r = directory.get_radio('Baofeng_UV-9R')
        probes = radio_detect.build_probes(preferred=uv9r)
        radio_detect.identify(radio, probes, pause=0)
        # magic, 0x02, ACK: no read ('S') or write ('X') commands
        self.assertEqual(UV9R_MAGIC + b'\x02\x06', radio.written)

    def test_no_radio(self):
        radio = FakeBaofeng(magic=b'\x99\x99\x99\x99\x99\x99\x99')
        probes = radio_detect.build_probes()[:3]
        self.assertIsNone(radio_detect.identify(radio, probes, pause=0))

    def test_cancel(self):
        radio = FakeBaofeng()
        probes = radio_detect.build_probes()
        self.assertIsNone(radio_detect.identify(
            radio, probes, cancelled=lambda: True, pause=0))
        self.assertEqual(b'', radio.written)

    def test_bad_ident_is_ignored(self):
        radio = FakeBaofeng(ident=b'\x01\x02\x03')
        probe = radio_detect.Probe(UV9R_MAGIC, [])
        self.assertIsNone(radio_detect.handshake(radio, UV9R_MAGIC,
                                                 timeout=0))
        self.assertIsNone(radio_detect.identify(radio, [probe], pause=0))

    def test_serial_errors_are_survived(self):
        radio = mock.MagicMock()
        radio.write.side_effect = OSError('cable unplugged')
        probes = radio_detect.build_probes()[:2]
        self.assertIsNone(radio_detect.identify(radio, probes, pause=0))
