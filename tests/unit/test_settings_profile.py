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
TEAM_9R = 'IT Team Sierra - impostazioni UV-9R'

# The UV-5R driver warns on every memory it writes (set_raw with str)
pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


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
    return load_sierra(uv5r_radio)


@pytest.fixture
def uv9r_sierra():
    """A UV-9R with the IT Team Sierra preset (the UV-9G test image has
    the same memory layout)"""
    from chirp import memmap
    from chirp.drivers import baofeng_wp970i
    image = directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_UV-9G.img'))
    return load_sierra(baofeng_wp970i.UV9R(memmap.MemoryMapBytes(
        image.get_mmap().get_byte_compatible().get_packed())))


def load_sierra(radio):
    from chirp import import_logic
    from chirp.drivers import generic_csv
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


def team(name=TEAM):
    return settings_profile.load(os.path.join(
        settings_profile.PROFILES_DIR, name + '.json'))


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
    # UHF TX stays on: the standard PMR446/LPD channels transmit
    assert after['limits_old.uhf.enable'] == 'True'
    assert after['workmode'] == 'Channel'
    assert (after['mdfa'], after['mdfb']) == ('Name', 'Name')
    assert (after['vfoa.widenarr'], after['vfob.txpower']) == (
        'Narrow', 'Low')


def test_profile_turns_uhf_tx_back_on(sierra_radio):
    # A radio set up with plus.5 had UHF TX off: the standard PMR446/LPD
    # channels must be able to transmit again
    settings_profile.apply(settings_profile.plan(profile(
        {'limits_old.uhf.enable': False}), sierra_radio), sierra_radio)
    settings_profile.apply(settings_profile.plan(team(), sierra_radio),
                           sierra_radio)
    assert values(sierra_radio)['limits_old.uhf.enable'] == 'True'


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


def test_apply_writes_only_changed_settings(sierra_radio):
    # Real radios carry out-of-range bytes; settings the profile does not
    # set must be neither validated nor rewritten
    obj = sierra_radio._memobj
    obj.settings.pttlt = 0xFF
    obj.poweron_msg.line1.set_raw(b'\xff' * 7)
    before = sierra_radio.get_mmap().get_packed()[0x1828:0x1838]
    plan = settings_profile.plan(team(), sierra_radio)
    settings_profile.apply(plan, sierra_radio)
    assert values(sierra_radio)['squelch'] == '3'
    assert int(obj.settings.pttlt) == 0xFF
    assert sierra_radio.get_mmap().get_packed()[0x1828:0x1838] == before


def test_plan_without_settings_is_a_profile_error(sierra_radio,
                                                  monkeypatch):
    monkeypatch.setattr(sierra_radio, 'get_settings', lambda: None)
    with pytest.raises(settings_profile.ProfileError):
        settings_profile.plan(team(), sierra_radio)


@pytest.mark.parametrize('doc', [
    {'name': 'x', 'settings': {}, 'radios': None},
    {'name': 'x', 'settings': {}, 'radios': 'Baofeng UV-5R'},
    {'name': 'x', 'settings': {}, 'memories': {'names': '*'}},
    {'name': 'x', 'settings': {}, 'memories': ['*']},
    {'name': 'x', 'settings': {}, 'memories': [{'names': '*',
                                                'extra': ['bcl']}]},
    {'name': 'x', 'settings': {}, 'memories': [{'names': 5,
                                                'extra': {}}]},
])
def test_load_rejects_bad_shapes(tmp_path, doc):
    with pytest.raises(settings_profile.ProfileError) as e:
        settings_profile.load(write(tmp_path, json.dumps(doc)))
    assert 'profile.json' in str(e.value)


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


