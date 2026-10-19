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

    def __init__(self):
        self.shown = []

    def __call__(self, parent, message, caption='', style=0, **k):
        dialogs = self

        class Dialog:
            def SetExtendedMessage(self, text):
                self.extended = text

            def ShowModal(self):
                dialogs.shown.append((caption, message,
                                      getattr(self, 'extended', '')))
                return wx.ID_OK

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
