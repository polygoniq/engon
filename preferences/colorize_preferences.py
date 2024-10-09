# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
from .. import polib


MODULE_CLASSES: typing.List[typing.Any] = []


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
            context.selected_objects,
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
            context.selected_objects,
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
            context.selected_objects,
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
            context.selected_objects,
            polib.custom_props_bpy.CustomPropertyNames.PQ_SECONDARY_COLOR_FACTOR,
            self.secondary_color_factor,
        ),
    )


MODULE_CLASSES.append(ColorizePreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in MODULE_CLASSES:
        bpy.utils.unregister_class(cls)
