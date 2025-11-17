# copyright (c) 2018- polygoniq xyz s.r.o.

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

from . import polib

ADDON_KEYMAPS: polib.keymaps_bpy.AddonKeymaps = []

# TODO: Ideally we would import here modules of the operators and get the bl_idname, but this
# would introduce circular deps and other dependency hell
KEYMAP_DEFINITIONS: polib.keymaps_bpy.KeymapDefinitions = {
    polib.keymaps_bpy.KeymapDefinition('Window', 'EMPTY', 'WINDOW'): [
        polib.keymaps_bpy.KeymapItemDefinition(
            "Toggle engon Browser", "engon.browser_toggle_area", 'E', 'PRESS', False, False, False
        ),
    ],
    polib.keymaps_bpy.KeymapDefinition('User Interface', 'EMPTY', 'WINDOW'): [
        polib.keymaps_bpy.KeymapItemDefinition(
            "Select Displayed Assets",
            "engon.browser_select_displayed",
            'A',
            'PRESS',
            True,
            False,
            False,
        ),
    ],
    polib.keymaps_bpy.KeymapDefinition('3D View', 'VIEW_3D', 'WINDOW'): [
        polib.keymaps_bpy.KeymapItemDefinition(
            "Click Assets", "engon.clicker", 'C', 'PRESS', False, False, True
        ),
        polib.keymaps_bpy.KeymapItemDefinition(
            "Snap to Ground", "engon.snap_to_ground", 'V', 'PRESS', False, False, False
        ),
    ],
}


def register():
    polib.keymaps_bpy.register_keymaps(ADDON_KEYMAPS, KEYMAP_DEFINITIONS)


def unregister():
    polib.keymaps_bpy.unregister_keymaps(ADDON_KEYMAPS)
