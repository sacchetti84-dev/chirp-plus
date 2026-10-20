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
import glob
import json
import os

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
    return Profile(name=doc['name'], radios=list(doc.get('radios', [])),
                   settings=dict(doc['settings']),
                   memories=list(doc.get('memories', [])), path=path)


def shipped_profiles():
    """The profiles that come with CHIRP Plus, sorted by name"""
    profiles = [load(path) for path in
                glob.glob(os.path.join(PROFILES_DIR, '*.json'))]
    return sorted(profiles, key=lambda p: p.name)


def fits(profile, radio):
    """True if the profile was written for this radio model"""
    return '%s %s' % (radio.VENDOR, radio.MODEL) in profile.radios
