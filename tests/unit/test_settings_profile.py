import json
import os

import pytest

from tests.unit import base  # noqa: F401 (installs the builtin _)
from chirp import directory
from chirp import settings_profile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
IMAGES = os.path.join(ROOT, 'tests', 'images')
TEAM = 'IT Team Sierra - impostazioni UV-5R'


@pytest.fixture(scope='module', autouse=True)
def drivers():
    directory.import_drivers()


@pytest.fixture
def uv5r_radio():
    return directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_UV-5R.img'))


def write(tmp_path, text, encoding='utf-8'):
    path = tmp_path / 'profile.json'
    path.write_bytes(text.encode(encoding))
    return str(path)


def test_shipped_team_sierra_profile():
    profiles = settings_profile.shipped_profiles()
    names = [p.name for p in profiles]
    assert TEAM in names
    assert names == sorted(names)
    team = profiles[names.index(TEAM)]
    assert team.radios == ['Baofeng UV-5R']
    assert team.settings['timeout'] == '60 sec'
    assert team.memories[0] == {'names': '*', 'extra': {'pttid': 'Off'}}


def test_load_rejects_broken_json(tmp_path):
    path = write(tmp_path, '{"name": "x", "settings": {"a": 1,}}')
    with pytest.raises(settings_profile.ProfileError) as e:
        settings_profile.load(path)
    assert 'profile.json' in str(e.value)


def test_load_accepts_utf8_bom(tmp_path):
    path = write(tmp_path, json.dumps({'name': 'BOM', 'settings': {}}),
                 encoding='utf-8-sig')
    profile = settings_profile.load(path)
    assert (profile.name, profile.radios, profile.memories) == ('BOM', [], [])
    assert profile.path == path


def test_load_requires_name_and_settings(tmp_path):
    for doc in ({'settings': {}}, {'name': 'x'}, ['not', 'a', 'dict']):
        with pytest.raises(settings_profile.ProfileError):
            settings_profile.load(write(tmp_path, json.dumps(doc)))


def test_fits(uv5r_radio):
    team = settings_profile.load(os.path.join(
        settings_profile.PROFILES_DIR, TEAM + '.json'))
    assert settings_profile.fits(team, uv5r_radio)
    other = directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_BF-A58S.img'))
    assert not settings_profile.fits(team, other)
