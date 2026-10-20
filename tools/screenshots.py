"""Take the UI screenshots of the GitHub landing page (.github/README.md).

Usage:  .venv\\Scripts\\python tools\\screenshots.py [--style classic]
                                     [--language it] [UV-9R image]

Builds a demo UV-9R image filled with the Italian presets (never your own
channels: the image only lends its settings), starts CHIRP Plus with a
throw-away copy of the configuration, opens each window through its real
menu command and saves it in .github/screenshots. Every dialog is
captured and cancelled at once: nothing talks to a radio. Windows only
(the capture uses PrintWindow).
"""
import argparse
import configparser
import ctypes
import glob
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, '.github', 'screenshots')
STOCK = os.path.join(ROOT, 'chirp', 'stock_configs')
APPDATA = os.path.join(os.environ.get('APPDATA', ''), 'CHIRP')
SIZE = (1280, 800)

user32 = ctypes.windll.user32
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
dwmapi = ctypes.windll.dwmapi
# PW_RENDERFULLCONTENT (2) gives a black picture in a wx bitmap: plain 0
PW_CLIENTANDFRAME = 0
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def demo_image(source, csv_name, target):
    """Write source with its memories replaced by a stock config"""
    from chirp import directory, import_logic
    from chirp.drivers import generic_csv
    radio = directory.get_radio_by_image(source)
    lo, hi = radio.get_features().memory_bounds
    for number in range(lo, hi + 1):
        radio.erase_memory(number)
    csv_radio = generic_csv.CSVRadio(os.path.join(STOCK, csv_name))
    clo, chi = csv_radio.get_features().memory_bounds
    location = lo
    for number in range(clo, chi + 1):
        mem = csv_radio.get_memory(number)
        if mem.empty:
            continue
        radio.set_memory(import_logic.import_mem(
            radio, csv_radio.get_features(), mem,
            overrides={'number': location}))
        location += 1
    radio.save_mmap(target)
    return target


def make_config(path, style):
    config = configparser.ConfigParser(interpolation=None)
    user = os.path.join(APPDATA, 'chirp.config')
    if os.path.exists(user):
        config.read(user, encoding='utf-8')
    for section in ('state', 'prefs'):
        if not config.has_section(section):
            config.add_section(section)
    config.set('state', 'agreed_to_license', 'True')
    config.set('state', 'window_w', str(SIZE[0]))
    config.set('state', 'window_h', str(SIZE[1]))
    config.set('state', 'window_x', '40')
    config.set('state', 'window_y', '40')
    config.set('prefs', 'ui_style', style)
    config.set('prefs', 'show_console', 'True')
    config.set('prefs', 'restore_tabs', 'False')
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, 'chirp.config'), 'w',
              encoding='utf-8') as f:
        config.write(f)


def settle(seconds=0.6):
    import wx
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        wx.SafeYield(None, True)
        time.sleep(0.02)


def grab(win, name):
    """Save the window (frame included) as .github/screenshots/<name>.png"""
    import wx
    win.Raise()
    win.Refresh()
    settle()
    hwnd = win.GetHandle()
    outer = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(outer))
    seen = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(seen),
                                    ctypes.sizeof(seen)) != 0:
        seen = outer
    width, height = outer.right - outer.left, outer.bottom - outer.top
    bmp = wx.Bitmap(width, height, 24)
    dc = wx.MemoryDC(bmp)
    if not user32.PrintWindow(hwnd, dc.GetHandle(), PW_CLIENTANDFRAME):
        # Fall back to copying the screen (the window must be on top)
        dc.Blit(0, 0, width, height, wx.ScreenDC(), outer.left, outer.top)
    dc.SelectObject(wx.NullBitmap)
    # Leave out the invisible resize borders of Windows 10/11
    bmp = bmp.GetSubBitmap(wx.Rect(seen.left - outer.left,
                                   seen.top - outer.top,
                                   seen.right - seen.left,
                                   seen.bottom - seen.top))
    path = os.path.join(OUT, name + '.png')
    bmp.SaveFile(path, wx.BITMAP_TYPE_PNG)
    print('saved', os.path.relpath(path, ROOT), bmp.GetSize(), flush=True)


