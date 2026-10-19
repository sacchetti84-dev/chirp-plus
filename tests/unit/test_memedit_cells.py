"""Cell edits on a real ChirpMemEdit (real wx, hidden frame).

Shared harness for the spreadsheet-like grid: the `memedit` fixture
gives a ChirpMemEdit loaded with the UV-5R test image.
"""

import os
import sys
import tempfile
from unittest import mock

import pytest

from tests.unit import base  # noqa

# test_wxui_radiothread puts a MagicMock in sys.modules['wx'] when it is
# collected; if that happened first there is no real wx to test with.
import wx  # noqa: E402
if isinstance(wx, mock.Mock) or not hasattr(wx, 'version'):
    pytest.skip('wx is mocked by another test module',
                allow_module_level=True)

from chirp.wxui import config  # noqa: E402

# Never touch the user's real CHIRP config: memedit and friends read
# config.get() at import time.
_TMPDIR = tempfile.TemporaryDirectory(prefix='chirp-memedit-test-')
config._CONFIG = config.ChirpConfig(_TMPDIR.name)
_CONF = config.get()
# IARU Region 1: 145.600 MHz is a repeater output with -600 kHz
_CONF.set_bool('north_america', False, 'bandplan')
_CONF.set_bool('iaru_r1', True, 'bandplan')

from chirp import directory  # noqa: E402
from chirp.wxui import memedit as memedit_mod  # noqa: E402
from chirp.wxui import cellops  # noqa: E402
from chirp.wxui import common  # noqa: E402

if memedit_mod.CONF._config is not config._CONFIG:
    pytest.skip('chirp.wxui.memedit was imported with another config',
                allow_module_level=True)

IMAGE = os.path.join(os.path.dirname(__file__), '..', 'images',
                     'Baofeng_UV-5R.img')


def _wx_modules():
    return {k: v for k, v in sys.modules.items()
            if k == 'wx' or k.startswith('wx.')}


# The real wx, as imported above
_REAL_WX = _wx_modules()


@pytest.fixture(scope='module')
def real_wx():
    """Put the real wx back in sys.modules while these tests run.

    Modules collected after this one (test_wxui_*) replace wx in
    sys.modules with mocks, and wx itself crashes (access violation)
    creating windows when it finds them there. Their own modules keep
    the mocks they imported, so swapping back afterwards is enough.
    """
    saved = _wx_modules()
    sys.modules.update(_REAL_WX)
    yield
    for name, module in _REAL_WX.items():
        if name in saved:
            sys.modules[name] = saved[name]
        else:
            del sys.modules[name]


@pytest.fixture(scope='module')
def wx_app(real_wx):
    try:
        app = wx.App(False)
    except Exception as e:
        pytest.skip('Unable to create a wx.App: %s' % e)
    yield app


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    """Any dialog would block the test run: make it fail instead."""
    def fail(*a, **k):
        raise AssertionError('Dialog opened: %r' % (a,))
    monkeypatch.setattr(wx, 'MessageBox', fail)
    monkeypatch.setattr(common.error_proof, 'show_error', fail)


def _make_menubar(frame):
    # undo_context() updates the Undo/Redo items of the main window menu
    menu = wx.Menu()
    menu.Append(wx.ID_UNDO, 'Undo')
    menu.Append(wx.ID_REDO, 'Redo')
    menu.AppendCheckItem(memedit_mod.TX_WORKFLOW_ID, 'TX workflow')
    menubar = wx.MenuBar()
    menubar.Append(menu, 'Edit')
    frame.SetMenuBar(menubar)


@pytest.fixture
def memedit(wx_app):
    directory.import_drivers()
    radio = directory.get_radio_by_image(IMAGE)
    frame = wx.Frame(None)
    _make_menubar(frame)
    editor = memedit_mod.ChirpMemEdit(radio, frame)
    # The memory editor is a sync editor for clone-mode radios, so
    # refresh() loads every memory into the grid right away
    editor.refresh()
    wx.SafeYield()
    try:
        yield editor
    finally:
        frame.Destroy()
        wx.SafeYield()


class FakeEvent:
    def __init__(self, row, col, text):
        self.row = row
        self.col = col
        self.text = text
        self.vetoed = False
        self.skipped = False

    def GetRow(self):
        return self.row

    def GetCol(self):
        return self.col

    def GetString(self):
        return self.text

    def Veto(self):
        self.vetoed = True

    def Skip(self):
        self.skipped = True


def _col_index(memedit, name):
    for i, col_def in enumerate(memedit._col_defs):
        if col_def.name == name:
            return i
    raise KeyError(name)


def test_harness_loads_memories(memedit):
    mem = memedit.memory_for_row(1)
    assert mem.number == 1
    assert mem.freq == 146000000
    # A copy: changing it does not touch the grid's memory
    mem.name = 'COPY'
    assert memedit.memory_for_row(1).name != 'COPY'
    assert memedit.column(_col_index(memedit, 'name')).name == 'name'


def test_single_edit_unchanged(memedit):
    # Row 0: memory 1 of the image fails validation (TX 0.00165 MHz)
    name_col = memedit._col_def_by_name('name')
    expected = memedit.apply_cell_value(memedit.memory_for_row(0),
                                        name_col, 'Rpt1')

    event = FakeEvent(0, _col_index(memedit, 'name'), 'Rpt1')
    memedit._memory_edited(event)

    assert not event.vetoed
    assert not event.skipped
    stored = memedit._radio.get_memory(0)
    assert stored.name == expected.name == memedit._radio.filter_name('Rpt1')
    assert memedit.memory_for_row(0).name == expected.name
    assert memedit._undo_queue[0].name == 'Manual edit of memory 0'


