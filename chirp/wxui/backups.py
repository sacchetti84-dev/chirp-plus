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

"""Browse the automatic backups made on every download and upload."""

import dataclasses
import datetime
import logging
import os
import re

import wx

from chirp import directory
from chirp import platform as chirp_platform
from chirp import radio_compare
from chirp.wxui import changes as changes_dialog
from chirp.wxui import theme

_ = wx.GetTranslation
LOG = logging.getLogger(__name__)

# Vendor_Model_download_20261019T005301.img (see ChirpMain._make_backup)
NAME_RE = re.compile(r'^(?P<radio>.+)_(?P<kind>download|upload)_'
                     r'(?P<when>\d{8}T\d{6})\.img$')


@dataclasses.dataclass
class Backup:
    path: str
    radio: str
    kind: str
    when: datetime.datetime
    size: int


def backup_dir():
    return chirp_platform.get_platform().config_file('backups')


def list_backups(folder=None):
    """Backups found in @folder, newest first"""
    folder = folder or backup_dir()
    found = []
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return []
    for name in names:
        m = NAME_RE.match(name)
        if not m:
            continue
        path = os.path.join(folder, name)
        try:
            when = datetime.datetime.strptime(m.group('when'),
                                              '%Y%m%dT%H%M%S')
            size = os.path.getsize(path)
        except (ValueError, OSError):
            continue
        found.append(Backup(path, m.group('radio').replace('_', ' ', 1),
                            m.group('kind'), when, size))
    found.sort(key=lambda b: b.when, reverse=True)
    return found


class BackupsDialog(wx.Dialog):
    """List of backups with Open, Compare with the current tab, Folder"""
    def __init__(self, parent, current_radio=None):
        super().__init__(parent, title=_('Backups'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._frame = parent
        self._current = current_radio
        self._backups = list_backups()
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)

        header = wx.StaticText(self, label=theme.prompt(
            'ls %s' % backup_dir()) if theme.enabled() else self.GetTitle())
        header.SetFont(theme.heading_font(11))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        info = wx.StaticText(self, label=_(
            'CHIRP saves a copy of the radio on every download and before '
            'every upload. Blue: read from the radio, orange: before writing '
            'to it.'))
        theme.wrap(info, 640)
        vbox.Add(info, border=12, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM)

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL |
                                wx.BORDER_SIMPLE)
        theme.keep(self.list, fg=True)
        for col, (name, width) in enumerate((
                (_('Date'), 160), (_('Radio'), 220), (_('Type'), 110),
                (_('Size'), 90))):
            self.list.InsertColumn(col, name, width=width)
        for i, b in enumerate(self._backups):
            self.list.InsertItem(i, b.when.strftime('%Y-%m-%d %H:%M:%S'))
            self.list.SetItem(i, 1, b.radio)
            self.list.SetItem(i, 2, _('download') if b.kind == 'download'
                              else _('upload'))
            self.list.SetItem(i, 3, '%.1f KB' % (b.size / 1024))
        vbox.Add(self.list, proportion=1, border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.EXPAND)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self._open = wx.Button(self, label=_('Open'))
        self._open.SetBitmap(theme.icon('folders', 16, 'file'))
        self._compare = wx.Button(self, label=_('Compare with open tab'))
        self._compare.SetBitmap(theme.icon('search', 16, 'info'))
        folder = wx.Button(self, label=_('Open folder'))
        folder.SetBitmap(theme.icon('folders', 16, 'dim'))
        for btn in (self._open, self._compare, folder):
            row.Add(btn, border=6, flag=wx.RIGHT)
        vbox.Add(row, border=12, flag=wx.ALL)
        vbox.Add(self.CreateButtonSizer(wx.CLOSE), border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND)

        self._open.Bind(wx.EVT_BUTTON, self._do_open)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._do_open)
        self._compare.Bind(wx.EVT_BUTTON, self._do_compare)
        folder.Bind(wx.EVT_BUTTON, lambda e: wx.LaunchDefaultApplication(
            backup_dir()))
        self.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE),
                  id=wx.ID_CLOSE)
        self.SetEscapeId(wx.ID_CLOSE)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._selected)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._selected)

        theme.style_dialog(self)
        self._color_rows()
        if self._backups:
            self.list.Select(0)
        self._selected(None)
        self.SetSize((720, 520))
        self.SetMinSize((520, 320))
        self.Centre()

    def _color_rows(self):
        if theme.enabled():
            self.list.SetBackgroundColour(theme.colour('field'))
        for i, b in enumerate(self._backups):
            self.list.SetItemTextColour(
                i, theme.tone('rx' if b.kind == 'download' else 'tx'))

    def _backup(self):
        i = self.list.GetFirstSelected()
        return self._backups[i] if i >= 0 else None

    def _selected(self, event):
        b = self._backup()
        self._open.Enable(b is not None)
        self._compare.Enable(b is not None and self._current is not None)

    def _do_open(self, event):
        b = self._backup()
        if b:
            self.EndModal(wx.ID_OK)
            wx.CallAfter(self._frame.open_file, b.path)

    def _do_compare(self, event):
        b = self._backup()
        if not b or self._current is None:
            return
        try:
            other = directory.get_radio_by_image(b.path)
            found = radio_compare.diff_radios(other, self._current)
        except Exception as e:
            LOG.exception('Compare with backup failed: %s', e)
            wx.MessageBox(str(e), _('Backups'), wx.ICON_ERROR, parent=self)
            return
        with changes_dialog.ChangesDialog(
                self, found, _('Backup compared with the open tab'),
                _('Close'), command='diff %s %s' % (
                    os.path.basename(b.path), _('open tab')),
                columns=(_('In the backup'), _('In the open tab')),
                question=False) as d:
            d.ShowModal()
