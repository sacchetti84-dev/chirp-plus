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

"""Compare two radio images: what an upload would change, and whether an
upload really landed in the radio.

No UI and no serial access here: callers download the images.
"""

import dataclasses
import logging

from chirp import settings as chirp_settings

LOG = logging.getLogger(__name__)

ADDED, REMOVED, CHANGED = 'added', 'removed', 'changed'


@dataclasses.dataclass
class Change:
    kind: str       # ADDED / REMOVED / CHANGED
    what: str       # 'memory' or 'setting'
    where: str      # memory number or setting path
    before: str
    after: str


def _memories(radio):
    lo, hi = radio.get_features().memory_bounds
    result = {}
    for number in range(lo, hi + 1):
        try:
            mem = radio.get_memory(number)
        except Exception as e:
            LOG.debug('Skipping memory %i: %s', number, e)
            continue
        result[number] = mem
    return result


def describe(mem):
    if mem is None or mem.empty:
        return ''
    parts = ['%.6f' % (mem.freq / 1000000), mem.name.strip()]
    if mem.duplex:
        parts.append('%s%.6f' % (mem.duplex, mem.offset / 1000000))
    if mem.tmode:
        parts.append(mem.tmode)
    parts.append(mem.mode)
    if mem.power:
        parts.append(str(mem.power))
    return ' '.join(p for p in parts if p)


def _key(mem):
    if mem is None or mem.empty:
        return None
    # Location first, then every CSV field: what the radio stores
    return tuple(mem.to_csv()[1:])


def diff_memories(old, new):
    old_mems, new_mems = _memories(old), _memories(new)
    changes = []
    for number in sorted(set(old_mems) | set(new_mems)):
        a, b = old_mems.get(number), new_mems.get(number)
        ka, kb = _key(a), _key(b)
        if ka == kb:
            continue
        kind = ADDED if ka is None else REMOVED if kb is None else CHANGED
        changes.append(Change(kind, 'memory', str(number), describe(a),
                              describe(b)))
    return changes


def _walk(element, path, out):
    for child in element:
        name = '%s/%s' % (path, child.get_shortname()) if path \
            else child.get_shortname()
        if isinstance(child, chirp_settings.RadioSetting):
            try:
                out[name] = str(child.value)
            except Exception as e:
                out[name] = '<%s>' % e
        else:
            _walk(child, name, out)


def setting_values(radio):
    """Flat {path: value} of the radio settings, {} if it has none"""
    try:
        groups = radio.get_settings()
    except Exception as e:
        LOG.debug('No settings for %s: %s', radio, e)
        return {}
    values = {}
    for group in groups or []:
        _walk(group, group.get_shortname(), values)
    return values


def diff_settings(old, new):
    a, b = setting_values(old), setting_values(new)
    changes = []
    for name in sorted(set(a) | set(b)):
        if a.get(name) != b.get(name):
            kind = ADDED if name not in a else REMOVED if name not in b \
                else CHANGED
            changes.append(Change(kind, 'setting', name, a.get(name, ''),
                                  b.get(name, '')))
    return changes


def diff_radios(old, new):
    """Everything that differs from @old to @new (memories, then settings)"""
    return diff_memories(old, new) + diff_settings(old, new)


def summary(changes):
    """Counts for a short message: {'memory': n, 'setting': m}"""
    counts = {'memory': 0, 'setting': 0}
    for change in changes:
        counts[change.what] += 1
    return counts


def _image(radio):
    try:
        return radio.get_mmap().get_byte_compatible()
    except Exception:
        return None


def written_ranges(radio):
    """Address ranges the driver writes on upload, or None if unknown"""
    ranges = getattr(radio, '_ranges', None)
    if ranges and all(len(r) == 2 for r in ranges):
        return [(int(s), int(e)) for s, e in ranges]
    return None


def verify_upload(uploaded, readback):
    """Check that @readback (downloaded right after the upload) holds what
    was uploaded.

    Byte for byte over the ranges the driver writes when it declares them
    (Baofeng style drivers), otherwise memory by memory.

    :returns: (method, problems): method is 'bytes' or 'memories';
              problems is a list of (start, end) ranges or of Changes
    """
    ranges = written_ranges(uploaded)
    a, b = _image(uploaded), _image(readback)
    if ranges and a is not None and b is not None:
        bad = []
        for start, end in ranges:
            if a.get(start, end - start) != b.get(start, end - start):
                first = next(i for i in range(start, end)
                             if a.get(i, 1) != b.get(i, 1))
                bad.append((first, end))
        return 'bytes', bad
    return 'memories', diff_memories(uploaded, readback)
