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
from . import feature_utils
from .. import polib
from .. import asset_helpers
from . import asset_pack_panels

MODULE_CLASSES: list[type] = []


@feature_utils.register_feature
class BranchMaskingPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "branch_masking"
    node_group_name = asset_helpers.BQ_MASK_BRANCHES_NODE_GROUP_NAME


@feature_utils.register_feature
class LeavesMaskingPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "leaves_masking"
    node_group_name = asset_helpers.BQ_MASK_LEAVES_NODE_GROUP_NAME


@polib.log_helpers_bpy.logged_panel
class BranchAndLeavesMaskingPanel(bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_botaniq_branch_and_leaves_masking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"
    bl_parent_id = asset_pack_panels.BotaniqPanel.bl_idname
    bl_label = "Branch and Leaves Masking"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return BranchMaskingPanelMixin.poll(context) or LeavesMaskingPanelMixin.poll(context)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_OB_EMPTY')

    def draw(self, context: bpy.types.Context) -> None:
        pass


MODULE_CLASSES.append(BranchAndLeavesMaskingPanel)


@polib.log_helpers_bpy.logged_panel
class BranchMaskingPanel(
    BranchMaskingPanelMixin,
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_branch_masking"
    bl_parent_id = BranchAndLeavesMaskingPanel.bl_idname
    bl_label = "Branch Masking"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_MASK_BRANCHES_NODE_GROUP_NAME
    )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = type(self).feature_name

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        if self.conditionally_draw_warning_no_adjustable_active_object(context, layout):
            return
        self.draw_active_object_modifiers_node_group_inputs_template(
            layout,
            context,
            BranchMaskingPanel.template,
        )


MODULE_CLASSES.append(BranchMaskingPanel)


@polib.log_helpers_bpy.logged_panel
class LeavesMaskingPanel(
    LeavesMaskingPanelMixin,
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_botaniq_leaves_masking"
    bl_parent_id = BranchAndLeavesMaskingPanel.bl_idname
    bl_label = "Leaves Masking"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.BQ_MASK_LEAVES_NODE_GROUP_NAME
    )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = type(self).feature_name

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        if self.conditionally_draw_warning_no_adjustable_active_object(context, layout):
            return
        self.draw_active_object_modifiers_node_group_inputs_template(
            layout,
            context,
            LeavesMaskingPanel.template,
        )


MODULE_CLASSES.append(LeavesMaskingPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
