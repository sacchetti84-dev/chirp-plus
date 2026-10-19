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

"""Check memories against the frequency allocations of a country.

The result is advice, not legal certainty: it points at channels that
transmit where a license is needed, where only receiving is allowed, or
with more power than a licence-free band permits. Rules are for Italy.
"""

import dataclasses
import math


def _(string):
    # Marker only: the UI translates templates and band names
    return string


LICENSE = 'license'       # transmitting needs a license
FREE = 'free'             # licence-free with power limit and approved radios
RX_ONLY = 'rx_only'       # transmitting is not allowed


@dataclasses.dataclass
class Band:
    lo: float              # MHz
    hi: float
    name: str
    use: str
    max_watts: float = None
    note: str = ''


# Italy (PNRF) - the bands a VHF/UHF handheld can reach
ITALY = [
    Band(87.5, 108.0, _('FM broadcast'), RX_ONLY),
    Band(108.0, 137.0, _('airband'), RX_ONLY),
    Band(144.0, 146.0, _('amateur 2 m'), LICENSE),
    Band(156.0, 162.025, _('marine VHF'), LICENSE,
         note=_('needs a maritime radio licence')),
    Band(430.0, 434.0, _('amateur 70 cm'), LICENSE),
    Band(435.0, 438.0, _('amateur satellite 70 cm'), LICENSE),
    # LPD sits inside the 70 cm amateur band: the narrowest band wins
    Band(433.05, 434.79, 'LPD', FREE, max_watts=0.01),
    Band(446.0, 446.2, 'PMR446', FREE, max_watts=0.5,
         note=_('only with approved PMR446 radios and fixed antenna')),
]

MSG_OUTSIDE = _('transmits on %(freq)s, outside the known bands')
MSG_RX_ONLY = _('transmits on %(freq)s (%(band)s): receive only, set '
                'Duplex to off')
MSG_LICENSE = _('%(band)s: transmitting needs a license')
MSG_POWER = _('%(band)s allows %(max)s W, this channel uses %(watts)s W')
MSG_NOTE = _('%(band)s: %(note)s')

INFO, WARN, BAD = 'info', 'warn', 'bad'


@dataclasses.dataclass
class Finding:
    number: object
    level: str              # info / warn / bad
    template: str           # one of MSG_*, translatable
    args: dict
    band: str = ''
    note: str = ''

    def message(self, translate=lambda s: s):
        args = dict(self.args)
        for key in ('band', 'note'):
            if key in args:
                args[key] = translate(args[key])
        text = translate(self.template) % args
        if self.note:
            text += ' (%s)' % translate(self.note)
        return text


def watts(power):
    """Power of a chirp PowerLevel in watts (float(level) is dBm)"""
    if power is None:
        return None
    try:
        return math.pow(10, float(power) / 10) / 1000
    except (TypeError, ValueError):
        return None


def band_for(freq_hz, bands=ITALY):
    mhz = freq_hz / 1000000.0
    matches = [b for b in bands if b.lo <= mhz <= b.hi]
    if not matches:
        return None
    # The narrowest allocation wins (LPD inside the 70 cm band)
    return min(matches, key=lambda b: b.hi - b.lo)


def tx_freq(mem):
    if mem.duplex == 'off':
        return None
    if mem.duplex == 'split':
        return mem.offset
    if mem.duplex == '+':
        return mem.freq + mem.offset
    if mem.duplex == '-':
        return mem.freq - mem.offset
    return mem.freq


def check_memory(mem, bands=ITALY):
    """Findings for one memory (empty list when there is nothing to say)"""
    if mem.empty:
        return []
    tx = tx_freq(mem)
    if tx is None:
        return []        # receive only: always fine
    band = band_for(tx, bands)
    where = '%.5f MHz' % (tx / 1000000.0)
    if band is None:
        return [Finding(mem.number, WARN, MSG_OUTSIDE, {'freq': where})]
    args = {'band': band.name, 'freq': where}
    if band.use == RX_ONLY:
        return [Finding(mem.number, BAD, MSG_RX_ONLY, args, band.name)]
    if band.use == LICENSE:
        return [Finding(mem.number, INFO, MSG_LICENSE, args, band.name,
                        band.note)]
    power = watts(mem.power)
    if (band.max_watts is not None and power is not None and
            power > band.max_watts * 1.05):
        args.update({'max': '%g' % band.max_watts, 'watts': '%.1f' % power})
        return [Finding(mem.number, WARN, MSG_POWER, args, band.name,
                        band.note)]
    if band.note:
        args['note'] = band.note
        return [Finding(mem.number, INFO, MSG_NOTE, args, band.name)]
    return []


def check_radio(radio, bands=ITALY):
    lo, hi = radio.get_features().memory_bounds
    findings = []
    for number in range(lo, hi + 1):
        try:
            mem = radio.get_memory(number)
        except Exception:
            continue
        findings.extend(check_memory(mem, bands))
    return findings


def summary(findings):
    counts = {INFO: 0, WARN: 0, BAD: 0}
    for f in findings:
        counts[f.level] += 1
    return counts
