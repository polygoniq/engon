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


class SculptureWearPreferences(bpy.types.PropertyGroup):
    bugholes_area: bpy.props.FloatProperty(
        name="Bug Holes Area",
        description="Amount of bug holes wear",
        default=0.5,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA,
            self.bugholes_area,
        ),
    )

    bugholes_mapping_scale: bpy.props.FloatProperty(
        name="Bug Holes Mapping Scale",
        description="Mapping scale of bug holes wear",
        default=2.0,
        min=0.01,
        max=10.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_MAPPING_SCALE,
            self.bugholes_mapping_scale,
        ),
    )

    bugholes_strength: bpy.props.FloatProperty(
        name="Bug Holes Strength",
        description="Strength of bug holes wear",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_STRENGTH,
            self.bugholes_strength,
        ),
    )

    fractures_area: bpy.props.FloatProperty(
        name="Fractures Area",
        description="Amount of fractures wear",
        default=0.5,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_AREA,
            self.fractures_area,
        ),
    )
    fractures_thickness: bpy.props.FloatProperty(
        name="Fractures Thickness",
        description="Thickness of fractures wear",
        default=0.125,
        min=0.01,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_THICKNESS,
            self.fractures_thickness,
        ),
    )
    fractures_strength: bpy.props.FloatProperty(
        name="Fractures Strength",
        description="Strength of fractures wear",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_STRENGTH,
            self.fractures_strength,
        ),
    )
    mapcracks_area: bpy.props.FloatProperty(
        name="Map Cracks Area",
        description="Amount of map cracks wear",
        default=0.5,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_AREA,
            self.mapcracks_area,
        ),
    )
    mapcracks_strength: bpy.props.FloatProperty(
        name="Map Cracks Strength",
        description="Strength of map cracks wear",
        default=1.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_STRENGTH,
            self.mapcracks_strength,
        ),
    )
    mapcracks_mapping_scale: bpy.props.FloatProperty(
        name="Map Cracks Mapping Scale",
        description="Mapping scale of map cracks wear",
        default=5.0,
        min=0.01,
        max=10.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_MAPPING_SCALE,
            self.mapcracks_mapping_scale,
        ),
    )
    dirt_density: bpy.props.FloatProperty(
        name="Dirt Density",
        description="Density of dirt wear",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            SculptureWearPanel.get_multiedit_adjustable_assets(context),
            polib.custom_props_bpy.CustomPropertyNames.PQ_DIRT_DENSITY,
            self.dirt_density,
        ),
    )


MODULE_CLASSES.append(SculptureWearPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class SculptureWearPanel(feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_feature_sculpture_wear"
    bl_parent_id = asset_pack_panels.AesthetiqPanel.bl_idname
    bl_label = "Sculpture Wear"
    feature_name = "sculptural_wear"
    related_custom_properties = {
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_MAPPING_SCALE,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_STRENGTH,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_AREA,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_THICKNESS,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_STRENGTH,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_AREA,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_STRENGTH,
        polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_MAPPING_SCALE,
        polib.custom_props_bpy.CustomPropertyNames.PQ_DIRT_DENSITY,
    }
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_simple(possible_assets)

    @classmethod
    def get_feature_icon(cls) -> str:
        return 'ORPHAN_DATA'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon=self.get_feature_icon())

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw_properties_bugholes(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_MAPPING_SCALE,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_STRENGTH,
        )

    def draw_properties_fractures(
        self, datablock: bpy.types.ID, layout: bpy.types.UILayout
    ) -> None:
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_AREA,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_THICKNESS,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_FRACTURES_STRENGTH,
        )

    def draw_properties_mapcracks(
        self, datablock: bpy.types.ID, layout: bpy.types.UILayout
    ) -> None:
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_AREA,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_MAPPING_SCALE,
        )
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_MAPCRACKS_STRENGTH,
        )

    def draw_properties_dirt(self, datablock: bpy.types.ID, layout: bpy.types.UILayout) -> None:
        self.draw_property(
            datablock,
            layout,
            polib.custom_props_bpy.CustomPropertyNames.PQ_DIRT_DENSITY,
        )

    def draw_multiedit_bugholes(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).sculpture_wear_preferences
        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA, None)
            is not None
            for o in adjustable_assets
        ):
            row = layout.row()
            row.prop(
                prefs,
                "bugholes_area",
                text="Area",
            )
            row.prop(
                prefs,
                "bugholes_mapping_scale",
                text="Scale",
            )
            row.prop(
                prefs,
                "bugholes_strength",
                text="Strength",
            )

    def draw_multiedit_fractures(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).sculpture_wear_preferences
        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA, None)
            is not None
            for o in adjustable_assets
        ):
            row = layout.row()
            row.prop(
                prefs,
                "fractures_area",
                text="Area",
            )
            row.prop(
                prefs,
                "fractures_thickness",
                text="Thickness",
            )
            row.prop(
                prefs,
                "fractures_strength",
                text="Strength",
            )

    def draw_multiedit_mapcracks(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).sculpture_wear_preferences
        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_WEAR_BUGHOLES_AREA, None)
            is not None
            for o in adjustable_assets
        ):
            row = layout.row()
            row.prop(
                prefs,
                "mapcracks_area",
                text="Area",
            )
            row.prop(
                prefs,
                "mapcracks_mapping_scale",
                text="Scale",
            )
            row.prop(
                prefs,
                "mapcracks_strength",
                text="Strength",
            )

    def draw_multiedit_dirt(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).sculpture_wear_preferences
        if any(
            o.get(polib.custom_props_bpy.CustomPropertyNames.PQ_DIRT_DENSITY, None) is not None
            for o in adjustable_assets
        ):
            row = layout.row()
            row.prop(
                prefs,
                "dirt_density",
                text="Density",
            )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        layout.label(text="Bug Holes:", icon='POINTCLOUD_DATA')

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Area", "Scale", "Strength"],
            layout,
            lambda layout, obj: self.draw_properties_bugholes(obj, layout),
        )

        self.draw_multiedit_bugholes(context, layout, possible_assets)

        layout.separator()

        layout.label(text="Fractures:", icon='MOD_NOISE')

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Area", "Thickness", "Strength"],
            layout,
            lambda layout, obj: self.draw_properties_fractures(obj, layout),
        )

        self.draw_multiedit_fractures(context, layout, possible_assets)
        layout.separator()

        layout.label(text="Map Cracks:", icon='VOLUME_DATA')

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Area", "Scale", "Strength"],
            layout,
            lambda layout, obj: self.draw_properties_mapcracks(obj, layout),
        )

        self.draw_multiedit_mapcracks(context, layout, possible_assets)
        layout.separator()

        layout.label(text="Dirt:", icon='NODE_MATERIAL')

        self.draw_adjustable_assets_property_table(
            possible_assets,
            ["Density"],
            layout,
            lambda layout, obj: self.draw_properties_dirt(obj, layout),
        )

        self.draw_multiedit_dirt(context, layout, possible_assets)


MODULE_CLASSES.append(SculptureWearPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
