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
import polib
from .. import preferences
from .. import asset_helpers
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


@polib.log_helpers_bpy.logged_operator
class EnterVertexPaintMode(bpy.types.Operator):
    bl_idname = "engon.aquatiq_enter_vertex_paint"
    bl_label = "Paint Mask"
    bl_description = "Enters vertex paint mode and allows you to paint vertex colors of " \
        f"'{asset_helpers.AQ_MASK_NAME}' mask"
    bl_options = {'REGISTER'}

    def __init__(self) -> None:
        super().__init__()
        # Control properties for draw method
        self.should_create_mask = False
        self.display_mask_warning = False

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        if self.display_mask_warning:
            col = layout.column(align=True)
            col.alert = True
            col.label(text="aquatiq maskable material not found!")
            col.label(text="Painting may not do anything!")

        if self.should_create_mask:
            col = layout.column(align=True)
            col.label(text="Mask is not present on active object.")
            col.label(
                text=f"Do you want to create '{asset_helpers.AQ_MASK_NAME}' vertex color layer?")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.active_object is None:
            return False

        # Applicable only to data that has vertex colors to paint on
        if context.active_object.data is None or \
                not hasattr(context.active_object.data, "vertex_colors"):
            return False

        return True

    def execute(self, context: bpy.types.Context):
        # This is guaranteed by the poll method
        assert context.active_object is not None
        assert context.active_object.data is not None

        active_object = context.active_object
        mask = active_object.data.vertex_colors.get(asset_helpers.AQ_MASK_NAME, None)
        if mask is None:
            if self.should_create_mask:
                mask = active_object.data.vertex_colors.new(name=asset_helpers.AQ_MASK_NAME)
            else:
                self.report({'ERROR'}, f"Vertex color layer '{asset_helpers.AQ_MASK_NAME}' is missing "
                            "from active object!")
                return {'CANCELLED'}

        active_object.data.vertex_colors.active = mask
        # Disable paint masks, this would confuse user if it is not possible to paint from scratch
        active_object.data.use_paint_mask_vertex = False
        active_object.data.use_paint_mask = False
        bpy.ops.object.mode_set(mode='VERTEX_PAINT')
        prefs = preferences.prefs_utils.get_preferences(context).aquatiq_preferences
        context.tool_settings.vertex_paint.brush.color = [prefs.draw_mask_factor] * 3

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # This is guaranteed by the poll method
        assert context.active_object is not None
        assert context.active_object.data is not None

        self.display_mask_warning = False
        self.should_create_mask = False

        maskable_node_groups = polib.node_utils_bpy.get_top_level_material_nodes_with_name(
            context.active_object,
            asset_helpers.AQ_MASKABLE_NODE_GROUP_NAMES
        )
        if next(maskable_node_groups, None) is None:
            self.display_mask_warning = True

        if context.active_object.data.vertex_colors.get(asset_helpers.AQ_MASK_NAME, None) is None:
            self.should_create_mask = True

        if self.display_mask_warning or self.should_create_mask:
            return context.window_manager.invoke_props_dialog(self)

        return self.execute(context)


MODULE_CLASSES.append(EnterVertexPaintMode)


@polib.log_helpers_bpy.logged_operator
class ApplyMask(bpy.types.Operator):
    bl_idname = "engon.aquatiq_apply_mask"
    bl_label = "Apply Mask"
    bl_description = "Applies current mask to all vertices or boundaries"
    bl_options = {'REGISTER', 'UNDO'}

    only_boundaries: bpy.props.BoolProperty(
        name="Select Only Boundaries",
        description="If true only the boundaries are selected",
        default=False
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'PAINT_VERTEX' and context.vertex_paint_object is not None \
            and context.vertex_paint_object.data is not None

    def execute(self, context: bpy.types.Context):
        assert context.vertex_paint_object is not None
        assert context.vertex_paint_object.data is not None

        logger.info(f"Working with vertex paint object {context.vertex_paint_object.name}")
        mesh: bpy.types.Mesh = context.vertex_paint_object.data
        prev_use_mask_vertex = mesh.use_paint_mask_vertex
        try:
            mesh.use_paint_mask_vertex = True
            # To select boundary loops we need to go to edit mode, the operator isn't available
            # in vertex paint directly
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            if self.only_boundaries:
                bpy.ops.mesh.region_to_loop()
            # Switching to vertex paint mode keeps the selection
            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
            # Applies selected color to selected vertices
            bpy.ops.paint.vertex_color_set()
        finally:
            mesh.use_paint_mask_vertex = prev_use_mask_vertex

        return {'FINISHED'}


MODULE_CLASSES.append(ApplyMask)


@polib.log_helpers_bpy.logged_operator
class ReturnToObjectMode(bpy.types.Operator):
    bl_idname = "engon.aquatiq_return_to_object_mode"
    bl_label = "Return To Object Mode"
    bl_description = "If not in object mode go back to object mode"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'PAINT_VERTEX'

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}


MODULE_CLASSES.append(ReturnToObjectMode)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
