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

import typing
import bpy
import logging
import polib
from .. import preferences
from .. import asset_helpers
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


class SetLightsStatus(bpy.types.Operator):
    bl_idname = "engon.traffiq_set_lights_status"
    bl_label = "Set Lights Status To Selected"
    bl_description = "Set lights status to selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    status: bpy.props.EnumProperty(
        items=preferences.traffiq_preferences.MAIN_LIGHT_STATUS,
        name="Lights Status",
    )

    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).traffiq_preferences
        prefs.lights_properties.main_lights_status = self.status
        return {'FINISHED'}


MODULE_CLASSES.append(SetLightsStatus)


def get_emergency_lights_container_from_hierarchy_with_root(
    obj: bpy.types.Object
) -> typing.Tuple[typing.Optional[bpy.types.Object], typing.Optional[bpy.types.Object]]:
    """Returns the first object in the hierarchy that contains emergency lights and the root of the hierarchy

    Returns None if no such object is found in the hierarchy of the given object.
    """
    def _contains_emergency_lights(obj: bpy.types.Object) -> bool:
        return len(polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
            obj, asset_helpers.TQ_EMERGENCY_LIGHTS_NODE_GROUP_NAME)) > 0

    emergency_lights = list(
        polib.asset_pack_bpy.get_root_objects_with_matched_child(
            [obj], lambda obj, _: _contains_emergency_lights(obj)))
    if len(emergency_lights) == 0:
        return None, None
    assert len(emergency_lights) == 1
    return emergency_lights[0]


def get_main_lights_status_text(value: float) -> str:
    ret = "Unknown"
    for min_value, status, _ in preferences.traffiq_preferences.MAIN_LIGHT_STATUS:
        if value < float(min_value):
            return ret
        ret = status

    return ret


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
