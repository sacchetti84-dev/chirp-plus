import threading
import unittest
from unittest import mock

from serial.tools import list_ports_common

from chirp.wxui import portdetect


def fake_port(device, description, hwid, vid=None, pid=None):
    port = list_ports_common.ListPortInfo(device, skip_link_detection=True)
    port.description = description
    port.hwid = hwid
    port.vid = vid
    port.pid = pid
    return port


# Taken from a real Windows machine (Italian locale)
COM1 = fake_port('COM1', 'Porta di comunicazione (COM1)', 'ACPI\\PNP0501\\0')
COM3 = fake_port('COM3', 'Collegamento standard seriale su Bluetooth (COM3)',
                 'BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_VID&0001')
COM5 = fake_port('COM5', 'USB-SERIAL CH340 (COM5)',
                 'USB VID:PID=1A86:7523 SER= LOCATION=1-11',
                 vid=0x1A86, pid=0x7523)
COM10 = fake_port('COM10', 'USB Serial Port (COM10)',
                  'USB VID:PID=0403:6001 SER=A12345',
                  vid=0x0403, pid=0x6001)
COM7 = fake_port('COM7', 'USB Serial Device (COM7)',
                 'USB VID:PID=1234:5678', vid=0x1234, pid=0x5678)
PROLIFIC = fake_port(
    'COM6', 'PL2303HXA PHASED OUT SINCE 2012. PLEASE CONTACT YOUR '
    'SUPPLIER. (COM6)', 'USB VID:PID=067B:2303', vid=0x067B, pid=0x2303)


class TestClassify(unittest.TestCase):
    def test_ch340_is_cable(self):
        p = portdetect.classify(COM5)
        self.assertEqual(portdetect.KIND_CABLE, p.kind)
        self.assertEqual('CH340', p.chip)
        self.assertTrue(p.is_cable)

    def test_bluetooth(self):
        p = portdetect.classify(COM3)
        self.assertEqual(portdetect.KIND_BLUETOOTH, p.kind)
        self.assertFalse(p.is_cable)

    def test_builtin(self):
        p = portdetect.classify(COM1)
        self.assertEqual(portdetect.KIND_BUILTIN, p.kind)
        self.assertFalse(p.is_cable)

    def test_unknown_usb_is_probably_cable(self):
        p = portdetect.classify(COM7)
        self.assertEqual(portdetect.KIND_USB, p.kind)
        self.assertTrue(p.is_cable)

    def test_prolific_counterfeit(self):
        p = portdetect.classify(PROLIFIC)
        self.assertFalse(p.usable)
        self.assertFalse(p.is_cable)
        self.assertEqual(portdetect.HINT_PROLIFIC, p.hint)

    @mock.patch('platform.system', return_value='Windows')
    def test_label_windows(self, _system):
        self.assertEqual('COM5: USB-SERIAL CH340',
                         portdetect.classify(COM5).label)
        self.assertEqual('COM10: FTDI FT232R - USB Serial Port',
                         portdetect.classify(COM10).label)
        self.assertEqual('COM1: Porta di comunicazione',
                         portdetect.classify(COM1).label)

    @mock.patch('platform.system', return_value='Linux')
    def test_label_linux(self, _system):
        port = fake_port('/dev/ttyUSB0', 'USB Serial', 'USB VID:PID=1A86:7523',
                         vid=0x1A86, pid=0x7523)
        self.assertEqual('CH340 - USB Serial (ttyUSB0)',
                         portdetect.classify(port).label)
        port = fake_port('/dev/ttyS0', 'n/a', 'n/a')
        self.assertEqual('ttyS0', portdetect.classify(port).label)
        self.assertEqual(portdetect.KIND_BUILTIN,
                         portdetect.classify(port).kind)


class TestChoose(unittest.TestCase):
    def test_scan_orders_cables_first(self):
        ports = portdetect.scan([COM1, COM3, COM10, COM5])
        self.assertEqual(['COM5', 'COM10', 'COM1', 'COM3'],
                         [p.device for p in ports])

    def test_scan_ignores_useless(self):
        port = fake_port('/dev/cu.Bluetooth-Incoming-Port', 'n/a', 'n/a')
        self.assertEqual([], portdetect.scan([port]))

    def test_choose_cable_over_com1(self):
        ports = portdetect.scan([COM1, COM3, COM5])
        self.assertEqual('COM5', portdetect.choose_port(ports))

    def test_choose_remembered_cable(self):
        ports = portdetect.scan([COM1, COM5, COM10])
        self.assertEqual('COM10',
                         portdetect.choose_port(ports, ['COM10', 'COM5']))

    def test_remembered_missing_falls_through(self):
        ports = portdetect.scan([COM1, COM5])
        self.assertEqual('COM5',
                         portdetect.choose_port(ports, ['COM9', 'COM1']))

    def test_remembered_non_cable_when_no_cable(self):
        ports = portdetect.scan([COM1, COM3])
        self.assertEqual('COM3',
                         portdetect.choose_port(ports, ['COM3']))

    def test_prolific_not_chosen(self):
        ports = portdetect.scan([PROLIFIC, COM1])
        self.assertEqual('COM1', portdetect.choose_port(ports))

    def test_nothing(self):
        self.assertIsNone(portdetect.choose_port([]))


class TestMonitor(unittest.TestCase):
    def test_poll_reports_changes(self):
        sequence = [[COM1], [COM1, COM5], [COM5]]
        monitor = portdetect.PortMonitor(
            scanner=lambda: portdetect.scan(sequence.pop(0)))
        ports, added, removed = monitor.poll()
        self.assertEqual(([], []), (added, removed))
        ports, added, removed = monitor.poll()
        self.assertEqual((['COM5'], []), (added, removed))
        ports, added, removed = monitor.poll()
        self.assertEqual(([], ['COM1']), (added, removed))
        self.assertEqual(['COM5'], [p.device for p in monitor.ports])

    def test_thread_notifies_listener(self):
        calls = []
        done = threading.Event()

        def listener(ports, added, removed):
            calls.append((ports, added, removed))
            done.set()

        monitor = portdetect.PortMonitor(
            interval=0.01, scanner=lambda: portdetect.scan([COM5]))
        try:
            monitor.add_listener(listener)
            self.assertTrue(done.wait(5))
        finally:
            monitor.stop()
        self.assertEqual('COM5', calls[0][0][0].device)
