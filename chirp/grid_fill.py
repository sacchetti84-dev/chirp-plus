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

"""Spreadsheet-like helpers for the memory grid.

Pure Python, no wx: series that continue a few cells, tables pasted from
a spreadsheet and the cells they land on.
"""

import csv
import io
import math
import re

_NAME_RE = re.compile(r'^(.*?)(\d+)(\D*)$')
_EPSILON = 1e-6


def to_number(text):
    """Return text as a float, or None if it is not a number.

    The decimal comma is accepted: '145,6' is 145.6.
    """
    try:
        number = float(text.strip().replace(',', '.'))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _decimals(text):
    """Number of decimal digits written in a numeric text."""
    text = text.strip().replace(',', '.')
    if '.' not in text:
        return 0
    return len(text.split('.', 1)[1])


def _format(number, decimals):
    # + 0.0 turns a negative zero into a plain zero
    return '%.*f' % (decimals, round(number, decimals) + 0.0)


def _split_name(text):
    """Split 'CH08' into ('CH', '08', ''), or None without digits."""
    match = _NAME_RE.match(text)
    return match.groups() if match else None


def _padding(digit_strings):
    """Width that keeps the zero padding, 0 if none of them is padded."""
    if any(len(d) > 1 and d[0] == '0' for d in digit_strings):
        return max(len(d) for d in digit_strings)
    return 0


def _numbers(start, step, count, decimals):
    return [_format(start + step * i, decimals) for i in range(count)]


def _names(prefix, suffix, first, step, count, width):
    """Numbered names, or None if one of them would be negative."""
    if min(first, first + step * (count - 1)) < 0:
        return None
    return ['%s%0*d%s' % (prefix, width, first + step * i, suffix)
            for i in range(count)]


def _cycle(values, count):
    return [values[i % len(values)] for i in range(count)]


def continue_series(values, count):
    """Return the `count` items that continue the series in `values`.

    Numbers continue with their constant difference, numbered names
    ('CH08', 'CH09') with their constant step and zero padding. A single
    value, or anything else, is repeated cyclically.
    """
    if count <= 0 or not values:
        return []
    if len(values) == 1:
        return _cycle(values, count)

    numbers = [to_number(v) for v in values]
    if None not in numbers:
        diffs = [y - x for x, y in zip(numbers, numbers[1:])]
        if all(abs(d - diffs[0]) < _EPSILON for d in diffs):
            decimals = max(_decimals(v) for v in values)
            return _numbers(numbers[-1] + diffs[0], diffs[0], count, decimals)
        return _cycle(values, count)

    parts = [_split_name(v) for v in values]
    if None not in parts and len({(p[0], p[2]) for p in parts}) == 1:
        ints = [int(p[1]) for p in parts]
        diffs = [y - x for x, y in zip(ints, ints[1:])]
        if all(d == diffs[0] for d in diffs):
            series = _names(parts[0][0], parts[0][2], ints[-1] + diffs[0],
                            diffs[0], count, _padding([p[1] for p in parts]))
            if series is not None:
                return series
    return _cycle(values, count)


def make_series(start, step, count):
    """Return `count` items starting at `start` and growing by `step`.

    `start` is a number or a numbered name; `step` a number, an integer
    for names. Whatever cannot be stepped is repeated.
    """
    if count <= 0:
        return []
    number = to_number(start)
    increment = to_number(step)
    if number is not None and increment is not None:
        decimals = max(_decimals(start), _decimals(step))
        return _numbers(number, increment, count, decimals)

    parts = _split_name(start)
    if parts and increment is not None and increment == int(increment):
        series = _names(parts[0], parts[2], int(parts[1]), int(increment),
                        count, _padding([parts[1]]))
        if series is not None:
            return series
    return [start] * count


def parse_table(text):
    """Split tab-separated text, as copied from a spreadsheet, into rows.

    Cells quoted by the spreadsheet (those holding tabs or line breaks)
    are unquoted.
    """
    return list(csv.reader(io.StringIO(text, newline=''), delimiter='\t'))


def is_header_row(row, labels):
    """True if every filled cell of `row` is one of the column labels."""
    wanted = {label.strip().casefold() for label in labels}
    cells = [cell.strip().casefold() for cell in row if cell.strip()]
    return bool(cells) and all(cell in wanted for cell in cells)


def target_cells(anchor_row, anchor_col, matrix, visible_rows, ncols):
    """Place a pasted matrix on the grid, starting at the anchor cell.

    Each matrix row goes to the next visible row from `anchor_row` on, so
    hidden rows are skipped. Returns the (row, column, text) cells to
    write and how many values fall outside the grid. Empty values are
    left out and not counted.
    """
    rows = [r for r in visible_rows if r >= anchor_row]
    cells = []
    dropped = 0
    for i, values in enumerate(matrix):
        for j, text in enumerate(values):
            if not text:
                continue
            col = anchor_col + j
            if i >= len(rows) or col >= ncols:
                dropped += 1
            else:
                cells.append((rows[i], col, text))
    return cells, dropped


def spread(value, cells):
    """Give the same value to every (row, column) cell."""
    return [(row, col, value) for row, col in cells]
