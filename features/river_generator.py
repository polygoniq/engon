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
from . import feature_utils
from .. import polib
from .. import asset_helpers

from . import asset_pack_panels

MODULE_CLASSES: list[type] = []


@feature_utils.register_feature
class RiverGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "river_generator"
    node_group_name = asset_helpers.AQ_RIVER_GENERATOR_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class RiverGeneratorPanel(RiverGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_river_generator"
    bl_parent_id = asset_pack_panels.AquatiqPanel.bl_idname
    bl_label = "River Generator"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='FORCE_FORCE')

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        self.conditionally_draw_warning_no_adjustable_active_object(context, layout)


MODULE_CLASSES.append(RiverGeneratorPanel)


@polib.log_helpers_bpy.logged_panel
class RiverGeneratorGeneralAdjustmentsPanel(
    RiverGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


@polib.log_helpers_bpy.logged_panel
class RiverGeneratorBankRiverbedAdjustmentsPanel(
    RiverGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


@polib.log_helpers_bpy.logged_panel
class RiverGeneratorScatterPanel(
    RiverGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


@polib.log_helpers_bpy.logged_panel
class RiverGeneratorAdvancedAdjustmentsPanel(
    RiverGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
