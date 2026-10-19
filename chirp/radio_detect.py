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

"""Find out which radio is on the cable, using only the clone handshake.

Baofeng style radios answer a model specific "magic" string with an ACK and
an ident block (0xAA ... 0xDD). This module tries the magic strings known by
the drivers, one at a time, exactly like the start of a download: it never
reads or writes memory. Several models share a magic (and a memory layout),
so the result is a list of compatible models, not always a single one.
"""

import collections
import contextlib
import dataclasses
import logging
import time

from chirp import directory

LOG = logging.getLogger(__name__)

ACK = b'\x06'
MAX_IDENT = 16


@dataclasses.dataclass
class Probe:
    magic: bytes
    classes: list   # radio classes that use this magic

    @property
    def label(self):
        return ', '.join(model_name(c) for c in self.classes)


@dataclasses.dataclass
class Result:
    probe: Probe
    ident: bytes

    @property
    def classes(self):
        return self.probe.classes


def model_name(rclass):
    return ('%s %s %s' % (rclass.VENDOR, rclass.MODEL,
                          rclass.VARIANT)).strip()


def _magics(rclass):
    """Magic strings a driver sends, for the Baofeng style families"""
    from chirp.drivers import baofeng_common, uv5r
    if issubclass(rclass, baofeng_common.BaofengCommonHT):
        return list(getattr(rclass, '_magic', []) or [])
    if issubclass(rclass, uv5r.BaofengUV5R):
        return list(getattr(rclass, '_idents', []) or [])
    return []


def build_probes(preferred=None):
    """One probe per distinct magic, the preferred model's magics first.

    :param preferred: a radio class (e.g. the last used model) or None
    """
    by_magic = collections.OrderedDict()
    for rclass in directory.DRV_TO_RADIO.values():
        if getattr(rclass, '_DETECTED_BY', None):
            continue
        for magic in _magics(rclass):
            by_magic.setdefault(magic, [])
            if rclass not in by_magic[magic]:
                by_magic[magic].append(rclass)
    probes = [Probe(magic, classes) for magic, classes in by_magic.items()]
    if preferred is not None:
        first = _magics(preferred)
        probes.sort(key=lambda p: (p.magic not in first,
                                   first.index(p.magic) if p.magic in first
                                   else 0))
        for probe in probes:
            if preferred in probe.classes:
                probe.classes.remove(preferred)
                probe.classes.insert(0, preferred)
    return probes


def handshake(pipe, magic, timeout=1.0):
    """Send @magic and return the ident block, or None if no answer.

    Same bytes as the drivers: magic (one byte at a time, which every
    family accepts), ACK expected, 0x02, ident up to 0xDD, then ACK/ACK.
    """
    pipe.timeout = timeout
    try:
        pipe.reset_input_buffer()
    except Exception:
        pass
    for byte in magic:
        pipe.write(bytes([byte]))
        time.sleep(0.01)
    if pipe.read(1) != ACK:
        return None
    pipe.write(b'\x02')
    ident = b''
    while len(ident) < MAX_IDENT:
        byte = pipe.read(1)
        if not byte:
            break
        ident += byte
        if byte == b'\xdd':
            break
    if not ident.startswith(b'\xaa') or not ident.endswith(b'\xdd'):
        LOG.debug('Bad ident for magic %s: %s', magic.hex(), ident.hex())
        return None
    pipe.write(ACK)
    pipe.read(1)
    return ident


def _driver_ident(rclass, ident):
    """The ident as the driver's own handshake would have returned it"""
    from chirp.drivers import uv5r
    if issubclass(rclass, uv5r.BaofengUV5R) and len(ident) == 12:
        # uv5r._do_ident() squeezes 12 byte answers (UV-6) down to 8
        return bytes([ident[0], ident[3], ident[5]]) + ident[7:]
    return ident


@contextlib.contextmanager
def already_identified(rclass, ident):
    """Let the next download by @rclass reuse a handshake already done.

    After answering the magic, the radio stays in program mode for 2-3
    seconds of silence (measured on a UV-9R) and ignores a second magic
    meanwhile, so a download started right after a detection must skip its
    own handshake. Later than that, a normal download works again.
    """
    from chirp.drivers import baofeng_common, uv5r
    if issubclass(rclass, baofeng_common.BaofengCommonHT):
        module = baofeng_common
    elif issubclass(rclass, uv5r.BaofengUV5R):
        module = uv5r
    else:
        raise ValueError('%s does not use a Baofeng handshake' % rclass)
    original = module._ident_radio
    pending = [_driver_ident(rclass, ident)]

    def reuse(radio):
        if pending:
            return pending.pop()
        return original(radio)

    module._ident_radio = reuse
    try:
        yield
    finally:
        module._ident_radio = original


def sync_in_after_identify(radio, ident):
    """Download from a radio whose handshake identify() just did"""
    with already_identified(type(radio), ident):
        radio.sync_in()


def identify(pipe, probes, status=None, cancelled=None, pause=0.3):
    """Try each probe until the radio answers.

    :param status: optional fn(index, total, probe) for progress
    :param cancelled: optional fn() returning True to stop early
    :returns: a Result, or None if nothing answered
    """
    for i, probe in enumerate(probes):
        if cancelled and cancelled():
            return None
        if status:
            status(i, len(probes), probe)
        try:
            ident = handshake(pipe, probe.magic)
        except Exception as e:
            LOG.warning('Handshake with %s failed: %s', probe.magic.hex(), e)
            ident = None
        if ident:
            LOG.info('Radio answered %s with ident %s (%s)',
                     probe.magic.hex(), ident.hex(), probe.label)
            return Result(probe, ident)
        time.sleep(pause)
    return None
