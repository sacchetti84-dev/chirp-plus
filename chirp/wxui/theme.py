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

"""Terminal look: black background, monospace text and semantic colors.

Colors mean the same thing everywhere (see TONES and PIANO-TERMINALE.md):
green ok, yellow warning, red error, cyan info, blue reads from the radio,
orange writes to the radio, white files, magenta tones and codes.

Everything here is a no-op with the classic look, so callers can apply it
unconditionally.
"""

import logging
import sys

import wx

from chirp.wxui import config

LOG = logging.getLogger(__name__)
CONF = config.get()
_ = wx.GetTranslation

STYLE_TERMINAL = 'terminal'
STYLE_CLASSIC = 'classic'

PALETTE = {
    # Surfaces
    'bg': '#0C0C0C',        # window background
    'panel': '#151515',     # toolbar, dialogs, labels
    'field': '#101010',     # editable fields, grid cells
    'faint': '#262626',     # grid lines, borders
    'select': '#1E3A5F',    # selection background
    'readonly': '#1A1A1A',  # immutable cells
    # Text
    'fg': '#CCCCCC',
    'dim': '#767676',
    'accent': '#16C60C',    # the prompt
    # Semantic tones
    'ok': '#16C60C',
    'warn': '#F9C74F',
    'bad': '#FF5F5F',
    'info': '#61D6D6',
    'rx': '#5C7CFA',
    'tx': '#FF8F3F',
    'file': '#F2F2F2',
    'code': '#D670D6',
}

# Short tags shown in front of messages, terminal style
TAGS = {
    'ok': '[ OK ]',
    'warn': '[WARN]',
    'bad': '[ERR ]',
    'info': '[INFO]',
    'rx': '[ RX ]',
    'tx': '[ TX ]',
    'file': '[FILE]',
}

# Same meaning, darker shades readable on the classic light background
CLASSIC_TONES = {
    'fg': '#2E2E2E',
    'dim': '#6B6B6B',
    'accent': '#107C10',
    'ok': '#107C10',
    'warn': '#9A6700',
    'bad': '#C42B1C',
    'info': '#00707A',
    'rx': '#0B57D0',
    'tx': '#C25100',
    'file': '#2E2E2E',
    'code': '#8E2A8E',
}

# Memory grid: each column is colored by what it is for
COLUMN_TONES = {
    'freq': 'info',
    'duplex': 'info',
    'offset': 'info',
    'name': 'file',
    'tmode': 'code',
    'rtone': 'code',
    'ctone': 'code',
    'dtcs': 'code',
    'rx_dtcs': 'code',
    'dtcs_polarity': 'code',
    'cross_mode': 'code',
    'power': 'tx',
    'skip': 'rx',
    'mode': 'fg',
    'tuning_step': 'fg',
    'comment': 'dim',
}

MONO_FACES = ('Cascadia Mono', 'Consolas', 'Lucida Console', 'Courier New')


def style():
    value = CONF.get('ui_style', 'prefs')
    if value in (STYLE_TERMINAL, STYLE_CLASSIC):
        return value
    # Earlier builds had an on/off "night vision" switch
    if CONF.is_defined('nvg_theme', 'prefs') and not CONF.get_bool(
            'nvg_theme', 'prefs'):
        return STYLE_CLASSIC
    return STYLE_TERMINAL


def enabled():
    return style() == STYLE_TERMINAL


def set_style(value):
    CONF.set('ui_style', value, 'prefs')


def colour(name):
    return wx.Colour(PALETTE[name])


def tone(name):
    """A semantic color for text on the current background"""
    table = PALETTE if enabled() else CLASSIC_TONES
    return wx.Colour(table.get(name, PALETTE.get(name, '#000000')))


def legend():
    """(tone, meaning) pairs, in the order shown to the user"""
    return [('ok', _('ok')),
            ('warn', _('warning')),
            ('bad', _('error')),
            ('info', _('info')),
            ('rx', _('reads the radio')),
            ('tx', _('writes the radio')),
            ('file', _('file')),
            ('code', _('tones'))]


def column_tone(col_name):
    if col_name.startswith('extra.'):
        return 'fg'
    return COLUMN_TONES.get(col_name, 'fg')


