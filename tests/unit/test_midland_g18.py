import os
import unittest

from chirp import chirp_common
from chirp import errors
from chirp import memmap
from chirp import settings
from chirp.drivers import midland_g18

IMAGE = os.path.join(os.path.dirname(__file__), '..', 'images',
                     'Midland_G18.img')


def load_image():
    with open(IMAGE, 'rb') as f:
        data, _metadata = chirp_common.CloneModeRadio._strip_metadata(
            f.read())
    return data


class FakeG18:
    """Serial stand-in that answers like the radio (protocol of 15/11/2026)"""

    def __init__(self, data):
        self.mem = bytearray(data)
        self.out = bytearray()
        self.written = []
        self.ended = False
        self.timeout = 1

    def write(self, data):
        data = bytes(data)
        if data == b'BONLINE':
            self.out += b'PX-5282\xff'
        elif data[:1] == b'R' and len(data) == 4:
            addr = (data[1] << 8) | data[2]
            self.out += data[:1].replace(b'R', b'W') + data[1:]
            self.out += self.mem[addr:addr + data[3]]
        elif data[:1] == b'W' and len(data) == 4 + 0x40:
            addr = (data[1] << 8) | data[2]
            self.mem[addr:addr + 0x40] = data[4:]
            self.written.append(addr)
            self.out += b'\x06'
        elif data == b'E':
            self.ended = True
        return len(data)

    def read(self, size=1):
        chunk = bytes(self.out[:size])
        del self.out[:size]
        return chunk

    def reset_input_buffer(self):
        self.out.clear()


