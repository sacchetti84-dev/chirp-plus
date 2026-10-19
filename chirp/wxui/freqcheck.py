# Copyright 2026 CHIRP contributors
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

"""Report of the frequency check (chirp/freq_check.py)."""

import wx

from chirp import freq_check
from chirp.wxui import theme

_ = wx.GetTranslation

LEVEL_LABELS = {
    freq_check.BAD: 'bad',
    freq_check.WARN: 'warn',
    freq_check.INFO: 'info',
}


class FreqCheckDialog(wx.Dialog):
    def __init__(self, parent, radio, findings):
        super().__init__(parent, title=_('Frequency check'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)
        header = wx.StaticText(self, label=theme.prompt(
            'check --country IT %s' % radio.MODEL.lower())
            if theme.enabled() else self.GetTitle())
        header.SetFont(theme.heading_font(12))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        counts = freq_check.summary(findings)
        line = wx.BoxSizer(wx.HORIZONTAL)
        for level, label in ((freq_check.BAD, _('errors')),
                             (freq_check.WARN, _('warnings')),
                             (freq_check.INFO, _('notes'))):
            tone = LEVEL_LABELS[level] if counts[level] else 'dim'
            text = wx.StaticText(self, label='%s %i %s   ' % (
                theme.TAGS[LEVEL_LABELS[level]], counts[level], label))
            text.SetForegroundColour(theme.tone(tone))
            theme.keep(text, fg=True)
            line.Add(text)
        vbox.Add(line, border=12, flag=wx.LEFT | wx.RIGHT)
        if not findings:
            ok = wx.StaticText(self, label='%s %s' % (
                theme.TAGS['ok'], _('No problems found.')))
            ok.SetForegroundColour(theme.tone('ok'))
            theme.keep(ok, fg=True)
            vbox.Add(ok, border=12, flag=wx.ALL)

        note = wx.StaticText(self, label=_(
            'Rules for Italy. This is advice, not a legal opinion: check '
            'your license and the radio approval.'))
        theme.wrap(note, 640)
        vbox.Add(note, border=12, flag=wx.ALL)

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SIMPLE)
        theme.keep(self.list, fg=True)
        for col, (name, width) in enumerate((
                (_('Channel'), 80), (_('Level'), 90), (_('Band'), 150),
                (_('Message'), 460))):
            self.list.InsertColumn(col, name, width=width)
        order = {freq_check.BAD: 0, freq_check.WARN: 1, freq_check.INFO: 2}

        def sort_key(f):
            # Numbered memories in numeric order, specials (names) after
            if isinstance(f.number, int):
                return order[f.level], 0, f.number, ''
            return order[f.level], 1, 0, str(f.number)
        findings = sorted(findings, key=sort_key)
        for i, f in enumerate(findings):
            self.list.InsertItem(i, str(f.number))
            self.list.SetItem(i, 1, theme.TAGS[LEVEL_LABELS[f.level]])
            self.list.SetItem(i, 2, wx.GetTranslation(f.band))
            self.list.SetItem(i, 3, f.message(wx.GetTranslation))
        vbox.Add(self.list, proportion=1, border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.EXPAND)
        vbox.Add(self.CreateButtonSizer(wx.CLOSE), border=12,
                 flag=wx.ALL | wx.EXPAND)
        self.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE),
                  id=wx.ID_CLOSE)
        self.SetEscapeId(wx.ID_CLOSE)

        theme.style_dialog(self)
        if theme.enabled():
            self.list.SetBackgroundColour(theme.colour('field'))
        for i, f in enumerate(findings):
            self.list.SetItemTextColour(i, theme.tone(LEVEL_LABELS[f.level]))
        self.SetSize((840, 520))
        self.SetMinSize((520, 320))
        self.Centre()
