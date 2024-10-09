# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
from .. import polib
from .. import asset_registry
from .. import interniq
from .. import preferences

MODULE_CLASSES = []


class ColorizePanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("colorize")) > 0


@polib.log_helpers_bpy.logged_panel
class ColorizePanel(ColorizePanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_colorize"
    # TODO: this feature is currently interniq-only, but in the future it should be moved to engon panel,
    # once all other asset packs implement colorize
    bl_parent_id = interniq.panel.InterniqPanel.bl_idname
    bl_label = "Colorize"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_HUE_SATURATION')

    def draw_properties(self, obj: bpy.types.Object, layout: bpy.types.UILayout) -> None:
        primary_layout = layout.column().row(align=True)
        polib.ui_bpy.draw_property(
            obj,
            primary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR,
        )
        polib.ui_bpy.draw_property(
            obj,
            primary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR,
        )
        secondary_layout = layout.column().row(align=True)
        polib.ui_bpy.draw_property(
            obj,
            secondary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR,
        )
        polib.ui_bpy.draw_property(
            obj,
            secondary_layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        selected_objects = set(context.selected_objects)
        colorable_objects = list(
            filter(
                lambda obj: polib.asset_pack_bpy.has_engon_property_feature(obj, "colorize"),
                polib.asset_pack_bpy.get_polygoniq_objects(selected_objects),
            )
        )

        if len(colorable_objects) == 0:
            layout.label(text="No colorable assets selected!")
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

        polib.ui_bpy.draw_property_table(
            colorable_objects,
            left_col,
            right_col,
            lambda layout, obj: self.draw_properties(obj, layout),
        )

        prefs = preferences.prefs_utils.get_preferences(context).colorize_preferences
        row = layout.row()
        row.label(text="Edit All Selected:")
        row.enabled = False

        row = layout.row(align=True)

        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_PRIMARY_COLOR_FACTOR) is not None
            for o in colorable_objects
        ):
            row.label(text="", icon='COLOR')
            row.prop(prefs, "primary_color", text="")
            row.prop(prefs, "primary_color_factor", text="Factor", slider=True)

        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR) is not None
            for o in colorable_objects
        ):
            row = layout.row(align=True)
            row.label(text="", icon='RESTRICT_COLOR_ON')
            row.prop(prefs, "secondary_color", text="")
            row.prop(prefs, "secondary_color_factor", text="Factor", slider=True)


MODULE_CLASSES.append(ColorizePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
