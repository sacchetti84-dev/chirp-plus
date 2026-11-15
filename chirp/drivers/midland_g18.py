# Copyright 2026 CHIRP Plus contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Midland G18 (400-520 MHz) clone-mode driver.

The protocol and the memory map were recovered by observing the Midland
"G18 v1.0.3" programming software; no command beyond what that software
sends is used:

    PC "BONLINE"                     radio "PX-5282" + FF
    PC "R" + addr(2, BE) + 0x40      radio "W" + addr + 0x40 + 64 bytes
    PC "W" + addr + 0x40 + 64 bytes  radio 06
    PC "E"                           (end, no answer)

The image is 8 KB. The last block (0x1FC0, calibration and serial number)
is read but never written, as the Midland software does.
"""

import logging
import struct

from chirp import bitwise
from chirp import chirp_common
from chirp import directory
from chirp import errors
from chirp import memmap
from chirp.settings import (
    InvalidValueError, RadioSetting, RadioSettingGroup, RadioSettings,
    RadioSettingValueBoolean, RadioSettingValueList, RadioSettingValueMap,
    RadioSettingValueString)

LOG = logging.getLogger(__name__)

MEMSIZE = 0x2000
BLOCK = 0x40
WRITE_END = 0x1FC0
IDENT = b'PX-5282'
NUM_CHANNELS = 256

MEM_FORMAT = """
struct {
  bbcd rxfreq[4];
  bbcd txfreq[4];
  u16 rxtone;
  u16 txtone;
  u8 unused12:2,
     compander:1,
     highpower:1,
     wide:1,
     reverse:1,
     bcl:2;
  u8 scramble_no:3,
     scramble:1,
     optsig:2,
     pttid:2;
  u8 unused14[2];
} memory[256];

struct {
  char name[8];
} names[256];

#seekto 0x1820;
u8 present[32];

u8 scanadd[32];

char ident[7];

#seekto 0x1880;
struct {
  u8 onlych:1,
     unknown80_6:1,
     eot:1,
     bot:1,
     roger:1,
     chname:1,
     unknown80_0:2;
  u8 unknown81_6:2,
     backlight:2,
     unknown81_3:1,
     autolock:1,
     scanmode:2;
  u8 rxstun:1,
     txstun:1,
     msgmode:2,
     save:1,
     beep:1,
     voice:2;
  u8 squelch;
  u8 tot;
  u8 menu_ani:1,
     menu_wn:1,
     menu_duplex:1,
     menu_offset:1,
     voxgain:4;
  u8 voxdelay;
  u8 vfostep;
  u8 unknown88[2];
  u8 unknown8a_7:1,
     pf1:1,
     power_ratio:2,
     sidetone:1,
     unknown8a_1:2,
     pttidtype:1;
  u8 pf4:4,
     pf3:4;
  u8 priority;
  u8 hold_pf4:4,
     hold_pf3:4;
  u8 unknown8e[2];
  char radioinfo[8];
  char poweronmsg[6];
  u8 unknown9e[2];
  char botcode[7];
  u8 botlast;
  char eotcode[7];
  u8 eotlast;
} settings;