def test_uv9r_profile(uv9r_sierra):
    profile = team(TEAM_9R)
    assert profile.radios == ['Baofeng UV-9R']
    assert settings_profile.fits(profile, uv9r_sierra)
    before = values(uv9r_sierra)
    plan = settings_profile.plan(profile, uv9r_sierra)
    assert plan.problems == []
    settings_profile.apply(plan, uv9r_sierra)
    after = values(uv9r_sierra)
    assert after['settings.squelch'] == '3'
    assert after['settings.timeout'] == '60 sec'
    assert after['settings.voice'] == 'Off'
    assert after['settings.fmradio'] == 'False'
    assert after['settings.workmode'] == 'Channel'
    assert after['wmchannel.mrcha'] == str(
        memory_named(uv9r_sierra, 'SIERRA1').number)
    assert after['wmchannel.mrchb'] == str(
        memory_named(uv9r_sierra, 'PMR 01').number)
    assert (after['vfo.a.txpower3'], after['vfo.b.widenarr']) == (
        'Low', 'Narrow')
    # Firmware and power-on texts, limits and VFO frequencies untouched
    for key in ('limits.uhf.upper', 'limits.vhf.lower', 'vfo.a.freq',
                'poweron_msg.line1', 'firmware_msg.line1'):
        assert after[key] == before[key], key
    assert extras(memory_named(uv9r_sierra, 'SIERR10'))['bcl'] == 'True'
    assert extras(memory_named(uv9r_sierra, 'PMR 01'))['pttid'] == 'Off'
    again = settings_profile.plan(profile, uv9r_sierra)
    assert again.changes == []


def test_shipped_profiles_one_per_radio():
    names = [p.name for p in settings_profile.shipped_profiles()]
    assert names == [TEAM, TEAM_9R]


def test_text_settings_are_idempotent(uv9r_sierra):
    # Text settings come back padded to their length: same text, no change
    p = profile({'poweron_msg.line1': 'SIERRA'})
    settings_profile.apply(settings_profile.plan(p, uv9r_sierra),
                           uv9r_sierra)
    assert values(uv9r_sierra)['poweron_msg.line1'].rstrip() == 'SIERRA'
    assert settings_profile.plan(p, uv9r_sierra).changes == []


@pytest.mark.parametrize('wanted', ['@', '@   '])
def test_empty_at_name_is_a_problem(sierra_radio, wanted):
    # A channel without a name must not be what '@' points to
    mem = sierra_radio.get_memory(0)
    mem.number, mem.name = 100, ''
    sierra_radio.set_memory(mem)
    plan = settings_profile.plan(profile({'wmchannel.mrcha': wanted}),
                                 sierra_radio)
    assert [p[0] for p in plan.problems] == ['wmchannel.mrcha']
    assert plan.changes == []


def test_multi_valued_setting_is_a_problem(sierra_radio, monkeypatch):
    group = settings.RadioSettingGroup('top', 'Top')
    group.append(settings.RadioSetting(
        'pair', 'Pair', settings.RadioSettingValueInteger(0, 9, 1),
        settings.RadioSettingValueInteger(0, 9, 2)))
    group.append(settings.RadioSetting(
        'one', 'One', settings.RadioSettingValueInteger(0, 9, 1)))
    root = settings.RadioSettings(group)
    monkeypatch.setattr(sierra_radio, 'get_settings', lambda: root)
    # A text value used to reach set_value() on the list of values
    plan = settings_profile.plan(profile({'pair': '3', 'one': 4}),
                                 sierra_radio)
    assert [p[0] for p in plan.problems] == ['pair']
    assert [c.where for c in plan.changes if c.what == 'setting'] == ['One']


def test_broken_file_does_not_hide_the_other_profiles(tmp_path,
                                                      monkeypatch):
    (tmp_path / 'good.json').write_text(
        json.dumps({'name': 'Good', 'settings': {}}), encoding='utf-8')
    (tmp_path / 'broken.json').write_text('{', encoding='utf-8')
    monkeypatch.setattr(settings_profile, 'PROFILES_DIR', str(tmp_path))
    assert [p.name for p in settings_profile.shipped_profiles()] == ['Good']
