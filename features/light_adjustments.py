# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import itertools
import typing
import math
from .. import polib
from .. import asset_registry
from .. import interniq
from .. import preferences

MODULE_CLASSES = []


class LightAdjustmentsPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("light_adjustments")) > 0


@polib.log_helpers_bpy.logged_panel
class LightAdjustmentsPanel(LightAdjustmentsPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_light_adjustments"
    # TODO: this feature is currently interniq-only, but in the future it should be moved to engon panel,
    # once all other asset packs implement light adjustments
    bl_parent_id = interniq.panel.InterniqPanel.bl_idname
    bl_label = "Light Adjustments"

    @staticmethod
    def get_adjustable_objects(
        possible_objects: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        possible_objects_and_children = itertools.chain.from_iterable(
            polib.asset_pack_bpy.get_hierarchy(obj) for obj in possible_objects
        )
        return filter(
            lambda obj: polib.asset_pack_bpy.has_engon_property_feature(obj, "light_adjustments"),
            possible_objects_and_children,
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='LIGHT')

    def draw_properties(self, obj: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        layout = layout.row(align=True)
        polib.ui_bpy.draw_property(
            obj,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            # text = invisible character, so the checkbox is aligned properly
            text=" ",
        )
        if obj.get(polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB):
            polib.ui_bpy.draw_property(
                obj,
                layout,
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
            )
        else:
            polib.ui_bpy.draw_property(
                obj,
                layout,
                polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
            )
        polib.ui_bpy.draw_property(
            obj,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        adjustable_lights = list(self.get_adjustable_objects(context.selected_objects))
        if len(adjustable_lights) == 0:
            layout.label(text="No assets with adjustable lights selected!")
            return

        unapplied_scale_lights = []
        for obj in adjustable_lights:
            if isinstance(obj, bpy.types.Object) and not all(
                math.isclose(s, 1.0, rel_tol=1e-3) for s in obj.scale
            ):
                unapplied_scale_lights.append(obj)

        if len(unapplied_scale_lights) > 0:
            more_objects_warning = ""
            leftover_lights_count = len(unapplied_scale_lights) - 1
            if leftover_lights_count > 0:
                more_objects_warning = f" and {leftover_lights_count} other light"
                more_objects_warning += 's' if leftover_lights_count > 1 else ''

            col = layout.column(align=True)
            col.alert = True
            col.label(
                text="Because of unapplied scale, strength is incorrect on:",
                icon='ERROR',
            )
            col.label(text=f"{unapplied_scale_lights[0].name}{more_objects_warning}!")

        if context.scene.render.engine != 'CYCLES':
            row = layout.row()
            row.alert = True
            row.label(text="Lights are only supported in CYCLES!", icon='ERROR')

        row = self.layout.row()

        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)

        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")

        row = right_col.row(align=True)
        row.enabled = False
        row.label(text="Direct Coloring")
        row.label(text="Color/Temperature")
        row.label(text="Strength")

        # TODO: selected assets table
        polib.ui_bpy.draw_property_table(
            adjustable_lights,
            left_col,
            right_col,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        prefs = preferences.prefs_utils.get_preferences(context).light_adjustments_preferences
        row = layout.row()
        row.label(text="Edit All Selected:")
        row.enabled = False
        row = layout.row(align=True)

        row.prop(prefs, "use_rgb", text="Direct Coloring")
        row = layout.row(align=True)
        if prefs.use_rgb:
            row.prop(prefs, "light_rgb", text="")
        else:
            row.prop(prefs, "light_temperature", text="Temperature (K)", slider=True)
        row.prop(prefs, "light_strength", text="Strength (W)", slider=True)


MODULE_CLASSES.append(LightAdjustmentsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
