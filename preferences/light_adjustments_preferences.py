# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
from .. import polib
from .. import features


MODULE_CLASSES: typing.List[typing.Any] = []


class LightAdjustmentsPreferences(bpy.types.PropertyGroup):
    @staticmethod
    def update_prop_with_use_rgb(
        context: bpy.types.Context,
        objs: typing.Iterable[bpy.types.Object],
        prop_name: str,
        value: polib.custom_props_bpy.CustomAttributeValueType,
        use_rgb_value: bool,
    ) -> None:
        materialized_objs = list(objs)
        polib.custom_props_bpy.update_custom_prop(
            context,
            materialized_objs,
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            use_rgb_value,
        )
        polib.custom_props_bpy.update_custom_prop(
            context,
            materialized_objs,
            prop_name,
            value,
        )

    use_rgb: bpy.props.BoolProperty(
        name="Use Direct Coloring instead of Temperature",
        description="Use Direct Coloring instead of Temperature",
        default=False,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            features.light_adjustments.LightAdjustmentsPanel.get_adjustable_objects(
                context.selected_objects
            ),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_USE_RGB,
            self.use_rgb,
        ),
    )

    light_temperature: bpy.props.IntProperty(
        name="Light Temperature",
        subtype='TEMPERATURE',
        description='Changes light temperature in Kelvins ranging from warm to cool',
        default=5000,
        min=0,  # blender "Temperature" shader node gets this wrong, 0K should be black, but its red
        max=12_000,  # blender "Temperature" shader node supports up to 12kK
        update=lambda self, context: LightAdjustmentsPreferences.update_prop_with_use_rgb(
            context,
            features.light_adjustments.LightAdjustmentsPanel.get_adjustable_objects(
                context.selected_objects
            ),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_KELVIN,
            self.light_temperature,
            False,
        ),
    )

    light_rgb: bpy.props.FloatVectorProperty(
        name="Light Color",
        subtype='COLOR',
        description='Changes light color across the RGB spectrum',
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        step=1,
        update=lambda self, context: LightAdjustmentsPreferences.update_prop_with_use_rgb(
            context,
            features.light_adjustments.LightAdjustmentsPanel.get_adjustable_objects(
                context.selected_objects
            ),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_RGB,
            self.light_rgb,
            True,
        ),
    )

    light_strength: bpy.props.FloatProperty(
        name="Light Strength",
        default=0.0,
        description='Changes the intensity of the light',
        min=0.0,
        subtype='FACTOR',
        soft_max=200,  # mostly> interior use, exterior lights can go to 2000 or more
        step=1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            features.light_adjustments.LightAdjustmentsPanel.get_adjustable_objects(
                context.selected_objects
            ),
            polib.custom_props_bpy.CustomPropertyNames.PQ_LIGHT_STRENGTH,
            self.light_strength,
        ),
    )


MODULE_CLASSES.append(LightAdjustmentsPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in MODULE_CLASSES:
        bpy.utils.unregister_class(cls)
