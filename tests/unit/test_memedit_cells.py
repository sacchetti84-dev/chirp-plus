"""Cell edits on a real ChirpMemEdit (real wx, hidden frame).

Shared harness for the spreadsheet-like grid: the `memedit` fixture
gives a ChirpMemEdit loaded with the UV-5R test image.
"""

import builtins
import os
import sys
import tempfile
import time
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

from chirp import chirp_common  # noqa: E402
from chirp import directory  # noqa: E402
from chirp import settings  # noqa: E402
from chirp.wxui import memedit as memedit_mod  # noqa: E402
from chirp.wxui import radiothread  # noqa: E402
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
    monkeypatch.setattr(wx, 'MessageDialog', fail)
    monkeypatch.setattr(wx, 'ProgressDialog', fail)
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


def _with_integer_extra(mem, mutable=True):
    """`mem` with its own extra: an integer setting 0-10, now 5."""
    value = settings.RadioSettingValueInteger(0, 10, 5)
    value.set_mutable(mutable)
    mem.extra = settings.RadioSettingGroup(
        'extra', 'extra', settings.RadioSetting('volume', 'Volume', value))
    return mem


def test_noninteractive_bad_extra_value_rejected(memedit):
    mem = _with_integer_extra(memedit.memory_for_row(1))
    col = memedit_mod.get_column_for_extra(memedit._radio,
                                           mem.extra['volume'])
    assert col.name == 'extra.volume'
    for text in ('abc', '42'):
        with pytest.raises(cellops.CellRejected):
            memedit.apply_cell_value(mem, col, text, interactive=False)
    mem = _with_integer_extra(memedit.memory_for_row(1), mutable=False)
    with pytest.raises(cellops.CellRejected):
        memedit.apply_cell_value(mem, col, '7', interactive=False)
    mem = _with_integer_extra(memedit.memory_for_row(1))
    out = memedit.apply_cell_value(mem, col, '7', interactive=False)
    assert int(out.extra['volume'].value) == 7


def test_settings_error_in_a_cell_does_not_stop_bulk_edit(memedit,
                                                          monkeypatch):
    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _seeded(memedit, {1: 'A', 2: 'B'})
    name_col = memedit._col_def_by_name('name')
    digest = name_col.digest_value

    def picky(mem, value):
        if value == 'BAD':
            raise settings.InvalidValueError('Not for this radio')
        return digest(mem, value)
    monkeypatch.setattr(name_col, 'digest_value', picky)
    name = _col_index(memedit, 'name')
    comment = _col_index(memedit, 'comment')
    result = memedit.bulk_edit('Test', [cellops.CellEdit(1, name, 'BAD'),
                                        cellops.CellEdit(1, comment, 'c1'),
                                        cellops.CellEdit(2, name, 'OK')])
    assert [m.number for m in result.changed] == [1, 2]
    assert memedit._radio.get_memory(1).name == 'A'
    assert memedit._radio.get_memory(2).name == 'OK'
    assert result.problems == [('1 name', 'Not for this radio')]
    caption, message, extended = dialogs.shown[0]
    assert extended == '[1 name]: Not for this radio'


def test_cell_commands_show_unexpected_errors(memedit, monkeypatch):
    shown = []
    monkeypatch.setattr(common.error_proof, 'show_error',
                        lambda *a, **k: shown.append(a))

    def broken(editor, edits):
        raise RuntimeError('boom')
    monkeypatch.setattr(cellops, 'apply_edits', broken)
    _seeded(memedit, {1: 'A', 2: 'B'})
    _select(memedit, 1, 2, 'name')
    memedit.fill_down()
    memedit.clear_cells()
    memedit.fill_to(4)
    assert len(shown) == 3
    _menu(memedit, monkeypatch, 1, 'name', click='Fill down')
    assert len(shown) == 4
    assert _names(memedit, [1, 2]) == ['A', 'B']


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


# Cell selection, bulk edits and fill down

def _seed(radio, names):
    """Store valid memories {number: name} straight in the radio."""
    for number, name in names.items():
        mem = chirp_common.Memory(number=number)
        mem.freq = 145500000 + number * 25000
        mem.name = name
        mem.mode = 'FM'
        mem.power = radio.get_features().valid_power_levels[0]
        assert radio.validate_memory(mem) == []
        radio.set_memory(mem)


def _seeded(memedit, names):
    _seed(memedit._radio, names)
    memedit.refresh()
    wx.SafeYield()


def _set_tone(memedit, number, tone):
    mem = memedit._radio.get_memory(number)
    mem.tmode = 'Tone'
    mem.rtone = tone
    memedit._radio.set_memory(mem)
    memedit.refresh()


def _select(memedit, top, bottom, name):
    col = _col_index(memedit, name)
    memedit._grid.ClearSelection()
    memedit._grid.SelectBlock(top, col, bottom, col)


def _tones(memedit, numbers):
    return [(memedit._radio.get_memory(n).tmode,
             memedit._radio.get_memory(n).rtone) for n in numbers]


class Dialogs:
    """Stands in for wx.MessageDialog and records what it was told."""

    def __init__(self, answer=wx.ID_OK):
        self.shown = []
        self.answer = answer

    def __call__(self, parent, message, caption='', style=0, **k):
        dialogs = self

        class Dialog:
            def SetExtendedMessage(self, text):
                self.extended = text

            def ShowModal(self):
                dialogs.shown.append((caption, message,
                                      getattr(self, 'extended', '')))
                return dialogs.answer

            def Destroy(self):
                pass

        return Dialog()


def test_grid_selects_cells(memedit):
    assert (memedit._grid.GetSelectionMode() ==
            wx.grid.Grid.GridSelectCells)
    # Dragging over cells selects them; channels drag from the row number
    assert not memedit._grid.CanDragCell()


def test_selected_cells_skip_hidden_rows_and_columns(memedit):
    hidden = [c for c in range(memedit._grid.GetNumberCols())
              if not memedit._grid.IsColShown(c)]
    assert hidden
    memedit._grid.HideRow(2)
    memedit._grid.SelectBlock(1, 0, 3, memedit._grid.GetNumberCols() - 1)
    cells = memedit.selected_cells()
    assert {r for r, c in cells} == {1, 3}
    assert not {c for r, c in cells} & set(hidden)
    assert cells == sorted(cells)
    assert 2 not in memedit.visible_rows()
    assert memedit.visible_rows()[:3] == [0, 1, 3]


def test_whole_row_selection_still_works(memedit):
    memedit._grid.SelectRow(2)
    assert memedit.get_selected_rows_safe() == [2]


def test_rectangle_over_all_visible_columns_is_whole_rows(memedit):
    shown = [c for c in range(memedit._grid.GetNumberCols())
             if memedit._grid.IsColShown(c)]
    memedit._grid.SelectBlock(3, shown[0], 4, shown[-1])
    assert memedit.get_selected_rows_safe() == [3, 4]


