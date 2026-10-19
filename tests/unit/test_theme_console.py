import threading
import unittest
from unittest import mock

from chirp.wxui import console
from chirp.wxui import theme


class TestTheme(unittest.TestCase):
    def setUp(self):
        self.conf = mock.MagicMock()
        self.values = {}
        self.conf.get.side_effect = lambda k, s: self.values.get((k, s))
        self.conf.is_defined.side_effect = (
            lambda k, s: (k, s) in self.values)
        self.conf.get_bool.side_effect = (
            lambda k, s, d=False: self.values.get((k, s), d))
        patcher = mock.patch.object(theme, 'CONF', self.conf)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_is_terminal(self):
        self.assertEqual(theme.STYLE_TERMINAL, theme.style())
        self.assertTrue(theme.enabled())

    def test_old_night_vision_off_means_classic(self):
        self.values[('nvg_theme', 'prefs')] = False
        self.assertEqual(theme.STYLE_CLASSIC, theme.style())

    def test_explicit_style_wins(self):
        self.values[('nvg_theme', 'prefs')] = False
        self.values[('ui_style', 'prefs')] = theme.STYLE_TERMINAL
        self.assertEqual(theme.STYLE_TERMINAL, theme.style())

    def test_label(self):
        self.assertEqual('scarica dalla radio [alt+d]',
                         theme.label('Scarica dalla radio', 'alt+d'))
        self.values[('ui_style', 'prefs')] = theme.STYLE_CLASSIC
        self.assertEqual('Scarica dalla radio',
                         theme.label('Scarica dalla radio', 'alt+d'))

    def test_column_tones_are_semantic(self):
        self.assertEqual('info', theme.column_tone('freq'))
        self.assertEqual('code', theme.column_tone('rtone'))
        self.assertEqual('code', theme.column_tone('dtcs'))
        self.assertEqual('tx', theme.column_tone('power'))
        self.assertEqual('dim', theme.column_tone('comment'))
        self.assertEqual('fg', theme.column_tone('extra.foo'))

    def test_every_tone_has_both_looks(self):
        for tone_name in ('ok', 'warn', 'bad', 'info', 'rx', 'tx', 'file',
                          'code', 'dim', 'fg'):
            self.assertIn(tone_name, theme.PALETTE)
            self.assertIn(tone_name, theme.CLASSIC_TONES)

    def test_prompt(self):
        self.assertEqual('chirp@plus:~$ scarica', theme.prompt('scarica'))


class TestConsole(unittest.TestCase):
    def test_log_and_listen(self):
        log = console.EventLog(size=3)
        got = []
        log.log('ok', 'one')
        backlog = log.add_listener(got.append)
        self.assertEqual(['one'], [e.text for e in backlog])
        log.log('tx', 'two')
        log.log('nonsense', 'three')
        self.assertEqual(['two', 'three'], [e.text for e in got])
        # Unknown tones fall back to info
        self.assertEqual('info', got[1].tone)

    def test_size_limit(self):
        log = console.EventLog(size=2)
        for i in range(5):
            log.log('info', str(i))
        self.assertEqual(['3', '4'], [e.text for e in log.entries])

    def test_remove_listener(self):
        log = console.EventLog()
        got = []
        log.add_listener(got.append)
        log.remove_listener(got.append)
        log.log('ok', 'x')
        self.assertEqual([], got)

    def test_threads(self):
        log = console.EventLog(size=1000)
        threads = [threading.Thread(target=lambda: [
            log.log('info', 'x') for _ in range(100)]) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(500, len(log.entries))

    def test_format(self):
        log = console.EventLog()
        log.log('bad', 'boom')
        line = console.format_entry(log.entries[0])
        self.assertTrue(line.endswith('[ERR ] boom'), line)
