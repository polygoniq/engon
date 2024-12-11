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


class ColorizePreferences(bpy.types.PropertyGroup):
    primary_color: bpy.props.FloatVectorProperty(
        name="Primary color",
        subtype='COLOR',
        description="Changes primary color of assets",
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            ColorizePanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR,
            self.primary_color,
        ),
    )

    primary_color_factor: bpy.props.FloatProperty(
        name="Primary factor",
        description="Changes intensity of the primary color",
        default=0.0,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            ColorizePanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR,
            self.primary_color_factor,
        ),
    )

    secondary_color: bpy.props.FloatVectorProperty(
        name="Secondary color",
        subtype='COLOR',
        description="Changes secondary color of assets",
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            ColorizePanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR,
            self.secondary_color,
        ),
    )

    secondary_color_factor: bpy.props.FloatProperty(
        name="Secondary factor",
        description="Changes intensity of the secondary color",
        default=0.0,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            ColorizePanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
            self.secondary_color_factor,
        ),
    )


MODULE_CLASSES.append(ColorizePreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class ColorizePanel(feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_feature_colorize"
    # TODO: this feature is currently interniq-only, but in the future it should be moved to engon panel,
    # once all other asset packs implement colorize
    bl_parent_id = asset_pack_panels.InterniqPanel.bl_idname
    bl_label = "Colorize"
    feature_name = "colorize"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR,
        polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR,
        polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR,
        polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_simple(possible_assets)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_HUE_SATURATION')

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        primary_layout = layout.column().row(align=True)
        self.draw_property(
            datablock,
            primary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR,
        )
        self.draw_property(
            datablock,
            primary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR,
        )
        secondary_layout = layout.column().row(align=True)
        self.draw_property(
            datablock,
            secondary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR,
        )
        self.draw_property(
            datablock,
            secondary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).colorize_preferences
        row = layout.row(align=True)

        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR) is not None
            for o in adjustable_assets
        ):
            row.label(text="", icon='COLOR')
            row.prop(prefs, "primary_color", text="")
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR,
                feature_utils.RandomizeColorPropertyOperator,
                row,
            )
            row.prop(prefs, "primary_color_factor", text="Factor", slider=True)
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR,
                feature_utils.RandomizeFloatPropertyOperator,
                row,
            )
        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR) is not None
            for o in adjustable_assets
        ):
            row = layout.row(align=True)
            row.label(text="", icon='RESTRICT_COLOR_ON')
            row.prop(prefs, "secondary_color", text="")
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR,
                feature_utils.RandomizeColorPropertyOperator,
                row,
            )
            row.prop(prefs, "secondary_color_factor", text="Factor", slider=True)
            self.draw_randomize_property_operator(
                polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
                feature_utils.RandomizeFloatPropertyOperator,
                row,
            )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        row = self.layout.row()

        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)

        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")

        right_table_header = right_col.row(align=True)
        row = right_table_header.column().row(align=True)
        row.enabled = False
        row.label(text="Primary")
        row.label(text="Factor")

        row = right_table_header.column().row(align=True)
        row.enabled = False
        row.label(text="Secondary")
        row.label(text="Factor")

        self.draw_adjustable_assets_property_table_body(
            possible_assets,
            left_col,
            right_col,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        layout.separator()
        self.draw_multiedit(context, layout, possible_assets)


MODULE_CLASSES.append(ColorizePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
