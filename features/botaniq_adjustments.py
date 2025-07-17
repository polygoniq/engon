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
from . import asset_pack_panels
from .. import polib
from .. import preferences
from .. import asset_helpers


MODULE_CLASSES = []


class BotaniqAdjustmentPreferences(bpy.types.PropertyGroup):
    brightness: bpy.props.FloatProperty(
        name="Brightness",
        description="Adjust assets brightness",
        default=1.0,
        min=0.0,
        max=10.0,
        soft_max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            BotaniqAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_BRIGHTNESS,
            self.brightness,
        ),
    )

    hue_per_branch: bpy.props.FloatProperty(
        name="Hue Per Branch",
        description="Randomize hue per branch",
        default=1.0,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            BotaniqAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH,
            self.hue_per_branch,
        ),
    )

    hue_per_leaf: bpy.props.FloatProperty(
        name="Hue Per Leaf",
        description="Randomize hue per leaf",
        default=1.0,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            BotaniqAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF,
            self.hue_per_leaf,
        ),
    )

    season_offset: bpy.props.FloatProperty(
        name="Season Offset",
        description="Change season of asset",
        default=1.0,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            BotaniqAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET,
            self.season_offset,
        ),
    )


MODULE_CLASSES.append(BotaniqAdjustmentPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class BotaniqAdjustmentsPanel(feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_feature_botaniq_adjustments"
    bl_parent_id = asset_pack_panels.BotaniqPanel.bl_idname
    bl_label = "Adjustments"
    feature_name = "botaniq_adjustments"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.BQ_BRIGHTNESS,
        polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH,
        polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF,
        polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return set(cls.get_selected_particle_system_targets(possible_assets)) | set(
            cls.filter_adjustable_assets_simple(possible_assets)
        )

    @classmethod
    def get_multiedit_adjustable_assets(
        cls, context: bpy.types.Context
    ) -> typing.Iterable[bpy.types.ID]:
        return set(cls.get_possible_assets(context)).union(
            asset_helpers.gather_instanced_objects(cls.get_possible_assets(context))
        )

    def get_season_from_value(self, value: float) -> str:
        # We need to change seasons at 0.125, 0.325, 0.625, 0.875
        # The list of seasons and values holds the "center" value of the season, not the boundaries
        # We need to do a bit of math to move it to get proper ranges. -0.125 moves from center to
        # start of the range, + 1.0 because fmod doesn't work with negative values
        adjusted_value: float = math.fmod(value - 0.125 + 1.0, 1.0)
        for season, max_value in reversed(polib.asset_pack.BOTANIQ_SEASONS_WITH_COLOR_CHANNEL):
            if adjusted_value <= max_value:
                return season
        return "unknown"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_HUE_SATURATION')

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.BQ_BRIGHTNESS
        )
        season_text = self.get_season_from_value(
            datablock.get(polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET, -1.0)
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET,
            text=season_text,
        )
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH
        )
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        prefs = preferences.prefs_utils.get_preferences(context).botaniq_adjustment_preferences
        row = layout.row(align=True)

        row.label(text="", icon='LIGHT_SUN')
        row.prop(prefs, "brightness", text="Brightness", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.BQ_BRIGHTNESS,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

        row = layout.row(align=True)
        row.label(text="", icon='FREEZE')
        row.prop(
            prefs,
            "season_offset",
            icon='FREEZE',
            text=f"Season: {self.get_season_from_value(prefs.season_offset)}",
            slider=True,
        )
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

        row = layout.row(align=True)
        row.label(text="", icon='COLORSET_12_VEC')
        row.prop(prefs, "hue_per_branch", text="Hue per Branch", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )

        row = layout.row(align=True)
        row.label(text="", icon='COLORSET_02_VEC')
        row.prop(prefs, "hue_per_leaf", text="Hue per Leaf", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF,
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
            ["Brightness", "Season", "Branch Hue", "Leaf Hue"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )
        layout.separator()
        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(BotaniqAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
