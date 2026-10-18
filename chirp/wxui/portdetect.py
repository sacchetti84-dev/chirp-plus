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

"""Automatic serial port detection for programming cables.

This module has no wx dependency so it can be unit tested. Strings that are
shown to the user are only marked for translation here (so xgettext finds
them); the UI translates them with wx.GetTranslation() when displaying.
"""

import dataclasses
import logging
import platform
import re
import threading

from serial.tools import list_ports

LOG = logging.getLogger(__name__)


def _(string):
    # Marker only: translation happens in the UI layer
    return string


KIND_CABLE = 'cable'
KIND_USB = 'usb'
KIND_BUILTIN = 'builtin'
KIND_BLUETOOTH = 'bluetooth'
KIND_OTHER = 'other'

SCORES = {
    KIND_CABLE: 100,
    KIND_USB: 70,
    KIND_OTHER: 30,
    KIND_BUILTIN: 20,
    KIND_BLUETOOTH: 10,
}

# Scores at or above this are considered "probably a programming cable"
CABLE_SCORE = SCORES[KIND_USB]

# USB-serial bridge chips used by radio programming cables, by (VID, PID)
KNOWN_CHIPS = {
    (0x1A86, 0x7523): 'CH340',
    (0x1A86, 0x7522): 'CH340K',
    (0x1A86, 0x5523): 'CH341',
    (0x1A86, 0x55D3): 'CH343',
    (0x1A86, 0x55D4): 'CH9102',
    (0x067B, 0x2303): 'PL2303',
    (0x067B, 0x23A3): 'PL2303GC',
    (0x067B, 0x23B3): 'PL2303GB',
    (0x067B, 0x23C3): 'PL2303GT',
    (0x067B, 0x23D3): 'PL2303GL',
    (0x067B, 0x23E3): 'PL2303GE',
    (0x067B, 0x23F3): 'PL2303GS',
    (0x0403, 0x6001): 'FTDI FT232R',
    (0x0403, 0x6010): 'FTDI FT2232',
    (0x0403, 0x6014): 'FTDI FT232H',
    (0x0403, 0x6015): 'FTDI FT231X',
    (0x10C4, 0xEA60): 'CP210x',
    (0x10C4, 0xEA70): 'CP2105',
    (0x0483, 0x5740): 'STM32 VCP',
}

# Ports that are listed by the OS but are never useful
IGNORED_DEVICES = (
    # MacOS unpaired bluetooth serial
    '/dev/cu.Bluetooth-Incoming-Port',
    '/dev/cu.debug-console',
    '/dev/cu.wlan-debug',
)

PROLIFIC_MARKERS = ('CONTACT YOUR SUPPLIER', 'PHASED OUT')

HINT_PROLIFIC = _('Prolific counterfeit or unsupported chip: the current '
                  'Windows driver refuses to work with it. Install an older '
                  'Prolific driver or use a CH340/FTDI cable.')
HINT_BLUETOOTH = _('Bluetooth serial port, not a programming cable')
HINT_BUILTIN = _('Built-in serial port of the computer')
HINT_CABLE = _('Programming cable detected')
HINT_USB = _('USB serial device')
HINT_OTHER = _('Serial port')


@dataclasses.dataclass
class PortInfo:
    device: str
    description: str
    kind: str
    chip: str
    score: int
    warning: str = ''
    vid: int | None = None
    pid: int | None = None

    @property
    def usable(self):
        return not self.warning

    @property
    def is_cable(self):
        return self.usable and self.score >= CABLE_SCORE

    @property
    def hint(self):
        if self.warning:
            return self.warning
        return {
            KIND_CABLE: HINT_CABLE,
            KIND_USB: HINT_USB,
            KIND_BUILTIN: HINT_BUILTIN,
            KIND_BLUETOOTH: HINT_BLUETOOTH,
        }.get(self.kind, HINT_OTHER)

    @property
    def short_device(self):
        if self.device.startswith('/dev/'):
            return self.device[len('/dev/'):]
        return self.device

    @property
    def label(self):
        """A unique, human-friendly label for a port chooser"""
        desc = clean_description(self.description, self.device)
        if self.chip and self.chip.split()[-1] not in desc:
            desc = '%s - %s' % (self.chip, desc) if desc else self.chip
        if not desc:
            return self.short_device
        if platform.system() == 'Windows':
            # Keep the COMn first so it is visible even when ellipsized
            return '%s: %s' % (self.short_device, desc)
        return '%s (%s)' % (desc, self.short_device)


