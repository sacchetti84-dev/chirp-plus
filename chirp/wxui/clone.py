# Copyright 2022 Dan Smith <chirp@f.danplanet.com>
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

import collections
import logging
import platform
import re
import textwrap
import threading
import webbrowser

import serial
from serial.tools import list_ports
import wx
import wx.lib.sized_controls

from chirp import chirp_common
from chirp import directory
from chirp.drivers import fake
from chirp import errors
from chirp.wxui import config
from chirp.wxui import common
from chirp.wxui import developer
from chirp.wxui import portdetect
from chirp.wxui import serialtrace

_ = wx.GetTranslation
LOG = logging.getLogger(__name__)
CONF = config.get()
HELPME = _('Help Me...')
CUSTOM = _('Custom...')
ID_RECENT = wx.NewId()
ID_REFRESH_PORTS = wx.NewId()
ID_SEARCH_MODEL = wx.NewId()

PORT_COLORS = {
    'good': wx.Colour(0x1B, 0x7F, 0x2A),
    'warn': wx.Colour(0xB3, 0x5C, 0x00),
    'bad': wx.Colour(0xC6, 0x28, 0x28),
}


def is_prolific_warning(string):
    return 'PL2303' in string and 'CONTACT YOUR SUPPLIER' in string


def get_model_label(rclass):
    detected = ','.join(set([
        detected_value(rclass, m)
        for m in rclass.detected_models(include_self=False)
        if not m.is_minor_variant()]))
    if len(detected) > (32 - 5):
        detected = 'others'
    return detected


def get_fakes():
    return {
        'Fake NOP': developer.FakeSerial,
        'Fake Echo NOP': developer.FakeEchoSerial,
        'Fake F7E': fake.FakeKenwoodSerial,
        'Fake UV17': fake.FakeUV17Serial,
        'Fake UV17Pro': fake.FakeUV17ProSerial,
        'Fake AT778': developer.FakeAT778,
        'Fake Open Error': developer.FakeErrorOpenSerial,
    }


class CloneThread(threading.Thread):
    def __init__(self, radio, dialog, fn):
        super(CloneThread, self).__init__()
        self._radio = radio
        self._dialog = dialog
        self._fn = getattr(self._radio, fn)
        self._radio.status_fn = self._status

    def stop(self):
        LOG.warning('Stopping clone thread')

        # Clear out our dialog reference, which should stop us from
        # eventing to a missing window, and reporting error, when we have
        # already been asked to cancel
        self._dialog = None

        # Close the serial, which should stop the clone soon
        self._radio.pipe.close()

    def _status(self, status):
        self._dialog._status(status)

    def run(self):
        try:
            self._fn()
        except errors.SpecificRadioError as e:
            if self._dialog:
                LOG.exception('Failed to clone: %s', e)
                self._dialog.fail(e)
            else:
                LOG.warning('Clone failed after cancel: %s', e)
        except Exception as e:
            if self._dialog:
                LOG.exception('Failed to clone: %s' % e)
                self._dialog.fail(str(e))
            else:
                LOG.warning('Clone failed after cancel: %s', e)
        else:
            if self._dialog:
                self._dialog.complete()
        finally:
            try:
                self._radio.pipe.close()
            except OSError:
                # If we were canceled and we have already closed an active
                # serial, this will fail with EBADF
                pass


# NOTE: This is the legacy settings thread that facilitates
# LiveAdapter to get/fetch settings.
class SettingsThread(threading.Thread):
    def __init__(self, radio, progdialog, settings=None):
        super(SettingsThread, self).__init__()
        self._radio = radio
        self._dialog = progdialog
        self.settings = settings
        self._dialog.SetRange(100)
        self.error = None

    def run(self):
        self._radio.pipe.open()
        try:
            self._run()
        except Exception as e:
            LOG.exception('Failed during setting operation')
            wx.CallAfter(self._dialog.Update, 100)
            self.error = str(e)
        finally:
            self._radio.pipe.close()

    def _run(self):
        if self.settings:
            msg = _('Applying settings')
        else:
            msg = _('Loading settings')
        wx.CallAfter(self._dialog.Update, 10, newmsg=msg)
        if self.settings:
            self._radio.set_settings(self.settings)
        else:
            self.settings = self._radio.get_settings()
        wx.CallAfter(self._dialog.Update, 100, newmsg=_('Complete'))


def open_serial(port, rclass):
    if port.startswith('Fake'):
        return get_fakes()[port]()
    if '://' in port:
        pipe = serial.serial_for_url(port, do_not_open=True)
        pipe.timeout = 0.25
        pipe.rtscts = rclass.HARDWARE_FLOW
        pipe.rts = rclass.WANTS_RTS
        pipe.dtr = rclass.WANTS_DTR
        pipe.open()
        pipe.baudrate = rclass.BAUD_RATE
    else:
        pipe = serialtrace.SerialTrace(
            baudrate=rclass.BAUD_RATE,
            rtscts=rclass.HARDWARE_FLOW, timeout=0.25)
        pipe.rts = rclass.WANTS_RTS
        pipe.dtr = rclass.WANTS_DTR
        pipe.port = port
        pipe.open()

    LOG.debug('Serial opened: %s (rts=%s dtr=%s)',
              pipe, pipe.rts, pipe.dtr)
    return pipe


