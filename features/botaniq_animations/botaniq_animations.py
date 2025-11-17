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
import logging

from bpy.types import ID
from . import animations
from .. import feature_utils
from .. import asset_pack_panels
from ... import polib
from ... import preferences

logger = logging.getLogger(f"polygoniq.{__name__}")

MODULE_CLASSES = []


class OperatorTarget(enum.StrEnum):
    SELECTED = 'Selected Objects'
    SCENE = 'Scene Objects'
    ALL = 'All Objects'


class WindPreset(enum.StrEnum):
    BREEZE = "Breeze"
    WIND = "Wind"
    STORM = "Storm"
    UNKNOWN = "Unknown"


class AnimationType(enum.StrEnum):
    WIND_BEST_FIT = "Wind-Best-Fit"
    WIND_TREE = "Wind-Tree"
    WIND_PALM = "Wind-Palm"
    WIND_LOW_VEGETATION = "Wind-Low-Vegetation"
    WIND_LOW_VEGETATION_PLANTS = "Wind-Low-Vegetation-Plants"
    WIND_SIMPLE = "Wind-Simple"
    UNKNOWN = "Unknown"


class WindStyle(enum.StrEnum):
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
                AnimationType.WIND_BEST_FIT,
                AnimationType.WIND_BEST_FIT,
                "Different animation types based on the selection",
                'SHADERFX',
                0,
            ),
            (
                AnimationType.WIND_TREE,
                AnimationType.WIND_TREE,
                "Animation mostly suited for tree assets",
                'BLANK1',
                1,
            ),
            (
                AnimationType.WIND_PALM,
                AnimationType.WIND_PALM,
                "Animation mostly suited for palm assets",
                'BLANK1',
                2,
            ),
            (
                AnimationType.WIND_LOW_VEGETATION,
                AnimationType.WIND_LOW_VEGETATION,
                "Animation mostly suited for low vegetation assets",
                'BLANK1',
                3,
            ),
            (
                AnimationType.WIND_LOW_VEGETATION_PLANTS,
                AnimationType.WIND_LOW_VEGETATION_PLANTS,
                "Animation mostly suited for low vegetation plant assets",
                'BLANK1',
                4,
            ),
            (
                AnimationType.WIND_SIMPLE,
                AnimationType.WIND_SIMPLE,
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
            (WindPreset.BREEZE, WindPreset.BREEZE, "Light breeze wind", 'BOIDS', 0),
            (WindPreset.WIND, WindPreset.WIND, "Moderate wind", 'CURVES_DATA', 1),
            (WindPreset.STORM, WindPreset.STORM, "Strong storm wind", 'MOD_NOISE', 2),
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
            (OperatorTarget.SELECTED, OperatorTarget.SELECTED, "All selected objects"),
            (OperatorTarget.SCENE, OperatorTarget.SCENE, "All objects in current scene"),
            (OperatorTarget.ALL, OperatorTarget.ALL, "All objects in the .blend file"),
        ],
        default=OperatorTarget.SCENE,
    )


MODULE_CLASSES.append(WindAnimationProperties)


class BotaniqAnimationsPreferences(bpy.types.PropertyGroup):

    wind_anim_properties: bpy.props.PointerProperty(
        name="Animation Properties",
        description="Wind animation related property group",
        type=WindAnimationProperties,
    )


