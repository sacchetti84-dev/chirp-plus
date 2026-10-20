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

"""Dialog listing what an upload will change in the radio."""

import wx

from chirp import radio_compare
from chirp.wxui import theme

_ = wx.GetTranslation

KIND_TONES = {
    radio_compare.ADDED: 'ok',
    radio_compare.REMOVED: 'bad',
    radio_compare.CHANGED: 'warn',
}


def kind_label(kind):
    return {radio_compare.ADDED: _('added'),
            radio_compare.REMOVED: _('removed'),
            radio_compare.CHANGED: _('changed')}[kind]


class ChangesDialog(wx.Dialog):
    """Shows the differences radio -> image and asks to go on.

    ShowModal() returns wx.ID_OK to upload, wx.ID_CANCEL to stop.
    """
    def __init__(self, parent, changes, title, action_label,
                 action_tone='tx', command=None, columns=None,
                 question=True, note=None, action_icon='upload',
                 summary=None):
        super().__init__(parent, title=title,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.changes = changes
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)

        header = wx.StaticText(self, label=theme.prompt(
            command or 'diff radio %s' % _('image'))
            if theme.enabled() else title)
        header.SetFont(theme.heading_font(12))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        counts = radio_compare.summary(changes)
        if changes and summary:
            text = summary
            tone = 'warn'
        elif changes and question:
            text = _('%(memories)i channels and %(settings)i settings will '
                     'change in the radio.') % {
                         'memories': counts['memory'],
                         'settings': counts['setting']}
            tone = 'warn'
        elif changes:
            text = _('%(memories)i channels and %(settings)i settings are '
                     'different.') % {'memories': counts['memory'],
                                      'settings': counts['setting']}
            tone = 'warn'
        elif question:
            text = _('The radio already holds this image: nothing would '
                     'change.')
            tone = 'ok'
        else:
            text = _('No differences.')
            tone = 'ok'
        summary = wx.StaticText(self, label='%s %s' % (theme.TAGS[tone],
                                                       text))
        summary.SetForegroundColour(theme.tone(tone))
        theme.keep(summary, fg=True)
        vbox.Add(summary, border=12, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM)
        if note:
            hint = wx.StaticText(self, label=note)
            hint.SetForegroundColour(theme.tone('dim'))
            theme.keep(hint, fg=True)
            vbox.Add(hint, border=12, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM)

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SIMPLE)
        theme.keep(self.list, fg=True)
        before, after = columns or (_('In the radio now'),
                                    _('After upload'))
        for col, (name, width) in enumerate((
                (_('Change'), 90), (_('Where'), 170),
                (before, 260), (after, 260))):
            self.list.InsertColumn(col, name, width=width)
        for i, change in enumerate(changes):
            where = (_('Memory %s') % change.where
                     if change.what == 'memory' else change.where)
            self.list.InsertItem(i, kind_label(change.kind))
            self.list.SetItem(i, 1, where)
            self.list.SetItem(i, 2, change.before)
            self.list.SetItem(i, 3, change.after)
            self.list.SetItemTextColour(
                i, theme.tone(KIND_TONES[change.kind]))
        vbox.Add(self.list, proportion=1, border=12,
                 flag=wx.EXPAND | wx.LEFT | wx.RIGHT)

        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL if question
                                         else wx.OK)
        vbox.Add(buttons, border=12, flag=wx.ALL | wx.EXPAND)
        # FindWindowById() would search every window: the parent dialog
        # has an OK button too
        ok = self.FindWindow(wx.ID_OK)
        ok.SetLabel(action_label)
        if question:
            ok.SetBitmap(theme.icon(action_icon, 16, action_tone))
        theme.style_dialog(self)
        if theme.enabled():
            ok.SetForegroundColour(theme.colour(action_tone))
            self.list.SetBackgroundColour(theme.colour('field'))
            for i, change in enumerate(changes):
                self.list.SetItemTextColour(
                    i, theme.colour(KIND_TONES[change.kind]))
        self.SetSize((860, 480 if changes else 220))
        self.SetMinSize((520, 200))
        self.Centre()
