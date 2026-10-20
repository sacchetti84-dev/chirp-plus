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

"""Radio > Apply settings profile (see chirp/settings_profile.py)"""

import logging

import wx

from chirp import chirp_common
from chirp import settings  # noqa: F401 (used by the tests through here)
from chirp import settings_profile
from chirp.wxui import changes as changes_dialog
from chirp.wxui import common
from chirp.wxui import console
from chirp.wxui import memedit
from chirp.wxui import settingsedit

LOG = logging.getLogger(__name__)


def add_menu(frame, parent_menu, callback):
    """Append the submenu: one item per shipped profile, then From file.

    @callback gets the Profile, or None for "From file...".
    """
    sub = wx.Menu()
    try:
        shipped = settings_profile.shipped_profiles()
    except settings_profile.ProfileError as e:
        LOG.error('Unable to load the shipped profiles: %s', e)
        shipped = []
    for profile in shipped:
        item = sub.Append(wx.ID_ANY, profile.name)
        frame.Bind(wx.EVT_MENU, lambda e, p=profile: callback(p), item)
    if shipped:
        sub.AppendSeparator()
    item = sub.Append(wx.ID_ANY, _('From file...'))
    frame.Bind(wx.EVT_MENU, lambda e: callback(None), item)
    return parent_menu.AppendSubMenu(sub, _('Apply settings profile'))


def choose_file(parent):
    """Ask for a profile file; None if cancelled or unreadable"""
    with wx.FileDialog(parent, _('Settings profile'),
                       wildcard='JSON (*.json)|*.json',
                       style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as d:
        if d.ShowModal() != wx.ID_OK:
            return None
        path = d.GetPath()
    try:
        return settings_profile.load(path)
    except settings_profile.ProfileError as e:
        wx.MessageBox(str(e), _('Settings profile'), wx.ICON_ERROR,
                      parent=parent)
        return None


def _show_problems(parent, problems):
    lines = ['[%s]: %s' % (key, reason) for key, reason in problems[:19]]
    if len(problems) > 19:
        lines.append(_('...and %i more') % (len(problems) - 19))
    d = wx.MessageDialog(parent, _('Some settings were not changed'),
                         _('Some settings were not changed'),
                         wx.OK | wx.ICON_WARNING)
    d.SetExtendedMessage('\n'.join(lines))
    d.ShowModal()
    d.Destroy()


def apply_profile(parent, editorset, profile):
    """Show what @profile changes in @editorset's radio and apply it.

    Returns True when something was applied.
    """
    radio = editorset.radio
    title = _('Settings profile')
    if (isinstance(radio, chirp_common.LiveRadio) or
            not isinstance(radio, chirp_common.CloneModeRadio)):
        wx.MessageBox(_('Settings profiles work on radio images downloaded '
                        'from a radio, not on live radios or files.'),
                      title, wx.ICON_INFORMATION, parent=parent)
        return False
    if not settings_profile.fits(profile, radio):
        d = wx.MessageDialog(parent, _('The profile is for %s. Apply it '
                                       'anyway?') % ', '.join(profile.radios),
                             title, wx.YES_NO | wx.NO_DEFAULT |
                             wx.ICON_QUESTION)
        answer = d.ShowModal()
        d.Destroy()
        if answer != wx.ID_YES:
            return False

    try:
        plan = settings_profile.plan(profile, radio)
    except settings_profile.ProfileError as e:
        wx.MessageBox(str(e), title, wx.ICON_ERROR, parent=parent)
        return False
    if not plan.changes:
        wx.MessageBox(_('The radio already has these settings.'), title,
                      wx.ICON_INFORMATION, parent=parent)
        if plan.problems:
            _show_problems(parent, plan.problems)
        return False

    with changes_dialog.ChangesDialog(
            parent, plan.changes, title, _('Apply'), action_tone='file',
            command='profile "%s"' % profile.name,
            columns=(_('Now'), _('With the profile')),
            note=_('Settings cannot be undone: to go back, open the backup '
                   'of the download.')) as d:
        if d.ShowModal() != wx.ID_OK:
            return False

    radio.set_settings(plan.settings_tree)
    edit = next((e for _t, e in editorset.iter_editors(memedit.ChirpMemEdit)),
                None)
    if plan.memories and edit is not None:
        with edit.undo_context(_('Profile %s') % profile.name):
            for mem in plan.memories:
                edit.set_memory(mem)
    elif plan.memories:
        for mem in plan.memories:
            radio.set_memory(mem)
    for _t, editor in editorset.iter_editors(settingsedit.ChirpSettingsEdit):
        editor.refresh()
        if editorset.current_editor is editor:
            # The tab on screen would stay blank until shown again
            editor.selected()
    target = edit or editorset
    wx.PostEvent(target, common.EditorChanged(target.GetId()))
    console.log('file', _('Applied profile %s') % profile.name)
    if plan.problems:
        _show_problems(parent, plan.problems)
    return True