class ChirpRadioPromptDialog(wx.Dialog):
    def __init__(self, *a, **k):
        self.radio = k.pop('radio')
        self.rconfig = config.get_for_radio(self.radio)
        self.prompt = k.pop('prompt')
        buttons = k.pop('buttons', wx.OK | wx.CANCEL)
        super().__init__(*a, **k)

        prompts = self.radio.get_prompts()
        self.message = getattr(prompts, self.prompt)

        if '\n' not in self.message:
            self.message = '\n'.join(textwrap.wrap(self.message))

        bs = self.CreateButtonSizer(buttons)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)
        instructions = wx.StaticText(self)
        instructions.SetLabelMarkup(self.message)
        vbox.Add(instructions,
                 border=20, flag=wx.ALL)
        if self.prompt == 'experimental':
            risk_warning = wx.StaticText(self)
            risk_warning.SetLabelMarkup(_('Do you accept the risk?'))
            vbox.Add(risk_warning, border=20, flag=wx.ALL)
        self.cb = wx.CheckBox(
            self, label=_("Do not prompt again for %s") % (
                '%s %s' % (self.radio.VENDOR, self.radio.MODEL)))
        vbox.Add(self.cb, border=20, flag=wx.ALL)
        vbox.Add(bs, flag=wx.ALL, border=10)
        self.Fit()
        self.Centre()

    def persist_flag(self, radio, flag):
        key = 'prompt_%s' % flag.lower()
        self.rconfig.set_bool(key, not self.cb.IsChecked())
        oldkey = '%s_%s' % (flag, directory.radio_class_id(radio))
        if CONF.is_defined(oldkey, 'clone_prompts'):
            CONF.remove_option(oldkey, 'clone_prompts')

    def check_flag(self, radio, flag):
        key = 'prompt_%s' % flag.lower()
        if not self.rconfig.is_defined(key):
            # FIXME: Remove this compatibility at some point
            oldkey = '%s_%s' % (flag, directory.radio_class_id(radio))
            return CONF.get_bool(oldkey.lower(), 'clone_prompts', True)
        return self.rconfig.get_bool(key, default=True)

    def ShowModal(self):
        if not self.message:
            LOG.debug('No %s prompt for radio' % self.prompt)
            return wx.ID_OK
        if not self.check_flag(self.radio, self.prompt):
            LOG.debug('Prompt %s disabled for radio' % self.prompt)
            return wx.ID_OK
        LOG.debug('Showing %s prompt' % self.prompt)
        status = super().ShowModal()
        if status in (wx.ID_OK, wx.ID_YES):
            LOG.debug('Setting flag for prompt %s' % self.prompt)
            self.persist_flag(self.radio, self.prompt)
        else:
            LOG.debug('No flag change for %s' % self.prompt)
        return status


def port_label(port):
    if platform.system() == 'Windows':
        # The OS format for description is "Long Name (COMn)", so use
        # port: desc to make the port visible early in the string without
        # changing the description format.
        label_fmt = '%(dev)s: %(desc)s'
    else:
        label_fmt = '%(desc)s (%(dev)s)'
    dev = port.device
    if dev.startswith('/dev/'):
        dev = dev.split('/dev/')[1]
    if not port.description:
        return dev
    elif port.description == 'n/a':
        return dev
    else:
        return label_fmt % ({'desc': port.description,
                             'dev': dev})


def port_sort_key(port):
    key = port.device
    if platform.system() == 'Windows':
        try:
            m = re.match('^COM([0-9]+)$', port.device)
            if m:
                key = 'COM%08i' % int(m.group(1))
        except Exception as e:
            LOG.warning('Failed to stable format %s: %s', port.device, e)

    return key


def model_value(rclass):
    return ('%s %s' % (rclass.MODEL, rclass.VARIANT)).strip()


def detected_value(parent_rclass, rclass):
    """Try to calculate a label for detected classes.

    This should be short and only represent the difference between them (like
    a VARIANT or different MODEL).
    """
    if parent_rclass.MODEL != rclass.MODEL:
        # If the model is different, use that
        label = rclass.MODEL
        # If the detected class is a modified MODEL (i.e. 'RT95' and 'RT95 VOX'
        # then strip off the prefix and the delimiter, if any.
        if label.startswith(parent_rclass.MODEL):
            label = label.replace(parent_rclass.MODEL, '').strip(' -_')
    else:
        # Assume the VARIANT is the distinguisher
        label = rclass.VARIANT

    # In case the detected class is a different vendor, prefix that
    if parent_rclass.VENDOR != rclass.VENDOR:
        label = '%s %s' % (rclass.VENDOR, label)

    label = label.strip()
    if not label:
        LOG.error('Calculated blank detected value of %s from %s',
                  rclass, parent_rclass)
    return label


# Make this global so it sticks for a session
CUSTOM_PORTS = []