MODULE_CLASSES.append(BotaniqAnimationsPreferences)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class AnimationsPanel(feature_utils.EngonAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_botaniq_animations"
    bl_parent_id = asset_pack_panels.BotaniqPanel.bl_idname
    bl_label = "Animations"
    bl_options = {'DEFAULT_CLOSED'}

    feature_name = "botaniq_animations"

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return filter(
            lambda obj: obj is not None
            and isinstance(obj, bpy.types.Object)
            and animations.is_animated(obj),
            possible_assets,
        )

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='FORCE_WIND')

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = self.__class__.feature_name

    def draw_object_anim_details(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        obj: bpy.types.Object,
        animated_object: bpy.types.Object,
    ) -> None:
        """Draws animation details of 'obj' into 'layout' based on 'context' and 'animated_obj'.

        'animated_obj' is the animated object of 'obj' which can be either itself or the object
        from it's instanced collection. Check 'animations.get_instanced_mesh_object'.
        """
        col = layout.column(align=True)
        col.label(text="Active Object", icon='INFO')
        if obj.instance_collection is None:
            col.label(text=obj.name, icon='OBJECT_DATA')
        else:
            split = col.split(factor=0.75, align=True)
            split.label(text=obj.name, icon='OUTLINER_COLLECTION')
            split.operator(
                animations.AnimationMakeInstanceUnique.bl_idname,
                text=f"{obj.instance_collection.users - 1}",
            )

        action = animated_object.animation_data.action
        assert action is not None
        animation_type, preset = animations.parse_action_name(action)
        animation_style = animations.get_wind_style(action)

        col = layout.column(align=True)
        split_factor = 0.5
        # Animation Type
        split = col.split(factor=split_factor, align=True)
        split.label(text="Animation:")
        split.label(text=str(animation_type))

        # Preset
        split = col.split(factor=split_factor, align=True)
        split.label(text="Preset:")
        split.label(text=str(preset))

        # Style
        split = col.split(factor=split_factor, align=True)
        split.label(text="Style:")
        split.label(text=str(animation_style))

        # Strength
        wind_strength = animations.infer_strength_from_action(action)
        if wind_strength is not None:
            split = col.split(factor=split_factor, align=True)
            split.label(text="Strength:")
            split.label(text=f"{wind_strength:.3f}x")

        if animation_style == WindStyle.LOOP:
            frame_range = action.frame_range

            # Loop Interval
            loop_interval = frame_range[1] - frame_range[0]
            split = col.split(factor=split_factor, align=True)
            split.label(text="Loop Interval:")
            split.label(text=f"{round(loop_interval)} frames")

            # Duration
            scene_interval = context.scene.frame_end - context.scene.frame_start
            scene_fps = animations.get_scene_fps(
                context.scene.render.fps, context.scene.render.fps_base
            )
            split = col.split(factor=split_factor, align=True)
            split.label(text="Duration:")
            split.label(text=f"{scene_interval / scene_fps:.1f} s")

            # Speed
            speed = loop_interval / animations.get_scene_fps_adjusted_interval(scene_fps)
            split = col.split(factor=split_factor, align=True)
            split.label(text="Speed:")
            split.label(text=f"{speed:.1f}x")

    def draw(self, context: bpy.types.Context):
        wind_properties = preferences.prefs_utils.get_preferences(
            context
        ).botaniq_animations_preferences.wind_anim_properties
        layout = self.layout

        row = polib.ui_bpy.scaled_row(layout, 1.5, align=True)
        row.operator(animations.AnimationAddWind.bl_idname, text="Add Animation", icon='ADD')
        layout.separator()

        row = layout.row(align=True)
        row.operator(
            animations.AnimationMakeInstanced.bl_idname, text="Make Instance", icon='GROUP'
        )
        row.operator(
            animations.AnimationRemoveWind.bl_idname, text="Remove Animation", icon='REMOVE'
        )

        row = layout.row(align=True)
        row.operator(animations.AnimationMute.bl_idname, text="Mute/Unmute Animation")

        if next(animations.get_animated_objects(context.selected_objects), None) is not None:
            col = layout.column(align=True)
            col.label(text="Preset & Strength")
            row = col.split(align=True, factor=0.75)
            row.prop(wind_properties, "preset", text="")
            row.operator(animations.AnimationApplyPreset.bl_idname, text="Set")

            row = col.split(align=True, factor=0.75)
            row.prop(wind_properties, "strength", text="Strength")
            row.operator(animations.AnimationApplyStrength.bl_idname, text="Set")

            col = layout.column(align=True)
            col.label(text="Animation Style")
            row = col.split(align=True)
            row.operator(
                animations.AnimationSetAnimStyle.bl_idname, text="Loop / Procedural Switch"
            )
            col.separator()

            row = col.split(align=True, factor=0.75)
            row.prop(wind_properties, "looping", text="Loop Frames")
            row.operator(animations.AnimationApplyLoop.bl_idname, text="Set")
            row = col.split(align=True)
            row.operator(animations.AnimationSetFrames.bl_idname, text="Set Scene Frames")
            col.separator()

            row = col.row(align=True)
            row.operator(animations.AnimationRandomizeOffset.bl_idname)

        col = layout.column(align=True)
        col.label(text="Alembic Bake")
        col.prop(wind_properties, "bake_folder")
        col.operator(animations.AnimationBake.bl_idname, text="Bake to Alembic")

        if self.conditionally_draw_warning_no_adjustable_active_object(
            context, layout, warning_text="Active object is not an asset with an animation!"
        ):
            return

        active_object = context.active_object
        if animations.has_6_6_or_older_action(context.active_object):
            col = layout.column(align=True)
            col.label(text="Asset has old Animation", icon='ERROR')
            col.label(text="Please respawn the asset or use")
            col.label(text="'Convert to Linked' and 'Convert to Editable' and")
            col.label(text="re-apply the animation.")

        animated_object = animations.get_instanced_mesh_object(active_object)
        if self.conditionally_draw_warning_no_adjustable_assets(
            filter(lambda obj: obj is not None, [animated_object]),
            layout,
            warning_text="Active object is not an asset with an animation!",
        ):
            return
        assert animated_object is not None

        self.draw_object_anim_details(context, layout, active_object, animated_object)


