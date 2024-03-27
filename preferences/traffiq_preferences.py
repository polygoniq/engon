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
import logging
import polib
from .. import asset_helpers
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


BUMPS_MODIFIER_NAME = "tq_bumps_displacement"
BUMPS_MODIFIERS_CONTAINER_NAME = "tq_Bump_Modifiers_Container"


class CarPaintProperties(bpy.types.PropertyGroup):
    @staticmethod
    def update_car_paint_color_prop(context, value: typing.Tuple[float, float, float, float]):
        # Don't allow to accidentally set color to random
        if all(v > 0.99 for v in value[:3]):
            value = (0.99, 0.99, 0.99, value[3])

        polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR,
            value
        )

    primary_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        description="Changes primary color of assets",
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        size=4,
        update=lambda self, context: CarPaintProperties.update_car_paint_color_prop(
            context, self.primary_color),
    )
    flakes_amount: bpy.props.FloatProperty(
        name="Flakes Amount",
        description="Changes amount of flakes in the car paint",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT,
            self.flakes_amount
        ),
    )
    clearcoat: bpy.props.FloatProperty(
        name="Clearcoat",
        description="Changes clearcoat property of car paint",
        default=0.2,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_CLEARCOAT,
            self.clearcoat
        ),
    )


MODULE_CLASSES.append(CarPaintProperties)


class WearProperties(bpy.types.PropertyGroup):
    @staticmethod
    def update_bumps_prop(context: bpy.types.Context, value: float):
        # Cache objects that support bumps
        bumps_objs = [
            obj for obj in context.selected_objects if polib.asset_pack_bpy.CustomPropertyNames.TQ_BUMPS in obj]

        modifier_library_path = None

        # Add bumps modifier that improves bumps effect on editable objects.
        # Bumps work for linked assets but looks better on editable ones with added modifier
        for obj in bumps_objs:
            # Object is not editable mesh
            if obj.data is None or obj.type != "MESH":
                continue
            # If modifier is not assigned to the object, append it from library
            if BUMPS_MODIFIER_NAME not in obj.modifiers:
                if modifier_library_path is None:
                    modifier_library_path = asset_helpers.get_asset_pack_library_path(
                        "traffiq", asset_helpers.TQ_MODIFIER_LIBRARY_BLEND)
                    if modifier_library_path is None:
                        raise RuntimeError("Modifier library of traffiq not found!")
                polib.asset_pack_bpy.append_modifiers_from_library(
                    BUMPS_MODIFIERS_CONTAINER_NAME, modifier_library_path, [obj])
                logger.info(f"Added bumps modifier on: {obj.name}")

            assert BUMPS_MODIFIER_NAME in obj.modifiers
            obj.modifiers[BUMPS_MODIFIER_NAME].strength = value

        polib.asset_pack_bpy.update_custom_prop(
            context,
            bumps_objs,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_BUMPS,
            value
        )

    dirt_wear_strength: bpy.props.FloatProperty(
        name="Dirt",
        description="Makes assets look dirty",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_DIRT,
            self.dirt_wear_strength
        ),
    )
    scratches_wear_strength: bpy.props.FloatProperty(
        name="Scratches",
        description="Makes assets look scratched",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_SCRATCHES,
            self.scratches_wear_strength
        ),
    )
    bumps_wear_strength: bpy.props.FloatProperty(
        name="Bumps",
        description="Makes assets look dented, appends displacement modifier for better effect if object is editable",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        step=0.1,
        update=lambda self, context: WearProperties.update_bumps_prop(
            context, self.bumps_wear_strength),
    )


MODULE_CLASSES.append(WearProperties)


class RigProperties(bpy.types.PropertyGroup):
    auto_bake_steering: bpy.props.BoolProperty(
        name="Auto Bake Steering",
        description="If true, follow path operator will automatically try to bake steering",
        default=True
    )
    auto_bake_wheels: bpy.props.BoolProperty(
        name="Auto Bake Wheel Rotation",
        description="If true, follow path operator will automatically try to bake wheel rotation",
        default=True
    )
    auto_reset_transforms: bpy.props.BoolProperty(
        name="Auto Reset Transforms",
        description="If true, follow path operator will automatically reset transforms"
        "of needed objects to give the expected results",
        default=True
    )


MODULE_CLASSES.append(RigProperties)


class LightsProperties(bpy.types.PropertyGroup):
    main_lights_status: bpy.props.EnumProperty(
        name="Main Lights Status",
        items=(
            ("0", "off", "Front and rear lights are off"),
            ("0.25", "park", "Park lights are on"),
            ("0.50", "low-beam", "Low-beam lights are on"),
            ("0.75", "high-beam", "High-beam lights are on"),
        ),
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            [polib.asset_pack_bpy.find_traffiq_lights_container(
                o) for o in context.selected_objects],
            polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS,
            float(self.main_lights_status)
        ),
    )


MODULE_CLASSES.append(LightsProperties)


class TraffiqPreferences(bpy.types.PropertyGroup):
    car_paint_properties: bpy.props.PointerProperty(
        type=CarPaintProperties
    )

    wear_properties: bpy.props.PointerProperty(
        type=WearProperties
    )

    lights_properties: bpy.props.PointerProperty(
        type=LightsProperties
    )

    rig_properties: bpy.props.PointerProperty(
        type=RigProperties
    )


MODULE_CLASSES.append(TraffiqPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