def test_cell_selection_is_not_whole_rows(memedit):
    memedit._grid.SetGridCursor(6, 0)
    _select(memedit, 2, 4, 'name')
    assert memedit.get_selected_rows_safe() == [6]


class FakeMouse:
    def __init__(self, grid, row, down, shift=False):
        rect = grid.CellToRect(row, 0)
        self.x, self.y = 5, rect.GetY() + rect.GetHeight() // 2
        self.down = down
        self.shift = shift

    def CmdDown(self):
        return False

    ControlDown = CmdDown

    def ShiftDown(self):
        return self.shift

    def LeftDown(self):
        return self.down

    def GetX(self):
        return self.x

    def GetY(self):
        return self.y


def test_row_number_shift_click_selects_whole_rows(memedit):
    grid = memedit._grid
    memedit._row_click(FakeMouse(grid, 1, True))
    memedit._row_click(FakeMouse(grid, 1, False))
    assert list(grid.GetSelectedRows()) == [1]
    memedit._row_click(FakeMouse(grid, 3, True, shift=True))
    memedit._row_click(FakeMouse(grid, 3, False, shift=True))
    assert list(grid.GetSelectedRows()) == [1, 2, 3]
    assert memedit.get_selected_rows_safe() == [1, 2, 3]


def test_find_starts_after_clicked_cell(memedit):
    # TMOOK1-4 are memories 59-62 of the image; a click only moves the
    # cursor in cell mode, and Find goes on from there
    memedit._grid.SetGridCursor(60, _col_index(memedit, 'name'))
    assert memedit.selected_rows() == []
    assert memedit.cb_find('TMOOK')
    assert memedit._grid.GetGridCursorRow() == 61


def _rectangle_without_last_column(memedit, top, bottom):
    grid = memedit._grid
    grid.HideCol(grid.GetNumberCols() - 1)
    shown = [c for c in range(grid.GetNumberCols()) if grid.IsColShown(c)]
    assert shown[-1] < grid.GetNumberCols() - 1
    grid.SelectBlock(top, shown[0], bottom, shown[-1])
    # wx itself only counts rectangles from column 0 to the last one
    assert list(grid.GetSelectedRows()) == []


def _menu_labels(menu):
    labels = []
    for item in menu.GetMenuItems():
        labels.append(item.GetItemLabelText())
        if item.GetSubMenu():
            labels.extend(_menu_labels(item.GetSubMenu()))
    return labels


def test_row_commands_share_whole_row_rule(memedit, monkeypatch, tmp_path):
    _rectangle_without_last_column(memedit, 59, 61)
    assert memedit.get_selected_rows_safe() == [59, 60, 61]
    assert memedit.selected_rows() == [59, 60, 61]

    # Right-click menu (Delete, Sort, Properties...); the app installs
    # ngettext() as a builtin at startup
    monkeypatch.setattr(builtins, 'ngettext',
                        lambda one, many, n: one if n == 1 else many,
                        raising=False)
    shown = []
    monkeypatch.setattr(memedit, 'PopupMenu',
                        lambda menu: shown.extend(_menu_labels(menu)))
    memedit._memory_rclick(FakeEvent(60, 2, ''))
    assert '3 Memories' in shown
    assert 'Sort 3 memories' in shown

    # Print
    assert ([m.number for m in memedit.get_selected_memories()] ==
            [59, 60, 61])

    # Export
    out = tmp_path / 'out.csv'
    memedit._export_to_file(str(out))
    text = out.read_text()
    assert [n for n in ('TMOOK1', 'TMOOK2', 'TMOOK3', 'TMOOK4')
            if n in text] == ['TMOOK1', 'TMOOK2', 'TMOOK3']

    # Undo restores the same rows
    with memedit.undo_context('Nothing') as ctx:
        pass
    assert ctx._pre_selection == [59, 60, 61]


def test_print_and_export_without_rows_mean_all(memedit, tmp_path):
    _select(memedit, 59, 61, 'name')
    assert memedit.selected_rows() == []
    assert (len(memedit.get_selected_memories()) ==
            memedit._grid.GetNumberRows())
    out = tmp_path / 'out.csv'
    memedit._export_to_file(str(out))
    assert 'TMOOK4' in out.read_text() and 'VTAC13' in out.read_text()


def test_selection_without_selected_blocks(memedit, monkeypatch):
    # wxPython < 4.1 has no Grid.GetSelectedBlocks()
    def fail(*a):
        raise AssertionError('GetSelectedBlocks() used')
    monkeypatch.setattr(memedit_mod, 'HAS_SELECTED_BLOCKS', False)
    monkeypatch.setattr(memedit_mod.ChirpMemoryGrid, 'GetSelectedBlocks',
                        fail, raising=False)
    grid = memedit._grid
    grid.SetGridCursor(6, 0)
    assert memedit.get_selected_rows_safe() == [6]
    grid.SelectRow(2)
    assert memedit.get_selected_rows_safe() == [2]
    assert memedit.selected_rows() == [2]
    _select(memedit, 3, 4, 'name')
    assert memedit.get_selected_rows_safe() == [6]
    assert memedit.selected_cells() == [(3, _col_index(memedit, 'name')),
                                        (4, _col_index(memedit, 'name'))]


def test_column_header_click_does_not_select_column(memedit):
    # Sorting stays (EVT_GRID_COL_SORT); the default handler that would
    # select the whole column in cell mode is not reached
    header = FakeEvent(-1, 2, '')
    memedit._label_click(header)
    assert not header.skipped
    corner = FakeEvent(-1, -1, '')
    memedit._label_click(corner)
    assert corner.skipped


