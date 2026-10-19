# Copyright 2026 CHIRP contributors
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

"""Map a clone mode image: which bytes belong to which driver structure.

Regions come from the driver's bitwise memory object (its top level
fields, with offset and size), so this works for any bitwise driver.
Bytes holding data that no field describes are reported as unknown.
"""

import dataclasses
import re

CHANNELS = 'channels'
NAMES = 'names'
SETTINGS = 'settings'
MESSAGES = 'messages'
SERVICE = 'service'      # squelch, limits, calibration: handle with care
UNKNOWN = 'unknown'      # data no structure describes
EMPTY = 'empty'          # 0xFF / 0x00 filler

# Same meaning as the colors elsewhere (theme.py)
KIND_TONES = {
    CHANNELS: 'info',
    NAMES: 'file',
    SETTINGS: 'code',
    MESSAGES: 'ok',
    SERVICE: 'tx',
    UNKNOWN: 'bad',
    EMPTY: 'dim',
}

_RULES = [
    (r'name', NAMES),
    (r'msg|message|welcome|poweron|logo|banner', MESSAGES),
    (r'squelch|limit|calib|tune|band|service|factory|aux', SERVICE),
    (r'^mem|memor|channel|chan', CHANNELS),
]


@dataclasses.dataclass
class Region:
    start: int
    end: int       # exclusive
    name: str
    kind: str

    @property
    def size(self):
        return self.end - self.start


def classify(name):
    lower = name.lower()
    for pattern, kind in _RULES:
        if re.search(pattern, lower):
            return kind
    return SETTINGS


def image_bytes(radio):
    return bytes(radio.get_mmap().get_byte_compatible().get(
        0, len(radio.get_mmap())))


def driver_regions(radio):
    """Top level fields of the driver's memory object, sorted by offset"""
    memobj = getattr(radio, '_memobj', None)
    if memobj is None or not hasattr(memobj, 'items'):
        return []
    regions = []
    for name, element in memobj.items():
        try:
            start = element.get_offset()
            size = element.size() // 8
        except Exception:
            continue
        if size <= 0:
            continue
        regions.append(Region(start, start + size, name, classify(name)))
    regions.sort(key=lambda r: r.start)
    return regions


def unknown_regions(data, regions, filler=(0xFF, 0x00), max_gap=3):
    """Runs of real data (not filler) outside every known region.

    Runs separated by at most @max_gap filler bytes are merged, so a table
    with a few zeros inside reads as one region.
    """
    covered = bytearray(len(data))
    for r in regions:
        for i in range(max(0, r.start), min(len(data), r.end)):
            covered[i] = 1
    found = []
    i = 0
    while i < len(data):
        if not covered[i] and data[i] not in filler:
            start = i
            while i < len(data) and not covered[i] and \
                    data[i] not in filler:
                i += 1
            near = found and start - found[-1].end <= max_gap
            if near and not any(covered[found[-1].end:start]):
                found[-1].end = i
            else:
                found.append(Region(start, i, 'unknown', UNKNOWN))
        else:
            i += 1
    return found


def build_map(radio):
    """(data, regions): all regions, known and unknown, by offset"""
    data = image_bytes(radio)
    known = driver_regions(radio)
    mem_size = getattr(radio, '_mem_size', None)
    if isinstance(mem_size, int) and 0 < mem_size < len(data):
        # Clone mode images keep the radio ident and CHIRP's metadata
        # after the radio memory
        known.append(Region(mem_size, len(data), 'ident + metadata',
                            MESSAGES))
    regions = sorted(known + unknown_regions(data, known),
                     key=lambda r: r.start)
    return data, regions


def byte_kinds(data, regions):
    """The kind of every byte (EMPTY for filler outside regions)"""
    kinds = [EMPTY] * len(data)
    for r in regions:
        for i in range(max(0, r.start), min(len(data), r.end)):
            kinds[i] = r.kind
    for i, b in enumerate(data):
        if kinds[i] != UNKNOWN and b in (0xFF,) and kinds[i] == EMPTY:
            kinds[i] = EMPTY
    return kinds


def hex_rows(data, width=16):
    """(offset, hex text, ascii text) per row"""
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hexes = ' '.join('%02X' % b for b in chunk)
        text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        yield offset, hexes, text
