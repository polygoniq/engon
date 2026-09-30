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

from . import feature_utils
from .. import polib
from .. import asset_helpers
from .. import materialiq

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


@feature_utils.register_feature
class MaterialiqHDRIPanelMixin(feature_utils.EngonFeaturePanelMixin):
    feature_name = "materialiq_hdri"


@polib.log_helpers_bpy.logged_panel
class HDRIPanel(MaterialiqHDRIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_hdri"
    bl_parent_id = materialiq.panel.MaterialiqPanel.bl_idname
    bl_label = "HDRI"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def get_feature_icon(cls) -> str:
        return 'WORLD'

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon=type(self).get_feature_icon())

    def draw(self, context: bpy.types.Context) -> None:
        pass


MODULE_CLASSES.append(HDRIPanel)


class HDRIBackgroundPanel(MaterialiqHDRIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_hdri_background"
    bl_parent_id = HDRIPanel.bl_idname
    bl_label = "Background"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.MQ_HDRI_BACKGROUND_NODE_GROUP_NAME,
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout

        if (
            context.scene.world is None
            or context.scene.world.node_tree is None
            or (
                len(
                    polib.node_utils_bpy.find_nodegroups_by_name(
                        context.scene.world.node_tree,
                        asset_helpers.MQ_HDRI_BACKGROUND_NODE_GROUP_NAME,
                    )
                )
                == 0
            )
        ):
            layout.label(text="Scene does not contain world with HDRI Background feature")
            return

        col = layout.column(align=True)
        type(self).template.draw_from_datablock(context.scene.world, col)


MODULE_CLASSES.append(HDRIBackgroundPanel)


class HDRIDomePanel(
    MaterialiqHDRIPanelMixin,
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_materialiq_hdri_dome"
    bl_parent_id = HDRIPanel.bl_idname
    bl_label = "Dome"

    dome_mapping_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.MQ_HDRI_DOME_MAPPING_NODE_GROUP_NAME,
    )
    dome_color_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.MQ_HDRI_DOME_COLOR_NODE_GROUP_NAME,
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x, "Normal Strength", "Alpha", "Ground Roughness", "Ground Boost"
        ),
    )
    dome_geometry_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.MQ_HDRI_DOME_GEOMETRY_NODE_GROUP_NAME,
        filter_=lambda x: not polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Material",
        ),
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout

        active_object = context.active_object
        dome_geometry_mods: list[bpy.types.NodesModifier] = []
        if active_object is not None and active_object.type == 'MESH':
            dome_geometry_mods = (
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    active_object,
                    asset_helpers.MQ_HDRI_DOME_GEOMETRY_NODE_GROUP_NAME,
                )
            )

        if len(dome_geometry_mods) == 0:
            layout.label(text="No active object with HDRI Dome feature")
            return

        found_material = None
        mod_inputs = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(dome_geometry_mods[0])
        if "Material" in mod_inputs:
            found_material = mod_inputs.get_input_value("Material")

        can_draw_dome_mapping = False
        can_draw_dome_color = False
        if found_material is not None and found_material.node_tree is not None:
            can_draw_dome_color = (
                len(
                    polib.node_utils_bpy.find_nodegroups_by_name(
                        found_material.node_tree,
                        asset_helpers.MQ_HDRI_DOME_COLOR_NODE_GROUP_NAME,
                    )
                )
                > 0
            )
            can_draw_dome_mapping = (
                len(
                    polib.node_utils_bpy.find_nodegroups_by_name(
                        found_material.node_tree,
                        asset_helpers.MQ_HDRI_DOME_MAPPING_NODE_GROUP_NAME,
                    )
                )
                > 0
            )

        col = layout.column(align=True)
        if can_draw_dome_mapping and found_material is not None:
            type(self).dome_mapping_template.draw_from_datablock(found_material, col)
        if can_draw_dome_color and found_material is not None:
            type(self).dome_color_template.draw_from_datablock(found_material, col)
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            type(self).dome_geometry_template,
        )


MODULE_CLASSES.append(HDRIDomePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
