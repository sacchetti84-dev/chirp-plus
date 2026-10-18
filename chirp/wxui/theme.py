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

"""Night vision ("NVG") theme: black background, phosphor green text.

Everything here is a no-op when the theme is disabled, so callers can
apply it unconditionally.
"""

import logging
import sys

import wx

from chirp.wxui import config

LOG = logging.getLogger(__name__)
CONF = config.get()

PALETTE = {
    'bg': '#0B110B',        # window background
    'panel': '#0F1A0F',     # raised surfaces (toolbar, dialogs)
    'field': '#0D1A0D',     # editable fields, grid cells
    'alt': '#0D170D',       # alternate surface
    'fg': '#7CFF6B',        # phosphor text
    'dim': '#3E8C36',       # secondary text, borders
    'faint': '#1E3A1C',     # grid lines, scan lines
    'accent': '#C8FF3D',    # highlights, active items
    'select': '#1F4D1A',    # selection background
    'readonly': '#142414',  # immutable cells
    'warn': '#FFB000',
    'bad': '#FF4D3D',
}

MONO_FACES = ('Cascadia Mono', 'Consolas', 'Lucida Console', 'Courier New')
STENCIL_FACES = ('Stencil', 'OCR A Extended')


def enabled():
    return CONF.get_bool('nvg_theme', 'prefs', True)


def colour(name):
    return wx.Colour(PALETTE[name])


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


def stencil_font(size=24):
    face = _first_face(STENCIL_FACES)
    if face:
        return wx.Font(size, wx.FONTFAMILY_DECORATIVE, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_NORMAL, faceName=face)
    return mono_font(size, bold=True)


def label(text):
    """Military style labels are upper case"""
    return text.upper() if enabled() else text


# Icon colors for the classic (light) look
CLASSIC_TONES = {
    'fg': '#2E3A2E',
    'dim': '#5F6B5F',
    'accent': '#1B7F2A',
    'warn': '#B35C00',
    'bad': '#C62828',
}

_ICON_CACHE = {}


def icon(name, size=24, tone='fg'):
    """A Tabler icon from chirp/share/icons as a wx.BitmapBundle.

    The SVGs draw with currentColor, which becomes the theme color for
    @tone (a PALETTE key). Bundles scale cleanly on high DPI screens.
    """
    color = (PALETTE if enabled() else CLASSIC_TONES).get(
        tone, PALETTE.get(tone, '#000000'))
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


def _apply_one(win):
    # Imported here so this module loads with a mocked wx in unit tests
    import wx.grid
    if (isinstance(win, _FONT_CLASSES) and
            not getattr(win, '_nvg_keep_font', False)):
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

    if isinstance(win, (wx.TextCtrl, wx.SearchCtrl, wx.ListBox,
                        wx.ListCtrl, wx.ComboBox, wx.SpinCtrl,
                        wx.CheckListBox)):
        win.SetBackgroundColour(colour('field'))
        win.SetForegroundColour(colour('fg'))
    elif isinstance(win, wx.Button):
        win.SetBackgroundColour(colour('field'))
        win.SetForegroundColour(colour('accent'))
    elif isinstance(win, (wx.StaticText, wx.CheckBox, wx.RadioButton,
                          wx.StaticBox)):
        win.SetBackgroundColour(win.GetParent().GetBackgroundColour()
                                if win.GetParent() else colour('bg'))
        # Keep colors that code set deliberately (e.g. port status)
        if not getattr(win, '_nvg_keep_fg', False):
            win.SetForegroundColour(colour('fg'))
    elif isinstance(win, wx.Gauge):
        win.SetBackgroundColour(colour('field'))
        win.SetForegroundColour(colour('fg'))
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
    grid.SetLabelTextColour(colour('accent'))
    grid.SetLabelFont(mono_font(9, bold=True))
    grid.SetGridLineColour(colour('faint'))
    grid.SetSelectionBackground(colour('select'))
    grid.SetSelectionForeground(colour('accent'))
    grid.SetCellHighlightColour(colour('accent'))
    grid.SetBackgroundColour(colour('bg'))
    grid.GetGridWindow().SetBackgroundColour(colour('bg'))
    if hasattr(grid, 'SetDefaultColLabelRenderer'):
        grid.SetDefaultColLabelRenderer(NVGLabelRenderer())
        grid.SetCornerLabelRenderer(NVGLabelRenderer())


