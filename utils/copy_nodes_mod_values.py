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
import logging
import typing
from .. import polib

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


@polib.log_helpers_bpy.logged_operator
class CopyGeonodesModifierValues(bpy.types.Operator):
    bl_idname = "engon.copy_geonodes_modifier_values"
    bl_label = "Copy Modifier Values"
    bl_description = "Copies values of geometry nodes modifier from one object to another"

    src_name: bpy.props.StringProperty(
        name="Source Object",
        description="The source object to copy modifier values from",
    )

    src_mod_idx: bpy.props.IntProperty(
        min=0,
        name="Source Modifier Index",
        description="Index of the modifier to copy from 'Source Object'",
    )

    dst_name: bpy.props.StringProperty(
        name="Destination Object",
        description="The destination object to copy modifier values to",
    )

    dst_mod_idx: bpy.props.IntProperty(
        name="Destination Modifier Index",
        description="Index of the modifier to copy to 'Destination Object'",
        min=0,
    )

    def execute(self, context: bpy.types.Context):
        src_object = bpy.data.objects.get(self.src_name)
        dst_object = bpy.data.objects.get(self.dst_name)
        if src_object is None or dst_object is None:
            self.report({'ERROR'}, "Source or destination object not found.")
            return {'CANCELLED'}

        src_mod = None
        dst_mod = None
        if self.src_mod_idx < len(src_object.modifiers):
            src_mod = src_object.modifiers[self.src_mod_idx]
        if self.dst_mod_idx < len(dst_object.modifiers):
            dst_mod = dst_object.modifiers[self.dst_mod_idx]

        if src_mod is None or dst_mod is None:
            self.report({'ERROR'}, "Source or destination modifier not found.")
            return {'CANCELLED'}

        if src_mod.type != 'NODES' or dst_mod.type != 'NODES':
            self.report(
                {'ERROR'}, "Source or destination modifier is not a geometry nodes modifier."
            )
            return {'CANCELLED'}

        success = polib.geonodes_mod_utils_bpy.copy_geometry_nodes_modifier_inputs(src_mod, dst_mod)
        if not success:
            self.report({'ERROR'}, "Failed to copy modifier inputs.")
            return {'CANCELLED'}

        dst_object.update_tag()
        polib.ui_bpy.tag_areas_redraw(context, {'VIEW_3D'})
        self.report(
            {'INFO'},
            f"Copied modifier values from '{src_object.name}[\"{src_mod.name}\"]' to '{dst_object.name}[\"{src_mod.name}\"]'.",
        )
        return {'FINISHED'}


MODULE_CLASSES.append(CopyGeonodesModifierValues)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
