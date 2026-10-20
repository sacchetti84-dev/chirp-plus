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

"""Apply lists of cell edits to radio memories, without any UI.

No wx here, so it can be tested without a GUI. The memory editor is
reached through a small duck-typed protocol:

    memory_for_row(row) -> Memory   a copy; KeyError if there is none
    column(col) -> col_def          with a .name and a .label
    apply_cell_value(mem, col_def, text, interactive=False) -> Memory
                                    raises CellRejected
    validate(mem) -> (warnings, errors)
"""

from dataclasses import dataclass

from chirp import chirp_common
from chirp import grid_fill

NUMERIC_COLUMNS = {'freq', 'offset', 'rtone', 'ctone', 'power'}
NO_EMPTY = {'freq', 'mode', 'tuning_step', 'power'}

_TEXT_FIELDS = ('name', 'comment')
_DEFAULT_FIELDS = ('tmode', 'skip', 'dtcs_polarity', 'cross_mode',
                   'rtone', 'ctone', 'dtcs', 'rx_dtcs')


class CellRejected(Exception):
    """The cell cannot take the value; the message says why."""


@dataclass
class CellEdit:
    row: int
    col: int
    text: str | None  # None clears the cell


@dataclass
class BulkResult:
    changed: list[chirp_common.Memory]
    # (label of the memory or cell, reason)
    problems: list[tuple[str, str]]


def column_title(col_def):
    """The title of a column on one line, as the user sees it.

    Two-word titles are written on two lines in the grid header.
    """
    return col_def.label.replace('/\n', '/').replace('\n', ' ')


def clear_cell(mem, name, title=None):
    """Give the field `name` of `mem` its empty value.

    `title` names the column in the messages (the field name if None).
    """
    title = title or name
    if name in NO_EMPTY:
        raise CellRejected(_('%s has no empty value') % title)
    fresh = chirp_common.Memory()
    try:
        if name in _TEXT_FIELDS:
            setattr(mem, name, '')
        elif name == 'duplex':
            mem.duplex = fresh.duplex
            mem.offset = 0
        elif name in _DEFAULT_FIELDS:
            setattr(mem, name, getattr(fresh, name))
        else:
            raise CellRejected(_('%s has no empty value') % title)
    except chirp_common.ImmutableValueError as e:
        raise CellRejected(str(e))


def _memory_label(mem):
    return str(mem.extd_number or mem.number)


def _by_row(edits):
    rows = {}
    for edit in edits:
        rows.setdefault(edit.row, []).append(edit)
    return rows


def _apply_one(editor, mem, col_def, text):
    """Apply a single edit and return the resulting memory."""
    name = col_def.name
    if name in mem.immutable:
        raise CellRejected(_('%s cannot be changed on this memory') %
                           column_title(col_def))
    if text is None:
        clear_cell(mem, name, column_title(col_def))
        return mem
    if name in NUMERIC_COLUMNS and grid_fill.to_number(text) is not None:
        text = text.strip().replace(',', '.')
    return editor.apply_cell_value(mem, col_def, text, interactive=False)


def apply_edits(editor, edits):
    """Apply `edits` and return the changed memories and the problems.

    Edits are grouped by row, rows in the order they first appear; in
    each row the frequency goes first, then the other columns in grid
    order. A rejected cell is reported, changes nothing, and the others
    go on; a row where no edit applied is left out and not validated.
    Problems name the cells by memory and column title. If the resulting
    memory has validation errors the whole row is dropped; warnings are
    reported and the memory is kept.
    """
    changed = []
    problems = []
    for row, row_edits in _by_row(edits).items():
        try:
            mem = editor.memory_for_row(row)
        except KeyError:
            for edit in row_edits:
                problems.append(
                    ('%s %s' % (row, column_title(editor.column(edit.col))),
                     _('Unable to edit memory before radio is loaded')))
            continue

        label = _memory_label(mem)
        ordered = sorted(
            row_edits,
            key=lambda e: (editor.column(e.col).name != 'freq', e.col))
        applied = False
        for edit in ordered:
            col_def = editor.column(edit.col)
            try:
                # On a copy: a rejected cell leaves nothing behind
                mem = _apply_one(editor, mem.dupe(), col_def, edit.text)
                applied = True
            except CellRejected as e:
                problems.append(
                    ('%s %s' % (label, column_title(col_def)), str(e)))

        if not applied:
            continue
        warnings, errors = editor.validate(mem)
        problems.extend((label, w) for w in warnings)
        if errors:
            problems.extend((label, e) for e in errors)
            continue
        changed.append(mem)
    return BulkResult(changed, problems)