def style_propgrid(pg):
    if not enabled():
        return
    pg.SetBackgroundColour(colour('bg'))
    pg.SetFont(mono_font(9))
    pg.SetCaptionBackgroundColour(colour('panel'))
    pg.SetCaptionTextColour(colour('accent'))
    pg.SetCellBackgroundColour(colour('field'))
    pg.SetCellTextColour(colour('fg'))
    pg.SetCellDisabledTextColour(colour('dim'))
    pg.SetMarginColour(colour('panel'))
    pg.SetLineColour(colour('faint'))
    pg.SetEmptySpaceColour(colour('bg'))
    pg.SetSelectionBackgroundColour(colour('select'))
    pg.SetSelectionTextColour(colour('accent'))


def draw_label(grid, dc, rect, text, h_align, v_align, fill=None):
    """Flat, bordered label in NVG colors (for grid label renderers)"""
    dc.SetBrush(wx.Brush(fill or colour('panel')))
    dc.SetPen(wx.Pen(colour('faint')))
    dc.DrawRectangle(rect)
    dc.SetBackgroundMode(wx.TRANSPARENT)
    dc.SetTextForeground(grid.GetLabelTextColour())
    dc.SetFont(grid.GetLabelFont())
    inner = wx.Rect(*rect)
    inner.Deflate(3, 2)
    grid.DrawTextRectangle(dc, text, inner, h_align, v_align)


class NVGLabelRenderer:
    """Column/corner label renderer for GridWithLabelRenderersMixin"""
    def Draw(self, grid, dc, rect, col):
        if col < 0:
            draw_label(grid, dc, rect, '', wx.ALIGN_CENTER, wx.ALIGN_CENTER)
            return
        h_align, v_align = grid.GetColLabelAlignment()
        draw_label(grid, dc, rect, grid.GetColLabelValue(col),
                   h_align, v_align)


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


class NVGPanel(wx.Panel):
    """A panel painted like a night vision scope: a ranging grid, a reticle
    and corner brackets. Children (buttons) sit on top. With the theme
    disabled this is a plain wx.Panel."""
    # Reticle center, as a fraction of the panel size
    RETICLE_AT = (0.5, 0.62)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        if enabled():
            self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
            self.Bind(wx.EVT_PAINT, self._paint)
            self.Bind(wx.EVT_SIZE, self._resized)

    def _resized(self, event):
        self.Refresh()
        event.Skip()

    def reticle(self):
        w, h = self.GetClientSize()
        cx = int(w * self.RETICLE_AT[0])
        cy = int(h * self.RETICLE_AT[1])
        r = max(40, min(w, h) // 5)
        return cx, cy, r

    def _paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        dc.SetBackground(wx.Brush(colour('bg')))
        dc.Clear()
        # Ranging grid
        dc.SetPen(wx.Pen(colour('faint'), 1))
        step = 48
        for x in range(0, w, step):
            dc.DrawLine(x, 0, x, h)
        for y in range(0, h, step):
            dc.DrawLine(0, y, w, y)
        # Reticle: three rings, a broken crosshair and mil ticks
        cx, cy, r = self.reticle()
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(colour('dim'), 1))
        for factor in (0.45, 1.0, 1.5):
            dc.DrawCircle(cx, cy, int(r * factor))
        gap, reach = int(r * 0.2), int(r * 1.7)
        dc.DrawLine(cx - reach, cy, cx - gap, cy)
        dc.DrawLine(cx + gap, cy, cx + reach, cy)
        dc.DrawLine(cx, cy - reach, cx, cy - gap)
        dc.DrawLine(cx, cy + gap, cx, cy + reach)
        tick_step = max(8, r // 8)
        for tick in range(tick_step, int(r * 1.5), tick_step):
            for sign in (-1, 1):
                dc.DrawLine(cx + sign * tick, cy - 4, cx + sign * tick, cy + 4)
                dc.DrawLine(cx - 4, cy + sign * tick, cx + 4, cy + sign * tick)
        # Corner brackets
        dc.SetPen(wx.Pen(colour('fg'), 2))
        m, s = 14, 36
        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            dc.DrawLine(x0, y0, x0 + dx * s, y0)
            dc.DrawLine(x0, y0, x0, y0 + dy * s)
        self.paint_extra(dc, w, h)

    def paint_extra(self, dc, w, h):
        pass

    @staticmethod
    def draw_centered(dc, text, font, color, cx, y):
        dc.SetFont(font)
        dc.SetTextForeground(color)
        tw, th = dc.GetTextExtent(text)
        dc.DrawText(text, cx - tw // 2, y)
        return th
