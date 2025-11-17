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
from .. import __package__ as base_package
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


class AssetPackPanelMixin(feature_utils.EngonFeaturePanelMixin):
    """Base mixin for engon asset pack panels. Feature name holds the name of the asset pack.

    Asset pack panel appears (polls True) if and only if an asset pack that is associated
    with the panel is registered.
    """

    bl_options = {'DEFAULT_CLOSED'}
    layout: bpy.types.UILayout

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(
            text="",
            icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id(self.feature_name),
        )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        polib.ui_bpy.draw_doc_button(
            self.layout,
            base_package,
            rel_url=f"panels/{self.feature_name}/panel_overview",
        )


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class BotaniqPanel(AssetPackPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_botaniq"
    bl_label = "botaniq"
    bl_order = 11

    feature_name = "botaniq"

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(BotaniqPanel)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class InterniqPanel(AssetPackPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_interniq"
    bl_label = "interniq"
    bl_order = 12

    feature_name = "interniq"

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(InterniqPanel)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class TraffiqPanel(AssetPackPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq"
    bl_label = "traffiq"
    bl_order = 13

    feature_name = "traffiq"

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(TraffiqPanel)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class AquatiqPanel(AssetPackPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_aquatiq"
    bl_label = "aquatiq"
    bl_order = 14

    feature_name = "aquatiq"

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(AquatiqPanel)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class AesthetiqPanel(AssetPackPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_aesthetiq"
    bl_label = "aesthetiq"
    bl_order = 15

    feature_name = "aesthetiq"

    def draw(self, context: bpy.types.Context):
        pass


MODULE_CLASSES.append(AesthetiqPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