def test_single_edit_invalid_still_vetoed(memedit, monkeypatch):
    monkeypatch.setattr(memedit, '_resolve_duplex', lambda mem: False)
    event = FakeEvent(1, _col_index(memedit, 'duplex'), '-')
    memedit._memory_edited(event)
    assert event.vetoed
    assert memedit._radio.get_memory(1).duplex == 'split'
    assert not memedit._undo_queue


def test_noninteractive_duplex_uses_band_offset(memedit):
    mem = memedit.memory_for_row(1)
    mem.freq = 145600000
    out = memedit.apply_cell_value(mem, memedit._col_def_by_name('duplex'),
                                   '-', interactive=False)
    assert out.duplex == '-' and out.offset == 600000


def test_noninteractive_duplex_keeps_offset_in_use(memedit):
    mem = memedit.memory_for_row(1)
    mem.freq = 145600000
    mem.duplex = '+'
    mem.offset = 7600000
    out = memedit.apply_cell_value(mem, memedit._col_def_by_name('duplex'),
                                   '-', interactive=False)
    assert out.duplex == '-' and out.offset == 7600000


def test_noninteractive_never_opens_dialogs(memedit, monkeypatch):
    def fail(*a, **k):
        raise AssertionError('interactive resolution used')
    for name in ('_resolve_duplex', '_resolve_offset', '_resolve_cross_mode',
                 '_resolve_tmode_cross'):
        monkeypatch.setattr(memedit, name, fail)

    apply = memedit.apply_cell_value
    col = memedit._col_def_by_name

    mem = memedit.memory_for_row(1)
    mem.freq = 145600000
    mem = apply(mem, col('duplex'), '-', interactive=False)
    assert mem.duplex == '-'

    mem = memedit.memory_for_row(0)
    mem.freq = 145600000
    mem = apply(mem, col('offset'), '0.600000', interactive=False)
    assert mem.duplex == '-' and mem.offset == 600000

    # 146.000 has no repeater shift in IARU R1: nothing to pick duplex from
    mem = memedit.memory_for_row(0)
    with pytest.raises(cellops.CellRejected) as e:
        apply(mem, col('offset'), '0.600000', interactive=False)
    assert str(e.value) == 'Needs a choice the bulk edit cannot make'

    mem = memedit.memory_for_row(0)
    with pytest.raises(cellops.CellRejected) as e:
        apply(mem, col('tmode'), 'Cross', interactive=False)
    assert str(e.value) == 'Needs a choice the bulk edit cannot make'

    mem = memedit.memory_for_row(0)
    with pytest.raises(cellops.CellRejected):
        apply(mem, col('cross_mode'), 'Tone->DTCS', interactive=False)


def test_noninteractive_bad_text_rejected(memedit):
    mem = memedit.memory_for_row(1)
    with pytest.raises(cellops.CellRejected):
        memedit.apply_cell_value(mem, memedit._col_def_by_name('freq'),
                                 'abc', interactive=False)
    with pytest.raises(cellops.CellRejected):
        memedit.apply_cell_value(mem, memedit._col_def_by_name('mode'),
                                 'XYZ', interactive=False)


def test_power_in_watts_picks_closest_level(memedit):
    mem = memedit.memory_for_row(1)
    out = memedit.apply_cell_value(mem, memedit._col_def_by_name('power'),
                                   '4.5W', interactive=False)
    assert str(out.power) == 'High'          # UV-5R: High 4 W, Low 1 W


def test_power_levels_by_label_and_decimal_comma(memedit):
    power = memedit._col_def_by_name('power')
    out = memedit.apply_cell_value(memedit.memory_for_row(1), power, 'Low',
                                   interactive=False)
    assert str(out.power) == 'Low'
    out = memedit.apply_cell_value(memedit.memory_for_row(1), power, '1,2',
                                   interactive=False)
    assert str(out.power) == 'Low'
    with pytest.raises(cellops.CellRejected):
        memedit.apply_cell_value(memedit.memory_for_row(1), power, 'Max',
                                 interactive=False)


def test_tone_column_sets_tmode(memedit):
    out = memedit.apply_cell_value(memedit.memory_for_row(1),
                                   memedit._col_def_by_name('rtone'), '100.0',
                                   interactive=False)
    assert out.rtone == 100.0 and out.tmode == 'Tone'


def test_protocol_for_cellops(memedit):
    col = _col_index(memedit, 'name')
    result = cellops.apply_edits(memedit, [cellops.CellEdit(0, col, 'Abc'),
                                           cellops.CellEdit(1, col, 'Def'),
                                           cellops.CellEdit(999, col, 'X')])
    # Row 1 is dropped: memory 1 of the image fails validation
    assert [m.number for m in result.changed] == [0]
    assert result.changed[0].name == memedit._radio.filter_name('Abc')
    assert [p[0] for p in result.problems] == ['1', '999 name']


def test_validate(memedit):
    mem = memedit.memory_for_row(0)
    assert memedit.validate(mem) == ([], [])
    assert memedit.validate(memedit.memory_for_row(1))[1]
    mem.freq = 30000000
    warnings, errors = memedit.validate(mem)
    assert errors
