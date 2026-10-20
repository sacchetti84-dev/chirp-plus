import json
import os

import pytest

from tests.unit import base  # noqa: F401 (installs the builtin _)
from chirp import directory
from chirp import settings
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


@pytest.fixture
def sierra_radio(uv5r_radio):
    """The UV-5R test image holding only the IT Team Sierra preset"""
    from chirp import import_logic
    from chirp.drivers import generic_csv
    radio = uv5r_radio
    lo, hi = radio.get_features().memory_bounds
    for number in range(lo, hi + 1):
        radio.erase_memory(number)
    csv_radio = generic_csv.CSVRadio(os.path.join(
        ROOT, 'chirp', 'stock_configs', 'IT Team Sierra.csv'))
    clo, chi = csv_radio.get_features().memory_bounds
    location = lo
    for number in range(clo, chi + 1):
        mem = csv_radio.get_memory(number)
        if mem.empty:
            continue
        radio.set_memory(import_logic.import_mem(
            radio, csv_radio.get_features(), mem,
            overrides={'number': location}))
        location += 1
    return radio


def team():
    return settings_profile.load(os.path.join(
        settings_profile.PROFILES_DIR, TEAM + '.json'))


def profile(settings=None, memories=None):
    return settings_profile.Profile(
        name='test', radios=['Baofeng UV-5R'], settings=settings or {},
        memories=memories or [], path='test.json')


def values(radio):
    """{internal name: str(value)} of every setting of the radio"""
    found = {}

    def walk(group):
        for element in group:
            if isinstance(element, settings.RadioSetting):
                found[element.get_name()] = str(element.value)
            else:
                walk(element)
    walk(radio.get_settings())
    return found


def memory_named(radio, name):
    lo, hi = radio.get_features().memory_bounds
    for number in range(lo, hi + 1):
        mem = radio.get_memory(number)
        if not mem.empty and mem.name.strip() == name:
            return mem
    raise KeyError(name)


def extras(mem):
    return {x.get_name(): str(x.value) for x in mem.extra}


def test_plan_does_not_touch_the_radio(sierra_radio):
    before = values(sierra_radio)
    plan = settings_profile.plan(team(), sierra_radio)
    assert plan.changes
    assert values(sierra_radio) == before


def test_every_profile_setting_applied(sierra_radio):
    plan = settings_profile.plan(team(), sierra_radio)
    assert plan.problems == []
    settings_profile.apply(plan, sierra_radio)
    after = values(sierra_radio)
    assert after['squelch'] == '3'
    assert after['save'] == '1:2'
    assert after['abr'] == '5'
    assert after['timeout'] == '60 sec'
    assert after['tdr'] == 'True'
    assert after['tdrab'] == 'A'
    assert after['fmradio'] == 'False'
    assert after['limits_old.uhf.enable'] == 'False'
    assert after['workmode'] == 'Channel'
    assert (after['mdfa'], after['mdfb']) == ('Name', 'Name')
    assert (after['vfoa.widenarr'], after['vfob.txpower']) == (
        'Narrow', 'Low')


def test_at_name_resolves_memory_number(sierra_radio):
    settings_profile.apply(settings_profile.plan(team(), sierra_radio),
                           sierra_radio)
    after = values(sierra_radio)
    assert after['wmchannel.mrcha'] == str(
        memory_named(sierra_radio, 'SIERRA1').number)
    assert after['wmchannel.mrchb'] == str(
        memory_named(sierra_radio, 'PMR 01').number)


def test_names_match_case_and_trailing_spaces(sierra_radio):
    plan = settings_profile.plan(profile(
        {'wmchannel.mrcha': '@sierra2 '},
        [{'names': 'sierra1*', 'extra': {'bcl': True}}]), sierra_radio)
    assert plan.problems == []
    settings_profile.apply(plan, sierra_radio)
    assert values(sierra_radio)['wmchannel.mrcha'] == str(
        memory_named(sierra_radio, 'SIERRA2').number)
    assert extras(memory_named(sierra_radio, 'SIERRA1'))['bcl'] == 'True'
    assert extras(memory_named(sierra_radio, 'SIERR10'))['bcl'] == 'False'


def test_alternative_keys_use_the_first_present(sierra_radio):
    plan = settings_profile.plan(profile(
        {'nope.key|limits_old.uhf.enable': False,
         'nope.a|nope.b': True}), sierra_radio)
    assert [p[0] for p in plan.problems] == ['nope.a|nope.b']
    settings_profile.apply(plan, sierra_radio)
    assert values(sierra_radio)['limits_old.uhf.enable'] == 'False'


def test_problems_do_not_stop_the_rest(sierra_radio):
    plan = settings_profile.plan(profile(
        {'unknown': 1, 'save': 'never', 'squelch': 42, 'tdr': 'yes',
         'wmchannel.mrcha': '@NOPE', 'beep': True}), sierra_radio)
    assert sorted(p[0] for p in plan.problems) == [
        'save', 'squelch', 'tdr', 'unknown', 'wmchannel.mrcha']
    before = values(sierra_radio)
    settings_profile.apply(plan, sierra_radio)
    after = values(sierra_radio)
    assert after['beep'] == 'True'
    for key in ('save', 'squelch', 'tdr', 'wmchannel.mrcha'):
        assert after[key] == before[key]


def test_memory_rules(sierra_radio):
    settings_profile.apply(settings_profile.plan(team(), sierra_radio),
                           sierra_radio)
    lo, hi = sierra_radio.get_features().memory_bounds
    seen = 0
    for number in range(lo, hi + 1):
        mem = sierra_radio.get_memory(number)
        if mem.empty:
            continue
        seen += 1
        assert extras(mem)['pttid'] == 'Off', mem.name
        want = 'True' if mem.name.startswith('SIERR') else 'False'
        assert extras(mem)['bcl'] == want, mem.name
    assert seen == 95


def test_changes_list_settings_and_memories(sierra_radio):
    plan = settings_profile.plan(team(), sierra_radio)
    kinds = {c.what for c in plan.changes}
    assert kinds == {'setting', 'memory'}
    squelch = [c for c in plan.changes if c.what == 'setting'
               and c.where == 'Carrier Squelch Level']
    assert [(c.before, c.after) for c in squelch] == [('1', '3')]
    assert len(plan.memories) == len(
        [c for c in plan.changes if c.what == 'memory'])


def test_second_plan_is_empty(sierra_radio):
    settings_profile.apply(settings_profile.plan(team(), sierra_radio),
                           sierra_radio)
    again = settings_profile.plan(team(), sierra_radio)
    assert (again.changes, again.memories, again.problems) == ([], [], [])


def test_shipped_profile_is_valid_for_uv5r(uv5r_radio):
    # Without the preset only the '@' names can be missing
    plan = settings_profile.plan(team(), uv5r_radio)
    assert sorted(p[0] for p in plan.problems) == [
        'wmchannel.mrcha', 'wmchannel.mrchb']


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
