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
import math
import typing
from . import feature_utils
from .. import polib
from .. import preferences
from . import asset_pack_panels

MODULE_CLASSES = []


class LightAdjustmentsPreferences(bpy.types.PropertyGroup):
    @staticmethod
    def update_prop_with_use_rgb(
        context: bpy.types.Context,
        objs: typing.Iterable[bpy.types.Object],
        prop_name: str,
        value: polib.custom_props_bpy.CustomAttributeValueType,
        use_rgb_value: bool,
    ) -> None:
        materialized_objs = list(objs)
        polib.custom_props_bpy.update_custom_prop(
            context,
            materialized_objs,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            use_rgb_value,
        )
        polib.custom_props_bpy.update_custom_prop(
            context,
            materialized_objs,
            prop_name,
            value,
        )

    use_rgb: bpy.props.BoolProperty(
        name="Use Direct Coloring instead of Temperature",
        description="Use Direct Coloring instead of Temperature",
        default=False,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            LightAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            self.use_rgb,
        ),
    )

    light_temperature: bpy.props.IntProperty(
        name="Light Temperature",
        subtype='TEMPERATURE',
        description='Changes light temperature in Kelvins ranging from warm to cool',
        default=5000,
        min=0,  # blender "Temperature" shader node gets this wrong, 0K should be black, but its red
        max=12_000,  # blender "Temperature" shader node supports up to 12kK
        update=lambda self, context: LightAdjustmentsPreferences.update_prop_with_use_rgb(
            context,
            LightAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
            self.light_temperature,
            False,
        ),
    )

    light_rgb: bpy.props.FloatVectorProperty(
        name="Light Color",
        subtype='COLOR',
        description='Changes light color across the RGB spectrum',
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: LightAdjustmentsPreferences.update_prop_with_use_rgb(
            context,
            LightAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
            self.light_rgb,
            True,
        ),
    )

    light_strength: bpy.props.FloatProperty(
        name="Light Strength",
        default=0.0,
        description='Changes the intensity of the light',
        min=0.0,
        subtype='FACTOR',
        soft_max=200,  # mostly> interior use, exterior lights can go to 2000 or more
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            LightAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
            self.light_strength,
        ),
    )


MODULE_CLASSES.append(LightAdjustmentsPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class LightAdjustmentsPanel(feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_feature_light_adjustments"
    # TODO: this feature is currently interniq-only, but in the future it should be moved to engon panel,
    # once all other asset packs implement light adjustments
    bl_parent_id = asset_pack_panels.InterniqPanel.bl_idname
    bl_label = "Light Adjustments"
    feature_name = "light_adjustments"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
        polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
        polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
        polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_hierarchical(possible_assets)

    def conditionally_draw_warning_unapplied_scale(self, context, layout):
        unapplied_scale_objects = []
        for obj in self.filter_adjustable_assets(context.selected_objects):
            if isinstance(obj, bpy.types.Object) and not all(
                math.isclose(s, 1.0, rel_tol=1e-3) for s in obj.scale
            ):
                unapplied_scale_objects.append(obj)
        if len(unapplied_scale_objects) > 0:
            more_objects_warning = ""
            if len(unapplied_scale_objects) > 1:
                more_objects_warning = f' and {len(unapplied_scale_objects) - 1} other objects'
            row = layout.row()
            row.alert = True
            row.label(
                text=f"Unapplied scale on {unapplied_scale_objects[0].name}{more_objects_warning}, "
                f"this might result in incorrect light strength",
                icon='ERROR',
            )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='LIGHT')

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        layout = layout.row(align=True)
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            # text = invisible character, so the checkbox is aligned properly
            text=" ",
        )
        if datablock.get(polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB):
            self.draw_property(
                datablock,
                layout,
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
            )
        else:
            self.draw_property(
                datablock,
                layout,
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
            )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        prefs = preferences.prefs_utils.get_preferences(context).light_adjustments_preferences
        row = layout.row(align=True)
        row.prop(prefs, "use_rgb", text="Direct Coloring")
        if prefs.use_rgb:
            row.prop(prefs, "light_rgb", text="")
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
                feature_utils.RandomizeColorPropertyOperator,
                row,
            )
        else:
            row.prop(prefs, "light_temperature", text="Temperature (K)", slider=True)
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
                feature_utils.RandomizeIntegerPropertyOperator,
                row,
            )
        row.prop(prefs, "light_strength", text="Strength (W)", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        self.conditionally_draw_warning_not_cycles(context, layout)
        self.conditionally_draw_warning_unapplied_scale(context, layout)

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Direct Coloring", "Color/Temperature", "Strength"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(LightAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