def test_fill_down_ctcss(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    _set_tone(memedit, 1, 100.0)
    _select(memedit, 1, 5, 'rtone')
    memedit.fill_down()
    assert _tones(memedit, range(1, 6)) == [('Tone', 100.0)] * 5
    assert memedit.memory_for_row(5).rtone == 100.0
    rtone = _col_index(memedit, 'rtone')
    assert (memedit._grid.GetCellValue(5, rtone) ==
            memedit._grid.GetCellValue(1, rtone))
    assert _tones(memedit, [0, 6]) == [('', 88.5), ('', 88.5)]


def test_fill_down_is_one_undo(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    _set_tone(memedit, 1, 100.0)
    _select(memedit, 1, 5, 'rtone')
    queued = len(memedit._undo_queue)
    memedit.fill_down()
    assert len(memedit._undo_queue) == queued + 1
    assert memedit._undo_queue[0].name == 'Fill 4 cells'
    memedit._undo(None)
    assert _tones(memedit, range(2, 6)) == [('', 88.5)] * 4
    assert _tones(memedit, [1]) == [('Tone', 100.0)]


def test_fill_down_skips_filtered_rows(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    _set_tone(memedit, 1, 100.0)
    memedit._grid.HideRow(3)
    _select(memedit, 1, 5, 'rtone')
    memedit.fill_down()
    assert _tones(memedit, [2, 4, 5]) == [('Tone', 100.0)] * 3
    assert _tones(memedit, [3]) == [('', 88.5)]
    assert memedit._undo_queue[0].name == 'Fill 3 cells'


def test_fill_down_in_sorted_view(memedit):
    # Digits sort before the names already in the image
    _seeded(memedit, {1: '0E', 2: '0D', 3: '0C', 4: '0B', 5: '0A'})
    _set_tone(memedit, 5, 100.0)
    name_col = _col_index(memedit, 'name')
    memedit._grid.SetSortingColumn(name_col, True)
    memedit._table.sort_via(name_col, True)
    memedit.refresh()
    rows = [memedit.mem2row(n) for n in (5, 4, 3, 2, 1)]
    # Sorted by name: 0A (memory 5) on top, 0E (memory 1) at the bottom
    assert rows == [1, 2, 3, 4, 5]
    assert [memedit.row2mem(r) for r in rows] == [5, 4, 3, 2, 1]
    _select(memedit, rows[0], rows[-1], 'rtone')
    memedit.fill_down()
    assert _tones(memedit, [5, 4, 3, 2, 1]) == [('Tone', 100.0)] * 5
    for n, name in ((1, '0E'), (2, '0D'), (4, '0B')):
        assert memedit._radio.get_memory(n).name == name
    assert _tones(memedit, [0, 6]) == [('', 88.5), ('', 88.5)]


def test_undo_after_rejection_restores_only_changed(memedit, monkeypatch):
    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    # Memory 1 of the image fails validation (split to 0.00165 MHz)
    _seeded(memedit, {2: 'M2', 3: 'M3'})
    _set_tone(memedit, 0, 100.0)
    _select(memedit, 0, 3, 'rtone')
    memedit.fill_down()
    assert _tones(memedit, [2, 3]) == [('Tone', 100.0)] * 2
    assert _tones(memedit, [1]) == [('', 88.5)]
    assert memedit._radio.get_memory(1).duplex == 'split'

    assert len(dialogs.shown) == 1
    caption, message, extended = dialogs.shown[0]
    assert caption == 'Some cells were not changed'
    assert extended.startswith('[1]: ')
    assert 'Tx freq' in extended

    undo = memedit._undo_queue[0]
    assert undo.name == 'Fill 3 cells'
    assert sorted(m.number for m in undo._mem_before) == [2, 3]
    memedit._undo(None)
    assert _tones(memedit, [2, 3]) == [('', 88.5)] * 2
    assert _tones(memedit, [0]) == [('Tone', 100.0)]
    assert memedit._radio.get_memory(1).duplex == 'split'


def test_bulk_edit_summary_is_capped(memedit, monkeypatch):
    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _seeded(memedit, {n: 'M%i' % n for n in range(2, 25)})
    col = _col_index(memedit, 'freq')
    edits = [cellops.CellEdit(row, col, None) for row in range(0, 25)]
    result = memedit.bulk_edit('Clear', edits)
    assert not result.changed
    assert len(result.problems) == 25
    # Nothing changed, nothing to undo
    assert not memedit._undo_queue
    assert len(dialogs.shown) == 1
    caption, message, extended = dialogs.shown[0]
    lines = extended.split('\n')
    assert len(lines) == 20
    assert lines[-1] == '...and 6 more'


def test_bulk_edit_writes_only_visible_rows(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 4)})
    memedit._grid.HideRow(2)
    col = _col_index(memedit, 'name')
    result = memedit.bulk_edit('Names', [cellops.CellEdit(r, col, 'X')
                                         for r in (1, 2, 3)])
    assert [m.number for m in result.changed] == [1, 3]
    assert memedit._radio.get_memory(2).name == 'M2'
    assert memedit._radio.get_memory(3).name == 'X'
    assert memedit._undo_queue[0].name == 'Names'


class FakeProgress:
    """Stands in for wx.ProgressDialog; aborts at `abort_at` if set."""
    made = []
    abort_at = None

    def __init__(self, title, message, maximum=100, parent=None, style=0):
        self.maximum = maximum
        self.style = style
        self.values = []
        self.destroyed = False
        FakeProgress.made.append(self)

    def Update(self, value, newmsg=''):
        self.values.append(value)
        abort = self.abort_at is not None and value >= self.abort_at
        return (not abort, False)

    def Destroy(self):
        self.destroyed = True


def _pump(until, timeout=20):
    deadline = time.monotonic() + timeout
    while not until():
        assert time.monotonic() < deadline, 'Timed out waiting'
        wx.SafeYield()
        time.sleep(0.005)


@pytest.fixture
def live_memedit(wx_app):
    directory.import_drivers()
    radio = directory.get_radio_by_image(IMAGE)
    _seed(radio, {n: 'M%i' % n for n in range(1, 26)})
    mem = radio.get_memory(1)
    mem.tmode = 'Tone'
    mem.rtone = 100.0
    radio.set_memory(mem)
    frame = wx.Frame(None)
    _make_menubar(frame)
    editor = memedit_mod.ChirpLiveMemEdit(radio, frame)
    thread = radiothread.RadioThread(radio)
    thread.start()
    editor.set_radio_thread(thread)
    editor.refresh()
    rows = editor._grid.GetNumberRows()
    try:
        _pump(lambda: len(editor._memory_cache) == rows and
              not editor._jobs)
        yield editor
    finally:
        thread.end()
        thread.join(5)
        frame.Destroy()
        wx.SafeYield()


def test_live_bulk_edit_shows_progress(live_memedit, monkeypatch):
    monkeypatch.setattr(wx, 'ProgressDialog', FakeProgress)
    monkeypatch.setattr(FakeProgress, 'made', [])
    _select(live_memedit, 1, 25, 'rtone')
    live_memedit.fill_down()
    progress, = FakeProgress.made
    assert progress.style & wx.PD_CAN_ABORT
    assert progress.maximum == 24
    assert progress.values[-1] == 24
    assert progress.destroyed
    _pump(lambda: not live_memedit._jobs)
    assert _tones(live_memedit, range(1, 26)) == [('Tone', 100.0)] * 25


def test_live_bulk_edit_abort_keeps_what_was_written(live_memedit,
                                                     monkeypatch):
    monkeypatch.setattr(wx, 'ProgressDialog', FakeProgress)
    monkeypatch.setattr(FakeProgress, 'made', [])
    monkeypatch.setattr(FakeProgress, 'abort_at', 5)
    _select(live_memedit, 1, 25, 'rtone')
    live_memedit.fill_down()
    _pump(lambda: not live_memedit._jobs)
    assert _tones(live_memedit, range(1, 7)) == [('Tone', 100.0)] * 6
    assert _tones(live_memedit, range(7, 26)) == [('', 88.5)] * 19
    undo = live_memedit._undo_queue[0]
    assert undo.name == 'Fill 24 cells'
    assert sorted(m.number for m in undo._mem_before) == [2, 3, 4, 5, 6]


def test_small_live_bulk_edit_has_no_progress(live_memedit):
    # wx.ProgressDialog fails the test if it is opened
    _select(live_memedit, 1, 5, 'rtone')
    live_memedit.fill_down()
    _pump(lambda: not live_memedit._jobs)
    assert _tones(live_memedit, range(1, 6)) == [('Tone', 100.0)] * 5


# Copy, paste, cut and clear cells

def _clipboard_out(memedit, monkeypatch):
    """Record what cb_copy() puts on the clipboard."""
    copied = []
    monkeypatch.setattr(memedit, 'cb_copy_data', copied.append)
    return copied


def _clipboard_in(monkeypatch, data):
    """Make cb_paste() find `data` on the clipboard."""
    monkeypatch.setattr(common.ChirpEditor, 'cb_paste', lambda self: data)


def _cursor(memedit, row, name):
    memedit._grid.ClearSelection()
    memedit._grid.SetGridCursor(row, _col_index(memedit, name))


def _names(memedit, numbers):
    return [memedit._radio.get_memory(n).name for n in numbers]


def _formats(data):
    return [f.GetType() for f in data.GetAllFormats()]


def test_copy_cells_is_tsv_of_shown_text(memedit, monkeypatch):
    _seeded(memedit, {1: 'A', 2: 'C'})
    grid = memedit._grid
    grid.ClearSelection()
    grid.SelectBlock(1, _col_index(memedit, 'freq'),
                     2, _col_index(memedit, 'name'))
    assert memedit.copy_cells_text() == '145.525000\tA\n145.550000\tC\n'

    # Text only: no CHIRP memories that would paste as whole channels
    copied = _clipboard_out(memedit, monkeypatch)
    memedit.cb_copy()
    data, = copied
    assert _formats(data) == [wx.DF_UNICODETEXT]
    assert data.GetText() == '145.525000\tA\n145.550000\tC\n'
    assert not memedit._undo_queue


def test_copy_cells_quotes_tabs_and_quotes(memedit, monkeypatch):
    monkeypatch.setattr(memedit._grid, 'GetCellValue',
                        lambda row, col: {0: 'a\tb', 1: 'say "hi"'}[row])
    monkeypatch.setattr(memedit, 'selected_cells', lambda: [(0, 1), (1, 1)])
    text = memedit.copy_cells_text()
    assert text == '"a\tb"\n"say ""hi"""\n'
    from chirp import grid_fill
    assert grid_fill.parse_table(text) == [['a\tb'], ['say "hi"']]


def test_paste_table_from_excel(memedit, monkeypatch):
    # Memories 2-4 of the image are empty; Excel ends lines with \r\n
    _cursor(memedit, 2, 'freq')
    _clipboard_in(monkeypatch,
                  wx.TextDataObject('145.600000\tRPT1\r\n145,625\tRPT2\r\n'))
    memedit.cb_paste()
    mem2, mem3 = (memedit._radio.get_memory(n) for n in (2, 3))
    assert (mem2.freq, mem2.name) == (145600000, 'RPT1')
    assert (mem3.freq, mem3.name) == (145625000, 'RPT2')
    assert memedit._radio.get_memory(4).empty
    assert len(memedit._undo_queue) == 1
    assert memedit._undo_queue[0].name == 'Paste 4 cells'
    memedit._undo(None)
    assert memedit._radio.get_memory(2).empty
    assert memedit._radio.get_memory(3).empty


def test_paste_explicit_offset_wins_over_band(memedit):
    # IARU R1: the band plan alone would give 145.600 a -600 kHz shift
    _cursor(memedit, 2, 'freq')
    row = ['145.600000', 'RPT'] + [''] * 6 + ['-', '7.600000']
    memedit.paste_table('\t'.join(row) + '\n')
    mem = memedit._radio.get_memory(2)
    assert (mem.freq, mem.duplex, mem.offset) == (145600000, '-', 7600000)


def _seed_duplex(memedit, rows):
    """Store {number: (freq, duplex, offset)} in the radio and refresh."""
    radio = memedit._radio
    for number, (freq, duplex, offset) in rows.items():
        mem = chirp_common.Memory(number=number)
        mem.freq = freq
        mem.duplex = duplex
        mem.offset = offset
        mem.name = 'M%i' % number
        mem.mode = 'FM'
        mem.power = radio.get_features().valid_power_levels[0]
        assert radio.validate_memory(mem) == []
        radio.set_memory(mem)
    memedit.refresh()
    wx.SafeYield()


def _duplexes(memedit, numbers):
    return [(memedit._radio.get_memory(n).duplex,
             memedit._radio.get_memory(n).offset) for n in numbers]


def test_paste_duplex_off_from_excel_keeps_tx_off(memedit, monkeypatch):
    # The Duplex and Offset columns of a CHIRP CSV opened in Excel. In
    # IARU R1 145.600 has a -600 kHz shift, the marine 156.800 none:
    # neither may turn transmit back on
    dialogs = Dialogs(answer=wx.ID_YES)
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _seed_duplex(memedit, {1: (145600000, 'off', 0),
                           2: (156800000, 'off', 0)})
    _cursor(memedit, 1, 'duplex')
    result = memedit.paste_table('off\t0.000000\r\noff\t0.000000\r\n')
    assert result.problems == []
    assert _duplexes(memedit, [1, 2]) == [('off', 0), ('off', 0)]
    assert [d[0] for d in dialogs.shown] == ['Overwrite cells?']


def test_paste_duplex_off_with_offset_on_repeater(memedit, monkeypatch):
    monkeypatch.setattr(wx, 'MessageDialog', Dialogs(answer=wx.ID_YES))
    _seed_duplex(memedit, {1: (145600000, '-', 600000)})
    _cursor(memedit, 1, 'duplex')
    result = memedit.paste_table('off\t0.600000\n')
    assert result.problems == []
    mem, = result.changed
    assert (mem.duplex, mem.offset) == ('off', 600000)
    # The UV-5R keeps no offset with transmit off
    assert memedit._radio.get_memory(1).duplex == 'off'


def test_noninteractive_offset_on_simplex(memedit):
    apply = memedit.apply_cell_value
    offset = memedit._col_def_by_name('offset')
    # A zero offset on simplex is simplex
    mem = memedit.memory_for_row(0)
    mem.freq = 156800000
    mem.duplex = ''
    out = apply(mem, offset, '0.000000', interactive=False)
    assert (out.duplex, out.offset) == ('', 0)
    # 'off' stays off whatever the offset
    mem = memedit.memory_for_row(0)
    mem.freq = 145600000
    mem.duplex = 'off'
    out = apply(mem, offset, '0.600000', interactive=False)
    assert (out.duplex, out.offset) == ('off', 600000)


def test_rejected_cell_in_saved_row_changes_nothing(memedit, monkeypatch):
    # 146.000 has no shift in IARU R1: the offset cannot be used, the
    # name in the same row is still stored, the offset is not
    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _seed_duplex(memedit, {1: (146000000, '', 0)})
    edits = [cellops.CellEdit(1, _col_index(memedit, 'name'), 'NEW'),
             cellops.CellEdit(1, _col_index(memedit, 'offset'), '0.600000')]
    result = memedit.bulk_edit('Test', edits)
    assert len(result.problems) == 1
    # What is stored, before the radio has its say
    mem, = result.changed
    assert (mem.name, mem.duplex, mem.offset) == ('NEW', '', 0)
    mem = memedit._radio.get_memory(1)
    assert (mem.name, mem.duplex, mem.offset) == ('NEW', '', 0)


def test_paste_header_row_skipped(memedit):
    _cursor(memedit, 2, 'freq')
    memedit.paste_table('Frequency\tName\n145.600000\tHDR\n')
    mem = memedit._radio.get_memory(2)
    assert (mem.freq, mem.name) == (145600000, 'HDR')
    assert memedit._radio.get_memory(3).empty


def test_paste_single_label_is_a_value(memedit, monkeypatch):
    # One value alone is never a header: 'Mode' is a fine name
    _seeded(memedit, {1: 'A'})
    monkeypatch.setattr(wx, 'MessageDialog', Dialogs())
    _cursor(memedit, 1, 'name')
    memedit.paste_table('Mode')
    assert _names(memedit, [1]) == [memedit._radio.filter_name('Mode')]


def test_paste_overflow_reported(memedit, monkeypatch):
    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    last = memedit._grid.GetNumberRows() - 1
    comment = _col_index(memedit, 'comment')
    assert comment == max(c for c in range(memedit._grid.GetNumberCols())
                          if memedit._grid.IsColShown(c))
    assert memedit._grid.GetCellValue(last, comment) == ''
    _cursor(memedit, last, 'comment')
    # 'y' is past the last column, the second row past the last memory
    result = memedit.paste_table('x\ty\nz\tw\n')
    assert ('', '3 values did not fit') in result.problems
    assert len(dialogs.shown) == 1
    caption, message, extended = dialogs.shown[0]
    assert caption == 'Some cells were not changed'
    assert '3 values did not fit' in extended.split('\n')


def test_paste_skips_hidden_columns(memedit, monkeypatch):
    # Copies leave hidden columns out, so pastes do too
    monkeypatch.setattr(wx, 'MessageDialog', Dialogs())
    grid = memedit._grid
    step = _col_index(memedit, 'tuning_step')
    assert not grid.IsColShown(step)
    _seeded(memedit, {1: 'A'})
    _cursor(memedit, 1, 'mode')
    memedit.paste_table('NFM\tS\n')
    mem = memedit._radio.get_memory(1)
    assert (mem.mode, mem.skip) == ('NFM', 'S')


def test_paste_one_value_into_selection(memedit, monkeypatch):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 5)})
    dialogs = Dialogs(answer=wx.ID_NO)
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _select(memedit, 1, 4, 'name')
    assert memedit.paste_table('X\n') is None
    assert _names(memedit, range(1, 5)) == ['M1', 'M2', 'M3', 'M4']
    assert [d[0] for d in dialogs.shown] == ['Overwrite cells?']
    assert not memedit._undo_queue

    dialogs.answer = wx.ID_YES
    result = memedit.paste_table('X\n')
    assert [m.number for m in result.changed] == [1, 2, 3, 4]
    assert _names(memedit, range(1, 5)) == ['X'] * 4
    assert memedit._undo_queue[0].name == 'Paste 4 cells'
    assert [d[0] for d in dialogs.shown] == ['Overwrite cells?'] * 2


