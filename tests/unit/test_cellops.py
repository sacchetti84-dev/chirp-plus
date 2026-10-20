import copy

import pytest

from chirp import chirp_common
from chirp.wxui import cellops
from tests.unit import base  # noqa


class Col:
    def __init__(self, name):
        self.name = name


class FakeEditor:
    """Columns in grid order: name, rtone, freq, comment, WARN, duplex."""

    def __init__(self, rows=(1, 2, 3)):
        self.memories = {}
        for row in rows:
            mem = chirp_common.Memory(row)
            mem.freq = 145000000
            self.memories[row] = mem
        self.columns = [Col(n) for n in
                        ('name', 'rtone', 'freq', 'comment', 'WARN',
                         'duplex')]
        self.calls = []

    def memory_for_row(self, row):
        return copy.deepcopy(self.memories[row])

    def column(self, col):
        return self.columns[col]

    def apply_cell_value(self, mem, col_def, text, interactive=False):
        assert interactive is False
        self.calls.append((mem.number, col_def.name, text))
        if text == 'BAD':
            raise cellops.CellRejected('bad value')
        if text == 'HALF':
            # Changes the memory, then gives up
            mem.tmode = 'Tone'
            raise cellops.CellRejected('half done')
        if col_def.name == 'WARN':
            mem.comment = 'WARN'
            return mem
        if col_def.name == 'freq':
            mem.freq = int(float(text) * 1000000)
        elif col_def.name == 'rtone':
            mem.rtone = float(text)
        else:
            setattr(mem, col_def.name, text)
        return mem

    def validate(self, mem):
        errors = []
        warnings = []
        if mem.freq == 0:
            errors.append('Memory must have a frequency')
        if mem.comment == 'WARN':
            warnings.append('Careful')
        return warnings, errors


def test_frequency_applied_before_other_columns():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 0, 'ABC'),
        cellops.CellEdit(1, 3, 'note'),
        cellops.CellEdit(1, 2, '146.0'),
    ])
    assert [c[1] for c in editor.calls] == ['freq', 'name', 'comment']
    assert result.problems == []
    assert result.changed[0].freq == 146000000


def test_rows_in_first_seen_order():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(3, 0, 'C'),
        cellops.CellEdit(1, 0, 'A'),
        cellops.CellEdit(3, 3, 'x'),
    ])
    assert [m.number for m in result.changed] == [3, 1]


def test_rejected_cell_is_reported_others_applied():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 0, 'BAD'),
        cellops.CellEdit(1, 3, 'note'),
        cellops.CellEdit(2, 0, 'BAD'),
    ])
    assert result.problems == [('1 name', 'bad value'),
                               ('2 name', 'bad value')]
    assert [m.number for m in result.changed] == [1]
    assert result.changed[0].comment == 'note'
    assert result.changed[0].name == ''


def test_validation_error_skips_the_row():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 2, '0'),
        cellops.CellEdit(2, 0, 'B'),
    ])
    assert [m.number for m in result.changed] == [2]
    assert result.problems == [('1', 'Memory must have a frequency')]


def test_validation_warning_keeps_the_memory():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [cellops.CellEdit(1, 4, 'x')])
    assert [m.number for m in result.changed] == [1]
    assert result.problems == [('1', 'Careful')]


def test_empty_memory_name_only_is_rejected():
    editor = FakeEditor()
    editor.memories[4] = chirp_common.Memory(4)
    editor.memories[4].freq = 0
    result = cellops.apply_edits(editor, [cellops.CellEdit(4, 0, 'NAME')])
    assert result.changed == []
    assert result.problems == [('4', 'Memory must have a frequency')]


def test_decimal_comma_in_numeric_columns():
    editor = FakeEditor()
    cellops.apply_edits(editor, [
        cellops.CellEdit(1, 1, '88,5'),
        cellops.CellEdit(1, 2, '145,6'),
        cellops.CellEdit(1, 0, 'A,B'),
        cellops.CellEdit(1, 3, '1,5'),
    ])
    assert sorted(editor.calls) == [
        (1, 'comment', '1,5'), (1, 'freq', '145.6'),
        (1, 'name', 'A,B'), (1, 'rtone', '88.5')]


