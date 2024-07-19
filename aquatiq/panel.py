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
from .. import polib
from . import paint_mask
from . import puddles
from . import materials
from .. import preferences
from .. import asset_registry
from .. import asset_helpers
from .. import ui_utils
from .. import __package__ as base_package


AQ_PAINT_VERTICES_WARNING_THRESHOLD = 16


MODULE_CLASSES: typing.List[typing.Type] = []


class AquatiqPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("aquatiq")) > 0


class RainGeneratorPanelMixin(
    AquatiqPanelInfoMixin, polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin
):
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        if obj is None:
            return False
        return (
            len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME
                )
            )
            > 0
        )


class RiverGeneratorPanelMixin(
    AquatiqPanelInfoMixin, polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin
):
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        if obj is None:
            return False
        return (
            len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME
                )
            )
            > 0
        )


@polib.log_helpers_bpy.logged_panel
class AquatiqPanel(AquatiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_aquatiq"
    bl_label = "aquatiq"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(
            text="", icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("aquatiq")
        )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        polib.ui_bpy.draw_doc_button(
            self.layout,
            base_package,
            rel_url="panels/aquatiq/panel_overview",
        )

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(AquatiqPanel)


class MaterialsPanel(AquatiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_aquatiq_materials"
    bl_parent_id = AquatiqPanel.bl_idname
    bl_label = "Material Adjustments"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_OCEAN')

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
        prefs = preferences.prefs_utils.get_preferences(context).aquatiq_preferences
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
        row.operator(
            paint_mask.ApplyMask.bl_idname, text="Boundaries", icon='MATPLANE'
        ).only_boundaries = True
        row.operator(
            paint_mask.ApplyMask.bl_idname, text="Fill", icon='SNAP_FACE'
        ).only_boundaries = False

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
    bl_idname = "VIEW_3D_PT_engon_aquatiq_puddles"
    bl_parent_id = MaterialsPanel.bl_idname
    bl_label = "Puddles"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_PUDDLES_NODEGROUP_NAME,
        filter_=lambda x: not polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Water Color",
            "Noise Scale",
        ),
    )

    @classmethod
    def poll(self, context: bpy.types.Context) -> bool:
        return context.mode != 'PAINT_VERTEX'

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='MATFLUID')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout

        layout.operator(puddles.AddPuddles.bl_idname, icon='ADD')
        layout.operator(puddles.RemovePuddles.bl_idname, icon='PANEL_CLOSE')

        if context.active_object is not None and puddles.check_puddles_nodegroup_count(
            [context.active_object], lambda x: x != 0
        ):
            col = layout.column(align=True)
            PuddlesPanel.template.draw_from_material(context.active_object.active_material, col)


MODULE_CLASSES.append(PuddlesPanel)


class RainGeneratorPanel(RainGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_rain_generator"
    bl_parent_id = AquatiqPanel.bl_idname
    bl_label = "Rain Generator"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            super().poll(context)
            or bpy.data.node_groups.get(asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME, None)
            is not None
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_DATA_LIGHTPROBE')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        obj = context.active_object
        if (
            obj is None
            or len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME
                )
            )
            == 0
        ):
            layout.label(text="Select a Rain Generator object")


MODULE_CLASSES.append(RainGeneratorPanel)


class RainGeneratorGeneralAdjustmentsPanel(RainGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_rain_generator_general_adjustments"
    bl_parent_id = RainGeneratorPanel.bl_idname
    bl_label = "General Adjustments"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x, "Self Object", "Realize Instances", "Collision", "Rain", "Randomize"
        ),
        socket_names_drawn_first=[
            "Self Object",
            "Collision Collection",
        ],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RainGeneratorGeneralAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(RainGeneratorGeneralAdjustmentsPanel)


class RainGeneratorSplashEffectsPanel(RainGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_rain_generator_splash_effects"
    bl_parent_id = RainGeneratorPanel.bl_idname
    bl_label = "Splash Effects"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "Splashes", "2D Effects"),
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RainGeneratorSplashEffectsPanel.template,
        )


MODULE_CLASSES.append(RainGeneratorSplashEffectsPanel)


class RainGeneratorCameraAdjustmentsPanel(RainGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_rain_generator_camera_adjustments"
    bl_parent_id = RainGeneratorPanel.bl_idname
    bl_label = "Camera Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "Camera", "Culling"),
        socket_names_drawn_first=["Camera Culling Camera"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RainGeneratorCameraAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(RainGeneratorCameraAdjustmentsPanel)


class RiverGeneratorPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator"
    bl_parent_id = AquatiqPanel.bl_idname
    bl_label = "River Generator"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            super().poll(context)
            or bpy.data.node_groups.get(asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME, None)
            is not None
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='FORCE_FORCE')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        obj = context.active_object
        if (
            obj is None
            or len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME
                )
            )
            == 0
        ):
            layout.label(text="Select a River Generator object")


MODULE_CLASSES.append(RiverGeneratorPanel)


class RiverGeneratorGeneralAdjustmentsPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator_general_adjustments"
    bl_parent_id = RiverGeneratorPanel.bl_idname
    bl_label = "General Adjustments"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Self Object",
            "Resolution",
            "Width",
            "Depth",
            "Seed",
            "Animation Speed",
        )
        and not polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Bank Width",
        ),
        socket_names_drawn_first=["Self Object"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RiverGeneratorGeneralAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(RiverGeneratorGeneralAdjustmentsPanel)


class RiverGeneratorBankRiverbedAdjustmentsPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator_bank_riverbed_adjustments"
    bl_parent_id = RiverGeneratorPanel.bl_idname
    bl_label = "Bank and Riverbed Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "Bank", "Riverbed"),
        socket_names_drawn_first=["Bank Material", "Riverbed Material"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RiverGeneratorBankRiverbedAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(RiverGeneratorBankRiverbedAdjustmentsPanel)


class RiverGeneratorScatterPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator_scatter"
    bl_parent_id = RiverGeneratorPanel.bl_idname
    bl_label = "Rocks and Vegetation"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "Vegetation", "Rocks"),
        socket_names_drawn_first=["Rocks", "Vegetation"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RiverGeneratorScatterPanel.template,
        )


MODULE_CLASSES.append(RiverGeneratorScatterPanel)


class RiverGeneratorAdvancedAdjustmentsPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator_advanced_adjustments"
    bl_parent_id = RiverGeneratorPanel.bl_idname
    bl_label = "Advanced Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x, "Noise", "Foam", "Caustic", "Collision"
        )
        and not polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Rocks Collision Complexity",
        ),
        socket_names_drawn_first=["Collision"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RiverGeneratorAdvancedAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(RiverGeneratorAdvancedAdjustmentsPanel)


def register(panel_name: str = "aquatiq"):
    AquatiqPanel.bl_label = panel_name
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
