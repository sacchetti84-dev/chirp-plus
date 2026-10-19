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

"""Program the current image into several radios in a row."""

import logging
import threading

import wx

from chirp import batch_program
from chirp import chirp_common
from chirp.wxui import clone
from chirp.wxui import config
from chirp.wxui import console
from chirp.wxui import portdetect
from chirp.wxui import theme

_ = wx.GetTranslation
LOG = logging.getLogger(__name__)
CONF = config.get()


class BatchDialog(wx.Dialog):
    def __init__(self, parent, radio):
        super().__init__(parent, title=_('Program several radios'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._radio = radio
        self._running = False
        self._ports = []
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)

        header = wx.StaticText(self, label=theme.prompt(
            'program --batch %s' % clone.model_value(radio).lower())
            if theme.enabled() else self.GetTitle())
        header.SetFont(theme.heading_font(12))
        header.SetForegroundColour(theme.tone('accent'))
        theme.keep(header, fg=True, font=True)
        vbox.Add(header, border=12, flag=wx.ALL)

        intro = wx.StaticText(self, label=_(
            'The same image is written into each radio. For every radio: '
            'connect the cable, turn the radio on, then press the button '
            '(or Enter). Wait for the result before moving the cable.'))
        theme.wrap(intro, 560)
        vbox.Add(intro, border=12, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM)

        grid = wx.FlexGridSizer(2, 8, 8)
        grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self, label=_('Image')),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        image = wx.StaticText(self, label='%s %s' % (radio.VENDOR,
                                                     clone.model_value(radio)))
        image.SetForegroundColour(theme.tone('file'))
        theme.keep(image, fg=True)
        grid.Add(image, flag=wx.ALIGN_CENTER_VERTICAL)
        grid.Add(wx.StaticText(self, label=_('Port')),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        self._port = wx.Choice(self)
        grid.Add(self._port, flag=wx.EXPAND)
        vbox.Add(grid, border=12, flag=wx.LEFT | wx.RIGHT | wx.EXPAND)

        self._verify = wx.CheckBox(
            self, label=_('Read back and verify each radio'))
        self._verify.SetValue(CONF.get_bool('upload_verify', 'prefs', True))
        vbox.Add(self._verify, border=12, flag=wx.ALL)

        self._go = wx.Button(self, wx.ID_ANY,
                             label=_('Program radio %i') % 1)
        self._go.SetBitmap(theme.icon('upload', 20, 'tx'))
        self._go.SetFont(theme.mono_font(12, bold=True))
        theme.keep(self._go, fg=True, font=True)
        self._go.Bind(wx.EVT_BUTTON, self._program)
        vbox.Add(self._go, border=12,
                 flag=wx.LEFT | wx.RIGHT | wx.EXPAND)

        self._gauge = wx.Gauge(self)
        vbox.Add(self._gauge, border=12, flag=wx.ALL | wx.EXPAND)
        self._status = wx.StaticText(self, label='')
        theme.keep(self._status, fg=True)
        vbox.Add(self._status, border=12, flag=wx.LEFT | wx.RIGHT)

        self._list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SIMPLE)
        theme.keep(self._list, fg=True)
        for col, (name, width) in enumerate((
                ('#', 40), (_('Result'), 260), (_('Verify'), 130),
                (_('Time'), 80))):
            self._list.InsertColumn(col, name, width=width)
        vbox.Add(self._list, proportion=1, border=12, flag=wx.ALL | wx.EXPAND)

        self._totals = wx.StaticText(self, label='')
        self._totals.SetFont(theme.mono_font(10, bold=True))
        theme.keep(self._totals, fg=True, font=True)
        vbox.Add(self._totals, border=12, flag=wx.LEFT | wx.RIGHT)

        buttons = self.CreateButtonSizer(wx.CLOSE)
        vbox.Add(buttons, border=12, flag=wx.ALL | wx.EXPAND)
        self.Bind(wx.EVT_BUTTON, self._close, id=wx.ID_CLOSE)
        self.SetEscapeId(wx.ID_CLOSE)

        self._batch = batch_program.Batch(radio, self._open_pipe)
        self._set_ports(portdetect.scan())
        self._show_totals()
        theme.style_dialog(self)
        if theme.enabled():
            self._go.SetForegroundColour(theme.colour('tx'))
            self._list.SetBackgroundColour(theme.colour('field'))
        self.SetSize((640, 620))
        self.SetMinSize((520, 480))
        self.Centre()
        self._go.SetDefault()
        self._go.SetFocus()

    def _set_ports(self, ports):
        self._ports = ports
        self._port.Set([p.label for p in ports])
        device = portdetect.choose_port(
            ports, [CONF.get('last_port', 'state')])
        for i, p in enumerate(ports):
            if p.device == device:
                self._port.SetSelection(i)

    def _open_pipe(self):
        # Called from the worker thread: uses the port picked on the button
        return clone.open_serial(self._device, self._radio)

    def _set_status(self, tone, text):
        self._status.SetForegroundColour(theme.tone(tone))
        self._status.SetLabel('%s %s' % (theme.TAGS[tone], text))
        self.Layout()

    def _program(self, event):
        if self._running or self._port.GetSelection() == wx.NOT_FOUND:
            return
        self._running = True
        self._device = self._ports[self._port.GetSelection()].device
        self._batch.verify = self._verify.GetValue()
        CONF.set_bool('upload_verify', self._batch.verify, 'prefs')
        self._go.Disable()
        self._port.Disable()
        self._verify.Disable()
        number = self._batch.done + 1
        self._set_status('tx', _('Writing radio %i...') % number)
        console.log('tx', _('Batch: writing radio %i') % number)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        def status(s):
            wx.CallAfter(self._progress, s)
        result = self._batch.program_next(status=status)
        wx.CallAfter(self._finished, result)

    def _progress(self, s):
        if not self:
            return
        self._gauge.SetRange(max(1, s.max))
        self._gauge.SetValue(min(s.cur, s.max))

    def _finished(self, result):
        if not self:
            return
        self._running = False
        row = self._list.GetItemCount()
        self._list.InsertItem(row, str(result.number))
        if result.error:
            text, tone = _('ERROR: %s') % result.error, 'bad'
        else:
            text, tone = _('written'), 'ok'
        verify = {None: _('not checked'), True: _('OK'),
                  False: _('%i differences') % result.problems}[
                      result.verified]
        if result.verified is False:
            tone = 'bad'
        self._list.SetItem(row, 1, text)
        self._list.SetItem(row, 2, verify)
        self._list.SetItem(row, 3, '%.0f s' % result.seconds)
        self._list.SetItemTextColour(row, theme.tone(tone))
        self._list.EnsureVisible(row)
        console.log(tone, _('Batch: radio %(n)i %(result)s, verify '
                            '%(verify)s') % {'n': result.number,
                                             'result': text,
                                             'verify': verify})
        if result.ok:
            self._set_status('ok', _('Radio %i done: connect the next one and '
                                     'press the button') % result.number)
            wx.Bell()
        else:
            self._set_status('bad', _('Radio %i failed: check it and press '
                                      'the button to retry with the next '
                                      'one') % result.number)
        self._gauge.SetValue(0)
        self._go.SetLabel(_('Program radio %i') % (self._batch.done + 1))
        self._go.Enable()
        self._port.Enable()
        self._verify.Enable()
        self._go.SetFocus()
        self._show_totals()

    def _show_totals(self):
        b = self._batch
        tone = 'bad' if b.failed else 'ok' if b.done else 'dim'
        self._totals.SetForegroundColour(theme.tone(tone))
        self._totals.SetLabel(
            _('Radios: %(done)i   ok: %(good)i   failed: %(failed)i') % {
                'done': b.done, 'good': b.good, 'failed': b.failed})

    @property
    def programmed(self):
        return self._batch.done

    def _close(self, event):
        if self._running:
            wx.MessageBox(_('Wait for the current radio to finish.'),
                          _('Program several radios'), parent=self)
            return
        self.EndModal(wx.ID_CLOSE)


def can_batch(radio):
    return isinstance(radio, chirp_common.CloneModeRadio)
