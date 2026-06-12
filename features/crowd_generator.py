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
from . import asset_pack_panels
from .. import polib
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


@feature_utils.register_feature
class CrowdGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "crowd_generator"
    node_group_name = asset_helpers.HQ_CROWD_GENERATOR_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class CrowdGeneratorPanel(
    CrowdGeneratorPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_crowd_generator"
    bl_parent_id = asset_pack_panels.HumaniqPanel.bl_idname
    bl_label = "Crowd Generator"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.HQ_CROWD_GENERATOR_NODE_GROUP_NAME,
    )

    @classmethod
    def get_feature_icon(cls) -> str:
        return 'COMMUNITY'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon=self.get_feature_icon())

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        if self.conditionally_draw_warning_no_adjustable_active_object(context, layout):
            return
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            CrowdGeneratorPanel.template,
        )


MODULE_CLASSES.append(CrowdGeneratorPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