def test_paste_into_empty_cells_does_not_ask(memedit):
    # Seeded memories have no comment; no_dialogs fails on any dialog
    _seeded(memedit, {1: 'A', 2: 'B'})
    _cursor(memedit, 1, 'comment')
    memedit.paste_table('c1\nc2\n')
    assert ([memedit._radio.get_memory(n).name for n in (1, 2)] ==
            ['A', 'B'])


def test_paste_malformed_table_does_not_crash(memedit, monkeypatch):
    from chirp import grid_fill

    def broken(text):
        raise grid_fill.csv.Error('field larger than field limit')
    monkeypatch.setattr(grid_fill, 'parse_table', broken)
    _cursor(memedit, 2, 'freq')
    memedit.paste_table('145.600000\t"RPT\n')
    mem = memedit._radio.get_memory(2)
    assert (mem.freq, mem.name) == (145600000, '"RPT')


def test_clear_cells(memedit, monkeypatch):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 4)})
    # Memory 4 is empty: its cells are left alone
    assert memedit._radio.get_memory(4).empty
    _select(memedit, 1, 4, 'name')
    memedit.cb_delete()
    assert _names(memedit, range(1, 4)) == ['', '', '']
    assert memedit._radio.get_memory(4).empty
    assert memedit._undo_queue[0].name == 'Clear 3 cells'

    dialogs = Dialogs()
    monkeypatch.setattr(wx, 'MessageDialog', dialogs)
    _select(memedit, 1, 2, 'freq')
    result = memedit.clear_cells()
    assert not result.changed
    assert [p[1] for p in result.problems] == ['freq has no empty value'] * 2
    assert memedit._radio.get_memory(1).freq == 145525000
    assert len(dialogs.shown) == 1
    memedit._undo(None)
    assert _names(memedit, range(1, 4)) == ['M1', 'M2', 'M3']


