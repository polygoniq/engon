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
import math
from . import feature_utils
from .. import polib
from .. import preferences
from . import asset_pack_panels


MODULE_CLASSES = []


MAIN_LIGHT_STATUS = [
    ("0", "Off", "Front and rear lights are off"),
    ("0.25", "Parking", "Parking lights are on"),
    ("0.50", "Low-Beam", "Low-Beam lights are on"),
    ("0.75", "High-Beam", "High-Beam lights are on"),
]


def get_main_lights_status_text(value: float) -> str:
    ret = "Unknown"
    for min_value, status, _ in MAIN_LIGHT_STATUS:
        if value < float(min_value):
            return ret
        ret = status
    if math.isclose(value, 420.0, abs_tol=0.001):
        ret = "Blaze it"
    return ret


class TraffiqLightsSettingsPreferences(bpy.types.PropertyGroup):
    main_lights_status: bpy.props.EnumProperty(
        name="Main Lights Status",
        items=MAIN_LIGHT_STATUS,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqLightsSettingsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_LIGHTS,
            float(self.main_lights_status),
        ),
    )

    main_lights_custom_strength: bpy.props.FloatProperty(
        name="Light Strength",
        description="Custom value for main lights status",
        min=0.0,
        soft_max=10.0,
        max=1_000_000.0,
        default=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqLightsSettingsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_LIGHTS,
            self.main_lights_custom_strength,
        ),
    )

    main_lights_use_custom_strength: bpy.props.BoolProperty(
        name="Custom Value",
        description="If true, main lights will be set to custom float value",
        default=False,
    )


MODULE_CLASSES.append(TraffiqLightsSettingsPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class TraffiqLightsSettingsPanel(
    feature_utils.TraffiqPropertyAssetFeatureControlPanelMixin, bpy.types.Panel
):
    bl_idname = "VIEW_3D_PT_engon_feature_traffiq_lights_settings"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_label = "Lights Settings"
    feature_name = "traffiq_lights_settings"
    related_custom_properties = {polib.custom_props_bpy.CustomPropertyNames.TQ_LIGHTS}
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_OB_LIGHT')

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        layout.prop(
            datablock,
            f'["{polib.custom_props_bpy.CustomPropertyNames.TQ_LIGHTS}"]',
            text=get_main_lights_status_text(
                datablock[polib.custom_props_bpy.CustomPropertyNames.TQ_LIGHTS]
            ),
            # slider=True,
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        prefs = preferences.prefs_utils.get_preferences(context).traffiq_lights_settings_preferences
        row = layout.row()
        row.prop(prefs, "main_lights_use_custom_strength")
        if prefs.main_lights_use_custom_strength:
            row.prop(prefs, "main_lights_custom_strength")
        else:
            row.prop(
                prefs,
                "main_lights_status",
                text="Status",
                icon='LIGHTPROBE_GRID' if bpy.app.version < (4, 1, 0) else 'LIGHTPROBE_VOLUME',
            )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return
        self.conditionally_draw_warning_not_cycles(context, layout)

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Light Strength"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(TraffiqLightsSettingsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