class TestG18Memories(unittest.TestCase):
    def setUp(self):
        self.radio = midland_g18.MidlandG18(
            memmap.MemoryMapBytes(load_image()))

    def test_match_model(self):
        data = load_image()
        self.assertTrue(midland_g18.MidlandG18.match_model(data, 'x.img'))
        other = data[:0x1860] + b'XX-0000\xff' + data[0x1868:]
        self.assertFalse(midland_g18.MidlandG18.match_model(other, 'x.img'))
        self.assertFalse(midland_g18.MidlandG18.match_model(data[:-1],
                                                            'x.img'))

    def test_features(self):
        rf = self.radio.get_features()
        self.assertEqual((1, 256), rf.memory_bounds)
        self.assertEqual(6, rf.valid_name_length)
        self.assertEqual([(400000000, 520000000)], rf.valid_bands)

    def test_pmr_channel(self):
        m = self.radio.get_memory(1)
        self.assertFalse(m.empty)
        self.assertEqual(446006250, m.freq)
        self.assertEqual('', m.duplex)
        self.assertEqual('P1', m.name)
        self.assertEqual('', m.tmode)
        self.assertEqual('NFM', m.mode)
        self.assertEqual('High', str(m.power))
        self.assertEqual('', m.skip)
        self.assertEqual('Off', str(m.extra['bcl'].value))
        self.assertEqual('Off', str(m.extra['pttid'].value))
        self.assertEqual('Off', str(m.extra['scrambler'].value))

    def test_toned_wide_channel(self):
        m = self.radio.get_memory(78)
        self.assertEqual(446093750, m.freq)
        self.assertEqual('H_196', m.name)
        self.assertEqual('TSQL', m.tmode)
        self.assertEqual(114.8, m.ctone)
        self.assertEqual('FM', m.mode)

    def test_scrambler_channel(self):
        # channel 48 has the scrambler on, number 1
        m = self.radio.get_memory(48)
        self.assertEqual('1', str(m.extra['scrambler'].value))

    def test_empty_channel(self):
        self.assertTrue(self.radio.get_memory(79).empty)
        self.assertTrue(self.radio.get_memory(256).empty)

    def test_dcs_cross_and_split_roundtrip(self):
        m = chirp_common.Memory(5)
        m.freq = 446056250
        m.duplex = 'split'
        m.offset = 433075000
        m.tmode = 'Cross'
        m.cross_mode = 'DTCS->Tone'
        m.dtcs = 754
        m.ctone = 67.0
        m.dtcs_polarity = 'RN'
        m.mode = 'FM'
        m.power = self.radio.get_features().valid_power_levels[0]
        m.name = 'TEST'
        m.skip = 'S'
        self.radio.set_memory(m)
        raw = self.radio.get_mmap().get_packed()
        rec = raw[4 * 16:5 * 16]
        self.assertEqual(b'\x44\x60\x56\x25\x43\x30\x75\x00', rec[0:8])
        self.assertEqual(b'\x06\x70', rec[8:10])      # RX tone (decode)
        self.assertEqual(b'\xc7\x54', rec[10:12])     # TX DCS 754 inverted
        n = self.radio.get_memory(5)
        # CHIRP shows a 13 MHz split as a negative offset
        self.assertEqual('-', n.duplex)
        self.assertEqual(12981250, n.offset)
        self.assertEqual('Cross', n.tmode)
        self.assertEqual('DTCS->Tone', n.cross_mode)
        self.assertEqual(754, n.dtcs)
        self.assertEqual('RN', n.dtcs_polarity)
        self.assertEqual(67.0, n.ctone)
        self.assertEqual('FM', n.mode)
        self.assertEqual('Low', str(n.power))
        self.assertEqual('TEST', n.name)
        self.assertEqual('S', n.skip)
        # name is 8 bytes padded with FF
        self.assertEqual(b'TEST\xff\xff\xff\xff', raw[0x1020:0x1028])
        # scan bitmap: channel 5 is bit 4 of 0x1840
        self.assertEqual(0, raw[0x1840] & 0x10)

    def test_set_keeps_unmapped_bits(self):
        # factory channels have byte 12 bit 0x20 (compander) set: keep it
        m = self.radio.get_memory(1)
        m.name = 'X'
        self.radio.set_memory(m)
        self.assertEqual(0x30, self.radio.get_mmap().get_packed()[12] & 0xf0)
        self.assertEqual(0x08, self.radio.get_mmap().get_packed()[13] & 0x08)

    def test_new_channel_like_midland_software(self):
        m = chirp_common.Memory(79)
        m.freq = 446100000
        m.mode = 'FM'
        m.power = self.radio.get_features().valid_power_levels[1]
        self.radio.set_memory(m)
        raw = self.radio.get_mmap().get_packed()
        self.assertEqual(b'\x44\x61\x00\x00\x44\x61\x00\x00'
                         b'\xff\xff\xff\xff\xd8\x08\xff\xff',
                         raw[0x4e0:0x4f0])
        self.assertEqual(0x7f, raw[0x1829])   # present
        self.assertEqual(0x7f, raw[0x1849])   # scan add
        self.assertFalse(self.radio.get_memory(79).empty)

    def test_erase(self):
        self.radio.erase_memory(2)
        raw = self.radio.get_mmap().get_packed()
        self.assertEqual(b'\xff' * 16, raw[16:32])
        self.assertEqual(b'\xff' * 8, raw[0x1008:0x1010])
        self.assertEqual(0, raw[0x1820] & 0x02)
        self.assertTrue(self.radio.get_memory(2).empty)

    def test_extras_roundtrip(self):
        m = self.radio.get_memory(3)
        m.extra['bcl'].value = 'QT/DQT'
        m.extra['pttid'].value = 'On'
        m.extra['scrambler'].value = '3'
        self.radio.set_memory(m)
        raw = self.radio.get_mmap().get_packed()
        self.assertEqual(2, raw[2 * 16 + 12] & 0x03)
        self.assertEqual(0x51, raw[2 * 16 + 13] & 0xf3)
        n = self.radio.get_memory(3)
        self.assertEqual('QT/DQT', str(n.extra['bcl'].value))
        self.assertEqual('On', str(n.extra['pttid'].value))
        self.assertEqual('3', str(n.extra['scrambler'].value))


