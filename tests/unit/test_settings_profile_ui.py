"""Radio > Apply settings profile, on a real ChirpEditorSet (real wx)."""

import os

import pytest

# The real-wx harness of the spreadsheet-like grid: same guards, same
# temporary config, same fixtures.
from tests.unit import test_memedit_cells as harness
from tests.unit.test_memedit_cells import (  # noqa: F401
    real_wx, wx_app, no_dialogs)

import wx  # noqa: E402

from chirp import directory  # noqa: E402
from chirp import chirp_common  # noqa: E402
from chirp import import_logic  # noqa: E402
from chirp import settings  # noqa: E402
from chirp import settings_profile  # noqa: E402
from chirp.drivers import generic_csv  # noqa: E402
from chirp.wxui import changes  # noqa: E402
from chirp.wxui import main  # noqa: E402
from chirp.wxui import memedit  # noqa: E402
from chirp.wxui import profiles  # noqa: E402
from chirp.wxui import settingsedit  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
IMAGES = os.path.join(ROOT, 'tests', 'images')
SIERRA_CSV = os.path.join(ROOT, 'chirp', 'stock_configs',
                          'IT Team Sierra.csv')
TEAM = 'IT Team Sierra - impostazioni UV-5R'

# The UV-5R driver warns on every memory it writes (set_raw with str)
pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


def team():
    return settings_profile.load(os.path.join(
        settings_profile.PROFILES_DIR, TEAM + '.json'))


def load_sierra(radio):
    lo, hi = radio.get_features().memory_bounds
    for number in range(lo, hi + 1):
        radio.erase_memory(number)
    csv_radio = generic_csv.CSVRadio(SIERRA_CSV)
    clo, chi = csv_radio.get_features().memory_bounds
    location = lo
    for number in range(clo, chi + 1):
        mem = csv_radio.get_memory(number)
        if not mem.empty:
            radio.set_memory(import_logic.import_mem(
                radio, csv_radio.get_features(), mem,
                overrides={'number': location}))
            location += 1
    return radio


def setting(radio, name):
    found = {}

    def walk(group):
        for element in group:
            if isinstance(element, settings.RadioSetting):
                found[element.get_name()] = str(element.value)
            else:
                walk(element)
    walk(radio.get_settings())
    return found[name]


@pytest.fixture
def frame(wx_app):  # noqa: F811 (pytest fixture)
    window = wx.Frame(None)
    harness._make_menubar(window)
    yield window
    window.Destroy()
    # Let wx finish deleting the children, or it complains at exit
    wx.SafeYield()


def editorset_for(frame, radio):
    eset = main.ChirpEditorSet(radio, None, frame)
    wx.SafeYield()
    return eset


