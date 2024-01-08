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
import polib
from . import paint_mask
from . import puddles
from . import materials
from .. import preferences
from .. import asset_registry
from .. import asset_helpers
from .. import ui_utils


AQ_PAINT_VERTICES_WARNING_THRESHOLD = 16


MODULE_CLASSES: typing.List[typing.Type] = []


class AquatiqPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("aquatiq")) > 0


@polib.log_helpers_bpy.logged_panel
class AquatiqPanel(AquatiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq"
    bl_label = "aquatiq"
    bl_order = 10

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(
            text="", icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("aquatiq"))

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(AquatiqPanel)


class MaterialsPanel(AquatiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_materials"
    bl_parent_id = AquatiqPanel.bl_idname
    bl_label = "Material"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon="OUTLINER_OB_FORCE_FIELD")

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.draw_material_limitations(self.layout, context.active_object)

    def draw_material_limitations(self, layout: bpy.types.UILayout, obj: bpy.types.Object):
        if obj is None:
            return

        active_material = obj.active_material
        if active_material is None:
            return

        material_name = polib.utils_bpy.remove_object_duplicate_suffix(active_material.name)
        warnings = materials.get_material_warnings_obj_based(obj, material_name)

        if len(warnings) == 0:
            return

        layout.alert = True
        op = layout.operator(ui_utils.ShowPopup.bl_idname, text="", icon='ERROR')
        op.message = "\n".join(warnings)
        op.title = "Material limitations warning"
        op.icon = 'ERROR'

    def draw_vertex_paint_ui(self, context: bpy.types.Context):
        layout = self.layout
        prefs = preferences.get_preferences(context).aquatiq_preferences
        brush = context.tool_settings.vertex_paint.brush
        unified_settings = context.tool_settings.unified_paint_settings

        if context.vertex_paint_object is None or context.vertex_paint_object.data is None:
            return

        mesh_data = context.vertex_paint_object.data

        if len(mesh_data.vertices) <= AQ_PAINT_VERTICES_WARNING_THRESHOLD:
            layout.label(text="Subdivide the mesh for more control!", icon='ERROR')

        col = layout.column(align=True)
        polib.ui_bpy.row_with_label(col, text="Mask")
        row = col.row(align=True)
        row.prop(prefs, "draw_mask_factor", slider=True)
        # Wrap color in another row to scale it so it is more rectangular
        color_wrapper = row.row(align=True)
        color_wrapper.scale_x = 0.3
        color_wrapper.prop(brush, "color", text="")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(paint_mask.ApplyMask.bl_idname,
                     text="Boundaries", icon='MATPLANE').only_boundaries = True
        row.operator(paint_mask.ApplyMask.bl_idname,
                     text="Fill", icon='SNAP_FACE').only_boundaries = False

        col = layout.column(align=True)
        polib.ui_bpy.row_with_label(col, text="Brush")
        col.prop(brush, "strength")
        col.prop(unified_settings, "size", slider=True)

        col = layout.column(align=True)
        polib.ui_bpy.row_with_label(col, text="Paint Only to Selected")
        row = col.row(align=True)
        row.prop(mesh_data, "use_paint_mask_vertex", text="Vertex")
        row.prop(mesh_data, "use_paint_mask", text="Face")

        layout.operator(paint_mask.ReturnToObjectMode.bl_idname, text="Return", icon='LOOP_BACK')

    def draw(self, context: bpy.types.Context):
        if context.mode == 'PAINT_VERTEX':
            self.draw_vertex_paint_ui(context)
            return

        layout: bpy.types.UILayout = self.layout

        asset_col = layout.column(align=True)
        polib.ui_bpy.scaled_row(asset_col, 1.2).operator(
            paint_mask.EnterVertexPaintMode.bl_idname, text="Paint Alpha Mask", icon='MOD_MASK'
        )


MODULE_CLASSES.append(MaterialsPanel)


class PuddlesPanel(AquatiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_puddles"
    bl_parent_id = MaterialsPanel.bl_idname
    bl_label = "Puddles"

    @classmethod
    def poll(self, context: bpy.types.Context) -> bool:
        return context.mode != 'PAINT_VERTEX'

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='MATFLUID')

    def draw_puddle_features(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        if context.active_object is None:
            return

        mat = context.active_object.active_material
        if mat is None:
            return

        puddles_name = asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
        puddle_nodes = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, puddles_name)
        if len(puddle_nodes) == 0:
            return
        puddle_props = preferences.get_preferences(context).aquatiq_preferences.puddle_properties

        col = layout.column(align=True)
        col.prop(puddle_props, "puddle_factor")
        col.prop(puddle_props, "puddle_scale")
        col.prop(puddle_props, "animation_speed")
        col.prop(puddle_props, "noise_strength")
        col.prop(puddle_props, "angle_threshold")

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout

        self.draw_puddle_features(context, layout)
        layout.operator(puddles.AddPuddles.bl_idname, icon='ADD')
        layout.operator(puddles.RemovePuddles.bl_idname, icon='PANEL_CLOSE')


MODULE_CLASSES.append(PuddlesPanel)


def register(panel_name: str = "aquatiq"):
    AquatiqPanel.bl_label = panel_name
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