class TestG18Settings(unittest.TestCase):
    def setUp(self):
        self.radio = midland_g18.MidlandG18(
            memmap.MemoryMapBytes(load_image()))

    def _find(self, group, name):
        for element in group:
            if element.get_name() == name:
                return element
            if hasattr(element, 'get_name') and not hasattr(element,
                                                            'value'):
                found = self._find(element, name)
                if found is not None:
                    return found
        return None

    def test_current_values(self):
        s = self.radio.get_settings()
        self.assertEqual('3', str(self._find(s, 'squelch').value))
        self.assertEqual('30s', str(self._find(s, 'tot').value))
        self.assertEqual('Carrier', str(self._find(s, 'scanmode').value))
        self.assertEqual('12.5K', str(self._find(s, 'vfostep').value))
        self.assertEqual('English', str(self._find(s, 'voice').value))
        self.assertEqual('MSG', str(self._find(s, 'msgmode').value))
        self.assertEqual('G18', str(self._find(s, 'poweronmsg').value))
        self.assertEqual('Monitor', str(self._find(s, 'pf3').value))
        self.assertEqual('Scan', str(self._find(s, 'hold_pf4').value))
        self.assertEqual('1', str(self._find(s, 'priority').value))
        self.assertEqual('76.0-108.0 MHz', str(self._find(s, 'fm_band').value))
        self.assertEqual('50K', str(self._find(s, 'fm_step').value))

    def test_no_stun_settings(self):
        s = self.radio.get_settings()
        self.assertIsNone(self._find(s, 'rxstun'))
        self.assertIsNone(self._find(s, 'txstun'))

    def test_set_settings_bytes(self):
        s = self.radio.get_settings()
        self._find(s, 'squelch').value = '7'
        self._find(s, 'pf4').value = 'H/L Power'
        self._find(s, 'power_ratio').value = '1:8'
        self._find(s, 'menu_ani').value = True
        self._find(s, 'poweronmsg').value = 'ABC'
        self._find(s, 'botcode').value = '123'
        self._find(s, 'priority').value = '5'
        self._find(s, 'fm_band').value = '76.0-91.0 MHz'
        self._find(s, 'fm_step').value = '100K'
        self._find(s, 'fm_mem1').value = '88.5'
        self.radio.set_settings(s)
        raw = self.radio.get_mmap().get_packed()
        self.assertEqual(7, raw[0x1883])
        self.assertEqual(0x64, raw[0x188b])
        self.assertEqual(0x30, raw[0x188a] & 0x30)
        self.assertEqual(0x80, raw[0x1885] & 0x80)
        self.assertEqual(b'ABC\xff\xff\xff', raw[0x1898:0x189e])
        self.assertEqual(b'123\xff\xff\xff\xff', raw[0x18a0:0x18a7])
        self.assertEqual(4, raw[0x188c])
        self.assertEqual(0x02, raw[0x1901] & 0x16)
        self.assertEqual(b'\x08\x85\x00\x00', raw[0x1908:0x190c])

    def test_bad_fm_memory_rejected(self):
        s = self.radio.get_settings()
        self._find(s, 'fm_mem2').value = '200'
        self.assertRaises(settings.InvalidValueError,
                          self.radio.set_settings, s)


class TestG18Clone(unittest.TestCase):
    def test_download(self):
        data = load_image()
        fake = FakeG18(data)
        radio = midland_g18.MidlandG18(fake)
        radio.sync_in()
        self.assertEqual(data, radio.get_mmap().get_packed())
        self.assertTrue(fake.ended)

    def test_upload_skips_calibration_and_clears_stun(self):
        data = bytearray(load_image())
        data[0x1882] |= 0xc0          # both stun bits on in the image
        fake = FakeG18(load_image())
        radio = midland_g18.MidlandG18(memmap.MemoryMapBytes(bytes(data)))
        radio.set_pipe(fake)
        radio.sync_out()
        self.assertEqual(list(range(0, 0x1fc0, 0x40)), fake.written)
        self.assertEqual(0, fake.mem[0x1882] & 0xc0)
        self.assertTrue(fake.ended)

    def test_wrong_radio_refused(self):
        fake = FakeG18(load_image())
        fake.write = lambda d: (fake.out.extend(b'PX-9999\xff')
                                if d == b'BONLINE' else None) or len(d)
        radio = midland_g18.MidlandG18(fake)
        self.assertRaises(errors.RadioError, radio.sync_in)