@pytest.fixture
def sierra_set(frame):
    directory.import_drivers()
    radio = load_sierra(directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_UV-5R.img')))
    return editorset_for(frame, radio)


def the_memedit(eset):
    return next(e for _t, e in eset.iter_editors(memedit.ChirpMemEdit))


@pytest.fixture
def answer(monkeypatch):
    """Make the changes dialog answer OK (or what the test sets)"""
    reply = {'value': wx.ID_OK, 'shown': 0}

    def show(self):
        reply['shown'] += 1
        return reply['value']
    monkeypatch.setattr(changes.ChangesDialog, 'ShowModal', show)
    return reply


@pytest.fixture
def boxes(monkeypatch):
    """Record wx.MessageBox texts instead of showing them"""
    seen = []
    monkeypatch.setattr(wx, 'MessageBox',
                        lambda text, *a, **k: seen.append(text))
    return seen


def test_menu_lists_profiles(frame):
    chosen = []
    menu = wx.Menu()
    item = profiles.add_menu(frame, menu, chosen.append)
    sub = item.GetSubMenu()
    labels = [i.GetItemLabelText() for i in sub.GetMenuItems()
              if not i.IsSeparator()]
    assert TEAM in labels
    assert labels[-1] == 'From file...'
    for i in sub.GetMenuItems():
        if i.GetItemLabelText() in (TEAM, 'From file...'):
            frame.ProcessEvent(wx.CommandEvent(wx.EVT_MENU.typeId,
                                               i.GetId()))
    assert [p.name if p else None for p in chosen] == [TEAM, None]


def test_apply_shows_changes_then_applies(sierra_set, answer, monkeypatch):
    refreshed = []
    monkeypatch.setattr(settingsedit.ChirpSettingsEdit, 'refresh',
                        lambda self: refreshed.append(self))
    radio = sierra_set.radio
    assert profiles.apply_profile(sierra_set, sierra_set, team())
    assert answer['shown'] == 1
    assert setting(radio, 'squelch') == '3'
    assert setting(radio, 'timeout') == '60 sec'
    edit = the_memedit(sierra_set)
    assert edit._undo_queue[0].name == 'Profile %s' % TEAM
    assert len(edit._undo_queue) == 1
    assert refreshed


def test_refresh_before_settings_tab_was_ever_shown(sierra_set):
    # Applying a profile refreshes the Settings tab even if it was never
    # opened: loading it afterwards must not select page -1
    editor = next(e for _t, e in sierra_set.iter_editors(
        settingsedit.ChirpSettingsEdit))
    editor.refresh()

    class Job:
        result = sierra_set.radio.get_settings()
    editor._initialize(Job())
    wx.SafeYield()
    assert editor._group_control.GetPageCount() > 0


def test_current_settings_tab_reloads(sierra_set, answer, monkeypatch):
    # The "Getting settings" wait dialog is a real ProgressDialog
    monkeypatch.setattr(settingsedit.ChirpSettingsEdit, 'start_wait_dialog',
                        lambda self, msg: None)
    monkeypatch.setattr(settingsedit.ChirpSettingsEdit, 'stop_wait_dialog',
                        lambda self: None)
    editor = next(e for _t, e in sierra_set.iter_editors(
        settingsedit.ChirpSettingsEdit))
    sierra_set.select_editor(name='Settings')
    for i in range(20):
        wx.SafeYield()
    assert editor._group_control.GetPageCount() > 0
    assert profiles.apply_profile(sierra_set, sierra_set, team())
    for i in range(20):
        wx.SafeYield()
    assert editor._group_control.GetPageCount() > 0


def test_radio_without_settings_shows_message(sierra_set, answer, boxes,
                                              monkeypatch):
    monkeypatch.setattr(sierra_set.radio, 'get_settings', lambda: None)
    assert not profiles.apply_profile(sierra_set, sierra_set, team())
    assert len(boxes) == 1
    assert answer['shown'] == 0


def test_cancel_changes_nothing(sierra_set, answer):
    answer['value'] = wx.ID_CANCEL
    radio = sierra_set.radio
    before = setting(radio, 'squelch')
    assert not profiles.apply_profile(sierra_set, sierra_set, team())
    assert setting(radio, 'squelch') == before
    assert the_memedit(sierra_set)._undo_queue == []


def test_already_applied_says_so(sierra_set, answer, boxes):
    assert profiles.apply_profile(sierra_set, sierra_set, team())
    assert not profiles.apply_profile(sierra_set, sierra_set, team())
    assert answer['shown'] == 1
    assert boxes == ['The radio already has these settings.']


def test_csv_tab_is_refused(frame, boxes, answer):
    eset = editorset_for(frame, generic_csv.CSVRadio(SIERRA_CSV))
    assert not profiles.apply_profile(eset, eset, team())
    assert answer['shown'] == 0
    assert len(boxes) == 1


def test_other_model_asks_first(frame, monkeypatch, answer):
    directory.import_drivers()
    radio = directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_BF-A58S.img'))
    eset = editorset_for(frame, radio)
    asked = []

    class No:
        def __init__(self, parent, text, *a, **k):
            asked.append(text)

        def ShowModal(self):
            return wx.ID_NO

        def Destroy(self):
            pass
    monkeypatch.setattr(wx, 'MessageDialog', No)
    assert not profiles.apply_profile(eset, eset, team())
    assert asked and 'Baofeng UV-5R' in asked[0]
    assert answer['shown'] == 0


@pytest.fixture
def dialog_args(monkeypatch):
    """The keyword arguments of the changes dialog (answers OK)"""
    seen = {}
    init = changes.ChangesDialog.__init__

    def spy(self, *a, **k):
        seen.update(k, args=a)
        init(self, *a, **k)
    monkeypatch.setattr(changes.ChangesDialog, '__init__', spy)
    monkeypatch.setattr(changes.ChangesDialog, 'ShowModal',
                        lambda self: wx.ID_OK)
    return seen


@pytest.fixture
def warnings_shown(monkeypatch):
    """(message, title, details) of every problems dialog"""
    shown = []

    class Dialog:
        def __init__(self, parent, text, title, *a, **k):
            self.text, self.title = text, title

        def SetExtendedMessage(self, details):
            shown.append((self.text, self.title, details))

        def ShowModal(self):
            return wx.ID_OK

        def Destroy(self):
            pass
    monkeypatch.setattr(wx, 'MessageDialog', Dialog)
    return shown


def broken_team():
    profile = team()
    profile.settings = dict(profile.settings, nope=1, squelch=99)
    return profile


def test_problems_are_shown_before_confirming(sierra_set, dialog_args,
                                              warnings_shown):
    assert profiles.apply_profile(sierra_set, sierra_set, broken_team())
    assert '[nope]' in dialog_args['note']
    assert '[squelch]' in dialog_args['note']


def test_dialog_does_not_look_like_an_upload(sierra_set, dialog_args,
                                             warnings_shown):
    assert profiles.apply_profile(sierra_set, sierra_set, team())
    assert dialog_args['action_icon'] != 'upload'
    assert 'image' in dialog_args['summary']
    assert 'in the radio' not in dialog_args['summary']


def test_problems_dialog_title_and_count(sierra_set, dialog_args,
                                         warnings_shown):
    assert profiles.apply_profile(sierra_set, sierra_set, broken_team())
    [(text, title, details)] = warnings_shown
    assert title == 'Settings profile'
    assert text == '2 settings were not changed'
    assert '[nope]' in details


def test_channel_changes_undo_in_one_step(sierra_set, answer):
    radio = sierra_set.radio
    edit = the_memedit(sierra_set)
    number = next(n for n in range(128)
                  if radio.get_memory(n).name.strip() == 'SIERRA1')
    assert profiles.apply_profile(sierra_set, sierra_set, team())
    extra = {x.get_name(): str(x.value)
             for x in radio.get_memory(number).extra}
    assert extra['bcl'] == 'True'
    edit._undo(None)
    extra = {x.get_name(): str(x.value)
             for x in radio.get_memory(number).extra}
    assert extra['bcl'] == 'False'


def test_live_radio_is_refused(boxes, answer):
    class Live(chirp_common.LiveRadio):
        VENDOR, MODEL = 'Baofeng', 'UV-5R'

        def __init__(self):
            pass

    class EditorSet:
        radio = Live()
    assert not profiles.apply_profile(None, EditorSet(), team())
    assert len(boxes) == 1
    assert answer['shown'] == 0


def test_other_model_yes_goes_on(frame, monkeypatch, answer):
    directory.import_drivers()
    eset = editorset_for(frame, directory.get_radio_by_image(
        os.path.join(IMAGES, 'Baofeng_BF-A58S.img')))

    class Yes:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_YES

        def SetExtendedMessage(self, text):
            pass

        def Destroy(self):
            pass
    monkeypatch.setattr(wx, 'MessageDialog', Yes)
    profiles.apply_profile(eset, eset, team())
    assert answer['shown'] == 1


def test_choose_file(frame, tmp_path, monkeypatch, boxes):
    good = tmp_path / 'good.json'
    good.write_text('{"name": "Mine", "settings": {}}', encoding='utf-8')
    broken = tmp_path / 'broken.json'
    broken.write_text('{', encoding='utf-8')
    picked = {}

    class Picker:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def ShowModal(self):
            return wx.ID_OK

        def GetPath(self):
            return picked['path']
    monkeypatch.setattr(wx, 'FileDialog', Picker)
    picked['path'] = str(good)
    assert profiles.choose_file(frame).name == 'Mine'
    picked['path'] = str(broken)
    assert profiles.choose_file(frame) is None
    assert len(boxes) == 1 and 'broken.json' in boxes[0]