class ChirpModelSearchDialog(wx.Dialog):
    """Find a radio model by typing part of its vendor or model name."""
    def __init__(self, parent, entries):
        """:param entries: list of (vendor, model, display) tuples"""
        super().__init__(parent, title=_('Find your radio'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entries = entries
        self._shown = []
        self.selection = None

        vbox = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(vbox)
        hint = wx.StaticText(
            self, label=_('Type part of the vendor or model name '
                          '(for example "UV-5R" or "Baofeng")'))
        vbox.Add(hint, border=10, flag=wx.ALL)
        self._search = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self._search.ShowCancelButton(True)
        self._search.SetDescriptiveText(_('Search radio'))
        vbox.Add(self._search, border=10,
                 flag=wx.EXPAND | wx.LEFT | wx.RIGHT)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE)
        vbox.Add(self._list, proportion=1, border=10, flag=wx.EXPAND | wx.ALL)
        bs = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(bs, border=10, flag=wx.ALL | wx.EXPAND)

        self._search.Bind(wx.EVT_TEXT, self._filter)
        self._search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._clear)
        self._search.Bind(wx.EVT_TEXT_ENTER, self._accept)
        # Newer wx reports Enter in a search control as a search event
        self._search.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self._accept)
        self._list.Bind(wx.EVT_LISTBOX_DCLICK, self._accept)
        self.Bind(wx.EVT_BUTTON, self._accept, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._key)

        self._filter(None)
        self.SetSize((480, 520))
        self.SetMinSize((360, 300))
        self.Centre()
        self._search.SetFocus()

    def _clear(self, event):
        self._search.SetValue('')

    def _key(self, event):
        # Let up/down move through the results while typing in the search
        step = {wx.WXK_UP: -1, wx.WXK_DOWN: 1}.get(event.GetKeyCode())
        if step is None or not self._shown:
            event.Skip()
            return
        idx = self._list.GetSelection() + step
        self._list.SetSelection(max(0, min(len(self._shown) - 1, idx)))

    def _filter(self, event):
        words = self._search.GetValue().lower().split()

        def matches(entry):
            text = ('%s %s' % (entry[0], entry[2])).lower()
            # Ignore dashes so "uv5r" finds "UV-5R"
            squashed = text.replace('-', '').replace(' ', '')
            return all(w in text or w.replace('-', '') in squashed
                       for w in words)

        self._shown = [e for e in self._entries if matches(e)]
        self._list.Set(['%s %s' % (e[0], e[2]) for e in self._shown])
        if self._shown:
            self._list.SetSelection(0)
        ok = self.FindWindowById(wx.ID_OK)
        if ok:
            ok.Enable(bool(self._shown))

    def _accept(self, event):
        idx = self._list.GetSelection()
        if idx == wx.NOT_FOUND or not self._shown:
            return
        vendor, model, _display = self._shown[idx]
        self.selection = (vendor, model)
        self.EndModal(wx.ID_OK)


