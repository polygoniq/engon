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

import typing
import bpy
from . import feature_utils
from .. import preferences
from .. import polib
from . import asset_pack_panels


MODULE_CLASSES = []


class PictorialAdjustmentsPreferences(bpy.types.PropertyGroup):
    contrast: bpy.props.FloatProperty(
        name="Contrast",
        description="Contrast adjustment",
        default=1.0,
        min=0.0,
        max=10.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            PictorialAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_CONTRAST,
            self.contrast,
        ),
    )

    saturation: bpy.props.FloatProperty(
        name="Saturation",
        description="Saturation adjustment",
        default=1.0,
        min=0.0,
        max=10.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            PictorialAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_SATURATION,
            self.saturation,
        ),
    )

    value: bpy.props.FloatProperty(
        name="Value",
        description="Value adjustment",
        default=1.0,
        min=0.0,
        max=10.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            PictorialAdjustmentsPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_VALUE,
            self.value,
        ),
    )


MODULE_CLASSES.append(PictorialAdjustmentsPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class PictorialAdjustmentsPanel(
    feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel
):
    bl_idname = "VIEW_3D_PT_engon_feature_pictorial_adjustments"
    bl_parent_id = asset_pack_panels.AesthetiqPanel.bl_idname
    bl_label = "Pictorial Adjustments"
    feature_name = "pictorial_adjustments"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_CONTRAST,
        polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_SATURATION,
        polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_VALUE,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_simple(possible_assets)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='UV')

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_CONTRAST,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_SATURATION,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PICTORIAL_ADJUSTMENT_VALUE,
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)
        prefs = preferences.prefs_utils.get_preferences(context).pictorial_adjustments_preferences
        row = layout.row(align=True)
        row.label(text="Contrast:")
        row.prop(prefs, "contrast", text="")
        row = layout.row(align=True)
        row.label(text="Saturation:")
        row.prop(prefs, "saturation", text="")
        row = layout.row(align=True)
        row.label(text="Value:")
        row.prop(prefs, "value", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Contrast", "Saturation", "Value"],
            layout,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(PictorialAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
