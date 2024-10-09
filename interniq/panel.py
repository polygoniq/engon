# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
from .. import polib
from .. import asset_registry
from .. import __package__ as base_package

MODULE_CLASSES = []


class InterniqPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("interniq")) > 0


@polib.log_helpers_bpy.logged_panel
class InterniqPanel(InterniqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_interniq"
    bl_label = "interniq"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(
            text="", icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("interniq")
        )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        polib.ui_bpy.draw_doc_button(
            self.layout,
            base_package,
            rel_url="panels/interniq/panel_overview",
        )

    def draw(self, context: bpy.types.Context) -> None:
        pass


MODULE_CLASSES.append(InterniqPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