def test_clear_cell_semantics():
    mem = chirp_common.Memory()
    mem.name = 'X'
    mem.duplex = '-'
    mem.offset = 600000
    cellops.clear_cell(mem, 'name')
    cellops.clear_cell(mem, 'duplex')
    assert (mem.name, mem.duplex, mem.offset) == ('', '', 0)
    with pytest.raises(cellops.CellRejected):
        cellops.clear_cell(mem, 'freq')


def test_clear_cell_resets_to_fresh_memory_values():
    fresh = chirp_common.Memory()
    mem = chirp_common.Memory()
    mem.comment = 'x'
    mem.tmode = 'Tone'
    mem.skip = 'S'
    mem.dtcs_polarity = 'RR'
    mem.cross_mode = 'DTCS->'
    mem.rtone = 100.0
    mem.ctone = 110.9
    mem.dtcs = 50
    mem.rx_dtcs = 51
    for name in ('comment', 'tmode', 'skip', 'dtcs_polarity', 'cross_mode',
                 'rtone', 'ctone', 'dtcs', 'rx_dtcs'):
        cellops.clear_cell(mem, name)
        assert getattr(mem, name) == getattr(fresh, name), name


def test_clear_cell_rejects_fields_without_empty_value():
    mem = chirp_common.Memory()
    for name in ('freq', 'mode', 'tuning_step', 'power'):
        with pytest.raises(cellops.CellRejected) as exc:
            cellops.clear_cell(mem, name)
        assert 'has no empty value' in str(exc.value)


def test_clearing_through_apply_edits():
    editor = FakeEditor()
    editor.memories[1].name = 'OLD'
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 0, None),
        cellops.CellEdit(1, 2, None),
    ])
    assert result.changed[0].name == ''
    assert result.changed[0].freq == 145000000
    assert len(result.problems) == 1
    assert 'has no empty value' in result.problems[0][1]
    assert editor.calls == []


def test_immutable_field_is_rejected():
    editor = FakeEditor()
    editor.memories[1].immutable = ['name']
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 0, 'A'),
        cellops.CellEdit(1, 0, None),
        cellops.CellEdit(1, 3, 'ok'),
    ])
    assert result.problems == [
        ('1 name', 'name cannot be changed on this memory'),
        ('1 name', 'name cannot be changed on this memory')]
    assert editor.calls == [(1, 'comment', 'ok')]
    assert result.changed[0].comment == 'ok'


def test_missing_memory_reports_every_cell():
    editor = FakeEditor(rows=())
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(9, 0, 'A'),
        cellops.CellEdit(9, 3, 'B'),
    ])
    assert result.changed == []
    assert [p[1] for p in result.problems] == [
        'Unable to edit memory before radio is loaded'] * 2


def test_extd_number_labels_the_problem():
    editor = FakeEditor()
    editor.memories[1].extd_number = 'VFO-A'
    result = cellops.apply_edits(editor, [cellops.CellEdit(1, 0, 'BAD')])
    assert result.problems == [('VFO-A name', 'bad value')]


def test_row_with_only_rejected_edits_is_left_alone():
    editor = FakeEditor()
    editor.memories[2].freq = 0     # already invalid before the edit
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(2, 0, 'BAD'),
        cellops.CellEdit(2, 2, None),
    ])
    assert result.changed == []
    assert [p[0] for p in result.problems] == ['2 freq', '2 name']


def test_rejected_cell_leaves_no_partial_change():
    editor = FakeEditor()
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 0, 'HALF'),
        cellops.CellEdit(1, 3, 'note'),
    ])
    assert result.problems == [('1 name', 'half done')]
    mem, = result.changed
    assert mem.comment == 'note'
    assert mem.tmode == ''
    # The editor's own memory is not touched either
    assert editor.memories[1].tmode == ''


def test_clearing_duplex_with_immutable_offset_changes_nothing():
    editor = FakeEditor()
    mem = editor.memories[1]
    mem.duplex = '-'
    mem.offset = 600000
    mem.immutable = ['offset']
    result = cellops.apply_edits(editor, [
        cellops.CellEdit(1, 5, None),
        cellops.CellEdit(1, 3, 'note'),
    ])
    assert [p[0] for p in result.problems] == ['1 duplex']
    mem, = result.changed
    assert (mem.duplex, mem.offset, mem.comment) == ('-', 600000, 'note')