def init_app(app):
    """Call once, before any window exists"""
    if not enabled():
        return
    if sys.platform == 'win32' and hasattr(app, 'MSWEnableDarkMode'):
        # Dark native menus, title bars, scrollbars and standard dialogs
        try:
            app.MSWEnableDarkMode(wx.App.DarkMode_Always)
        except Exception as e:
            LOG.warning('Unable to enable dark mode: %s', e)


def _first_face(faces):
    available = set(wx.FontEnumerator.GetFacenames())
    for face in faces:
        if face in available:
            return face
    return None


def mono_font(size=10, bold=False):
    face = _first_face(MONO_FACES)
    weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
    if face:
        return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                       weight, faceName=face)
    return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, weight)


def heading_font(size=16):
    return mono_font(size, bold=True)


def label(text, key=None):
    """Terminal labels read like commands: lower case, with the shortcut"""
    if not enabled():
        return text
    text = text.lower()
    return '%s [%s]' % (text, key) if key else text


def wrap(text_ctrl, width):
    """Wrap a StaticText in the font it will be shown with.

    Wrapping before the terminal font is applied leaves the text cut, as
    the monospace font is wider.
    """
    if enabled():
        size = text_ctrl.GetFont().GetPointSize()
        text_ctrl.SetFont(mono_font(size if 7 <= size <= 14 else 9))
        keep(text_ctrl, font=True)
    text_ctrl.Wrap(width)
    return text_ctrl


def prompt(command):
    """A shell prompt line, e.g. for dialog headers"""
    return 'chirp@plus:~$ %s' % command


_ICON_CACHE = {}


def icon(name, size=24, tone_name='fg'):
    """A Tabler icon from chirp/share/icons as a wx.BitmapBundle.

    The SVGs draw with currentColor, which becomes the color of the
    semantic tone (see TONES). Bundles scale cleanly on high DPI screens.
    """
    color = tone(tone_name).GetAsString(wx.C2S_HTML_SYNTAX)
    key = (name, size, color)
    if key not in _ICON_CACHE:
        from importlib import resources
        try:
            svg = resources.files('chirp.share').joinpath(
                'icons', '%s.svg' % name).read_text(encoding='utf-8')
        except (FileNotFoundError, OSError) as e:
            LOG.warning('Missing icon %s: %s', name, e)
            return wx.BitmapBundle()
        svg = svg.replace('currentColor', color)
        _ICON_CACHE[key] = wx.BitmapBundle.FromSVG(svg.encode('utf-8'),
                                                   wx.Size(size, size))
    return _ICON_CACHE[key]


def apply(window):
    """Recursively color a window and its children"""
    if not enabled() or not window:
        return
    _apply_one(window)
    for child in window.GetChildren():
        if isinstance(child, wx.TopLevelWindow):
            # Separate dialogs/frames are themed by their own code
            continue
        apply(child)


_FONT_CLASSES = (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioButton,
                 wx.Choice, wx.ComboBox, wx.TextCtrl, wx.SearchCtrl,
                 wx.ListBox, wx.CheckListBox, wx.TreeCtrl, wx.ListCtrl,
                 wx.StaticBox, wx.SpinCtrl)


def keep(win, fg=False, font=False):
    """Mark a control whose color/font was set on purpose"""
    if fg:
        win._term_keep_fg = True
    if font:
        win._term_keep_font = True
    return win


