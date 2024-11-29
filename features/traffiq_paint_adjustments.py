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
import random
from . import feature_utils
from .. import polib
from .. import preferences
from . import asset_pack_panels


MODULE_CLASSES = []


class TraffiqPaintAdjustmentPreferences(bpy.types.PropertyGroup):
    @staticmethod
    def update_car_paint_color_prop(
        context,
        affected_assets: typing.Iterable[bpy.types.Object],
        value: typing.Tuple[float, float, float, float],
    ):
        # Don't allow to accidentally set color to random
        if all(v > 0.99 for v in value[:3]):
            value = (0.99, 0.99, 0.99, value[3])

        polib.custom_props_bpy.update_custom_prop(
            context,
            affected_assets,
            polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR,
            value,
        )

    primary_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        description="Changes primary color of assets",
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        size=4,
        update=lambda self, context: TraffiqPaintAdjustmentPreferences.update_car_paint_color_prop(
            context,
            TraffiqPaintAdjustmentsPanel.get_multiedit_adjustable_assets(context),
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

RANDOM_COLOR = (1.0, 1.0, 1.0, 1.0)


@polib.log_helpers_bpy.logged_operator
class SetColor(bpy.types.Operator):
    bl_idname = "engon.traffiq_paint_adjustments_set_color"
    bl_label = "Set Color to given value"
    bl_description = "Set color of selected assets to given value"

    bl_options = {'REGISTER', 'UNDO'}

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0, 1.0),
        size=4,
    )
    obj_name: bpy.props.StringProperty(
        name="Object Name",
        description="Name of the object to set color to. If unset, all selected objects will be affected",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT'

    def execute(self, context: bpy.types.Context):
        affected_objects = []
        if self.obj_name is not None and self.obj_name != "":
            affected_objects = [bpy.data.objects[self.obj_name]]
        else:
            possible_assets = TraffiqPaintAdjustmentsPanel.extend_with_active_object(
                context, context.selected_objects
            )
            affected_objects = TraffiqPaintAdjustmentsPanel.filter_adjustable_assets(
                possible_assets
            )

        for obj in affected_objects:
            if obj.get(polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR, None) is None:
                continue

            obj[polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR] = self.color
            obj.update_tag(refresh={'OBJECT'})

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


MODULE_CLASSES.append(SetColor)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class TraffiqPaintAdjustmentsPanel(
    feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel
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

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_hierarchical(possible_assets)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_HUE_SATURATION')

    def draw_properties(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        current_color = datablock.get(
            polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR, None
        )
        if current_color is None:
            layout.label(text="-")
        elif tuple(current_color) == RANDOM_COLOR:
            layout.label(text="Random")
            op = layout.operator(
                SetColor.bl_idname,
                text="",
                icon='CANCEL',
            )
            op.color = (
                random.uniform(0.0, 1.0),
                random.uniform(0.0, 1.0),
                random.uniform(0.0, 1.0),
                1.0,
            )
            op.obj_name = datablock.name
        else:
            self.draw_property(
                datablock, layout, polib.custom_props_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR
            )
            op = layout.operator(
                SetColor.bl_idname,
                text="",
                icon='FILE_3D',
            )
            op.color = RANDOM_COLOR
            op.obj_name = datablock.name
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
        )
        row = col.row(align=True)
        row.prop(prefs, "clearcoat", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_CLEARCOAT,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )
        row = col.row(align=True)
        row.prop(prefs, "flakes_amount", slider=True)
        self.draw_randomize_property_operator(
            polib.custom_props_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT,
            feature_utils.RandomizeFloatPropertyOperator,
            row,
        )
        row = self.layout.row()
        op = row.operator(SetColor.bl_idname, icon='COLOR', text="Set Color to Random in Shader")
        op.obj_name = ""
        op.color = RANDOM_COLOR

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
