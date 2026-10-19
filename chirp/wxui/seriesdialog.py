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

"""Ask for the start and step of a series to write in some cells."""

import wx

from chirp import grid_fill
from chirp.wxui import theme

_ = wx.GetTranslation


class SeriesDialog(wx.Dialog):
    """Start and step of a series for `count` cells.

    After ShowModal() returns wx.ID_OK, `values` holds the `count` items.
    """

    def __init__(self, parent, start, count):
        super().__init__(parent, title=_('Series'))
        self._count = count
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)

        header = wx.StaticText(self, label=theme.prompt(
            'series --count %i' % count)
            if theme.enabled() else self.GetTitle())
        header.SetFont(theme.heading_font(12))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        intro = wx.StaticText(self, label=_(
            'Values for %i cells, from the first one down. Frequencies '
            'step in MHz (0.025 is 25 kHz); numbered names such as CH01 '
            'step by whole numbers.') % count)
        theme.wrap(intro, 420)
        vbox.Add(intro, border=12, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM)

        grid = wx.FlexGridSizer(2, 8, 8)
        grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self, label=_('Start')),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        self._start = wx.TextCtrl(self, value=start)
        grid.Add(self._start, flag=wx.EXPAND)
        grid.Add(wx.StaticText(self, label=_('Step')),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        self._step = wx.TextCtrl(self, value='1')
        grid.Add(self._step, flag=wx.EXPAND)
        grid.Add(wx.StaticText(self, label=_('Preview')),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        self._preview = wx.StaticText(self, label='')
        self._preview.SetForegroundColour(theme.tone('file'))
        theme.keep(self._preview, fg=True)
        grid.Add(self._preview, flag=wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)
        vbox.Add(grid, border=12, flag=wx.LEFT | wx.RIGHT | wx.EXPAND)

        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(buttons, border=12, flag=wx.ALL | wx.EXPAND)

        self._start.Bind(wx.EVT_TEXT, self._update)
        self._step.Bind(wx.EVT_TEXT, self._update)
        self._update()
        theme.style_dialog(self)
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.Centre()
        self._step.SetFocus()
        self._step.SelectAll()

    @property
    def values(self):
        return grid_fill.make_series(self._start.GetValue().strip(),
                                     self._step.GetValue().strip(),
                                     self._count)

    def _update(self, event=None):
        values = self.values
        text = ', '.join(values[:3])
        if len(values) > 3:
            text += ', ...'
        self._preview.SetLabel(text)
        ok = self.FindWindow(wx.ID_OK)
        if ok:
            ok.Enable(bool(self._start.GetValue().strip()) and
                      grid_fill.to_number(self._step.GetValue()) is not None)