def _apply_one(win):
    # Imported here so this module loads with a mocked wx in unit tests
    import wx.grid
    if (isinstance(win, _FONT_CLASSES) and
            not getattr(win, '_term_keep_font', False)):
        size = win.GetFont().GetPointSize()
        win.SetFont(mono_font(size if 7 <= size <= 14 else 9,
                              bold=win.GetFont().GetWeight() >=
                              wx.FONTWEIGHT_BOLD))
    if isinstance(win, wx.grid.Grid):
        style_grid(win)
        return
    try:
        import wx.propgrid
        if isinstance(win, wx.propgrid.PropertyGrid):
            style_propgrid(win)
            return
    except ImportError:
        pass

    keep_fg = getattr(win, '_term_keep_fg', False)
    if isinstance(win, (wx.TextCtrl, wx.SearchCtrl, wx.ListBox,
                        wx.ListCtrl, wx.ComboBox, wx.SpinCtrl,
                        wx.CheckListBox)):
        win.SetBackgroundColour(colour('field'))
        if not keep_fg:
            win.SetForegroundColour(colour('fg'))
    elif isinstance(win, wx.Button):
        win.SetBackgroundColour(colour('field'))
        if not keep_fg:
            win.SetForegroundColour(colour('fg'))
    elif isinstance(win, (wx.StaticText, wx.CheckBox, wx.RadioButton,
                          wx.StaticBox)):
        win.SetBackgroundColour(win.GetParent().GetBackgroundColour()
                                if win.GetParent() else colour('bg'))
        if not keep_fg:
            win.SetForegroundColour(colour('fg'))
    elif isinstance(win, wx.Gauge):
        win.SetBackgroundColour(colour('field'))
        win.SetForegroundColour(colour('ok'))
    elif isinstance(win, (wx.Dialog, wx.Frame, wx.ToolBar, wx.StatusBar)):
        win.SetBackgroundColour(colour('panel'))
        win.SetForegroundColour(colour('fg'))
    elif isinstance(win, wx.Window):
        win.SetBackgroundColour(colour('bg'))
        win.SetForegroundColour(colour('fg'))
    win.Refresh()


def style_dialog(dialog):
    """Theme a dialog right before it is shown"""
    if not enabled():
        return
    dialog.SetBackgroundColour(colour('panel'))
    dialog.SetForegroundColour(colour('fg'))
    for child in dialog.GetChildren():
        apply(child)


def style_grid(grid):
    if not enabled():
        return
    grid.SetDefaultCellBackgroundColour(colour('field'))
    grid.SetDefaultCellTextColour(colour('fg'))
    grid.SetLabelBackgroundColour(colour('panel'))
    grid.SetLabelTextColour(colour('dim'))
    grid.SetLabelFont(mono_font(9, bold=True))
    grid.SetGridLineColour(colour('faint'))
    grid.SetSelectionBackground(colour('select'))
    grid.SetSelectionForeground(colour('file'))
    grid.SetCellHighlightColour(colour('accent'))
    grid.SetBackgroundColour(colour('bg'))
    grid.GetGridWindow().SetBackgroundColour(colour('bg'))
    if hasattr(grid, 'SetDefaultColLabelRenderer'):
        grid.SetDefaultColLabelRenderer(TermLabelRenderer())
        grid.SetCornerLabelRenderer(TermLabelRenderer())


def style_propgrid(pg):
    if not enabled():
        return
    pg.SetBackgroundColour(colour('bg'))
    pg.SetFont(mono_font(9))
    pg.SetCaptionBackgroundColour(colour('panel'))
    pg.SetCaptionTextColour(colour('info'))
    pg.SetCellBackgroundColour(colour('field'))
    pg.SetCellTextColour(colour('fg'))
    pg.SetCellDisabledTextColour(colour('dim'))
    pg.SetMarginColour(colour('panel'))
    pg.SetLineColour(colour('faint'))
    pg.SetEmptySpaceColour(colour('bg'))
    pg.SetSelectionBackgroundColour(colour('select'))
    pg.SetSelectionTextColour(colour('file'))


def draw_label(grid, dc, rect, text, h_align, v_align, fill=None,
               text_colour=None):
    """Flat, bordered grid label (for grid label renderers)"""
    dc.SetBrush(wx.Brush(fill or colour('panel')))
    dc.SetPen(wx.Pen(colour('faint')))
    dc.DrawRectangle(rect)
    dc.SetBackgroundMode(wx.TRANSPARENT)
    dc.SetTextForeground(text_colour or grid.GetLabelTextColour())
    dc.SetFont(grid.GetLabelFont())
    inner = wx.Rect(*rect)
    inner.Deflate(3, 2)
    grid.DrawTextRectangle(dc, text, inner, h_align, v_align)


class TermLabelRenderer:
    """Column/corner label renderer for GridWithLabelRenderersMixin.

    Column headers take the color of their column's function."""
    def Draw(self, grid, dc, rect, col):
        if col < 0:
            draw_label(grid, dc, rect, '', wx.ALIGN_CENTER, wx.ALIGN_CENTER)
            return
        h_align, v_align = grid.GetColLabelAlignment()
        # Set by the memory editor: {column index: wx.Colour}
        color = getattr(grid, 'column_tones', {}).get(col)
        draw_label(grid, dc, rect, grid.GetColLabelValue(col),
                   h_align, v_align, text_colour=color)


