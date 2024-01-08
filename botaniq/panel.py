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

import os
import re
import random
import bpy
import itertools
import typing
import math
import polib
from .. import asset_helpers
from .. import asset_registry
from .. import preferences
from . import animations
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


ADDON_CLASSES: typing.List[typing.Type] = []


def botaniq_duplicate_data_filter(data: bpy.types.ID) -> bool:
    pattern = re.compile(r"^\.[0-9]{3}$")
    if not pattern.match(data.name[-4:]):
        return False

    orig_name = polib.utils_bpy.remove_object_duplicate_suffix(data.name)
    if isinstance(data, bpy.types.NodeGroup):
        return orig_name.startswith("bq_")

    if isinstance(data, bpy.types.Material):
        return orig_name.startswith("bq_")

    if isinstance(data, bpy.types.Image):
        img_path = os.path.abspath(bpy.path.abspath(data.filepath, library=data.library))
        install_path = preferences.get_preferences(bpy.context).install_path
        try:
            return os.path.commonpath([img_path, install_path]) == install_path
        except ValueError:
            # not on the same drive
            return False

    # TODO: log warning or raise exception?
    return False


@polib.log_helpers_bpy.logged_operator
class SetColor(bpy.types.Operator):
    bl_idname = "engon.botaniq_set_color_of_active_obj"
    bl_label = "Set Color Of Active Object"
    bl_description = "Set color of the active object"
    bl_options = {'REGISTER', 'UNDO'}

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0, 1.0),
        size=4,
        min=0.0,
        max=1.0
    )

    def execute(self, context: bpy.types.Context):
        context.active_object.color = self.color
        return {'FINISHED'}


ADDON_CLASSES.append(SetColor)


@polib.log_helpers_bpy.logged_operator
class RandomizeFloatProperty(bpy.types.Operator):
    bl_idname = "engon.botaniq_randomize_float_property"
    bl_label = "Randomize Float Property"
    bl_description = "Set random value from specified interval for a custom property of selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    custom_property_name: bpy.props.StringProperty(options={'HIDDEN'})

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        prefs = preferences.get_preferences(context)
        layout.prop(prefs, "float_min", slider=True)
        layout.prop(prefs, "float_max", slider=True)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context)
        for obj in set(context.selected_objects).union(asset_helpers.gather_instanced_objects(context.selected_objects)):
            custom_prop = obj.get(self.custom_property_name, None)
            if custom_prop is None:
                continue
            random_value = random.uniform(prefs.float_min, prefs.float_max)
            polib.asset_pack_bpy.update_custom_prop(
                context,
                [obj],
                self.custom_property_name,
                random_value
            )

            logger.info(
                f"Property {self.custom_property_name} randomized on asset {obj.name} with "
                f"range ({prefs.float_min, prefs.float_max}) and resulting value {random_value}"
            )
        return {'FINISHED'}


ADDON_CLASSES.append(RandomizeFloatProperty)


class BotaniqPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("botaniq")) > 0


