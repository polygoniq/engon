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
from .. import preferences
from . import asset_pack_panels


MODULE_CLASSES = []


BUMPS_MODIFIER_NAME = "tq_bumps_displacement"
BUMPS_MODIFIERS_CONTAINER_NAME = "tq_Bump_Modifiers_Container"


class TraffiqWearPreferences(bpy.types.PropertyGroup):
    @staticmethod
    def update_bumps_prop(
        context: bpy.types.Context,
        possible_objects: typing.Iterable[bpy.types.Object],
        value: float,
    ):
        # Cache objects that support bumps
        bumps_objs = [
            obj
            for obj in possible_objects
            if polib.custom_props_bpy.CustomPropertyNames.TQ_BUMPS in obj
        ]

        modifier_library_path = None

        # Add bumps modifier that improves bumps effect on editable objects.
        # Bumps work for linked assets but looks better on editable ones with added modifier
        for obj in bumps_objs:
            # Object is not editable mesh
            if obj.data is None or obj.type != "MESH":
                continue
            # If modifier is not assigned to the object, append it from library
            if BUMPS_MODIFIER_NAME not in obj.modifiers:
                if modifier_library_path is None:
                    modifier_library_path = asset_helpers.get_asset_pack_library_path(
                        "traffiq", asset_helpers.TQ_MODIFIER_LIBRARY_BLEND
                    )
                    if modifier_library_path is None:
                        raise RuntimeError("Modifier library of traffiq not found!")
                polib.asset_pack_bpy.append_modifiers_from_library(
                    BUMPS_MODIFIERS_CONTAINER_NAME, modifier_library_path, [obj]
                )
                logger.info(f"Added bumps modifier on: {obj.name}")

            assert BUMPS_MODIFIER_NAME in obj.modifiers
            obj.modifiers[BUMPS_MODIFIER_NAME].strength = value

        polib.custom_props_bpy.update_custom_prop(
            context, bumps_objs, polib.custom_props_bpy.CustomPropertyNames.TQ_BUMPS, value
        )

    dirt_wear_strength: bpy.props.FloatProperty(
        name="Dirt",
        description="Makes assets look dirty",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqWearAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_DIRT,
            self.dirt_wear_strength,
        ),
    )
    scratches_wear_strength: bpy.props.FloatProperty(
        name="Scratches",
        description="Makes assets look scratched",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqWearAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_SCRATCHES,
            self.scratches_wear_strength,
        ),
    )
    bumps_wear_strength: bpy.props.FloatProperty(
        name="Bumps",
        description="Makes assets look dented, appends displacement modifier for better effect if object is editable",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        update=lambda self, context: TraffiqWearPreferences.update_bumps_prop(
            context,
            TraffiqWearAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            self.bumps_wear_strength,
        ),
    )


MODULE_CLASSES.append(TraffiqWearPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class TraffiqWearAdjustmentsPanel(
    feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel
):
    bl_idname = "VIEW_3D_PT_engon_feature_traffiq_wear_adjustments"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_label = "Wear Adjustments"
    feature_name = "traffiq_wear"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.TQ_DIRT,
        polib.custom_props_bpy.CustomPropertyNames.TQ_SCRATCHES,
        polib.custom_props_bpy.CustomPropertyNames.TQ_BUMPS,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_hierarchical(possible_assets)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='UV')

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_DIRT)
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_SCRATCHES
        )
        self.draw_property(datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_BUMPS)

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        prefs = preferences.prefs_utils.get_preferences(context).traffiq_wear_preferences
        col = layout.column()

        row = col.row(align=True)
        row.prop(prefs, "dirt_wear_strength", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_DIRT,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

        row = col.row(align=True)
        row.prop(prefs, "scratches_wear_strength", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_SCRATCHES,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

        row = col.row(align=True)
        row.prop(prefs, "bumps_wear_strength", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_BUMPS,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        possible_assets = self.get_possible_assets(context)
        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Dirt", "Scratches", "Bumps"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(TraffiqWearAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