MODULE_CLASSES.append(AnimationsPanel)


@polib.log_helpers_bpy.logged_panel
class AnimationAdvancedPanel(feature_utils.EngonAssetFeatureControlPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_botaniq_animations_advanced"
    bl_parent_id = AnimationsPanel.bl_idname
    bl_label = "Animations Advanced"

    feature_name = "botaniq_animations"

    @classmethod
    def filter_adjustable_assets(cls, possible_assets: typing.Iterable[ID]) -> typing.Iterable[ID]:
        return filter(
            lambda obj: obj is not None
            and animations.get_instanced_mesh_object(obj)
            and animations.is_animated(obj),
            possible_assets,
        )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT'

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='OPTIONS')

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        if self.conditionally_draw_warning_no_adjustable_active_object(
            context, layout, warning_text="Active object is not an asset with an animation!"
        ):
            return

        animated_object = animations.get_instanced_mesh_object(context.active_object)
        assert animated_object is not None

        col = layout.column(align=True)
        row = col.row(align=True)
        row.label(text="Modifier")
        sub_col = row.column()
        sub_col.alignment = 'RIGHT'
        sub_col.label(text="Strength")
        sub_col = row.column()
        sub_col.alignment = 'RIGHT'
        sub_col.label(text="Enabled")

        action = animated_object.animation_data.action
        scale_mod_prop_map = animations.get_envelope_multiplier_mod_prop_map(action)
        for mod_name, fmod_limits in sorted(
            animations.get_animation_state_control_modifiers(action), key=lambda x: x[0]
        ):
            modifier = animated_object.modifiers.get(mod_name, None)
            if modifier is None:
                logger.warning(f"Modifier {mod_name} not found on object {animated_object.name}")
                continue

            row = col.row(align=True)
            row.label(text=f"{mod_name[len('bq_'):]}")

            mod, prop = scale_mod_prop_map.get(mod_name, (None, None))
            amplitude_col = row.column(align=True)
            amplitude_col.alignment = 'RIGHT'
            if mod is not None:
                amplitude_col.prop(mod, prop, text="")
            else:
                amplitude_col.label(text="Not Controllable")

            row.prop(modifier, "show_viewport", text="")
            # For some reason next icon from the desired one has to be used: AUTO => CHECKMARK
            row.prop(
                fmod_limits, "mute", text="", icon='AUTO' if fmod_limits.mute is True else 'BLANK1'
            )


MODULE_CLASSES.append(AnimationAdvancedPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
