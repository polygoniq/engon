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
import os
import enum
from .. import polib
from .. import asset_helpers


MODULE_CLASSES: typing.List[typing.Any] = []


class WindPreset(enum.Enum):
    BREEZE = "Breeze"
    WIND = "Wind"
    STORM = "Storm"
    UNKNOWN = "Unknown"


class AnimationType(enum.Enum):
    WIND_BEST_FIT = "Wind-Best-Fit"
    WIND_TREE = "Wind-Tree"
    WIND_PALM = "Wind-Palm"
    WIND_LOW_VEGETATION = "Wind-Low-Vegetation"
    WIND_LOW_VEGETATION_PLANTS = "Wind-Low-Vegetation-Plants"
    WIND_SIMPLE = "Wind-Simple"
    UNKNOWN = "Unknown"


class WindStyle(enum.Enum):
    LOOP = "Loop"
    PROCEDURAL = "Procedural"
    UNKNOWN = "Unknown"


class WindAnimationProperties(bpy.types.PropertyGroup):
    auto_make_instance: bpy.props.BoolProperty(
        name="Automatic Make Instance",
        description="Automatically make instance out of object when spawning animation. "
        "Better performance, but assets share data, customization per instance",
        default=False,
    )

    animation_type: bpy.props.EnumProperty(
        name="Wind animation type",
        description="Select one of predefined animations types."
        "This changes the animation and animation modifier stack",
        items=(
            (
                AnimationType.WIND_BEST_FIT.value,
                AnimationType.WIND_BEST_FIT.value,
                "Different animation types based on the selection",
                'SHADERFX',
                0,
            ),
            (
                AnimationType.WIND_TREE.value,
                AnimationType.WIND_TREE.value,
                "Animation mostly suited for tree assets",
                'BLANK1',
                1,
            ),
            (
                AnimationType.WIND_PALM.value,
                AnimationType.WIND_PALM.value,
                "Animation mostly suited for palm assets",
                'BLANK1',
                2,
            ),
            (
                AnimationType.WIND_LOW_VEGETATION.value,
                AnimationType.WIND_LOW_VEGETATION.value,
                "Animation mostly suited for low vegetation assets",
                'BLANK1',
                3,
            ),
            (
                AnimationType.WIND_LOW_VEGETATION_PLANTS.value,
                AnimationType.WIND_LOW_VEGETATION_PLANTS.value,
                "Animation mostly suited for low vegetation plant assets",
                'BLANK1',
                4,
            ),
            (
                AnimationType.WIND_SIMPLE.value,
                AnimationType.WIND_SIMPLE.value,
                "Simple animation, works only on assets with Leaf_ or Grass_ materials",
                'BLANK1',
                5,
            ),
        ),
    )

    preset: bpy.props.EnumProperty(
        name="Wind animation preset",
        description="Select one of predefined animations presets."
        "This changes detail of animation and animation modifier stack",
        items=(
            (WindPreset.BREEZE.value, WindPreset.BREEZE.value, "Light breeze wind", 'BOIDS', 0),
            (WindPreset.WIND.value, WindPreset.WIND.value, "Moderate wind", 'CURVES_DATA', 1),
            (WindPreset.STORM.value, WindPreset.STORM.value, "Strong storm wind", 'MOD_NOISE', 2),
        ),
    )

    strength: bpy.props.FloatProperty(
        name="Wind strength",
        description="Strength of the wind applied on the trees",
        default=0.25,
        min=0.0,
        soft_max=1.0,
    )

    looping: bpy.props.IntProperty(
        name="Loop time",
        description="At how many frames should the animation repeat. Minimal value to ensure good "
        "animation appearance is 80",
        default=120,
        min=80,
    )

    bake_folder: bpy.props.StringProperty(
        name="Bake Folder",
        description="Folder where baked .abc animations are saved",
        default=os.path.realpath(os.path.expanduser("~/botaniq_animations/")),
        subtype='DIR_PATH',
    )

    # Used to choose target of most wind animation operators but not all.
    # It's not used in operators where it doesn't make sense,
    # e.g. Add Animation works on selected objects.
    operator_target: bpy.props.EnumProperty(
        name="Target",
        description="Choose to what objects the operator should apply",
        items=[
            ('SELECTED', "Selected Objects", "All selected objects"),
            ('SCENE', "Scene Objects", "All objects in current scene"),
            ('ALL', "All Objects", "All objects in the .blend file"),
        ],
        default='SCENE',
    )


MODULE_CLASSES.append(WindAnimationProperties)


class BotaniqPreferences(bpy.types.PropertyGroup):
    float_min: bpy.props.FloatProperty(
        name="Min Value",
        description="Miniumum float value",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
    )

    float_max: bpy.props.FloatProperty(
        name="Max Value", description="Maximum float value", default=1.0, min=0.0, max=1.0, step=0.1
    )

    brightness: bpy.props.FloatProperty(
        name="Brightness",
        description="Adjust assets brightness",
        default=1.0,
        min=0.0,
        max=10.0,
        soft_max=1.0,
        step=0.1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_BRIGHTNESS,
            self.brightness,
        ),
    )

    hue_per_branch: bpy.props.FloatProperty(
        name="Hue Per Branch",
        description="Randomize hue per branch",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH,
            self.hue_per_branch,
        ),
    )

    hue_per_leaf: bpy.props.FloatProperty(
        name="Hue Per Leaf",
        description="Randomize hue per leaf",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF,
            self.hue_per_leaf,
        ),
    )

    season_offset: bpy.props.FloatProperty(
        name="Season Offset",
        description="Change season of asset",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.custom_props_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            polib.custom_props_bpy.CustomPropertyNames.BQ_SEASON_OFFSET,
            self.season_offset,
        ),
    )

    wind_anim_properties: bpy.props.PointerProperty(
        name="Animation Properties",
        description="Wind animation related property group",
        type=WindAnimationProperties,
    )

    def get_adjustment_affected_objects(self, context: bpy.types.Context):
        extended_objects = set(context.selected_objects)
        if context.active_object is not None:
            extended_objects.add(context.active_object)

        return set(extended_objects).union(asset_helpers.gather_instanced_objects(extended_objects))


MODULE_CLASSES.append(BotaniqPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
