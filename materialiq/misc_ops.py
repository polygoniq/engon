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
import logging
from .. import polib

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class ReplaceMaterial(bpy.types.Operator):
    bl_idname = "engon.materialiq_replace_material"
    bl_label = "Replace Material"
    bl_description = "Replace a material used on selected or all objects for another material"
    bl_options = {'REGISTER', 'UNDO'}

    mat_orig_name: bpy.props.StringProperty(
        name="Original Material Name",
        maxlen=63,
        options={'SKIP_SAVE'},
    )
    mat_rep_name: bpy.props.StringProperty(
        name="Replacement Material Name",
        maxlen=63,
    )
    only_selected: bpy.props.BoolProperty(
        name="Only selected",
        description="Replaces materials only for the selected objects",
        default=False,
    )
    update_selection: bpy.props.BoolProperty(
        name="Update Selection",
        description="Select affected objects and deselect unaffected",
        default=True,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(bpy.data.materials) > 0

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop_search(self, "mat_orig_name", bpy.data, "materials")
        layout.prop_search(self, "mat_rep_name", bpy.data, "materials")
        layout.prop(self, "only_selected")
        layout.prop(self, "update_selection")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        active_material = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if self.mat_orig_name == "" and active_material is not None:
            self.mat_orig_name = active_material.name

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context):
        mat_orig = bpy.data.materials.get(self.mat_orig_name, None)
        mat_rep = bpy.data.materials.get(self.mat_rep_name, None)

        errors_messages: list[str] = []

        if mat_orig is None:
            errors_messages.append(f"Material '{self.mat_orig_name}' does not exist!")
        if mat_rep is None:
            errors_messages.append(f"Material '{self.mat_rep_name}' does not exist!")
        if len(errors_messages) != 0:
            for message in errors_messages:
                self.report({'ERROR'}, message)
            return {'CANCELLED'}

        assert isinstance(mat_orig, bpy.types.Material) and isinstance(mat_rep, bpy.types.Material)
        objects = context.selected_objects if self.only_selected else context.scene.objects
        polib.material_utils_bpy.replace_materials(
            {mat_orig}, mat_rep, objects, self.update_selection
        )
        self.report(
            {'INFO'}, f"Replaced material '{self.mat_orig_name}' with '{self.mat_rep_name}'"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ReplaceMaterial)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