class ChirpCloneDialog(wx.Dialog):
    def __init__(self, *a, **k):
        allow_detected_models = k.pop('allow_detected_models', False)
        super(ChirpCloneDialog, self).__init__(
            *a, title=_('Communicate with radio'), **k)
        self._clone_thread = None
        self._running = False
        # Set when the user explicitly picks a port in this dialog, so that
        # automatic detection never fights with them.
        self._user_chose_port = False
        self._model_ready = False
        self._portinfo = {}
        grid = wx.FlexGridSizer(2, 5, 5)
        grid.AddGrowableCol(1)
        bs = self.CreateButtonSizer(wx.OK | wx.CANCEL)

        if developer.developer_mode():
            for fakeserial in get_fakes().keys():
                if fakeserial not in CUSTOM_PORTS:
                    CUSTOM_PORTS.append(fakeserial)

        def _add_grid(label, control):
            grid.Add(wx.StaticText(self, label=label),
                     proportion=1, border=10,
                     flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT | wx.LEFT)
            grid.Add(control,
                     proportion=1, border=10,
                     flag=wx.EXPAND | wx.RIGHT | wx.LEFT)

        port_panel = wx.Panel(self)
        port_vbox = wx.BoxSizer(wx.VERTICAL)
        port_panel.SetSizer(port_vbox)
        port_hbox = wx.BoxSizer(wx.HORIZONTAL)
        port_vbox.Add(port_hbox, flag=wx.EXPAND)
        self._port = wx.Choice(port_panel, choices=[])
        self._port.SetMinSize((260, -1))
        self._refresh = wx.Button(port_panel, ID_REFRESH_PORTS,
                                  label=_('Refresh'))
        self._refresh.SetToolTip(_('Search again for connected cables'))
        port_hbox.Add(self._port, proportion=1, border=10, flag=wx.RIGHT)
        port_hbox.Add(self._refresh)
        status_hbox = wx.BoxSizer(wx.HORIZONTAL)
        port_vbox.Add(status_hbox, border=4, flag=wx.TOP | wx.EXPAND)
        self._port_icon = wx.StaticBitmap(port_panel)
        self._port_status = wx.StaticText(port_panel, label='')
        status_hbox.Add(self._port_icon, border=4,
                        flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        status_hbox.Add(self._port_status, proportion=1,
                        flag=wx.ALIGN_CENTER_VERTICAL)
        self.Bind(wx.EVT_CHOICE, self._selected_port, self._port)
        _add_grid(_('Port'), port_panel)
        self.set_ports()

        panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(hbox)
        self._vendor = wx.Choice(panel, choices=['Icom', 'Yaesu'])
        self.Bind(wx.EVT_CHOICE, self._selected_vendor, self._vendor)
        self._recent = wx.Button(panel, ID_RECENT, label=_('Recent...'))
        self._recent.Enable(bool(CONF.get('recent_models', 'state')))
        self._search_model = wx.Button(panel, ID_SEARCH_MODEL,
                                       label=_('Search...'))
        self._search_model.SetToolTip(
            _('Find your radio by typing part of its name'))
        hbox.Add(self._vendor, proportion=1, border=10, flag=wx.RIGHT)
        hbox.Add(self._recent, border=5, flag=wx.RIGHT)
        hbox.Add(self._search_model)
        _add_grid(_('Vendor'), panel)

        self._model_choices = []
        self._model = wx.Choice(self, choices=self._model_choices)
        _add_grid(_('Model'), self._model)
        self.Bind(wx.EVT_CHOICE, self._selected_model, self._model)

        self.gauge = wx.Gauge(self)

        self.Bind(wx.EVT_BUTTON, self._action)

        vbox = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label=_(
            'Connect the programming cable to the radio and to the '
            'computer, then turn the radio on. The cable port is detected '
            'automatically.'))
        intro.Wrap(460)
        vbox.Add(intro, border=15, flag=wx.LEFT | wx.RIGHT | wx.TOP)
        vbox.Add(grid, proportion=1,
                 flag=wx.TOP | wx.BOTTOM | wx.EXPAND,
                 border=15)
        self.model_msg = wx.StaticText(
            self,
            label='',
            style=(wx.ALIGN_CENTER_HORIZONTAL | wx.ST_NO_AUTORESIZE |
                   wx.ELLIPSIZE_END))
        self.status_msg = wx.StaticText(
            self, label='',
            style=(wx.ALIGN_CENTER_HORIZONTAL | wx.ST_NO_AUTORESIZE |
                   wx.ELLIPSIZE_END))
        vbox.Add(self.status_msg,
                 border=5, proportion=0,
                 flag=wx.EXPAND | wx.BOTTOM)
        vbox.Add(self.gauge, flag=wx.EXPAND | wx.RIGHT | wx.LEFT, border=10,
                 proportion=0)
        vbox.Add(self.model_msg,
                 border=5, proportion=0,
                 flag=wx.EXPAND | wx.BOTTOM)
        vbox.Add(wx.StaticLine(self), flag=wx.EXPAND | wx.ALL, border=5)
        vbox.Add(bs, flag=wx.ALL, border=10)
        self.SetSizer(vbox)
        self.Center()

        self._vendors = collections.defaultdict(list)
        for rclass in directory.DRV_TO_RADIO.values():
            if (not issubclass(rclass, chirp_common.CloneModeRadio) and
                    not issubclass(rclass, chirp_common.LiveRadio)):
                continue
            if (getattr(rclass, '_DETECTED_BY', None) and
                    not allow_detected_models):
                continue
            self._vendors[rclass.VENDOR].append(rclass)
            self._add_aliases(rclass)

        for models in self._vendors.values():
            models.sort(key=lambda x: '%s %s' % (x.MODEL, x.VARIANT))

        self._vendor.Set(sorted(self._vendors.keys()))
        try:
            self.select_vendor_model(CONF.get('last_vendor', 'state'),
                                     CONF.get('last_model', 'state'))
        except ValueError:
            LOG.warning('Last vendor/model (%s/%s) not found',
                        CONF.get('last_vendor', 'state'),
                        CONF.get('last_model', 'state'))
        self._model_ready = True
        self._select_port_for_model()

        self.SetMinSize((520, 300))
        self.Fit()

        self._monitor = portdetect.get_monitor()
        self._monitor.add_listener(self._ports_changed_bg)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._destroyed)

    def _destroyed(self, event):
        event.Skip()
        if event.GetEventObject() is self:
            self._monitor.remove_listener(self._ports_changed_bg)

    def _ports_changed_bg(self, ports, added, removed):
        # Called from the monitor thread
        wx.CallAfter(self._ports_changed, ports, added, removed)

    def _ports_changed(self, ports, added, removed):
        if not self or self._running:
            # Dialog is gone, or we are talking to the radio right now
            return
        known = {p.device for p in self._portinfo.values()}
        new_devices = {p.device for p in ports}
        if new_devices == known:
            return
        current = self.get_selected_port()
        new_cables = [p for p in ports if p.device in added and p.is_cable]
        if new_cables:
            # A cable was just plugged in: that is almost certainly the one
            # the user wants, even if they picked something else before.
            cable = new_cables[0]
            self._user_chose_port = False
            self.set_ports(ports, select=cable.device)
            self._set_port_status(
                'good', _('New cable connected on %s') % cable.short_device,
                cable)
        elif current in removed:
            self._user_chose_port = False
            self.set_ports(ports)
            self._set_port_status(
                'bad', _('The cable on %s was disconnected') % current)
        else:
            self.set_ports(ports, select=current)

    def _preferred_ports(self):
        preferred = []
        if self._model_ready:
            try:
                rconfig = config.get_for_radio(self.get_selected_rclass())
                preferred.append(rconfig.get('last_port'))
            except Exception as e:
                LOG.debug('No per-model port: %s', e)
        preferred.append(CONF.get('last_port', 'state'))
        return [p for p in preferred if p]

    def set_ports(self, system_ports=None, select=None):
        if system_ports and isinstance(system_ports[0], portdetect.PortInfo):
            ports = system_ports
        else:
            # An empty list means "nothing found", None means "go look"
            ports = portdetect.scan(system_ports or None)

        LOG.debug('All system ports: %s', ports)
        self._portinfo = {p.device: p for p in ports}
        self.ports = [(p.device, p.label) for p in ports]

        favorite_ports = CONF.get('favorite_ports', 'state') or ''
        for port in favorite_ports.split(','):
            if port and port not in [x[0] for x in self.ports]:
                self.ports.insert(0, (port, port))

        for port in CUSTOM_PORTS:
            if port not in [x[0] for x in self.ports]:
                self.ports.insert(0, (port, port))

        if not select:
            select = portdetect.choose_port(ports, self._preferred_ports())

        if not self.ports:
            LOG.warning('No ports available; action will be disabled')
        okay_btn = self.FindWindowById(self.GetAffirmativeId())
        okay_btn.Enable(bool(self.ports))

        self._port.SetItems([x[1] for x in self.ports] +
                            [CUSTOM, HELPME])
        for device, name in self.ports:
            if device == select:
                self._port.SetStringSelection(name)
                break
        else:
            if self.ports:
                port = self.ports[0]
                self._port.SetStringSelection(port[1])
            else:
                port = '(no ports available)'
            LOG.warning('Last port %r is unavailable, defaulting to %s',
                        select, port)
        self._update_port_status()

    def _set_port_status(self, level, text, info=None):
        if info is not None and info.hint:
            text = '%s - %s' % (text, wx.GetTranslation(info.hint))
        art = {'good': wx.ART_TICK_MARK,
               'warn': wx.ART_WARNING,
               'bad': wx.ART_ERROR}.get(level, wx.ART_INFORMATION)
        self._port_icon.SetBitmap(
            wx.ArtProvider.GetBitmap(art, wx.ART_MENU, (16, 16)))
        self._port_status.SetForegroundColour(
            PORT_COLORS.get(level, wx.SystemSettings.GetColour(
                wx.SYS_COLOUR_WINDOWTEXT)))
        self._port_status.SetLabel(text)
        self._port_status.Wrap(420)
        self._port_status.SetToolTip(text)
        self.Layout()

    def _update_port_status(self):
        if not self.ports:
            self._set_port_status(
                'bad', _('No serial port found. Check the cable and its '
                         'driver, then press Refresh.'))
            return
        device = self.get_selected_port()
        info = self._portinfo.get(device)
        cables = [p for p in self._portinfo.values() if p.is_cable]
        if info is None:
            self._set_port_status('info', _('Manually entered port'))
        elif not info.usable:
            self._set_port_status('bad', info.short_device, info)
        elif info.is_cable:
            if len(cables) > 1:
                self._set_port_status(
                    'warn', _('%i cables found, %s selected: check that it '
                              'is the right one') % (len(cables),
                                                     info.short_device))
            else:
                self._set_port_status('good', info.chip or info.short_device,
                                      info)
        elif cables:
            self._set_port_status(
                'warn', _('%s is probably not your cable, %s looks like a '
                          'programming cable') % (info.short_device,
                                                  cables[0].short_device))
        else:
            self._set_port_status(
                'warn', _('No programming cable recognized, %s selected') %
                info.short_device, info)

    def get_selected_port(self):
        selected = self._port.GetStringSelection()
        for device, name in self.ports:
            if name == selected:
                return device
        LOG.warning('Did not find device for selected port %s' % selected)
        return selected

    def set_selected_port(self, devname):
        for device, name in self.ports:
            if device == devname:
                self._port.SetStringSelection(name)
                return True
        else:
            LOG.debug('Port %s not in current list', devname)

    def _port_assist(self, event):
        r = wx.MessageBox(
            _('Unplug your cable (if needed) and then click OK'),
            _('USB Port Finder'),
            style=wx.OK | wx.CANCEL | wx.OK_DEFAULT, parent=self)
        if r == wx.CANCEL:
            return
        before = list_ports.comports()
        r = wx.MessageBox(
            _('Plug in your cable and then click OK'),
            _('USB Port Finder'),
            style=wx.OK | wx.CANCEL | wx.OK_DEFAULT, parent=self)
        if r == wx.CANCEL:
            return
        after = list_ports.comports()
        before_devs = {p.device for p in before}
        changed = [p for p in after if p.device not in before_devs]
        found = None
        if not changed:
            wx.MessageBox(
                _('Unable to determine port for your cable. '
                  'Check your drivers and connections.'),
                _('USB Port Finder'), parent=self)
            self.set_ports(after)
            return
        elif len(changed) == 1:
            found = portdetect.classify(changed[0])
            msg = '%s\n%s' % (_('Your cable appears to be on port:'),
                              found.label)
            if found.warning:
                msg += '\n\n' + wx.GetTranslation(found.warning)
            wx.MessageBox(msg, _('USB Port Finder'), parent=self)
        else:
            wx.MessageBox(
                _('More than one port found: %s') % ', '.join(
                    p.device for p in changed),
                _('USB Port Finder'), parent=self)
            self.set_ports(after)
            return
        self._user_chose_port = True
        self.set_ports(after, select=found.device)

    def _prolific_assist(self, event):
        r = wx.MessageBox(
            _('Your Prolific-based USB device will not work without '
              'reverting to an older version of the driver. Visit the '
              'CHIRP website to read more about how to resolve this?'),
            _('Prolific USB device'),
            style=wx.YES | wx.NO | wx.YES_DEFAULT, parent=self)
        if r == wx.YES:
            webbrowser.open(
                'https://chirpmyradio.com/projects/chirp/wiki/'
                'ProlificDriverDeprecation')

    def _add_aliases(self, rclass):
        for alias in rclass.ALIASES:
            class DynamicRadioAlias(rclass):
                _orig_rclass = rclass
                VENDOR = alias.VENDOR
                MODEL = alias.MODEL
                VARIANT = alias.VARIANT

            self._vendors[alias.VENDOR].append(DynamicRadioAlias)

    def disable_model_select(self):
        self._vendor.Disable()
        self._model.Disable()
        self._recent.Disable()
        self._search_model.Disable()

    def enable_model_select(self):
        self._vendor.Enable()
        self._model.Enable()
        self._recent.Enable()
        self._search_model.Enable()

    def disable_running(self):
        self._running = True
        self._port.Disable()
        self._refresh.Disable()
        self.FindWindowById(wx.ID_OK).Disable()

    def enable_running(self):
        self._running = False
        self._port.Enable()
        self._refresh.Enable()
        self.FindWindowById(wx.ID_OK).Enable()

    def _persist_choices(self):
        raise NotImplementedError()

    def _refresh_ports(self):
        current = self.get_selected_port() if self._user_chose_port else None
        self.set_ports(select=current)

    def _search_models(self):
        entries = []
        for vendor in sorted(self._vendors):
            for rclass in self._vendors[vendor]:
                display = model_value(rclass)
                detected = get_model_label(rclass)
                if detected:
                    display += ' (+ %s)' % detected
                entries.append((vendor, model_value(rclass), display))
        with ChirpModelSearchDialog(self, entries) as d:
            if d.ShowModal() != wx.ID_OK or not d.selection:
                return
            vendor, model = d.selection
        self.select_vendor_model(vendor, model)
        self._selected_model(None)

    def _selected_port(self, event):
        okay_btn = self.FindWindowById(self.GetAffirmativeId())
        if self._port.GetStringSelection() == CUSTOM:
            port = wx.GetTextFromUser(_('Enter custom port:'),
                                      _('Custom Port'),
                                      parent=self)
            if port:
                CUSTOM_PORTS.append(port)
                self._user_chose_port = True
            self.set_ports(select=port or None)
            return
        elif self._port.GetStringSelection() == HELPME:
            self._port_assist(event)
            return
        self._user_chose_port = True
        self._update_port_status()
        info = self._portinfo.get(self.get_selected_port())
        if (is_prolific_warning(self._port.GetStringSelection()) or
                (info is not None and not info.usable)):
            self._prolific_assist(event)
            okay_btn.Enable(False)
            return
        self._persist_choices()
        okay_btn.Enable(True)

    def _select_vendor(self, vendor):
        display_models = []
        actual_models = []
        for rclass in self._vendors[vendor]:
            display = model_value(rclass)
            actual_models.append(display)
            detected = get_model_label(rclass)
            if detected:
                display += ' (+ %s)' % detected
            display_models.append(display)

        self._model_choices = actual_models
        self._model.Set(display_models)
        self._model.SetSelection(0)

    def _do_recent(self):
        recent = CONF.get('recent_models', 'state')
        if recent:
            recent = recent.split(';')
        else:
            recent = []
        recent_strs = ['%s %s' % tuple(vm.split(':', 1)) for vm in recent]
        d = wx.SingleChoiceDialog(self,
                                  _('Choose a recent model'),
                                  _('Recent'),
                                  recent_strs)
        box = d.GetSizer()
        panel = wx.Panel(d)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(hbox)
        box.Insert(box.GetItemCount() - 1, panel)

        def remove_selected(event):
            listbox = [x for x in d.GetChildren()
                       if isinstance(x, wx.ListBox)][0]
            idx = listbox.GetSelection()
            listbox.Delete(idx)
            del recent_strs[idx]
            del recent[idx]
            CONF.set('recent_models', ';'.join(recent), 'state')
            listbox.SetSelection(max(0, idx - 1))

        always = wx.CheckBox(panel, label=_('Always start with recent list'))
        always.SetValue(CONF.get_bool('always_start_recent', 'state'))
        remove = wx.Button(panel, label=_('Remove'))
        remove.SetToolTip(_('Remove selected model from list'))
        remove.Bind(wx.EVT_BUTTON, remove_selected)
        hbox.Add(always, border=10, flag=wx.ALL | wx.EXPAND)
        hbox.Add(remove, border=10, flag=wx.ALL)

        d.SetSize((400, 400))
        d.SetMinSize((400, 400))
        d.SetMaxSize((400, 400))
        d.Center()
        c = d.ShowModal()
        if c == wx.ID_OK and recent:
            vendor, model = recent[d.GetSelection()].split(':')
            self.select_vendor_model(vendor, model)
            CONF.set_bool('always_start_recent', always.GetValue(), 'state')

    def _selected_vendor(self, event):
        self._select_vendor(event.GetString())
        self._persist_choices()
        self._select_port_for_model()

    def _selected_model(self, event):
        self._persist_choices()
        self._select_port_for_model()

    def select_vendor_model(self, vendor, model):
        self._vendor.SetSelection(self._vendor.GetItems().index(vendor))
        self._select_vendor(vendor)
        self._model.SetSelection(self._model_choices.index(model))
        self._select_port_for_model()

    def _select_port_for_model(self):
        if not self._model_ready:
            # Still building the dialog; __init__ calls us when ready
            return
        vendor = self._vendor.GetStringSelection()
        model = self._model.GetStringSelection()
        if self._user_chose_port:
            LOG.debug('Keeping user-chosen port %s for %s %s',
                      self.get_selected_port(), vendor, model)
            return

        ports = list(self._portinfo.values())
        port = portdetect.choose_port(ports, self._preferred_ports())
        if port and self.set_selected_port(port):
            LOG.debug('Automatically chose port %s for %s %s',
                      port, vendor, model)
        else:
            LOG.debug('No recent/available port for %s %s', vendor, model)
        self._update_port_status()

    def _remember_port_for_selected(self):
        rclass = self.get_selected_rclass()
        rconfig = config.get_for_radio(rclass)
        port = self.get_selected_port()
        rconfig.set('last_port', port)
        LOG.debug('Recorded last-used port %s for %s %s',
                  port, rclass.VENDOR, rclass.MODEL)

    def _status(self, status):
        def _safe_status():
            self.gauge.SetRange(status.max)
            self.gauge.SetValue(min(status.cur, status.max))
            self.status_msg.SetLabel(status.msg)

        wx.CallAfter(_safe_status)

    def complete(self):
        self._radio.pipe.close()
        wx.CallAfter(self.EndModal, wx.ID_OK)

    def fail(self, error):
        def safe_fail():
            common.error_proof.show_error(
                error, parent=self,
                title=_('Error communicating with radio'))
            if isinstance(self, ChirpDownloadDialog):
                self.enable_model_select()
            self.enable_running()
        wx.CallAfter(safe_fail)

    def cancel_action(self):
        if isinstance(self, ChirpDownloadDialog):
            self.enable_model_select()
        self._running = False
        self._port.Enable()
        self._refresh.Enable()
        s = chirp_common.Status()
        s.cur = 0
        s.max = 1
        s.msg = ''
        self._status(s)
        self.FindWindowById(wx.ID_OK).Enable()

    def get_selected_rclass(self):
        vendor = self._vendor.GetStringSelection()
        model = self._model.GetSelection()
        LOG.debug('Selected %r' % self._vendors[vendor][model])
        return self._vendors[vendor][model]

    def _action(self, event):
        id = event.GetEventObject().GetId()
        if id == wx.ID_CANCEL:
            if self._clone_thread:
                self._clone_thread.stop()
            self.EndModal(id)
            return
        elif id == ID_REFRESH_PORTS:
            self._refresh_ports()
            return
        elif id == ID_SEARCH_MODEL:
            self._search_models()
            return
        try:
            self._actual_action(event)
        except Exception as e:
            self.fail(str(e))
            return


