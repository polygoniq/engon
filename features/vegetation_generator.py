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
from . import feature_utils
from . import asset_pack_panels
from .. import polib
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


@feature_utils.register_feature
class VegetationGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "vegetation_generator"
    node_group_name = asset_helpers.BQ_CURVES_GENERATOR_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class VegetationGeneratorPanel(
    VegetationGeneratorPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_vegetation_generator"
    bl_parent_id = asset_pack_panels.BotaniqPanel.bl_idname
    bl_label = "Vegetation Generator"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_CURVES_GENERATOR_NODE_GROUP_NAME,
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_DATA_CURVES')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        if self.conditionally_draw_warning_no_adjustable_active_object(context, layout):
            return
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            VegetationGeneratorPanel.template,
        )


MODULE_CLASSES.append(VegetationGeneratorPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
