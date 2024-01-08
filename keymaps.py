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

import bpy
import typing
import collections

ADDON_KEYMAPS: typing.List[typing.Tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []

# Keymap defines a set of keys that are active over a certain space and region in Blender
# For example items of KeymapDefinition("View 3D", "VIEW_3D", "WINDOW") will react to all events
# in the 3D view. For global events a KeymapDefinition("Window", "EMPTY", "WINDOW") can be used.
# The first entry is the name of the keymap in Preferences / Keymap.
KeymapDefinition = collections.namedtuple("KeymapDefinition", ["name", "space_type", "region_type"])
KeymapItemDefinition = collections.namedtuple(
    "KeymapItemDefinition", ["bl_idname", "key", "action", "ctrl", "shift", "alt"])


# TODO: Ideally we would import here the MAPR_ToggleArea and get the bl_idname, but this
# would introduce circular deps and other dependency hell
KEYMAP_DEFINITIONS: typing.Dict[KeymapDefinition, typing.List[KeymapItemDefinition]] = {
    KeymapDefinition('Window', 'EMPTY', 'WINDOW'): [
        KeymapItemDefinition("engon.browser_toggle_area", 'E', 'PRESS', False, False, False),
    ]
}


def draw_settings_ui(context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
    col = layout.column(align=True)

    # keyconfigs.user can be none in background mode
    if context.window_manager.keyconfigs.user is None:
        return

    for km_def, km_items_def in KEYMAP_DEFINITIONS.items():
        km_items = context.window_manager.keyconfigs.user.keymaps[km_def.name].keymap_items
        for km_item_def in km_items_def:
            km_item: bpy.types.KeyMapItem = km_items.get(km_item_def.bl_idname, None)
            if km_item is None:
                continue

            assert km_item is not None
            row = col.row()
            row.label(text=km_item.name)
            row.prop(km_item, "type", text="", full_event=True)


def _register_keymaps():
    ADDON_KEYMAPS.clear()
    wm = bpy.context.window_manager
    # wm.keyconfigs.addon can be None while Blender is running in background mode
    if wm.keyconfigs.addon is None:
        return

    for km_def, km_items_def in KEYMAP_DEFINITIONS.items():
        km = wm.keyconfigs.addon.keymaps.new(
            name=km_def.name, space_type=km_def.space_type, region_type=km_def.region_type)

        for bl_idname, key, action, ctrl, shift, alt in km_items_def:
            kmi = km.keymap_items.new(bl_idname, key, action, ctrl=ctrl, shift=shift, alt=alt)
            ADDON_KEYMAPS.append((km, kmi))


def _unregister_keymaps():
    for km, kmi in ADDON_KEYMAPS:
        km.keymap_items.remove(kmi)

    ADDON_KEYMAPS.clear()


def register():
    _register_keymaps()


def unregister():
    _unregister_keymaps()