class ChirpDownloadDialog(ChirpCloneDialog):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.SetTitle(_('Download from radio'))
        self.FindWindowById(wx.ID_OK).SetLabel(_('Download'))
        if (CONF.get_bool('always_start_recent', 'state') and
                CONF.get('recent_models', 'state')):
            self._do_recent()
        # Clean up old-style port recall
        CONF.remove_section('port_recall')

    def _selected_model(self, event):
        super(ChirpDownloadDialog, self)._selected_model(event)
        rclass = self.get_selected_rclass()
        prompts = rclass.get_prompts()
        self.model_msg.SetLabel('')
        if prompts.experimental:
            d = ChirpRadioPromptDialog(
                self,
                title=_('Experimental driver'),
                buttons=wx.YES_NO | wx.NO_DEFAULT,
                radio=rclass,
                prompt='experimental')
            d.SetAffirmativeId(wx.ID_YES)
            d.SetEscapeId(wx.ID_NO)
            r = d.ShowModal()
            if r == wx.ID_CANCEL:
                LOG.info('User did not accept experimental risk for %s',
                         rclass)
                self.FindWindowById(wx.ID_OK).Disable()
            else:
                LOG.info('User accepted experimental risk for %s',
                         rclass)
                self.FindWindowById(wx.ID_OK).Enable()

    def _actual_action(self, event):
        id = event.GetEventObject().GetId()
        if id == ID_RECENT:
            self._do_recent()
            return

        self._persist_choices()
        self.disable_model_select()
        self.disable_running()

        port = self.get_selected_port()
        LOG.debug('Using port %r' % port)
        rclass = self.get_selected_rclass()

        prompts = rclass.get_prompts()
        if prompts.info:
            d = ChirpRadioPromptDialog(self,
                                       title=_('Radio information'),
                                       radio=rclass,
                                       prompt='info')
            if d.ShowModal() != wx.ID_OK:
                self.cancel_action()
                return
        if prompts.pre_download:
            d = ChirpRadioPromptDialog(self,
                                       title=_('Download instructions'),
                                       radio=rclass,
                                       prompt='pre_download')
            if d.ShowModal() != wx.ID_OK:
                self.cancel_action()
                return

        serial = open_serial(port, rclass)

        # See if the driver detects we should be using a different radio class
        # to communicate with this model
        try:
            rclass = rclass.detect_from_serial(serial)
            LOG.info('Detected %s from serial', rclass)
        except NotImplementedError:
            pass
        except errors.RadioError as e:
            LOG.error('Radio serial detection failed: %s', e)
            self.fail(str(e))
            return
        except Exception as e:
            LOG.exception('Exception during detection: %s', e)
            self.fail(_('Internal driver error'))
            return

        self.model_msg.SetLabel('%s %s %s' % (
            rclass.VENDOR, rclass.MODEL, rclass.VARIANT))

        self._remember_port_for_selected()

        try:
            self._radio = rclass(serial)
        except Exception as e:
            LOG.exception('Failed to open serial: %s' % e)
            self.fail(str(e))
            return

        if isinstance(self._radio, chirp_common.LiveRadio):
            if CONF.get_bool('live_adapter', 'state', False):
                # Use LiveAdapter to make LiveRadio behave like CloneMode
                self._radio = common.LiveAdapter(self._radio)
            else:
                # Live radios are live
                # FIXME: This needs to make sure we can talk to the radio first
                self.EndModal(wx.ID_OK)
                return

        self._radio.status_fn = self._status

        self._clone_thread = CloneThread(self._radio, self, 'sync_in')
        self._clone_thread.start()

    def _persist_choices(self):
        # On download, persist the selections from the actual UI boxes
        CONF.set('last_vendor', self._vendor.GetStringSelection(), 'state')
        CONF.set('last_model', self._model_choices[self._model.GetSelection()],
                 'state')
        CONF.set('last_port', self.get_selected_port(), 'state')
        recent = CONF.get('recent_models', 'state')
        if recent:
            recent = recent.split(';')
        else:
            recent = []
        modelstr = '%s:%s' % (self._vendor.GetStringSelection(),
                              self._model_choices[self._model.GetSelection()])
        if modelstr in recent:
            recent.remove(modelstr)
        recent.insert(0, modelstr)
        recent = recent[:10]
        CONF.set('recent_models', ';'.join(recent), 'state')


