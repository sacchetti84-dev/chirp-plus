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

"""The fill handle of the memory grid.

A small square at the bottom-right corner of the selected cells, as in
spreadsheets: dragging it down continues the selected cells over the
rows below. The handle only finds the rows; the caller fills them.
"""

import wx

from chirp.wxui import theme

_ = wx.GetTranslation

# Side of the square, in pixels
SIZE = 7
# Width of the border around the rows a drag will fill
PREVIEW_WIDTH = 2


def colour():
    """The color of the handle and of the preview border."""
    if theme.enabled():
        return theme.tone('tx')
    return wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)


def selection_block(grid):
    """The (top, left, bottom, right) cells around the grid selection.

    None when nothing is selected, or before wxPython 4.1.
    """
    try:
        blocks = list(grid.GetSelectedBlocks())
    except AttributeError:
        return None
    if not blocks:
        return None
    return (min(b.GetTopRow() for b in blocks),
            min(b.GetLeftCol() for b in blocks),
            max(b.GetBottomRow() for b in blocks),
            max(b.GetRightCol() for b in blocks))


class FillHandle(wx.Window):
    """A draggable square at the corner of the selection of `grid`.

    Dragging it down and releasing calls on_fill(last_row), the last
    grid row to fill. `block` returns the (top, left, bottom, right)
    cells the handle belongs to, or None to hide it; `editable` returns
    False to hide it on a read-only grid.
    """

    def __init__(self, grid, on_fill, block=None, editable=None):
        parent = grid.GetGridWindow()
        super().__init__(parent, size=(SIZE, SIZE), style=wx.BORDER_NONE)
        self._grid = grid
        self._on_fill = on_fill
        self._block = block or (lambda: selection_block(grid))
        self._editable = editable or (lambda: True)
        # The block being dragged, and the last row the drag would fill
        self._drag = None
        self._target = None
        self._pending = False

        # Four thin windows around the rows a drag will fill: no drawing
        # on the grid window, which repaints itself at any time
        self._preview = []
        for _side in range(4):
            line = wx.Window(parent, style=wx.BORDER_NONE)
            # Painted, not erased: in the dark mode of Windows a plain
            # background color comes out black
            line.SetBackgroundStyle(wx.BG_STYLE_PAINT)
            line.Bind(wx.EVT_PAINT, self._on_paint_line)
            line.Hide()
            self._preview.append(line)

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
        self.SetToolTip(_('Drag down to continue the selected cells'))
        self.Hide()

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        # The grid window keeps the keyboard focus during a drag
        for window in (self, parent):
            window.Bind(wx.EVT_KEY_DOWN, self._on_key)

    def AcceptsFocus(self):
        # Clicking the handle leaves the focus on the grid
        return False

    def update(self):
        """Move to the corner of the selection, or hide."""
        self._pending = False
        if self._drag is not None:
            # Moving or hiding the window that has the mouse would end
            # the drag
            return
        rect = self._corner_rect()
        if rect is None:
            self.Hide()
            return
        self.SetPosition(rect.GetPosition())
        self.Show()
        self.Raise()
        self.Refresh()

    def update_later(self):
        """update() once the grid has finished what it is doing.

        Selection and scroll events come before the grid changes; many
        calls in a row make one update.
        """
        if not self._pending:
            self._pending = True
            wx.CallAfter(self._deferred_update)

    def _deferred_update(self):
        # The editor may be closed before this runs
        if self:
            self.update()

    def preview_rows(self):
        """(first, last) rows of the preview during a drag, or None."""
        if self._drag is None or self._target is None:
            return None
        return self._drag[2] + 1, self._target

    def _corner_rect(self):
        block = self._block()
        if block is None or not self._editable():
            return None
        _top, _left, bottom, right = block
        cell = self._grid.CellToRect(bottom, right)
        x, y = self._grid.CalcScrolledPosition(cell.GetRight(),
                                               cell.GetBottom())
        width, height = self.GetParent().GetClientSize()
        if not (0 <= x < width and 0 <= y < height):
            return None
        return wx.Rect(x - SIZE // 2, y - SIZE // 2, SIZE, SIZE)

    def _on_paint(self, event):
        dc = wx.PaintDC(self)
        # Outlined with the cell color, so it stands out on the
        # selection border
        dc.SetPen(wx.Pen(self._grid.GetDefaultCellBackgroundColour()))
        dc.SetBrush(wx.Brush(colour()))
        dc.DrawRectangle(0, 0, SIZE, SIZE)

    def _on_paint_line(self, event):
        dc = wx.PaintDC(event.GetEventObject())
        dc.SetBackground(wx.Brush(colour()))
        dc.Clear()

    def _on_left_down(self, event):
        block = self._block()
        if (block is None or not self._editable() or
                self._grid.IsCellEditControlShown()):
            return
        self._drag = block
        self._target = None
        self.CaptureMouse()

    def _row_at(self, pos):
        """The grid row under `pos` (handle coordinates), clamped."""
        x, y = self.GetPosition() + pos
        _x, y = self._grid.CalcUnscrolledPosition(x, y)
        row = self._grid.YToRow(y, clipToMinMax=True)
        return min(max(row, 0), self._grid.GetNumberRows() - 1)

    def _on_motion(self, event):
        if self._drag is None:
            event.Skip()
            return
        row = self._row_at(event.GetPosition())
        _top, _left, bottom, right = self._drag
        # Below the window: scroll one more row into view
        y = self.GetPosition().y + event.GetPosition().y
        if y >= self.GetParent().GetClientSize().height:
            self._grid.MakeCellVisible(row, right)
        if row > bottom:
            self._target = row
            self._show_preview()
        else:
            self._target = None
            self._hide_preview()

    def _show_preview(self):
        _top, left, bottom, right = self._drag
        first = self._grid.CellToRect(bottom + 1, left)
        last = self._grid.CellToRect(self._target, right)
        x0, y0 = self._grid.CalcScrolledPosition(first.GetLeft(),
                                                 first.GetTop())
        x1, y1 = self._grid.CalcScrolledPosition(last.GetRight(),
                                                 last.GetBottom())
        width = max(x1 - x0 + 1, PREVIEW_WIDTH)
        height = max(y1 - y0 + 1, PREVIEW_WIDTH)
        sides = ((x0, y0, width, PREVIEW_WIDTH),
                 (x0, y1 - PREVIEW_WIDTH + 1, width, PREVIEW_WIDTH),
                 (x0, y0, PREVIEW_WIDTH, height),
                 (x1 - PREVIEW_WIDTH + 1, y0, PREVIEW_WIDTH, height))
        for line, rect in zip(self._preview, sides):
            line.SetSize(*rect)
            line.Show()

    def _hide_preview(self):
        for line in self._preview:
            line.Hide()

    def _end_drag(self):
        self._drag = None
        self._target = None
        self._hide_preview()
        if self.HasCapture():
            self.ReleaseMouse()

    def _on_left_up(self, event):
        if self._drag is None:
            return
        target = self._target
        self._end_drag()
        if target is not None:
            self._on_fill(target)
        self.update()

    def _on_capture_lost(self, event):
        self._end_drag()
        self.update()

    def _on_key(self, event):
        if self._drag is not None and event.GetKeyCode() == wx.WXK_ESCAPE:
            self._end_drag()
            self.update()
            return
        event.Skip()