def test_cut_cells_is_copy_and_clear(memedit, monkeypatch):
    _seeded(memedit, {1: 'A', 2: 'B'})
    copied = _clipboard_out(memedit, monkeypatch)
    _select(memedit, 1, 2, 'name')
    memedit.cb_copy(cut=True)
    data, = copied
    assert data.GetText() == 'A\nB\n'
    assert _names(memedit, [1, 2]) == ['', '']
    assert not memedit._radio.get_memory(1).empty
    assert memedit._undo_queue[0].name == 'Clear 2 cells'


def test_row_copy_paste_unchanged(memedit, monkeypatch):
    copied = _clipboard_out(memedit, monkeypatch)
    memedit._grid.SelectRow(59)
    memedit.cb_copy()
    data, = copied
    native = data.GetObject(wx.DataFormat(common.CHIRP_DATA_MEMORY))
    assert isinstance(native, wx.CustomDataObject)
    text = data.GetObject(wx.DataFormat(wx.DF_UNICODETEXT)).GetText()
    assert text.startswith('Location\t')

    # CHIRP memories go to the selected row
    _clipboard_in(monkeypatch, native)
    memedit._grid.SelectRow(2)
    memedit.cb_paste()
    assert _names(memedit, [2]) == ['TMOOK1']
    assert memedit._undo_queue[0].name == 'Paste memories'

    # The TSV of whole rows too, with whole rows selected...
    _clipboard_in(monkeypatch, wx.TextDataObject(text))
    memedit._grid.SelectRow(3)
    memedit.cb_paste()
    assert _names(memedit, [3]) == ['TMOOK1']
    # ...or a CHIRP header with Location, from just the cursor
    _cursor(memedit, 4, 'name')
    memedit.cb_paste()
    assert _names(memedit, [4]) == ['TMOOK1']
    assert memedit._undo_queue[0].name == 'Paste memories'