class ChirpUploadDialog(ChirpCloneDialog):
    def __init__(self, radio, *a, **k):
        super(ChirpUploadDialog, self).__init__(*a, allow_detected_models=True,
                                                **k)
        self.SetTitle(_('Upload to radio'))
        self.FindWindowById(wx.ID_OK).SetLabel(_('Upload'))
        self._radio = radio

        self.select_vendor_model(self._radio.VENDOR, model_value(self._radio))
        self.disable_model_select()

        if isinstance(self._radio, chirp_common.LiveRadio):
            self._radio = common.LiveAdapter(self._radio)

    def _actual_action(self, event):
        self._persist_choices()
        self.disable_running()
        port = self.get_selected_port()

        prompts = self._radio.get_prompts()
        if prompts.info:
            d = ChirpRadioPromptDialog(self,
                                       title=_('Radio information'),
                                       radio=self._radio,
                                       prompt='info')
            if d.ShowModal() != wx.ID_OK:
                self.cancel_action()
                return

        if prompts.display_pre_upload_prompt_before_opening_port:
            s = None
        else:
            LOG.debug('Opening serial %r before upload prompt' % port)
            s = open_serial(port, self._radio)

        if prompts.pre_upload:
            d = ChirpRadioPromptDialog(self,
                                       title=_('Upload instructions'),
                                       radio=self._radio,
                                       prompt='pre_upload')
            if d.ShowModal() != wx.ID_OK:
                self.cancel_action()
                if s:
                    s.close()
                return

        baud = self._radio.BAUD_RATE
        if self._radio.pipe:
            baud = self._radio.pipe.baudrate

        if s is None:
            LOG.debug('Opening serial %r after upload prompt' % port)
            s = open_serial(port, self._radio)

        self._remember_port_for_selected()

        try:
            self._radio.set_pipe(s)
            # Short-circuit straight to the previous baudrate for variable-
            # rate radios to sync back up faster
            self._radio.pipe.baudrate = baud
        except Exception as e:
            self.fail(str(e))
            return

        self._radio._status_fn = self._status

        self._clone_thread = CloneThread(self._radio, self, 'sync_out')
        self._clone_thread.start()

    def _persist_choices(self):
        # On upload, we may have a detected-only subclass, which won't be
        # selectable normally. If so, use the detected_by instead of the
        # actual driver
        parent = getattr(self._radio, '_DETECTED_BY', None)
        model = model_value(parent or self._radio)
        CONF.set('last_vendor', self._vendor.GetStringSelection(), 'state')
        CONF.set('last_model', model, 'state')
        CONF.set('last_port', self.get_selected_port(), 'state')
