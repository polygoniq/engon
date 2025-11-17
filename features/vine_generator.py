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
class VineGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "vine_generator"
    node_group_name = asset_helpers.BQ_VINE_GENERATOR_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class VineGeneratorPanel(
    VineGeneratorPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_vine_generator"
    bl_parent_id = asset_pack_panels.BotaniqPanel.bl_idname
    bl_label = "Vine Generator"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon="GRAPH")

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


MODULE_CLASSES.append(VineGeneratorPanel)


@polib.log_helpers_bpy.logged_panel
class VineGeneratorGeneralAdjustmentsPanel(
    VineGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_vine_generator_general_adjustments"
    bl_parent_id = VineGeneratorPanel.bl_idname
    bl_label = "General Adjustments"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_VINE_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Target Object",
            "Target Collection",
            "Merge Distance",
            "Curve Subdivision",
            "Cast to Target",
            "Angle Threshold",
            "Normal Orientation",
            "Seed",
        ),
        socket_names_drawn_first=["Target Object", "Target Collection"],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            VineGeneratorGeneralAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(VineGeneratorGeneralAdjustmentsPanel)


@polib.log_helpers_bpy.logged_panel
class VineGeneratorStemAdjustmentsPanel(
    VineGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_vine_generator_stem_adjustments"
    bl_parent_id = VineGeneratorPanel.bl_idname
    bl_label = "Stem Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_VINE_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Stem",
        ),
        socket_names_drawn_first=[
            "Stem Material",
        ],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            VineGeneratorStemAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(VineGeneratorStemAdjustmentsPanel)


@polib.log_helpers_bpy.logged_panel
class VineGeneratorLeavesAdjustmentsPanel(
    VineGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_vine_generator_leaves_adjustments"
    bl_parent_id = VineGeneratorPanel.bl_idname
    bl_label = "Leaves Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_VINE_GENERATOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Leaves",
            "Leaf",
            "Min Scale",
            "Max Scale",
            "Rotation Sky",
            "Deviation Sky",
        ),
        socket_names_drawn_first=[
            "Leaves Collection",
        ],
    )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            VineGeneratorLeavesAdjustmentsPanel.template,
        )


MODULE_CLASSES.append(VineGeneratorLeavesAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
