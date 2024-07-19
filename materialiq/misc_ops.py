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
from .. import hatchery

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class ReplaceMaterial(bpy.types.Operator):
    bl_idname = "engon.materialiq_replace_material"
    bl_label = "Replace Material"
    bl_description = "Replace a material used on selected or all objects for another material"
    bl_options = {'REGISTER', 'UNDO'}

    mat_orig: bpy.props.StringProperty(
        name="Original",
        maxlen=63,
    )
    mat_rep: bpy.props.StringProperty(
        name="Replacement",
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
        layout.prop_search(self, "mat_orig", bpy.data, "materials")
        layout.prop_search(self, "mat_rep", bpy.data, "materials")
        layout.prop(self, "only_selected")
        layout.prop(self, "update_selection")

    def invoke(self, context: bpy.types.Context, event):
        return context.window_manager.invoke_props_dialog(self)

    def replace_material(
        self, m1: str, m2: str, only_selected: bool = True, update_selection: bool = False
    ) -> None:
        # replace material named m1 with material named m2
        # m1 is the name of original material
        # m2 is the name of the material to replace it with

        mat_orig = bpy.data.materials.get(m1, None)
        mat_rep = bpy.data.materials.get(m2, None)

        errors_messages: typing.List[str] = []

        if mat_orig is None:
            errors_messages.append(f"Material '{m1}' does not exist!")
        if mat_rep is None:
            errors_messages.append(f"Material '{m2}' does not exist!")
        if len(errors_messages) != 0:
            for message in errors_messages:
                self.report({'ERROR'}, message)
            return

        if mat_orig == mat_rep:
            return

        objs = bpy.context.selected_editable_objects if only_selected else bpy.data.objects

        for ob in objs:
            if not hatchery.utils.can_have_materials_assigned(ob):
                continue

            changed = False
            for m in ob.material_slots:
                if m.material != mat_orig:
                    continue

                m.material = mat_rep
                # don't break the loop as the material can be
                # ref'd more than once
                changed = True

            if update_selection:
                ob.select_set(changed)

    def execute(self, context: bpy.types.Context):
        self.replace_material(
            self.mat_orig, self.mat_rep, self.only_selected, self.update_selection
        )
        logger.info(f"Replaced material {self.mat_orig} with material {self.mat_rep}")
        self.mat_orig = ""
        self.mat_rep = ""
        return {'FINISHED'}


MODULE_CLASSES.append(ReplaceMaterial)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
