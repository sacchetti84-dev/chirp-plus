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

"""A compact channel card to print, cut and keep with the radio.

Plain HTML (simple enough for wx.html printing): channel number, name,
frequency, tone and shift, in two columns.
"""

import datetime
import html


def _(string):
    # Marker only: callers pass translated labels in
    return string


LABELS = {
    'ch': _('Ch'),
    'name': _('Name'),
    'freq': _('MHz'),
    'tone': _('Tone'),
    'shift': _('Shift'),
}


def tone_text(mem):
    """Short tone description: T88.5, T88.5/S88.5, D023N, ..."""
    if mem.tmode == 'Tone':
        return 'T%.1f' % mem.rtone
    if mem.tmode == 'TSQL':
        return 'TS%.1f' % mem.ctone
    if mem.tmode == 'DTCS':
        return 'D%03i%s' % (mem.dtcs, mem.dtcs_polarity[0])
    if mem.tmode == 'Cross':
        return mem.cross_mode
    return ''


def shift_text(mem):
    if mem.duplex in ('+', '-'):
        return '%s%.3f' % (mem.duplex, mem.offset / 1000000)
    if mem.duplex == 'split':
        return 'TX %.4f' % (mem.offset / 1000000)
    if mem.duplex == 'off':
        return 'RX'
    return ''


def used_memories(radio):
    lo, hi = radio.get_features().memory_bounds
    found = []
    for number in range(lo, hi + 1):
        try:
            mem = radio.get_memory(number)
        except Exception:
            continue
        if not mem.empty:
            found.append(mem)
    return found


def _table(mems, labels):
    rows = ['<tr>%s</tr>' % ''.join(
        '<th align="left">%s</th>' % html.escape(labels[k])
        for k in ('ch', 'name', 'freq', 'tone', 'shift'))]
    for mem in mems:
        cells = [str(mem.number), mem.name.strip(),
                 '%.4f' % (mem.freq / 1000000), tone_text(mem),
                 shift_text(mem)]
        rows.append('<tr>%s</tr>' % ''.join(
            '<td nowrap><tt>%s</tt></td>' % html.escape(c) for c in cells))
    return ('<table border="1" cellspacing="0" cellpadding="2" '
            'width="100%%">%s</table>' % ''.join(rows))


def build_html(radio, labels=None, title=None, per_column=32,
               today=None):
    """HTML pages: two columns of @per_column channels each"""
    labels = dict(LABELS, **(labels or {}))
    mems = used_memories(radio)
    title = title or '%s %s' % (radio.VENDOR, radio.MODEL)
    today = today or datetime.date.today()
    head = ('<p><b>%s</b> &nbsp; <font size="-1">%s &nbsp; %i ch</font>'
            '</p>' % (html.escape(title), today.isoformat(), len(mems)))
    pages = []
    per_page = per_column * 2
    for start in range(0, max(1, len(mems)), per_page):
        left = mems[start:start + per_column]
        right = mems[start + per_column:start + per_page]
        pages.append(
            '%s<table width="100%%" cellspacing="0"><tr>'
            '<td valign="top" width="50%%">%s</td>'
            '<td valign="top" width="50%%">%s</td></tr></table>' % (
                head, _table(left, labels),
                _table(right, labels) if right else ''))
    sep = '<div style="page-break-before:always"></div>'
    return '<html><body>%s</body></html>' % sep.join(pages)
