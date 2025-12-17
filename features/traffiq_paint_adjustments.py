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


class TraffiqPaintAdjustmentPreferences(bpy.types.PropertyGroup):
    primary_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        description="Changes primary color of assets",
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        size=4,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqPaintAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR,
            self.primary_color,
        ),
    )
    flakes_amount: bpy.props.FloatProperty(
        name="Flakes Amount",
        description="Changes amount of flakes in the car paint",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqPaintAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT,
            self.flakes_amount,
        ),
    )
    clearcoat: bpy.props.FloatProperty(
        name="Clearcoat",
        description="Changes clearcoat property of car paint",
        default=0.2,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            TraffiqPaintAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.TQ_CLEARCOAT,
            self.clearcoat,
        ),
    )


MODULE_CLASSES.append(TraffiqPaintAdjustmentPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class TraffiqPaintAdjustmentsPanel(
    feature_utils.TraffiqPropertyAssetFeatureControlPanelMixin, bpy.types.Panel
):
    bl_idname = "VIEW_3D_PT_engon_feature_traffiq_paint_adjustments"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_label = "Paint Adjustments"
    feature_name = "traffiq_paint_adjustments"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR,
        polib.custom_props_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT,
        polib.custom_props_bpy.CustomPropertyNames.TQ_CLEARCOAT,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def get_feature_icon(cls) -> str:
        return 'MOD_HUE_SATURATION'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon=self.get_feature_icon())

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR
        )
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_CLEARCOAT
        )
        self.draw_property(
            datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        prefs = preferences.prefs_utils.get_preferences(
            context
        ).traffiq_paint_adjustments_preferences
        col = layout.column()
        row = col.row(align=True)
        row.prop(prefs, "primary_color")
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR,
            feature_utils.RandomizeColorPropertyOperator,
            row,
            use_one_value_per_hierarchy=True,
        )
        row = col.row(align=True)
        row.prop(prefs, "clearcoat", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_CLEARCOAT,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
            use_one_value_per_hierarchy=True,
        )
        row = col.row(align=True)
        row.prop(prefs, "flakes_amount", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
            use_one_value_per_hierarchy=True,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Color", "Clearcoat", "Flakes Amount"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(TraffiqPaintAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
