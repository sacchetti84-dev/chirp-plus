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

"""Read-only hex view of an image, every byte colored by what it is."""

import wx
import wx.stc

from chirp import memory_map
from chirp.wxui import theme

_ = wx.GetTranslation

KIND_NAMES = {
    memory_map.CHANNELS: _('channels'),
    memory_map.NAMES: _('names'),
    memory_map.SETTINGS: _('settings'),
    memory_map.MESSAGES: _('messages and ident'),
    memory_map.SERVICE: _('service (squelch, limits): careful'),
    memory_map.UNKNOWN: _('unknown data (calibration?)'),
    memory_map.EMPTY: _('empty'),
}
KINDS = list(memory_map.KIND_TONES)
OFFSET_STYLE = len(KINDS)
ROW_WIDTH = 16
# "0000  " + 16 * "XX " + " " + 16 ascii
HEX_COL = 6
ASCII_COL = HEX_COL + ROW_WIDTH * 3 + 1


class MemoryMapDialog(wx.Dialog):
    def __init__(self, parent, radio):
        super().__init__(parent, title=_('Memory map'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER |
                         wx.MAXIMIZE_BOX)
        self._data, self._regions = memory_map.build_map(radio)
        self._kinds = memory_map.byte_kinds(self._data, self._regions)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)

        header = wx.StaticText(self, label=theme.prompt(
            'hexdump %s %s' % (radio.VENDOR.lower(), radio.MODEL.lower()))
            if theme.enabled() else self.GetTitle())
        header.SetFont(theme.heading_font(12))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        legend = wx.WrapSizer(wx.HORIZONTAL)
        for kind in KINDS:
            text = wx.StaticText(self, label='■ %s   ' % KIND_NAMES[kind])
            text.SetForegroundColour(theme.tone(
                memory_map.KIND_TONES[kind]))
            theme.keep(text, fg=True)
            legend.Add(text, border=2, flag=wx.BOTTOM)
        vbox.Add(legend, border=12, flag=wx.LEFT | wx.RIGHT | wx.EXPAND)

        split = wx.BoxSizer(wx.HORIZONTAL)
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL |
                                wx.BORDER_SIMPLE)
        theme.keep(self.list, fg=True)
        for col, (name, width) in enumerate((
                (_('Start'), 70), (_('End'), 70), (_('Bytes'), 60),
                (_('Name'), 150))):
            self.list.InsertColumn(col, name, width=width)
        for i, r in enumerate(self._regions):
            self.list.InsertItem(i, '0x%04X' % r.start)
            self.list.SetItem(i, 1, '0x%04X' % r.end)
            self.list.SetItem(i, 2, str(r.size))
            self.list.SetItem(i, 3, r.name)
        self.list.SetMinSize((370, -1))
        split.Add(self.list, border=8, flag=wx.RIGHT | wx.EXPAND)

        self.hex = wx.stc.StyledTextCtrl(self)
        self._setup_styles()
        self._fill()
        split.Add(self.hex, proportion=1, flag=wx.EXPAND)
        vbox.Add(split, proportion=1, border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND)

        known = sum(r.size for r in self._regions
                    if r.kind != memory_map.UNKNOWN)
        unknown = sum(r.size for r in self._regions
                      if r.kind == memory_map.UNKNOWN)
        totals = wx.StaticText(self, label=_(
            '%(size)i bytes: %(known)i described by the driver, %(unknown)i '
            'with data the driver does not describe') % {
                'size': len(self._data), 'known': known, 'unknown': unknown})
        totals.SetForegroundColour(theme.tone('bad' if unknown else 'ok'))
        theme.keep(totals, fg=True)
        vbox.Add(totals, border=12, flag=wx.ALL)
        vbox.Add(self.CreateButtonSizer(wx.CLOSE), border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND)
        self.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE),
                  id=wx.ID_CLOSE)
        self.SetEscapeId(wx.ID_CLOSE)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._goto)

        theme.style_dialog(self)
        if theme.enabled():
            self.list.SetBackgroundColour(theme.colour('field'))
        for i, r in enumerate(self._regions):
            self.list.SetItemTextColour(i, theme.tone(
                memory_map.KIND_TONES[r.kind]))
        self.SetSize((1180, 720))
        self.SetMinSize((800, 400))
        self.Centre()

    def _setup_styles(self):
        stc = self.hex
        font = theme.mono_font(10)
        bg = theme.colour('bg') if theme.enabled() else wx.Colour('#FFFFFF')
        stc.StyleSetBackground(wx.stc.STC_STYLE_DEFAULT, bg)
        stc.StyleSetFont(wx.stc.STC_STYLE_DEFAULT, font)
        stc.StyleClearAll()
        for i, kind in enumerate(KINDS):
            stc.StyleSetForeground(i, theme.tone(
                memory_map.KIND_TONES[kind]))
            stc.StyleSetBackground(i, bg)
            stc.StyleSetFont(i, font)
        stc.StyleSetForeground(OFFSET_STYLE, theme.tone('dim'))
        stc.StyleSetBackground(OFFSET_STYLE, bg)
        stc.StyleSetFont(OFFSET_STYLE, font)
        stc.SetMarginWidth(1, 0)
        stc.SetCaretForeground(theme.tone('accent'))
        stc.SetSelBackground(True, theme.colour('select'))
        stc.SetWrapMode(wx.stc.STC_WRAP_NONE)

    def _fill(self):
        stc = self.hex
        lines = []
        for offset, hexes, text in memory_map.hex_rows(self._data,
                                                       ROW_WIDTH):
            lines.append('%04X  %-*s %s' % (offset, ROW_WIDTH * 3 - 1,
                                            hexes, text))
        stc.SetText('\n'.join(lines))
        # Style byte by byte; pos is a byte offset in the (ASCII) text
        index = {kind: i for i, kind in enumerate(KINDS)}
        line_len = len(lines[0]) + 1 if lines else 0
        stc.StartStyling(0)
        for row, line in enumerate(lines):
            base = row * line_len
            stc.StartStyling(base)
            stc.SetStyling(HEX_COL, OFFSET_STYLE)
            first = row * ROW_WIDTH
            count = min(ROW_WIDTH, len(self._data) - first)
            for i in range(count):
                style = index[self._kinds[first + i]]
                stc.StartStyling(base + HEX_COL + i * 3)
                stc.SetStyling(2, style)
                stc.StartStyling(base + ASCII_COL + i)
                stc.SetStyling(1, style)
        stc.SetReadOnly(True)

    def _goto(self, event):
        region = self._regions[event.GetIndex()]
        line = region.start // ROW_WIDTH
        self.hex.ScrollToLine(max(0, line - 2))
        start = self.hex.PositionFromLine(line) + HEX_COL + \
            (region.start % ROW_WIDTH) * 3
        self.hex.SetSelection(start, start + 2)