def make_tab_art():
    """Tab art for the main wx.aui.AuiNotebook.

    The generic art picks a readable text color for dark tabs (the flat
    default does not). Subclassing tab arts from Python crashes wxPython
    4.3 (heap corruption on AddPage), so only the stock setters are used.
    """
    import wx.aui
    art = wx.aui.AuiGenericTabArt()
    art.SetColour(colour('panel'))
    art.SetActiveColour(colour('select'))
    art.SetNormalFont(mono_font(9))
    art.SetSelectedFont(mono_font(9, bold=True))
    art.SetMeasuringFont(mono_font(9, bold=True))
    return art


class TermPanel(wx.Panel):
    """A panel painted like a terminal screen: lines of colored text and
    clickable commands. Subclasses fill self.lines in refresh_lines().

    A line is a list of (text, tone) segments. A command line also has
    a callback and is drawn highlighted under the mouse. With the classic
    look this is a plain wx.Panel and draws nothing.
    """
    LINE_SPACING = 4

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lines = []
        self._hits = []
        self._hover = None
        self._cursor_on = True
        if not enabled():
            return
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._paint)
        self.Bind(wx.EVT_SIZE, self._resized)
        self.Bind(wx.EVT_MOTION, self._motion)
        self.Bind(wx.EVT_LEFT_UP, self._click)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._leave)
        self._blink = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._toggle_cursor, self._blink)
        self._blink.Start(530)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._destroyed)

    def _destroyed(self, event):
        event.Skip()
        if event.GetEventObject() is self:
            self._blink.Stop()

    def _resized(self, event):
        self.Refresh()
        event.Skip()

    def _toggle_cursor(self, event):
        self._cursor_on = not self._cursor_on
        self.RefreshRect(self._cursor_rect if hasattr(self, '_cursor_rect')
                         else self.GetClientRect())

    def _motion(self, event):
        hover = None
        for i, (rect, _fn) in enumerate(self._hits):
            if rect.Contains(event.GetPosition()):
                hover = i
                break
        if hover != self._hover:
            self._hover = hover
            self.SetCursor(wx.Cursor(wx.CURSOR_HAND if hover is not None
                                     else wx.CURSOR_ARROW))
            self.Refresh()

    def _leave(self, event):
        if self._hover is not None:
            self._hover = None
            self.Refresh()

    def _click(self, event):
        for rect, fn in self._hits:
            if rect.Contains(event.GetPosition()):
                fn()
                return
        event.Skip()

    def refresh_lines(self):
        """Override: rebuild self.lines"""

    def font(self):
        return mono_font(11)

    def _paint(self, event):
        self.refresh_lines()
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        dc.SetBackground(wx.Brush(colour('bg')))
        dc.Clear()
        dc.SetBackgroundMode(wx.TRANSPARENT)
        margin = 28
        y = margin
        self._hits = []
        for line in self.lines:
            segments, fn, font = line['segments'], line.get('fn'), \
                line.get('font') or self.font()
            dc.SetFont(font)
            # Block art (the banner) must touch the next line
            lh = dc.GetCharHeight() + line.get('spacing', self.LINE_SPACING)
            x = margin
            if fn is not None:
                rect = wx.Rect(margin - 8, y - 2, w - 2 * margin + 16, lh + 2)
                if self._hover == len(self._hits):
                    dc.SetBrush(wx.Brush(colour('select')))
                    dc.SetPen(wx.TRANSPARENT_PEN)
                    dc.DrawRectangle(rect)
                self._hits.append((rect, fn))
            for text, tone_name in segments:
                dc.SetTextForeground(tone(tone_name))
                dc.DrawText(text, x, y)
                x += dc.GetTextExtent(text)[0]
            if line.get('cursor'):
                cw = dc.GetTextExtent('_')[0]
                self._cursor_rect = wx.Rect(x, y, cw + 2, lh)
                if self._cursor_on:
                    dc.SetBrush(wx.Brush(colour('accent')))
                    dc.SetPen(wx.TRANSPARENT_PEN)
                    dc.DrawRectangle(x + 1, y + 2, cw, lh - 6)
            y += lh
            if y > h:
                break