#seekto 0x1900;
struct {
  u8 unknown0;
  u8 unknown1_5:3,
     step:1,
     unknown1_3:1,
     band:2,
     unknown1_0:1;
  u8 unknown2[2];
  bbcd current[4];
  struct {
    bbcd freq[4];
  } mem[6];
} fm;
"""

POWER_LEVELS = [chirp_common.PowerLevel('Low', watts=0.5),
                chirp_common.PowerLevel('High', watts=2.0)]
MODES = ['FM', 'NFM']
TONE_MODES = ['', 'Tone', 'TSQL', 'DTCS', 'Cross']
CROSS_MODES = ['Tone->Tone', 'Tone->DTCS', 'DTCS->Tone', 'DTCS->',
               '->Tone', '->DTCS', 'DTCS->DTCS']
DUPLEXES = ['', '+', '-', 'split']
STEPS = [2.5, 5.0, 6.25, 10.0, 12.5, 25.0]
NAME_CHARS = chirp_common.CHARSET_UPPER_NUMERIC + ' -_+*/'

BCL_LIST = ['Off', 'Carrier', 'QT/DQT']
PTTID_LIST = ['Off', 'On']
SCRAMBLE_LIST = ['Off'] + [str(x) for x in range(1, 9)]

SQUELCH_LIST = [str(x) for x in range(10)]
TOT_LIST = ['Off'] + ['%ss' % (x * 30) for x in range(1, 10)]
SCANMODE_LIST = ['Time', 'Carrier', 'Seek']
VFOSTEP_LIST = ['2.5K', '5K', '6.25K', '10K', '12.5K', '25K', '50K', '100K']
BACKLIGHT_LIST = ['Off', 'Auto', 'On']
VOICE_MAP = [('Off', 0), ('English', 3)]
POWER_RATIO_LIST = ['1:3', '1:2', '1:4', '1:8']
VOXGAIN_LIST = ['Off'] + [str(x) for x in range(1, 10)]
VOXDELAY_LIST = ['1s', '2s', '3s', '4s']
MSGMODE_LIST = ['Off', 'DC', 'MSG']
PTTIDTYPE_LIST = ['MSK', 'DTMF']
KEY_LIST = ['Off', 'Send 1450Hz Signal', 'Send 1750Hz Signal',
            'Send 2315Hz Signal', 'Monitor', 'Scan', 'H/L Power', 'Tx>Rx',
            'Revert Freq', 'Radio']
PRIORITY_LIST = [str(x) for x in range(1, NUM_CHANNELS + 1)]
FM_BAND_LIST = ['87.5-108.0 MHz', '76.0-91.0 MHz', '76.0-108.0 MHz',
                '65.0-76.0 MHz']
FM_BANDS = [(87.5, 108.0), (76.0, 91.0), (76.0, 108.0), (65.0, 76.0)]
FM_STEP_LIST = ['100K', '50K']
CODE_CHARS = '0123456789ABCD*#'
TEXT_CHARS = chirp_common.CHARSET_ASCII


def _bit(bitmap, number):
    index = number - 1
    return bool(bitmap[index // 8] & (1 << (index % 8)))


def _set_bit(bitmap, number, value):
    index = number - 1
    byte = int(bitmap[index // 8])
    if value:
        byte |= 1 << (index % 8)
    else:
        byte &= ~(1 << (index % 8)) & 0xFF
    bitmap[index // 8] = byte


def _bcd_digits(value, digits):
    """Pack an integer as BCD in the low 4*digits bits"""
    packed = 0
    for i, ch in enumerate(reversed(('%0*d' % (digits, value))[-digits:])):
        packed |= int(ch) << (4 * i)
    return packed


def _unbcd(value, digits):
    result = 0
    for i in reversed(range(digits)):
        nibble = (value >> (4 * i)) & 0xF
        if nibble > 9:
            raise ValueError('not BCD')
        result = result * 10 + nibble
    return result


def decode_tone(raw):
    """Return (mode, value, polarity) for a 16-bit tone field"""
    raw = int(raw)
    if raw == 0xFFFF:
        return '', None, None
    try:
        if raw & 0x8000:
            code = _unbcd(raw & 0x0FFF, 3)
            if code in chirp_common.ALL_DTCS_CODES:
                return 'DTCS', code, 'R' if raw & 0x4000 else 'N'
        else:
            tone = _unbcd(raw & 0x3FFF, 4) / 10.0
            if tone in chirp_common.TONES:
                return 'Tone', tone, None
    except ValueError:
        pass
    LOG.debug('Unsupported tone value %04x', raw)
    return '', None, None


def encode_tone(mode, value, polarity):
    if mode == 'Tone':
        return _bcd_digits(int(round(value * 10)), 4)
    if mode == 'DTCS':
        raw = 0x8000 | _bcd_digits(value, 3)
        if polarity == 'R':
            raw |= 0x4000
        return raw
    return 0xFFFF


def _decode_text(field):
    return str(field).split('\xff')[0].rstrip()


def _encode_text(field, text, size):
    field.set_value(text.ljust(size, '\xff')[:size])


def _transfer_error(action, exc):
    if isinstance(exc, errors.RadioError):
        return exc
    LOG.debug('G18 %s failed', action, exc_info=True)
    return errors.RadioError('G18 %s failed: %s' % (action, exc))


@directory.register
class MidlandG18(chirp_common.CloneModeRadio):
    """Midland G18"""
    VENDOR = 'Midland'
    MODEL = 'G18'
    BAUD_RATE = 9600
    _memsize = MEMSIZE

    @classmethod
    def get_prompts(cls):
        rp = chirp_common.RadioPrompts()
        rp.experimental = (
            'This driver was written from observations of the Midland '
            'software. Download a backup copy of the radio before '
            'uploading anything.')
        rp.pre_download = (
            '1. Turn the radio off.\n'
            '2. Connect the programming cable.\n'
            '3. Turn the radio on.\n'
            '4. Click OK to read the radio.')
        rp.pre_upload = (
            '1. Turn the radio off.\n'
            '2. Connect the programming cable.\n'
            '3. Turn the radio on (battery charged).\n'
            '4. Click OK to write the radio. Do not move the cable '
            'until it finishes.')
        return rp

    @classmethod
    def match_model(cls, filedata, filename):
        # Also recognize raw 8 KB dumps of the radio (no CHIRP metadata)
        return (len(filedata) >= MEMSIZE and
                filedata[0x1860:0x1867] == IDENT)

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_settings = True
        rf.has_bank = False
        rf.has_ctone = True
        rf.has_cross = True
        rf.has_rx_dtcs = True
        rf.has_dtcs_polarity = True
        rf.has_tuning_step = False
        rf.can_odd_split = True
        rf.has_name = True
        rf.valid_name_length = 6
        rf.valid_characters = NAME_CHARS
        rf.valid_skips = ['', 'S']
        rf.valid_modes = MODES
        rf.valid_tmodes = TONE_MODES
        rf.valid_cross_modes = CROSS_MODES
        rf.valid_duplexes = DUPLEXES
        rf.valid_power_levels = POWER_LEVELS
        rf.valid_tuning_steps = STEPS
        rf.valid_dtcs_codes = chirp_common.ALL_DTCS_CODES
        rf.valid_bands = [(400000000, 520000000)]
        rf.memory_bounds = (1, NUM_CHANNELS)
        return rf

    def process_mmap(self):
        self._memobj = bitwise.parse(MEM_FORMAT, self._mmap)

    # ---------------------------------------------------------- transfer

    def _write(self, data):
        self.pipe.write(data)

    def _read(self, size):
        data = self.pipe.read(size)
        if len(data) != size:
            raise errors.RadioError('Radio did not answer (got %i of %i '
                                    'bytes)' % (len(data), size))
        return data

    def _enter(self):
        try:
            self.pipe.timeout = 1
        except Exception:
            pass
        for attempt in range(3):
            try:
                self.pipe.reset_input_buffer()
            except Exception:
                pass
            self._write(b'BONLINE')
            answer = self.pipe.read(8)
            if answer[:7] == IDENT:
                return
            LOG.debug('G18 handshake %i: %r', attempt, answer)
            if answer:
                break
        raise errors.RadioError('The radio did not answer as a Midland G18 '
                                '(check cable, port and that it is on)')

    def _exit(self):
        try:
            self._write(b'E')
        except Exception:
            LOG.debug('Could not send end command', exc_info=True)

    def _status(self, msg, cur):
        status = chirp_common.Status()
        status.msg = msg
        status.cur = cur
        status.max = MEMSIZE
        status_fn = getattr(self, 'status_fn', None)
        if status_fn:
            status_fn(status)

    def sync_in(self):
        try:
            self._enter()
            data = b''
            for addr in range(0, MEMSIZE, BLOCK):
                self._write(struct.pack('>cHB', b'R', addr, BLOCK))
                head = self._read(4)
                if head != struct.pack('>cHB', b'W', addr, BLOCK):
                    raise errors.RadioError('Unexpected answer at 0x%04x' %
                                            addr)
                data += self._read(BLOCK)
                self._status('Reading from radio', addr + BLOCK)
            self._exit()
        except Exception as e:
            raise _transfer_error('download', e)
        if data[0x1860:0x1867] != IDENT:
            raise errors.RadioError('Downloaded data is not a G18 image')
        self._mmap = memmap.MemoryMapBytes(data)
        self.process_mmap()

    def sync_out(self):
        if self.get_mmap()[0x1860:0x1867] != IDENT:
            raise errors.RadioError('This image does not come from a G18')
        if self._memobj is None:
            self.process_mmap()
        # Never upload a remote-disable (DisStun) state
        self._memobj.settings.rxstun = 0
        self._memobj.settings.txstun = 0
        data = self.get_mmap().get_packed()
        try:
            self._enter()
            for addr in range(0, WRITE_END, BLOCK):
                self._write(struct.pack('>cHB', b'W', addr, BLOCK) +
                            data[addr:addr + BLOCK])
                if self._read(1) != b'\x06':
                    raise errors.RadioError('Radio refused block 0x%04x' %
                                            addr)
                self._status('Writing to radio', addr + BLOCK)
            self._exit()
        except Exception as e:
            raise _transfer_error('upload', e)

    # ---------------------------------------------------------- memories

    def get_raw_memory(self, number):
        return (repr(self._memobj.memory[number - 1]) +
                repr(self._memobj.names[number - 1]))

    def _is_empty(self, number):
        raw = self._memobj.memory[number - 1]
        return (not _bit(self._memobj.present, number) or
                raw.rxfreq.get_raw() == b'\xff\xff\xff\xff')

    def get_memory(self, number):
        mem = chirp_common.Memory(number)
        if self._is_empty(number):
            mem.empty = True
            return mem
        raw = self._memobj.memory[number - 1]
        mem.freq = int(raw.rxfreq) * 10
        txfreq = int(raw.txfreq) * 10
        chirp_common.split_to_offset(mem, mem.freq, txfreq)
        mem.name = _decode_text(self._memobj.names[number - 1].name)
        mem.mode = 'FM' if raw.wide else 'NFM'
        mem.power = POWER_LEVELS[int(raw.highpower)]
        mem.skip = '' if _bit(self._memobj.scanadd, number) else 'S'
        chirp_common.split_tone_decode(mem, decode_tone(raw.txtone),
                                       decode_tone(raw.rxtone))

        mem.extra = RadioSettingGroup('extra', 'Extra')
        bcl = int(raw.bcl)
        mem.extra.append(RadioSetting(
            'bcl', 'Busy channel lockout',
            RadioSettingValueList(BCL_LIST, current_index=min(bcl, 2))))
        mem.extra.append(RadioSetting(
            'pttid', 'PTT ID',
            RadioSettingValueList(PTTID_LIST,
                                  current_index=int(raw.pttid != 0))))
        scramble = int(raw.scramble_no) + 1 if raw.scramble else 0
        mem.extra.append(RadioSetting(
            'scrambler', 'Scrambler',
            RadioSettingValueList(SCRAMBLE_LIST, current_index=scramble)))
        return mem

    def set_memory(self, mem):
        number = mem.number
        raw = self._memobj.memory[number - 1]
        name = self._memobj.names[number - 1]
        if mem.empty:
            raw.set_raw(b'\xff' * 16)
            name.set_raw(b'\xff' * 8)
            _set_bit(self._memobj.present, number, False)
            _set_bit(self._memobj.scanadd, number, True)
            return

        if self._is_empty(number):
            # Same starting point as a channel created by the Midland
            # software: unused bits stay at 1, compander/reverse at 0
            raw.set_raw(b'\xff' * 12 + b'\xd8\x08\xff\xff')
            name.set_raw(b'\xff' * 8)

        raw.rxfreq = mem.freq // 10
        if mem.duplex == '+':
            raw.txfreq = (mem.freq + mem.offset) // 10
        elif mem.duplex == '-':
            raw.txfreq = (mem.freq - mem.offset) // 10
        elif mem.duplex == 'split':
            raw.txfreq = mem.offset // 10
        else:
            raw.txfreq = mem.freq // 10

        txtone, rxtone = chirp_common.split_tone_encode(mem)
        raw.txtone = encode_tone(*txtone)
        raw.rxtone = encode_tone(*rxtone)
        raw.wide = mem.mode == 'FM'
        raw.highpower = (mem.power is None or
                         POWER_LEVELS.index(mem.power) == 1)
        _encode_text(name.name, mem.name.rstrip(), 8)
        _set_bit(self._memobj.present, number, True)
        _set_bit(self._memobj.scanadd, number, mem.skip != 'S')

        for setting in mem.extra:
            value = str(setting.value)
            if setting.get_name() == 'bcl':
                raw.bcl = BCL_LIST.index(value)
            elif setting.get_name() == 'pttid':
                # keep any other non-zero value the radio already had
                if value == 'Off':
                    raw.pttid = 0
                elif raw.pttid == 0:
                    raw.pttid = 1
            elif setting.get_name() == 'scrambler':
                index = SCRAMBLE_LIST.index(value)
                raw.scramble = index > 0
                if index:
                    raw.scramble_no = index - 1

    # ---------------------------------------------------------- settings

    def _list(self, name, label, options, obj, field):
        index = int(getattr(obj, field))
        value = RadioSettingValueList(
            options, current_index=index if index < len(options) else 0)
        rs = RadioSetting(name, label, value)
        rs.set_apply_callback(
            lambda s: setattr(obj, field, options.index(str(s.value))))
        return rs

    def _bool(self, name, label, obj, field):
        rs = RadioSetting(name, label,
                          RadioSettingValueBoolean(bool(getattr(obj, field))))
        rs.set_apply_callback(
            lambda s: setattr(obj, field, int(bool(s.value))))
        return rs

    def _text(self, name, label, obj, field, size, charset):
        value = RadioSettingValueString(0, size,
                                        _decode_text(getattr(obj, field)),
                                        autopad=False, charset=charset)
        rs = RadioSetting(name, label, value)
        rs.set_apply_callback(
            lambda s: _encode_text(getattr(obj, field),
                                   str(s.value).rstrip(), size))
        return rs

    def get_settings(self):
        st = self._memobj.settings
        fm = self._memobj.fm

        basic = RadioSettingGroup('basic', 'Optional Features')
        basic.append(self._list('squelch', 'Squelch level', SQUELCH_LIST,
                                st, 'squelch'))
        basic.append(self._list('tot', 'Time out timer', TOT_LIST,
                                st, 'tot'))
        basic.append(self._bool('save', 'Battery save', st, 'save'))
        basic.append(self._list('power_ratio', 'Battery save ratio',
                                POWER_RATIO_LIST, st, 'power_ratio'))
        basic.append(self._list('scanmode', 'Scan mode', SCANMODE_LIST,
                                st, 'scanmode'))
        basic.append(self._list('vfostep', 'VFO step', VFOSTEP_LIST,
                                st, 'vfostep'))
        basic.append(self._list('backlight', 'Back light', BACKLIGHT_LIST,
                                st, 'backlight'))
        basic.append(self._bool('autolock', 'Auto key lock', st,
                                'autolock'))
        voice = RadioSetting('voice', 'Voice announce',
                             RadioSettingValueMap(VOICE_MAP, int(st.voice)))
        voice.set_apply_callback(
            lambda s: setattr(st, 'voice', s.value.get_mem_val()))
        basic.append(voice)
        basic.append(self._bool('beep', 'Beep', st, 'beep'))
        basic.append(self._list('voxgain', 'VOX gain level', VOXGAIN_LIST,
                                st, 'voxgain'))
        basic.append(self._list('voxdelay', 'VOX delay time', VOXDELAY_LIST,
                                st, 'voxdelay'))
        basic.append(self._list('msgmode', 'Power-on message mode',
                                MSGMODE_LIST, st, 'msgmode'))
        basic.append(self._text('poweronmsg', 'Power-on message', st,
                                'poweronmsg', 6, TEXT_CHARS))
        basic.append(self._list('pttidtype', 'PTT ID type', PTTIDTYPE_LIST,
                                st, 'pttidtype'))
        basic.append(self._bool('bot', 'Send BOT code', st, 'bot'))
        basic.append(self._text('botcode', 'BOT code', st, 'botcode', 7,
                                CODE_CHARS))
        basic.append(self._bool('eot', 'Send EOT code', st, 'eot'))
        basic.append(self._text('eotcode', 'EOT code', st, 'eotcode', 7,
                                CODE_CHARS))
        basic.append(self._bool('sidetone', 'DTMF side tone', st,
                                'sidetone'))
        basic.append(self._bool('roger', 'Roger tone', st, 'roger'))
        basic.append(self._bool('chname', 'Show channel name', st,
                                'chname'))
        basic.append(self._bool('onlych', 'Channel mode only', st,
                                'onlych'))
        basic.append(self._list('priority', 'Priority channel',
                                PRIORITY_LIST, st, 'priority'))

        menus = RadioSettingGroup('menus', 'Optional Menus')
        menus.append(self._bool('menu_offset', 'Offset frequency menu', st,
                                'menu_offset'))
        menus.append(self._bool('menu_duplex', 'Duplex menu', st,
                                'menu_duplex'))
        menus.append(self._bool('menu_wn', 'Wide/narrow menu', st,
                                'menu_wn'))
        menus.append(self._bool('menu_ani', 'ANI menu', st, 'menu_ani'))

        keys = RadioSettingGroup('keys', 'Key Assignment')
        keys.append(self._list('pf3', 'PF3', KEY_LIST, st, 'pf3'))
        keys.append(self._list('pf4', 'PF4', KEY_LIST, st, 'pf4'))
        keys.append(self._list('hold_pf3', 'PF3 long press', KEY_LIST, st,
                               'hold_pf3'))
        keys.append(self._list('hold_pf4', 'PF4 long press', KEY_LIST, st,
                               'hold_pf4'))
        keys.append(self._bool('pf1', 'Emergency key (PF1)', st, 'pf1'))

        radio = RadioSettingGroup('fmradio', 'FM Radio')
        radio.append(self._list('fm_band', 'Band', FM_BAND_LIST, fm, 'band'))
        radio.append(self._list('fm_step', 'Step', FM_STEP_LIST, fm, 'step'))
        for i in range(6):
            radio.append(self._fm_memory(i))

        return RadioSettings(basic, menus, keys, radio)

    def _fm_memory(self, index):
        fm = self._memobj.fm
        field = fm.mem[index].freq
        if field.get_raw()[0] == 0xFF:
            current = ''
        else:
            current = '%.2f' % (int(field) / 100000.0)
        rs = RadioSetting('fm_mem%i' % (index + 1),
                          'Memory %i (MHz)' % (index + 1),
                          RadioSettingValueString(0, 6, current,
                                                  autopad=False,
                                                  charset='0123456789.'))

        def apply(setting):
            text = str(setting.value).strip()
            if not text:
                field.set_raw(b'\xff' * 4)
                return
            try:
                mhz = float(text)
            except ValueError:
                raise InvalidValueError('Not a frequency: %s' % text)
            low, high = FM_BANDS[int(fm.band)]
            if not low <= mhz <= high:
                raise InvalidValueError(
                    'FM memory %s MHz is outside the band %s-%s MHz' % (
                        text, low, high))
            field.set_value(int(round(mhz * 100000)))

        rs.set_apply_callback(apply)
        return rs

    def set_settings(self, settings):
        for element in settings:
            if not isinstance(element, RadioSetting):
                self.set_settings(element)
                continue
            if element.has_apply_callback():
                element.run_apply_callback()