def test_portable_text_paste_unchanged(memedit, monkeypatch):
    _clipboard_in(monkeypatch, wx.TextDataObject('[146.520000/+0.600]'))
    _cursor(memedit, 2, 'name')
    memedit.cb_paste()
    mem = memedit._radio.get_memory(2)
    assert (mem.freq, mem.duplex, mem.offset) == (146520000, '+', 600000)
    assert mem.name == ''


def test_row_delete_unchanged(memedit):
    _seeded(memedit, {1: 'A'})
    memedit._grid.SelectRow(1)
    memedit.cb_delete()
    assert memedit._radio.get_memory(1).empty


def test_paste_anchor_is_top_left_of_block(memedit):
    # Dragged from the bottom-right cell: the cursor stays there, the
    # table still starts at the top-left cell, as in a spreadsheet
    grid = memedit._grid
    grid.ClearSelection()
    grid.SetGridCursor(4, _col_index(memedit, 'name'))
    grid.SelectBlock(2, _col_index(memedit, 'freq'),
                     4, _col_index(memedit, 'name'))
    memedit.paste_table('145.600000\tP1\n145.625000\tP2\n')
    mem2, mem3 = (memedit._radio.get_memory(n) for n in (2, 3))
    assert (mem2.freq, mem2.name) == (145600000, 'P1')
    assert (mem3.freq, mem3.name) == (145625000, 'P2')
    assert memedit._radio.get_memory(4).empty


# Keyboard, menu and series

def _key(window, code, modifiers=wx.MOD_NONE):
    """Send a key press to `window`; True if nobody skipped it."""
    event = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    event.SetKeyCode(code)
    event.SetControlDown(bool(modifiers & wx.MOD_CONTROL))
    event.SetShiftDown(bool(modifiers & wx.MOD_SHIFT))
    event.SetEventObject(window)
    return window.GetEventHandler().ProcessEvent(event)


def test_ctrl_d_calls_fill_down(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    _set_tone(memedit, 1, 100.0)
    _select(memedit, 1, 5, 'rtone')
    _key(memedit._grid.GetGridWindow(), ord('D'), wx.MOD_CONTROL)
    assert _tones(memedit, range(1, 6)) == [('Tone', 100.0)] * 5
    assert memedit._undo_queue[0].name == 'Fill 4 cells'


def _edit(memedit, row, name, value):
    """Open the cell editor at (row, name) and type `value` in it."""
    grid = memedit._grid
    col = _col_index(memedit, name)
    grid.SetGridCursor(row, col)
    grid.EnableCellEditControl()
    assert grid.IsCellEditControlShown()
    editor = grid.GetCellEditor(row, col)
    editor.GetControl().SetValue(value)
    editor.DecRef()


def test_ctrl_enter_writes_all_selected(memedit):
    memedit.GetTopLevelParent().Show()
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 5)})
    _select(memedit, 1, 4, 'name')
    _edit(memedit, 1, 'name', 'NEW')
    # While editing, the editor gives Enter to the grid itself
    _key(memedit._grid, wx.WXK_RETURN, wx.MOD_CONTROL)
    assert not memedit._grid.IsCellEditControlShown()
    assert _names(memedit, range(1, 5)) == ['NEW'] * 4
    assert len(memedit._undo_queue) == 1
    assert memedit._undo_queue[0].name == 'Fill 4 cells'
    memedit._undo(None)
    assert _names(memedit, range(1, 5)) == ['M1', 'M2', 'M3', 'M4']


def test_ctrl_enter_in_choice_column(memedit):
    # The choice editor always reports a change when it closes: the
    # value it had must not be stored on its own first
    memedit.GetTopLevelParent().Show()
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 4)})
    _select(memedit, 1, 3, 'mode')
    _edit(memedit, 1, 'mode', 'NFM')
    assert memedit.enter_in_selection()
    assert [memedit._radio.get_memory(n).mode for n in (1, 2, 3)] == \
        ['NFM'] * 3
    assert len(memedit._undo_queue) == 1
    assert memedit._undo_queue[0].name == 'Fill 3 cells'
    # Not editing: nothing to write
    assert not memedit.enter_in_selection()


def test_delete_key_clears_cells(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 4)})
    _select(memedit, 1, 3, 'name')
    assert _key(memedit._grid.GetGridWindow(), wx.WXK_DELETE)
    assert _names(memedit, range(1, 4)) == ['', '', '']
    assert memedit._undo_queue[0].name == 'Clear 3 cells'


def test_delete_key_with_rows_unchanged(memedit):
    _seeded(memedit, {1: 'A'})
    memedit._grid.SelectRow(1)
    _key(memedit._grid.GetGridWindow(), wx.WXK_DELETE)
    assert _names(memedit, [1]) == ['A']
    assert not memedit._undo_queue


def test_series_dialog_values(wx_app):
    from chirp.wxui import seriesdialog
    d = seriesdialog.SeriesDialog(None, '431.600', 3)
    try:
        d._step.SetValue('0.025')
        assert d.values == ['431.600', '431.625', '431.650']
        assert '431.600, 431.625, 431.650' in d._preview.GetLabel()
        assert d.FindWindow(wx.ID_OK).IsEnabled()
        d._step.SetValue('abc')
        assert not d.FindWindow(wx.ID_OK).IsEnabled()
        d._start.SetValue('CH08')
        d._step.SetValue('2')
        assert d.values == ['CH08', 'CH10', 'CH12']
    finally:
        d.Destroy()


def _menu(memedit, monkeypatch, row, name, click=None):
    """Right-click (row, name): the menu labels, enabled or not.

    With `click`, that item of the menu is chosen.
    """
    items = []

    def popup(menu):
        for item in menu.GetMenuItems():
            items.append((item.GetItemLabelText(), item.IsEnabled()))
            if item.GetItemLabelText() == click:
                menu.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU,
                                                  item.GetId()))
    monkeypatch.setattr(memedit, 'PopupMenu', popup)
    monkeypatch.setattr(builtins, 'ngettext',
                        lambda one, many, n: one if n == 1 else many,
                        raising=False)
    memedit._memory_rclick(FakeEvent(row, _col_index(memedit, name), ''))
    return items


CELL_MENU = ['Copy cells', 'Paste', 'Fill down', 'Series...', 'Clear cells']


