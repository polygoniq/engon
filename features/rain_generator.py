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

MODULE_CLASSES: typing.List[typing.Type] = []


@feature_utils.register_feature
class RainGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "rain_generator"
    node_group_name = asset_helpers.AQ_RAIN_GENERATOR_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class RainGeneratorPanel(RainGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_aquatiq_rain_generator"
    bl_parent_id = asset_pack_panels.AquatiqPanel.bl_idname
    bl_label = "Rain Generator"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_DATA_LIGHTPROBE')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        self.conditionally_draw_warning_no_adjustable_active_object(context, layout)


MODULE_CLASSES.append(RainGeneratorPanel)


class RainGeneratorGeneralAdjustmentsPanel(
    RainGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


class RainGeneratorSplashEffectsPanel(
    RainGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


class RainGeneratorCameraAdjustmentsPanel(
    RainGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):
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


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