def clean_description(description, device):
    """Remove useless or duplicated parts of the OS description"""
    if not description or description == 'n/a':
        return ''
    # Windows describes ports as "Long Name (COMn)", drop the duplicate
    short = device.split('/')[-1]
    desc = re.sub(r'\s*\(%s\)$' % re.escape(short), '', description).strip()
    return '' if desc == short else desc


def sort_key(device):
    """Sort COM2 before COM10 on Windows, plain sort elsewhere"""
    m = re.match(r'^COM([0-9]+)$', device)
    if m:
        return 'COM%08i' % int(m.group(1))
    return device


def classify(port):
    """Turn a pyserial ListPortInfo into a PortInfo"""
    desc = port.description or ''
    hwid = (port.hwid or '').upper()
    vid = getattr(port, 'vid', None)
    pid = getattr(port, 'pid', None)
    chip = KNOWN_CHIPS.get((vid, pid), '') if vid is not None else ''
    warning = ''

    udesc = desc.upper()
    if 'PL2303' in udesc and any(m in udesc for m in PROLIFIC_MARKERS):
        warning = HINT_PROLIFIC
        chip = chip or 'PL2303'

    if 'BTHENUM' in hwid or 'BLUETOOTH' in udesc or 'BLUETOOTH' in hwid:
        kind = KIND_BLUETOOTH
    elif chip:
        kind = KIND_CABLE
    elif vid is not None:
        kind = KIND_USB
    elif ('ACPI' in hwid or 'PNP0501' in hwid or
            re.match(r'^/dev/tty(S|AMA)[0-9]+$', port.device)):
        kind = KIND_BUILTIN
    else:
        kind = KIND_OTHER

    score = SCORES[kind]
    if warning:
        score = min(score, 40)
    return PortInfo(device=port.device, description=desc, kind=kind,
                    chip=chip, score=score, warning=warning,
                    vid=vid, pid=pid)


def scan(system_ports=None):
    """Return classified ports, best candidates first"""
    if system_ports is None:
        try:
            system_ports = list_ports.comports()
        except Exception as e:
            LOG.exception('Failed to enumerate serial ports: %s', e)
            system_ports = []
    ports = [classify(p) for p in system_ports
             if p.device not in IGNORED_DEVICES]
    ports.sort(key=lambda p: (-p.score, sort_key(p.device)))
    return ports


def choose_port(ports, preferred=()):
    """Pick the port most likely connected to the radio.

    :param ports: list of PortInfo (as returned by scan())
    :param preferred: devices the user used before, most important first
    :returns: the chosen device name, or None
    """
    by_dev = {p.device: p for p in ports}
    have_cable = any(p.is_cable for p in ports)
    for dev in preferred:
        port = by_dev.get(dev)
        if port is None:
            continue
        # A remembered port wins, unless it is something that is clearly
        # not a cable (like COM1) while a real cable is plugged in.
        if port.is_cable or not have_cable:
            return dev
    for port in ports:
        if port.usable:
            return port.device
    return ports[0].device if ports else None


class PortMonitor:
    """Watch for serial ports appearing and disappearing.

    Enumeration runs in a background thread so a slow driver never blocks
    the UI. Listeners are called from that thread with
    (ports, added, removed); UI code must marshal to its own thread.
    """
    def __init__(self, interval=1.5, scanner=scan):
        self._interval = interval
        self._scanner = scanner
        self._listeners = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._known = None
        self.ports = []

    def add_listener(self, fn):
        with self._lock:
            self._listeners.append(fn)
        self._ensure_running()

    def remove_listener(self, fn):
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def _ensure_running(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name='PortMonitor')
        self._thread.start()

    def stop(self):
        self._stop.set()

    def poll(self):
        """Scan once; returns (ports, added, removed) device lists"""
        ports = self._scanner()
        devices = {p.device for p in ports}
        if self._known is None:
            added, removed = [], []
        else:
            added = sorted(devices - self._known, key=sort_key)
            removed = sorted(self._known - devices, key=sort_key)
        self._known = devices
        self.ports = ports
        return ports, added, removed

    def _run(self):
        first = True
        while not self._stop.is_set():
            try:
                ports, added, removed = self.poll()
            except Exception as e:
                LOG.exception('Port monitor scan failed: %s', e)
            else:
                if first or added or removed:
                    if added or removed:
                        LOG.info('Serial ports changed: +%s -%s',
                                 added, removed)
                    with self._lock:
                        listeners = list(self._listeners)
                    for fn in listeners:
                        try:
                            fn(ports, added, removed)
                        except Exception as e:
                            LOG.exception('Port listener failed: %s', e)
                first = False
            self._stop.wait(self._interval)


_MONITOR = None


def get_monitor():
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = PortMonitor()
    return _MONITOR