def test_cell_menu_items(memedit, monkeypatch):
    _cursor(memedit, 1, 'name')
    _select(memedit, 1, 3, 'name')
    items = _menu(memedit, monkeypatch, 2, 'name')
    assert [label for label, enabled in items] == CELL_MENU
    assert all(enabled for label, enabled in items)

    monkeypatch.setattr(memedit_mod.ChirpMemEdit, 'editable',
                        property(lambda self: False))
    items = _menu(memedit, monkeypatch, 2, 'name')
    assert [label for label, enabled in items if enabled] == ['Copy cells']

    # The cursor alone, or whole rows: the menu of today
    _cursor(memedit, 2, 'name')
    assert 'Properties' in [label for label, enabled in
                            _menu(memedit, monkeypatch, 2, 'name')]
    memedit._grid.SelectRow(2)
    assert 'Properties' in [label for label, enabled in
                            _menu(memedit, monkeypatch, 2, 'name')]


def test_cell_menu_commands(memedit, monkeypatch):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 4)})
    _select(memedit, 1, 3, 'name')
    _menu(memedit, monkeypatch, 1, 'name', click='Fill down')
    assert _names(memedit, range(1, 4)) == ['M1'] * 3
    _menu(memedit, monkeypatch, 1, 'name', click='Clear cells')
    assert _names(memedit, range(1, 4)) == [''] * 3
    copied = _clipboard_out(memedit, monkeypatch)
    _menu(memedit, monkeypatch, 1, 'name', click='Copy cells')
    assert copied[0].GetText() == '\n\n\n'


class FakeSeries:
    made = []

    def __init__(self, parent, start, count):
        self.start, self.count = start, count
        FakeSeries.made.append(self)
        from chirp import grid_fill
        self.values = grid_fill.make_series('431.600000', '0.025', count)

    def ShowModal(self):
        return wx.ID_OK

    def Destroy(self):
        pass


def test_cell_menu_series(memedit, monkeypatch):
    from chirp.wxui import seriesdialog
    monkeypatch.setattr(seriesdialog, 'SeriesDialog', FakeSeries)
    monkeypatch.setattr(FakeSeries, 'made', [])
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 5)})
    # A block of two columns: the series goes in the cursor column
    memedit._grid.ClearSelection()
    memedit._grid.SetGridCursor(1, _col_index(memedit, 'freq'))
    memedit._grid.SelectBlock(1, _col_index(memedit, 'freq'),
                              4, _col_index(memedit, 'name'))
    _menu(memedit, monkeypatch, 1, 'freq', click='Series...')
    dialog, = FakeSeries.made
    assert (dialog.start, dialog.count) == ('145.525000', 4)
    assert ([memedit._radio.get_memory(n).freq for n in range(1, 5)] ==
            [431600000, 431625000, 431650000, 431675000])
    assert _names(memedit, range(1, 5)) == ['M1', 'M2', 'M3', 'M4']
    assert memedit._undo_queue[0].name == 'Series in 4 cells'
    assert len(memedit._undo_queue) == 1


def test_right_click_outside_selection_moves_it(memedit, monkeypatch):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    name = _col_index(memedit, 'name')
    freq = _col_index(memedit, 'freq')
    # Inside the selection: it stays, and the menu is for its cells
    _select(memedit, 1, 3, 'name')
    items = _menu(memedit, monkeypatch, 2, 'name')
    assert [label for label, enabled in items] == CELL_MENU
    assert memedit.selected_cells() == [(1, name), (2, name), (3, name)]
    # Outside: the cursor moves to the clicked cell, the selection goes,
    # and the menu is the one of that memory
    items = _menu(memedit, monkeypatch, 5, 'freq')
    assert memedit.selected_cells() == []
    assert (memedit._grid.GetGridCursorRow(),
            memedit._grid.GetGridCursorCol()) == (5, freq)
    assert 'Properties' in [label for label, enabled in items]
    # Whole rows: a click in them keeps them, a click elsewhere does not
    memedit._grid.SelectRow(2)
    _menu(memedit, monkeypatch, 2, 'name')
    assert memedit.selected_rows() == [2]
    _menu(memedit, monkeypatch, 4, 'name')
    assert memedit.selected_rows() == []
    assert memedit._grid.GetGridCursorRow() == 4
    # The menu key opens the menu of the selection wherever the cursor is
    memedit._grid.SelectRow(2)
    memedit._grid.SetGridCursor(0, name)
    shown = []
    monkeypatch.setattr(memedit, 'PopupMenu',
                        lambda menu: shown.append(menu))
    memedit._show_context_menu_at_cursor()
    assert shown
    assert memedit.selected_rows() == [2]


# Fill handle

def _show(memedit):
    frame = memedit.GetTopLevelParent()
    frame.SetSize((1000, 700))
    frame.Show()
    frame.Layout()
    wx.SafeYield()


def _freqs(memedit, numbers):
    return [memedit._radio.get_memory(n).freq for n in numbers]


def _set_freqs(memedit, freqs):
    for number, freq in freqs.items():
        mem = memedit._radio.get_memory(number)
        mem.freq = freq
        memedit._radio.set_memory(mem)
    memedit.refresh()
    wx.SafeYield()


def test_fill_to_continues_frequency_series(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 7)})
    _set_freqs(memedit, {1: 146000000, 2: 146025000})
    _select(memedit, 1, 2, 'freq')
    queued = len(memedit._undo_queue)
    memedit.fill_to(5)
    assert _freqs(memedit, range(1, 7)) == [
        146000000, 146025000, 146050000, 146075000, 146100000, 145650000]
    assert _names(memedit, range(1, 6)) == ['M1', 'M2', 'M3', 'M4', 'M5']
    freq = _col_index(memedit, 'freq')
    assert memedit._grid.GetCellValue(5, freq) == '146.100000'
    assert len(memedit._undo_queue) == queued + 1
    assert memedit._undo_queue[0].name == 'Fill 3 cells'
    memedit._undo(None)
    assert _freqs(memedit, range(3, 6)) == [145575000, 145600000, 145625000]


def test_fill_to_skips_hidden_rows(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 7)})
    _set_freqs(memedit, {1: 146000000, 2: 146025000})
    memedit._grid.HideRow(4)
    _select(memedit, 1, 2, 'freq')
    memedit.fill_to(6)
    # The series goes on over the rows that are shown
    assert _freqs(memedit, [3, 5, 6]) == [146050000, 146075000, 146100000]
    assert _freqs(memedit, [4]) == [145600000]
    assert memedit._undo_queue[0].name == 'Fill 3 cells'


def test_fill_to_copies_single_value(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 6)})
    _select(memedit, 1, 1, 'name')
    memedit.fill_to(3)
    assert _names(memedit, range(1, 5)) == ['M1', 'M1', 'M1', 'M4']
    assert memedit._undo_queue[0].name == 'Fill 2 cells'
    # Nothing after the selection: nothing to do
    queued = len(memedit._undo_queue)
    memedit.fill_to(1)
    assert len(memedit._undo_queue) == queued


def _corner(memedit, row, name):
    grid = memedit._grid
    rect = grid.CellToRect(row, _col_index(memedit, name))
    return grid.CalcScrolledPosition(rect.GetRight(), rect.GetBottom())


