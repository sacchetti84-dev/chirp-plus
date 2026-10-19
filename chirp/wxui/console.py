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

"""Event console: a short, colored history of what CHIRP did.

log('rx', 'Downloaded Baofeng UV-9R') can be called from any thread; each
line gets a time stamp, a tag ([ OK ], [WARN], ...) and the color of its
tone (see theme.TAGS / theme.PALETTE).
"""

import collections
import datetime
import logging
import threading

import wx

from chirp.wxui import theme

LOG = logging.getLogger(__name__)

Entry = collections.namedtuple('Entry', 'time tone text')


class EventLog:
    def __init__(self, size=500):
        self.entries = collections.deque(maxlen=size)
        self._listeners = []
        self._lock = threading.Lock()

    def log(self, tone, text):
        if tone not in theme.TAGS:
            tone = 'info'
        entry = Entry(datetime.datetime.now(), tone, text)
        with self._lock:
            self.entries.append(entry)
            listeners = list(self._listeners)
        LOG.info('console %s %s', theme.TAGS[tone], text)
        for fn in listeners:
            try:
                fn(entry)
            except Exception as e:
                LOG.exception('Console listener failed: %s', e)

    def add_listener(self, fn):
        with self._lock:
            self._listeners.append(fn)
            return list(self.entries)

    def remove_listener(self, fn):
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)


_LOG = EventLog()


def get():
    return _LOG


def log(tone, text):
    _LOG.log(tone, text)


def format_entry(entry):
    return '%s %s %s' % (entry.time.strftime('%H:%M:%S'),
                         theme.TAGS[entry.tone], entry.text)


class ConsolePanel(wx.Panel):
    """Read-only, colored view of the event log"""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        self._text = wx.TextCtrl(
            self, style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 |
                         wx.TE_DONTWRAP | wx.BORDER_NONE))
        self._text._term_keep_fg = True
        self._text.SetFont(theme.mono_font(9))
        self._text._term_keep_font = True
        if theme.enabled():
            self._text.SetBackgroundColour(theme.colour('bg'))
            self.SetBackgroundColour(theme.colour('bg'))
        sizer.Add(self._text, 1, wx.EXPAND | wx.ALL, 4)
        for entry in get().add_listener(self._entry_bg):
            self._append(entry)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._destroyed)

    def _destroyed(self, event):
        event.Skip()
        if event.GetEventObject() is self:
            get().remove_listener(self._entry_bg)

    def _entry_bg(self, entry):
        wx.CallAfter(self._append, entry)

    def _append(self, entry):
        if not self:
            return
        text = self._text
        text.SetInsertionPointEnd()
        text.SetDefaultStyle(wx.TextAttr(theme.tone('dim')))
        text.AppendText(entry.time.strftime('%H:%M:%S '))
        text.SetDefaultStyle(wx.TextAttr(theme.tone(entry.tone)))
        text.AppendText(theme.TAGS[entry.tone] + ' ')
        text.SetDefaultStyle(wx.TextAttr(
            theme.tone('fg' if entry.tone in ('info', 'file') else
                       entry.tone)))
        text.AppendText(entry.text + '\n')
        text.ShowPosition(text.GetLastPosition())

    def clear(self):
        self._text.Clear()