class Shooter:
    def __init__(self, demo, before, style):
        self.demo = demo
        self.before = before
        self.style = style
        self.name = None
        # What the next dialog answers; None is Cancel
        self.answer = None

    def fake_show_modal(self, dialog):
        import wx
        dialog.Show()
        settle(1.0)
        if self.name:
            grab(dialog, self.name)
            self.name = None
        dialog.Hide()
        answer, self.answer = self.answer, None
        return wx.ID_CANCEL if answer is None else answer

    def menu(self, name, handler, *args, **kwargs):
        self.name = name
        try:
            handler(*args, **kwargs)
        except Exception as e:
            print('FAILED %s: %s' % (name, e), flush=True)
        settle(0.3)

    def spreadsheet(self, main):
        """The 70 cm repeaters RU0-RU3 selected (frequency and name),
        with the fill handle dragged down over four emptied channels."""
        import wx
        editor = main.current_editorset.current_editor
        grid = editor._grid
        cols = [c.name for c in editor._col_defs]
        freq, name = cols.index('freq'), cols.index('name')
        rows = {grid.GetCellValue(r, name): r
                for r in range(grid.GetNumberRows())}
        top = rows['RU0']
        radio = main.current_editorset.radio
        numbers = [editor.row2mem(row) for row in range(top + 4, top + 8)]
        kept = [radio.get_memory(number) for number in numbers]
        for number in numbers:
            radio.erase_memory(number)
        editor.refresh()
        settle(1)
        grid.MakeCellVisible(top + 12, freq)
        grid.MakeCellVisible(top - 4, freq)
        grid.ClearSelection()
        grid.SetGridCursor(top, freq)
        grid.SelectBlock(top, freq, top + 3, name)
        settle(0.5)
        handle = editor._fill_handle
        handle.update()

        def mouse(kind, y):
            event = wx.MouseEvent(kind)
            event.SetPosition(wx.Point(3, y - handle.GetPosition().y))
            event.SetEventObject(handle)
            handle.GetEventHandler().ProcessEvent(event)

        last = grid.CellToRect(top + 7, freq)
        _x, y = grid.CalcScrolledPosition(
            last.GetLeft(), last.GetTop() + last.GetHeight() // 2)
        mouse(wx.wxEVT_LEFT_DOWN, handle.GetPosition().y + 3)
        mouse(wx.wxEVT_MOTION, y)
        # No real mouse holds the capture: raising the window for the
        # picture would end the drag
        if handle.HasCapture():
            handle.ReleaseMouse()
        print('fill preview over rows', handle.preview_rows(), flush=True)
        grab(main, 'spreadsheet')
        # Esc: the drag ends without writing anything
        key = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
        key.SetKeyCode(wx.WXK_ESCAPE)
        key.SetEventObject(handle)
        handle.GetEventHandler().ProcessEvent(key)
        # The other pictures show the demo as it is
        for mem in kept:
            radio.set_memory(mem)
        grid.ClearSelection()
        editor.refresh()
        settle(1)

    def run(self):
        import wx
        from chirp import radio_compare, directory
        from chirp.wxui import changes, clone
        main = [w for w in wx.GetTopLevelWindows() if w.IsShown()][0]
        main.SetSize(*SIZE)
        main.SetPosition((40, 40))
        settle(1.5)
        if self.style == 'classic':
            main.open_file(self.demo)
            settle(2)
            grab(main, 'memories-classic')
            os._exit(0)

        grab(main, 'welcome')
        # Anything but OK in the About window closes CHIRP, as declining
        # the license does
        self.answer = wx.ID_OK
        self.menu('about', main._menu_about, None)
        main.open_file(self.demo)
        settle(2)
        # Show repeaters and satellites, where duplex and tones are set
        grid = main.current_editorset.current_editor._grid
        grid.MakeCellVisible(71, 0)
        grid.MakeCellVisible(50, 0)
        grid.SetGridCursor(56, 0)
        settle(0.5)
        grab(main, 'memories')
        self.spreadsheet(main)

        # Two channels a careless edit could produce, so the check has
        # something to say beyond the notes
        radio = main.current_editorset.radio
        for number, freq, name in ((72, 118100000, 'TOWER'),
                                   (73, 446006250, 'PMR 01')):
            mem = radio.get_memory(number)
            mem.empty = False
            mem.freq, mem.name, mem.mode = freq, name, 'NFM'
            mem.power = radio.get_features().valid_power_levels[0]
            radio.set_memory(mem)
        self.menu('frequency-check', main._menu_freqcheck, None)
        for number in (72, 73):
            radio.erase_memory(number)
        self.menu('memory-map', main._menu_memmap, None)
        # Demo backups in a relative folder, so the picture shows neither
        # your backups nor your user name
        from chirp.wxui import backups
        here = os.getcwd()
        os.chdir(os.path.dirname(self.demo))
        folder = os.path.join('CHIRP', 'backups')
        os.makedirs(folder, exist_ok=True)
        for kind, stamp in (('download', '20261012T182204'),
                            ('upload', '20261012T183510'),
                            ('download', '20261016T091522'),
                            ('upload', '20261019T185911'),
                            ('download', '20261019T190240')):
            shutil.copy(self.demo, os.path.join(
                folder, 'Baofeng_UV-9R_%s_%s.img' % (kind, stamp)))
        real_dir = backups.backup_dir
        backups.backup_dir = lambda: folder
        self.menu('backups', main._menu_backups, None)
        backups.backup_dir = real_dir
        os.chdir(here)
        self.menu('batch-programming', main._menu_batch, None)
        self.menu('download', main._menu_download, None)

        radio = main.current_editorset.radio
        self.name = 'upload'
        with clone.ChirpUploadDialog(radio, main) as d:
            d.Centre()
            d.ShowModal()

        # What the radio holds before: the calling list, an older name and
        # frequency, and a channel the new image no longer has
        old = directory.get_radio_by_image(self.before)
        mem = old.get_memory(1)
        mem.freq, mem.name = 145262500, 'OLD'
        old.set_memory(mem)
        mem = old.get_memory(16)
        mem.rtone, mem.tmode = 88.5, 'Tone'
        old.set_memory(mem)
        mem = old.get_memory(90)
        mem.empty = False
        mem.freq, mem.name = 145212500, 'FRIEND'
        old.set_memory(mem)
        found = radio_compare.diff_radios(old, radio)
        self.name = 'compare-before-upload'
        with changes.ChangesDialog(main, found, _('Changes in the radio'),
                                   _('Upload')) as d:
            d.SetSize(1000, 640)
            d.Centre()
            d.ShowModal()

        # The print preview needs a printer: show the same page in a frame
        import wx.html
        from chirp import pocket_card
        labels = {k: wx.GetTranslation(v)
                  for k, v in pocket_card.LABELS.items()}
        frame = wx.Frame(main, title=_('Pocket channel card'),
                         size=(900, 760))
        page = wx.html.HtmlWindow(frame)
        page.SetStandardFonts(9, 'Arial', 'Consolas')
        # Paper is white, even with the dark mode of the terminal look
        page.SetPage(pocket_card.build_html(radio, labels=labels).replace(
            '<body>', '<body bgcolor="#ffffff" text="#000000">'))
        frame.Centre()
        frame.Show()
        grab(frame, 'pocket-card')
        frame.Destroy()
        settle(0.5)
        # Upload backups made by the batch dialog are removed by the app;
        # the demo never changed, so nothing asks to be saved
        os._exit(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('image', nargs='?',
                        help='UV-9R image (default: newest backup)')
    parser.add_argument('--style', default='terminal',
                        choices=('terminal', 'classic'))
    parser.add_argument('--language', default='en_US',
                        help='UI language (default en_US, as the page)')
    args = parser.parse_args()
    image = args.image or max(
        glob.glob(os.path.join(APPDATA, 'backups', 'Baofeng_UV-9R_*.img')),
        key=os.path.getmtime)
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='chirp-shots-')

    import chirp
    from chirp import directory
    chirp.CHIRP_VERSION = 'next-20261016-plus'
    directory.import_drivers()
    demo = demo_image(image, 'IT Radioamatori tutto in uno.csv',
                      os.path.join(tmp, 'UV-9R ham radio.img'))
    before = demo_image(image, 'IT Chiamata e simplex radioamatori.csv',
                        os.path.join(tmp, 'UV-9R before.img'))
    make_config(os.path.join(tmp, 'config'), args.style)

    import wx
    shooter = Shooter(demo, before, args.style)
    wx.Dialog.ShowModal = lambda d: shooter.fake_show_modal(d)
    main_loop = wx.App.MainLoop

    def loop(app):
        wx.CallLater(2500, shooter.run)
        return main_loop(app)
    wx.App.MainLoop = loop

    sys.argv = ['chirpwx', '--config-dir', os.path.join(tmp, 'config'),
                '--force-language', args.language]
    try:
        from chirp.wxui import chirpmain
        chirpmain()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