def test_handle_follows_selection(memedit):
    _show(memedit)
    handle = memedit._fill_handle
    grid = memedit._grid
    grid.ClearSelection()
    grid.SelectBlock(1, _col_index(memedit, 'freq'),
                     3, _col_index(memedit, 'name'))
    # update() runs after the selection event
    wx.SafeYield()
    assert handle.IsShown()
    assert tuple(handle.GetSize()) == (7, 7)
    assert handle.GetParent() is grid.GetGridWindow()
    assert handle.GetRect().Contains(_corner(memedit, 3, 'name'))

    _select(memedit, 4, 6, 'freq')
    wx.SafeYield()
    assert handle.IsShown()
    assert handle.GetRect().Contains(_corner(memedit, 6, 'freq'))

    # Cursor alone: the handle is at the cursor cell, as in spreadsheets
    _cursor(memedit, 2, 'freq')
    wx.SafeYield()
    assert handle.IsShown()
    assert handle.GetRect().Contains(_corner(memedit, 2, 'freq'))
    # Whole rows: no handle
    grid.SelectRow(2)
    wx.SafeYield()
    assert not handle.IsShown()

    # Corner scrolled out of view: no handle
    _select(memedit, 1, 2, 'freq')
    wx.SafeYield()
    assert handle.IsShown()
    grid.MakeCellVisible(120, _col_index(memedit, 'freq'))
    handle.update()
    assert not handle.IsShown()


def test_handle_hidden_when_read_only(memedit, monkeypatch):
    monkeypatch.setattr(memedit_mod.ChirpMemEdit, 'editable',
                        property(lambda self: False))
    _show(memedit)
    _select(memedit, 1, 3, 'freq')
    wx.SafeYield()
    memedit._fill_handle.update()
    assert not memedit._fill_handle.IsShown()


def _mouse(handle, kind, grid_y):
    """A mouse event on the handle at height `grid_y` of the grid window."""
    event = wx.MouseEvent(kind)
    event.SetPosition(wx.Point(3, grid_y - handle.GetPosition().y))
    event.SetEventObject(handle)
    handle.GetEventHandler().ProcessEvent(event)


def _row_y(memedit, row):
    rect = memedit._grid.CellToRect(row, _col_index(memedit, 'freq'))
    return memedit._grid.CalcScrolledPosition(
        rect.GetLeft(), rect.GetTop() + rect.GetHeight() // 2)[1]


def test_handle_drag_fills(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 7)})
    _set_freqs(memedit, {1: 146000000, 2: 146025000})
    _show(memedit)
    _select(memedit, 1, 2, 'freq')
    wx.SafeYield()
    handle = memedit._fill_handle
    assert handle.IsShown()
    start = handle.GetPosition().y + 3
    _mouse(handle, wx.wxEVT_LEFT_DOWN, start)
    _mouse(handle, wx.wxEVT_MOTION, _row_y(memedit, 4))
    assert handle.preview_rows() == (3, 4)
    _mouse(handle, wx.wxEVT_MOTION, _row_y(memedit, 5))
    assert handle.preview_rows() == (3, 5)
    _mouse(handle, wx.wxEVT_LEFT_UP, _row_y(memedit, 5))
    assert handle.preview_rows() is None
    assert _freqs(memedit, range(1, 7)) == [
        146000000, 146025000, 146050000, 146075000, 146100000, 145650000]
    assert len(memedit._undo_queue) == 1
    assert memedit._undo_queue[0].name == 'Fill 3 cells'


def test_handle_on_cursor_cell_copies_it(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 7)})
    _show(memedit)
    # A plain click: only the cursor, no selected block
    _cursor(memedit, 2, 'name')
    wx.SafeYield()
    assert memedit.selected_cells() == []
    handle = memedit._fill_handle
    assert handle.IsShown()
    assert handle.GetRect().Contains(_corner(memedit, 2, 'name'))
    _mouse(handle, wx.wxEVT_LEFT_DOWN, handle.GetPosition().y + 3)
    _mouse(handle, wx.wxEVT_MOTION, _row_y(memedit, 4))
    assert handle.preview_rows() == (3, 4)
    _mouse(handle, wx.wxEVT_LEFT_UP, _row_y(memedit, 4))
    assert _names(memedit, range(1, 6)) == ['M1', 'M2', 'M2', 'M2', 'M5']
    assert memedit._undo_queue[0].name == 'Fill 2 cells'


def test_fill_to_from_cursor_cell_continues_name(memedit):
    _seeded(memedit, {1: 'CH01', 2: 'M2', 3: 'M3'})
    _cursor(memedit, 1, 'name')
    memedit.fill_to(3)
    assert _names(memedit, range(1, 4)) == ['CH01', 'CH01', 'CH01']
    # Whole rows selected: the handle does not belong to them
    memedit._grid.SelectRow(1)
    queued = len(memedit._undo_queue)
    assert memedit.fill_to(3) is None
    assert len(memedit._undo_queue) == queued


def test_handle_drag_cancelled(memedit):
    _seeded(memedit, {n: 'M%i' % n for n in range(1, 7)})
    _show(memedit)
    _select(memedit, 1, 2, 'name')
    wx.SafeYield()
    handle = memedit._fill_handle
    start = handle.GetPosition().y + 3
    # Esc while dragging
    _mouse(handle, wx.wxEVT_LEFT_DOWN, start)
    _mouse(handle, wx.wxEVT_MOTION, _row_y(memedit, 5))
    assert handle.preview_rows() == (3, 5)
    _key(handle, wx.WXK_ESCAPE)
    assert handle.preview_rows() is None
    _mouse(handle, wx.wxEVT_LEFT_UP, _row_y(memedit, 5))
    # Released inside the selection
    _mouse(handle, wx.wxEVT_LEFT_DOWN, start)
    _mouse(handle, wx.wxEVT_MOTION, _row_y(memedit, 1))
    assert handle.preview_rows() is None
    _mouse(handle, wx.wxEVT_LEFT_UP, _row_y(memedit, 1))
    assert _names(memedit, range(1, 7)) == ['M%i' % n for n in range(1, 7)]
    assert not memedit._undo_queue


def test_handle_drag_stops_at_last_row(memedit):
    _show(memedit)
    grid = memedit._grid
    last = grid.GetNumberRows() - 1
    grid.MakeCellVisible(last, _col_index(memedit, 'name'))
    _select(memedit, last - 2, last - 1, 'name')
    wx.SafeYield()
    handle = memedit._fill_handle
    assert handle.IsShown()
    filled = []
    handle._on_fill = filled.append
    _mouse(handle, wx.wxEVT_LEFT_DOWN, handle.GetPosition().y + 3)
    _mouse(handle, wx.wxEVT_MOTION,
           grid.GetGridWindow().GetClientSize().height + 200)
    assert handle.preview_rows() == (last, last)
    _mouse(handle, wx.wxEVT_LEFT_UP,
           grid.GetGridWindow().GetClientSize().height + 200)
    assert filled == [last]
