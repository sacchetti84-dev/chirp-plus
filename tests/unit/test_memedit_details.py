"""Every channel detail in the grid: the extra fields are columns."""

import pytest

from tests.unit import test_memedit_cells as harness
from tests.unit.test_memedit_cells import (  # noqa: F401
    real_wx, wx_app, memedit)

import wx  # noqa: E402

from chirp.wxui import common  # noqa: E402
from chirp.wxui import memedit as memedit_mod  # noqa: E402

pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


def names(editor):
    return [c.name for c in editor._col_defs]


def test_extra_fields_shown_by_default(memedit):  # noqa: F811
    # CHIRP Plus: no need for right click > Properties to see them
    assert not harness._CONF.is_defined('expand_extra', 'state')
    cols = names(memedit)
    for field in ('extra.bcl', 'extra.pttid', 'extra.scode'):
        assert field in cols
    # Still in front of the comment, which stays last
    assert cols[-1] == 'comment'


def test_extra_fields_can_be_hidden(memedit):  # noqa: F811
    harness._CONF.set_bool('expand_extra', False, 'state')
    try:
        memedit.refresh()
        wx.SafeYield()
        assert not [c for c in names(memedit) if c.startswith('extra.')]
    finally:
        harness._CONF.remove_option('expand_extra', 'state')


def test_view_menu_item_checked_by_default(wx_app):  # noqa: F811
    items = memedit_mod.ChirpMemEdit.get_menu_items()
    toggle = next(i for i in items[common.EditorMenuItem.MENU_VIEW]
                  if getattr(i, '_conf_key', None) == 'expand_extra')
    menu = wx.Menu()
    menu.Append(toggle)
    toggle.add_menu_callback()
    assert toggle.IsChecked()
