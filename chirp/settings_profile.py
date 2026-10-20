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

"""Settings profiles: a set of radio settings to apply in one go.

A profile is a JSON file (see chirp/settings_profiles) with
- "name": shown in the menu;
- "radios": the "VENDOR MODEL" it was written for;
- "settings": {internal setting name: value}, the value as CHIRP shows
  it (option text, integer, true/false, text); "a|b" lists alternative
  names (firmware variants), "@NAME" is the number of the memory called
  NAME;
- "memories": rules {"names": "SIERRA*", "extra": {column: value}}
  applied to the extra columns of the matching non-empty memories.
"""
import dataclasses
import fnmatch
import glob
import json
import os

from chirp import radio_compare
from chirp import settings

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'settings_profiles')


class ProfileError(Exception):
    """A profile file that cannot be used"""


@dataclasses.dataclass
class Profile:
    name: str
    radios: list
    settings: dict
    memories: list
    path: str


def load(path):
    """Read a profile file"""
    where = os.path.basename(path)
    try:
        with open(path, encoding='utf-8-sig') as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise ProfileError('%s: %s' % (where, e))
    if (not isinstance(doc, dict) or not isinstance(doc.get('name'), str)
            or not isinstance(doc.get('settings'), dict)):
        raise ProfileError(_('%s: a profile needs a "name" and '
                             '"settings"') % where)
    radios = doc.get('radios', [])
    memories = doc.get('memories', [])
    if (not isinstance(radios, list)
            or not all(isinstance(r, str) for r in radios)):
        raise ProfileError(_('%s: "radios" must be a list of names') % where)
    if (not isinstance(memories, list)
            or not all(isinstance(r, dict)
                       and isinstance(r.get('names', '*'), str)
                       and isinstance(r.get('extra', {}), dict)
                       for r in memories)):
        raise ProfileError(_('%s: "memories" must be a list of '
                             '{"names": text, "extra": {...}}') % where)
    return Profile(name=doc['name'], radios=list(radios),
                   settings=dict(doc['settings']),
                   memories=list(memories), path=path)


def shipped_profiles():
    """The profiles that come with CHIRP Plus, sorted by name"""
    profiles = [load(path) for path in
                glob.glob(os.path.join(PROFILES_DIR, '*.json'))]
    return sorted(profiles, key=lambda p: p.name)


def fits(profile, radio):
    """True if the profile was written for this radio model"""
    return '%s %s' % (radio.VENDOR, radio.MODEL) in profile.radios


@dataclasses.dataclass
class Plan:
    settings_tree: object          # radio.get_settings(), only the changed
    changes: list                  # radio_compare.Change, what will change
    memories: list                 # changed copies of memories
    problems: list                 # (profile key, reason)


def _index(group, found=None):
    """{internal name: RadioSetting} of a settings tree"""
    found = {} if found is None else found
    for element in group:
        if isinstance(element, settings.RadioSetting):
            found[element.get_name()] = element
        else:
            _index(element, found)
    return found


def _keep_only(group, keep):
    """Drop from @group every setting not in @keep (a set of ids)"""
    for element in group.values():
        if isinstance(element, settings.RadioSetting):
            if id(element) not in keep:
                del group[element]
        else:
            _keep_only(element, keep)


def _clean_name(name):
    return (name or '').strip().upper()


def _memories(radio):
    lo, hi = radio.get_features().memory_bounds
    return [m for m in (radio.get_memory(n) for n in range(lo, hi + 1))
            if not m.empty]


def _convert(value_obj, wanted, mems):
    """The value to give @value_obj for the profile's @wanted, or raise"""
    if isinstance(wanted, str) and wanted.startswith('@'):
        if not isinstance(value_obj, settings.RadioSettingValueInteger):
            raise ValueError(_('"@" names a channel, only for numbers'))
        name = _clean_name(wanted[1:])
        for mem in mems:
            if _clean_name(mem.name) == name:
                return mem.number
        raise ValueError(_('no channel called %s') % wanted[1:].strip())
    if isinstance(value_obj, settings.RadioSettingValueBoolean):
        ok = isinstance(wanted, bool)
    elif isinstance(value_obj, settings.RadioSettingValueInteger):
        ok = isinstance(wanted, int) and not isinstance(wanted, bool)
    else:
        ok = isinstance(wanted, str)
    if not ok:
        raise ValueError(_('wrong kind of value: %r') % (wanted,))
    return wanted


def _set(setting, wanted, mems):
    """Set @setting to @wanted; True if it changed. Raises ValueError."""
    new = _convert(setting.value, wanted, mems)
    old = setting.value.get_value()
    if old == new:
        return False
    try:
        setting.value.set_value(new)
    except settings.InvalidValueError as e:
        raise ValueError(str(e))
    return True


def plan(profile, radio):
    """What applying @profile to @radio would change, without changing it"""
    tree = radio.get_settings()
    if not tree:
        raise ProfileError(_('this radio has no settings'))
    index = _index(tree)
    mems = _memories(radio)
    changes, problems, changed = [], [], set()

    for key, wanted in profile.settings.items():
        name = next((n for n in key.split('|') if n in index), None)
        if name is None:
            problems.append((key, _('this radio has no such setting')))
            continue
        setting = index[name]
        before = str(setting.value)
        try:
            is_changed = _set(setting, wanted, mems)
        except ValueError as e:
            problems.append((key, str(e)))
            continue
        if is_changed:
            changed.add(id(setting))
            changes.append(radio_compare.Change(
                radio_compare.CHANGED, 'setting', setting.get_shortname(),
                before, str(setting.value)))

    changed_mems = []
    for mem in mems:
        diffs = []
        columns = {x.get_name(): x for x in mem.extra}
        for rule in profile.memories:
            if not fnmatch.fnmatchcase(_clean_name(mem.name),
                                       _clean_name(rule.get('names', '*'))):
                continue
            for column, wanted in rule.get('extra', {}).items():
                if column not in columns:
                    problems.append(('%s %s' % (mem.number, column),
                                     _('this channel has no such column')))
                    continue
                before = str(columns[column].value)
                try:
                    if _set(columns[column], wanted, mems):
                        diffs.append((column, before,
                                      str(columns[column].value)))
                except ValueError as e:
                    problems.append(('%s %s' % (mem.number, column), str(e)))
        if diffs:
            changed_mems.append(mem)
            changes.append(radio_compare.Change(
                radio_compare.CHANGED, 'memory', str(mem.number),
                ', '.join('%s: %s' % (c, b) for c, b, _a in diffs),
                ', '.join('%s: %s' % (c, a) for c, _b, a in diffs)))
    # Only what the profile changes goes back to the radio: rewriting the
    # rest would re-encode (or choke on) bytes the profile never meant
    # to touch
    for group in tree:
        _keep_only(group, changed)
    return Plan(tree, changes, changed_mems, problems)


def apply(plan, radio):
    """Write a plan into the radio image"""
    radio.set_settings(plan.settings_tree)
    for mem in plan.memories:
        radio.set_memory(mem)
