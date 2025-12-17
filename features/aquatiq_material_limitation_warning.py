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
from .. import utils
from .. import polib

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


class MaterialWarning:
    VOLUME = "Object has to have volume for this material to work correctly."
    SHORELINE = (
        "Material is from the complex shoreline scene, open it to see how it works with\n"
        "other materials to create the best result."
    )


MATERIAL_WARNING_MAP = {
    "aq_Water_Ocean": {MaterialWarning.SHORELINE, MaterialWarning.VOLUME},
    "aq_Water_Shoreline": {MaterialWarning.SHORELINE},
    "aq_Water_Swimming-Pool": {MaterialWarning.VOLUME},
    "aq_Water_Lake": {MaterialWarning.VOLUME},
    "aq_Water_Pond": {MaterialWarning.VOLUME},
}


def get_material_warnings_obj_based(obj: bpy.types.Object, material_name: str) -> set[str]:

    warnings = MATERIAL_WARNING_MAP.get(material_name, None)
    if warnings is None:
        return set()

    # Create copy of the original set so the original isn't modified
    warnings = set(warnings)
    if not polib.linalg_bpy.is_obj_flat(obj):
        warnings -= {MaterialWarning.VOLUME}

    return warnings


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class AquatiqMaterialLimitationsPanel(feature_utils.EngonFeaturePanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_aquatiq_material_limitation_warning"
    bl_parent_id = asset_pack_panels.AquatiqPanel.bl_idname
    bl_label = "Material Limitations"

    feature_name = "aquatiq_material_limitation_warning"

    @classmethod
    def get_material_limitations(cls, obj: bpy.types.Object | None) -> set[str]:
        if obj is None:
            return set()

        active_material = obj.active_material
        if active_material is None:
            return set()

        material_name = polib.utils_bpy.remove_object_duplicate_suffix(active_material.name)
        warnings = get_material_warnings_obj_based(obj, material_name)
        return warnings

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            super().poll(context)
            and context.active_object is not None
            and len(cls.get_material_limitations(context.active_object)) > 0
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.alert = True
        self.layout.label(text="", icon='ERROR')

    def draw_material_limitations(self, layout: bpy.types.UILayout, obj: bpy.types.Object | None):
        warnings = self.get_material_limitations(obj)

        if len(warnings) == 0:
            return

        layout.alert = True
        op = layout.operator(
            utils.show_popup.ShowPopup.bl_idname,
            text=f"See {len(warnings)} warning{'s' if len(warnings) > 1 else ''}",
            icon='ERROR',
        )
        op.message = "\n".join(warnings)
        op.title = "Material limitations warning"
        op.icon = 'ERROR'

    def draw(self, context: bpy.types.Context):
        self.draw_material_limitations(self.layout, context.active_object)


MODULE_CLASSES.append(AquatiqMaterialLimitationsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