@polib.log_helpers_bpy.logged_panel
class BotaniqPanel(BotaniqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_botaniq"
    bl_label = "botaniq"
    bl_order = 10

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(
            text="", icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("botaniq"))

    def draw(self, context: bpy.types.Context):
        pass


ADDON_CLASSES.append(BotaniqPanel)


class AdjustmentMixin:
    @classmethod
    def has_pps(
        cls,
        obj: bpy.types.Object
    ) -> bool:
        for particle_system in obj.particle_systems:
            if polib.asset_pack_bpy.is_pps(particle_system.name):
                return True
        return False

    @classmethod
    def get_selected_botaniq_assets(
        cls,
        context: bpy.types.Context
    ) -> typing.Iterable[bpy.types.Object]:
        objects = set(context.selected_objects)
        if context.active_object is not None:
            objects.add(context.active_object)

        return filter(
            lambda obj: asset_helpers.is_asset_with_engon_feature(obj, "botaniq"),
            polib.asset_pack_bpy.find_polygoniq_root_objects(objects)
        )

    @classmethod
    def get_selected_particle_system_targets(
        cls,
        context: bpy.types.Context
    ) -> typing.Iterable[bpy.types.Object]:
        objects = set(context.selected_objects)
        if context.active_object is not None:
            objects.add(context.active_object)
        return filter(
            lambda obj: AdjustmentMixin.has_pps(obj),
            objects
        )


@polib.log_helpers_bpy.logged_panel
class AdjustmentsPanel(BotaniqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_botaniq_adjustments"
    bl_parent_id = BotaniqPanel.bl_idname
    bl_label = "Adjustments"

    # The maximum number of assets to be displayed with details in the panel
    MAX_DISPLAYED_ASSETS = 10

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_HUE_SATURATION')

    def get_season_from_value(self, value: float) -> str:
        # We need to change seasons at 0.125, 0.325, 0.625, 0.875
        # The list of seasons and values holds the "center" value of the season, not the boundaries
        # We need to do a bit of math to move it to get proper ranges. -0.125 moves from center to
        # start of the range, + 1.0 because fmod doesn't work with negative values
        adjusted_value: float = math.fmod(value - 0.125 + 1.0, 1.0)
        for season, max_value in reversed(polib.asset_pack_bpy.BOTANIQ_SEASONS_WITH_COLOR_CHANNEL):
            if adjusted_value <= max_value:
                return season
        return "unknown"

    def draw_obj_properties(
        self,
        obj: bpy.types.Object,
        left_col: bpy.types.UILayout,
        right_col: bpy.types.UILayout,
        spaces: int = 0
    ) -> None:
        row = left_col.row()
        row.label(text=f"{spaces * ' '}{obj.name}")
        row = right_col.row()

        brightness = obj.get(polib.asset_pack_bpy.CustomPropertyNames.BQ_BRIGHTNESS, None)
        season = obj.get(polib.asset_pack_bpy.CustomPropertyNames.BQ_SEASON_OFFSET, None)
        random_per_branch = obj.get(
            polib.asset_pack_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH, None)
        random_per_leaf = obj.get(
            polib.asset_pack_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF, None)
        if brightness is not None:
            row.label(text=f"{brightness:.2f}")
        else:
            row.label(text="-")

        if season is not None:
            row.label(text=f"{self.get_season_from_value(season)}")
        else:
            row.label(text="-")

        if random_per_branch is not None:
            row.label(text=f"{random_per_branch:.2f}")
        else:
            row.label(text="-")

        if random_per_leaf is not None:
            row.label(text=f"{random_per_leaf:.2f}")
        else:
            row.label(text="-")

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        # we can only make the adjustments on botaniq or botaniq asset pack assets or targets of
        # botaniq particle systems
        assets = set(AdjustmentMixin.get_selected_botaniq_assets(context))
        ps_objects = set(AdjustmentMixin.get_selected_particle_system_targets(context))
        ps_object_to_instanced_objects = {
            obj: set(asset_helpers.gather_instanced_objects([obj])) for obj in ps_objects}
        # Objects that are not in particle systems and are not particle system containers
        assets = assets - ps_objects - \
            set(itertools.chain(*ps_object_to_instanced_objects.values()))
        if len(assets) == 0 and len(ps_objects) == 0:
            layout.label(text="No botaniq assets or particle systems selected!")
            return

        row = layout.row()
        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)
        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")
        row = right_col.row()
        row.enabled = False
        row.label(text="Brightness")
        row.label(text="Season")
        row.label(text="Branch Hue")
        row.label(text="Leaf Hue")

        displayed_assets = 0
        for obj in assets:
            if displayed_assets >= AdjustmentsPanel.MAX_DISPLAYED_ASSETS:
                left_col.label(text=f"... and {len(assets) - displayed_assets} additional asset(s)")
                break

            self.draw_obj_properties(obj, left_col, right_col)
            displayed_assets += 1

        # Let's always draw the objects of the particle system, don't trim the objects inside
        for i, (scatter_obj, instanced_objects) in enumerate(ps_object_to_instanced_objects.items()):
            if displayed_assets >= AdjustmentsPanel.MAX_DISPLAYED_ASSETS:
                left_col.label(
                    text=f"... and {len(ps_object_to_instanced_objects) - i} additional scatter(s)")
                break

            left_col.label(text=scatter_obj.name, icon='PARTICLES')
            # Empty text to just keep the layout flow
            right_col.label(text="")
            for obj in instanced_objects:
                self.draw_obj_properties(obj, left_col, right_col, spaces=4)
                displayed_assets += 1

        prefs = preferences.get_preferences(context).botaniq_preferences
        row = layout.row(align=True)
        row.label(text="", icon='LIGHT_SUN')
        row.prop(prefs, "brightness", text="Brightness", slider=True)
        row.operator(
            RandomizeFloatProperty.bl_idname, text="", icon='FILE_3D'
        ).custom_property_name = polib.asset_pack_bpy.CustomPropertyNames.BQ_BRIGHTNESS

        row = layout.row(align=True)
        row.label(text="", icon='BRUSH_MIX')
        row.prop(prefs, "season_offset", icon='BRUSH_MIX',
                 text=f"Season: {self.get_season_from_value(prefs.season_offset)}", slider=True)
        row.operator(
            RandomizeFloatProperty.bl_idname, text="", icon='FILE_3D'
        ).custom_property_name = polib.asset_pack_bpy.CustomPropertyNames.BQ_SEASON_OFFSET

        row = layout.row(align=True)
        row.label(text="", icon='COLORSET_12_VEC')
        row.prop(prefs, "hue_per_branch", text="Hue per Branch", slider=True)
        row.operator(
            RandomizeFloatProperty.bl_idname, text="", icon='FILE_3D'
        ).custom_property_name = polib.asset_pack_bpy.CustomPropertyNames.BQ_RANDOM_PER_BRANCH

        row = layout.row(align=True)
        row.label(text="", icon='COLORSET_02_VEC')
        row.prop(prefs, "hue_per_leaf", text="Hue per Leaf", slider=True)
        row.operator(
            RandomizeFloatProperty.bl_idname, text="", icon='FILE_3D'
        ).custom_property_name = polib.asset_pack_bpy.CustomPropertyNames.BQ_RANDOM_PER_LEAF


ADDON_CLASSES.append(AdjustmentsPanel)


@polib.log_helpers_bpy.logged_panel
class AnimationsPanel(BotaniqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_botaniq_animations"
    bl_parent_id = BotaniqPanel.bl_idname
    bl_label = "Animations"

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='FORCE_WIND')

    def draw_object_anim_details(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        obj: bpy.types.Object,
        animated_object: bpy.types.Object
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
                text=f"{obj.instance_collection.users - 1}")

        action = animated_object.animation_data.action
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
        split.label(text=str(animation_style.value))

        # Strength
        wind_strength = animations.infer_strength_from_action(action)
        if wind_strength is not None:
            split = col.split(factor=split_factor, align=True)
            split.label(text="Strength:")
            split.label(text=f"{wind_strength:.3f}x")

        if animation_style == preferences.WindStyle.LOOP:
            frame_range = animations.get_frame_range(action)
            if frame_range is not None:
                # Loop Interval
                loop_interval = frame_range[1] - frame_range[0]
                split = col.split(factor=split_factor, align=True)
                split.label(text="Loop Interval:")
                split.label(text=f"{round(loop_interval)} frames")

                # Duration
                scene_interval = context.scene.frame_end - context.scene.frame_start
                scene_fps = animations.get_scene_fps(
                    context.scene.render.fps, context.scene.render.fps_base)
                split = col.split(factor=split_factor, align=True)
                split.label(text="Duration:")
                split.label(text=f"{scene_interval / scene_fps:.1f} s")

                # Speed
                speed = loop_interval / animations.get_scene_fps_adjusted_interval(scene_fps)
                split = col.split(factor=split_factor, align=True)
                split.label(text="Speed:")
                split.label(text=f"{speed:.1f}x")

    def draw(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        layout = self.layout

        row = polib.ui_bpy.scaled_row(layout, 1.5, align=True)
        row.operator(animations.AnimationAddWind.bl_idname, text="Add Animation", icon='ADD')
        layout.separator()

        row = layout.row(align=True)
        row.operator(animations.AnimationMakeInstanced.bl_idname,
                     text="Make Instance", icon='GROUP')
        row.operator(animations.AnimationRemoveWind.bl_idname,
                     text="Remove Animation", icon='REMOVE')

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
            row.operator(animations.AnimationSetAnimStyle.bl_idname,
                         text="Loop / Procedural Switch")
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

        active_object = context.active_object
        if active_object is None:
            return

        if animations.has_6_6_or_older_action(context.active_object):
            col = layout.column(align=True)
            col.label(text="Asset has old Animation", icon='ERROR')
            col.label(text="Please respawn the asset or use")
            col.label(text="'Convert to Linked' and 'Convert to Editable' and")
            col.label(text="re-apply the animation.")

        animated_object = animations.get_instanced_mesh_object(active_object)
        if animated_object is None:
            return

        if not animations.is_animated(animated_object):
            return

        self.draw_object_anim_details(context, layout, active_object, animated_object)


ADDON_CLASSES.append(AnimationsPanel)


@polib.log_helpers_bpy.logged_panel
class AnimationAdvancedPanel(BotaniqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_botaniq_animations_advanced"
    bl_parent_id = AnimationsPanel.bl_idname
    bl_label = "Animations Advanced"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.active_object is None:
            return False

        if context.mode != 'OBJECT':
            return False

        instanced_obj = animations.get_instanced_mesh_object(context.active_object)
        if instanced_obj is None:
            return False

        return animations.is_animated(instanced_obj)

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='OPTIONS')

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        animated_object = animations.get_instanced_mesh_object(context.active_object)
        if animated_object is None:
            return

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
        for mod_name, fmod_limits in sorted(animations.get_animation_state_control_modifiers(action), key=lambda x: x[0]):
            row = col.row(align=True)
            row.label(text=f"{mod_name[len('bq_'):]}")

            mod, prop = scale_mod_prop_map.get(mod_name, (None, None))
            amplitude_col = row.column(align=True)
            amplitude_col.alignment = 'RIGHT'
            if mod is not None:
                amplitude_col.prop(mod, prop, text="")
            else:
                amplitude_col.label(text="Not Controllable")

            row.prop(animated_object.modifiers[mod_name], "show_viewport", text="")
            # For some reason next icon from the desired one has to be used: AUTO => CHECKMARK
            row.prop(fmod_limits, "mute", text="",
                     icon='AUTO' if fmod_limits.mute is True else 'BLANK1')


ADDON_CLASSES.append(AnimationAdvancedPanel)


def register():
    for cls in ADDON_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(ADDON_CLASSES):
        bpy.utils.unregister_class(cls)
