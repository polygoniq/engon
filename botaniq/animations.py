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
import collections
import os
import random
import logging
import polib
import mapr
from .. import preferences
from .. import asset_helpers
from .. import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")

MODULE_CLASSES: typing.List[typing.Type] = []


DEFAULT_PRESET = preferences.botaniq_preferences.WindPreset.WIND
DEFAULT_WIND_STRENGTH = 0.5
MODIFIER_STACK_NAME_PREFIX = "bq_Modifier-Stack"
ANIMATION_INSTANCES_COLLECTION = "animation_instances"
ANIMATED_INSTANCE_PREFIX = "Anim_"
ANIMATION_DEFAULT_INTERVAL = 120
ANIMATION_DEFAULT_FPS = 24
MUTING_STORED_ACTION_NAME = "bq_muted_action"
# First three FCurve modifiers define animation style by their enabled status
# 1) Cyclic to ensure looping between first and last keyframe
# 2) Generator that flattens the FCurve if the style is switched to procedural to cancel the looping
# 3) Noise for procedural animation type
WIND_ANIMATION_FCURVE_STYLE_MODS = ['CYCLES', 'GENERATOR', 'NOISE']
# This represent modifiers status when LOOPING style, its inversion represent PROCEDURAL style
LOOPING_STACK_STATUS = [('CYCLES', True), ('GENERATOR', False), ('NOISE', False)]
# FCurves that can be adjusted by user are expected to have this modifier stack on top of style stack:
# 4) Envelope to multiply the individual FCurve strength in the UI
# 5) Limits to disable the FCurve entirely
WIND_ANIMATION_FCURVE_UI_MODS = ['ENVELOPE', 'LIMITS']


def load_helper_object_names() -> typing.Set[str]:
    path = preferences.get_preferences(bpy.context).botaniq_preferences.animation_data_path
    if path is None:
        return set()

    with bpy.data.libraries.load(path) as (data_from, _):
        return set(data_from.objects)


def link_animation_data(
    animation_type: str
) -> typing.Tuple[bpy.types.Library, bpy.types.Collection, typing.List[bpy.types.Action]]:
    anim_data_collection_name = f"bq_Animation-Data_{animation_type}"
    anim_lib_path = preferences.get_preferences(bpy.context).botaniq_preferences.animation_data_path
    if anim_lib_path is None:
        raise RuntimeError(
            "Can't link animation data, couldn't find any asset pack with botaniq engon feature "
            "that has a bq_Library_Animation_Data.blend file in blends/model folder.")
    anim_lib_basename = os.path.basename(anim_lib_path)
    old_anim_lib = bpy.data.libraries.get(anim_lib_basename, None)

    # We reload the library every time to get the latest data and prevent ReferenceError if the
    # library was removed
    if old_anim_lib is not None:
        old_anim_lib.reload()

    with bpy.data.libraries.load(anim_lib_path, link=True) as (data_from, data_to):
        assert anim_data_collection_name in data_from.collections
        data_to.collections = [anim_data_collection_name]
        data_to.actions = [x for x in data_from.actions if x.startswith(
            f"bq_{animation_type}")]

    assert anim_lib_basename in bpy.data.libraries
    anim_lib = bpy.data.libraries.get(anim_lib_basename)

    assert len(data_to.collections) == 1
    anim_collection = data_to.collections[0]

    assert anim_collection is not None
    return anim_lib, anim_collection, data_to.actions


def remove_orphan_actions() -> typing.Iterable[str]:
    removed_action_names = []
    for action in list(bpy.data.actions):
        if action.name.startswith("bq_") and action.users == 0:
            removed_action_names.append(action.name)
            bpy.data.actions.remove(action)

    return removed_action_names


def get_instanced_mesh_object(obj: bpy.types.Object) -> typing.Optional[bpy.types.Object]:
    """Returns first mesh object in instanced collection of 'obj',
    if 'obj' is not instanced this returns 'obj'.

    If 'obj' should be instanced but it's instance isn't assigned this returns None.
    """
    assert obj is not None
    if obj.instance_type == 'COLLECTION':
        # Return None if object is set to be instanced, but it's collection isn't set
        if obj.instance_collection is None:
            return None

        for instanced_object in obj.instance_collection.objects:
            if instanced_object.type != 'MESH':
                continue

            return instanced_object

    return obj


def infer_modifier_from_data_path(data_path: str) -> typing.Optional[str]:
    """Returns name of affected modifier from data path. If it is not possible to infer
    modifier name returns None.
    """
    # This line evaluates the actual name of the modifier from the fcurve data_path
    # example: data_path = 'modifiers["bq_branch-group_1"].offset' -> result "bq_branch_group"
    # at index 1
    data_path_split = data_path.split("\"", 2)
    if data_path_split[0] != "modifiers[":
        return None

    return data_path_split[1]


def get_animation_state_control_modifiers(
    action: bpy.types.Action
) -> typing.Set[typing.Tuple[str, bpy.types.FModifierLimits]]:
    """Returns set of last 'LIMITS' modifiers from fcurves in 'action'.
    These fcurve modifiers are used to control the state of the animation modifier (on/off).
    """
    control_modifiers = set()
    for fcurve in action.fcurves:
        modifier_name = infer_modifier_from_data_path(fcurve.data_path)
        if modifier_name is None:
            continue

        fcurve_mod = fcurve.modifiers[-1]
        if fcurve_mod.type != 'LIMITS':
            continue

        control_modifiers.add((modifier_name, fcurve_mod))

    return control_modifiers


def get_envelope_modifier(fmodifiers: bpy.types.FCurveModifiers) -> typing.Optional[bpy.types.FModifierEnvelope]:
    """Returns first 'ENVELOPE' modifier in FCurve modifier stack if is present."""
    for modifier in fmodifiers:
        if modifier.type == 'ENVELOPE':
            return modifier
    return None


def set_animation_strength(action: bpy.types.Action, value: float) -> None:
    """Changes 'max' value of 'ENVELOPE' modifiers control point.
    This is used to control the strength of the animation.
    """
    for fcurve in action.fcurves:
        envelope_mod = get_envelope_modifier(fcurve.modifiers)
        if envelope_mod is None:
            continue
        # Envelope control point is a reference point for scaling the animation, its
        # position is expected to be at 0 of Y axis. Its minimal value is 0
        # and maximum value is the multiplier of the fcurves strength
        control_points = envelope_mod.control_points
        if len(control_points) == 0:
            continue
        control_points[0].max = value


def parse_action_name(action: bpy.types.Action) -> typing.Tuple[str, str]:
    """Returns tuple of (animation_type, preset) parsed from the name of 'action'."""
    assert action.name.count("_", 2)
    split = polib.utils_bpy.remove_object_duplicate_suffix(action.name).split("_")
    return split[1], split[2]


def get_scene_fps(fps: int, fps_base: float) -> float:
    return fps / fps_base


def get_scene_fps_adjusted_interval(scene_fps: float) -> int:
    return int(ANIMATION_DEFAULT_INTERVAL * (scene_fps / ANIMATION_DEFAULT_FPS))


def infer_strength_from_action(
    action: typing.Optional[bpy.types.Action]
) -> typing.Optional[float]:
    """Returns the average strength of wind animation inferred from the 'ENVELOPE' modifiers in
    fcurves from 'action'. This is mainly for UI purpose to display strength of active animation.
    """
    if action is None:
        return None

    strengths = []
    for fcurve in action.fcurves:
        envelope_mod = get_envelope_modifier(fcurve.modifiers)
        if envelope_mod is None:
            continue

        control_points = envelope_mod.control_points
        if len(control_points) == 0:
            continue
        strengths.append(control_points[0].max)

    if len(strengths) == 0:
        return None
    return sum(strengths) / len(strengths)


def get_envelope_multiplier_mod_prop_map(
    action: typing.Optional[bpy.types.Action]
) -> typing.Dict[str, typing.Tuple[bpy.types.FModifier, str]]:
    """Finds and returns a map of modifier names -> (fcurve modifier, property name)

    Key is the name of modifier on the object. Value tuple contains fcurve modifier
    and property name of the property affecting the amplitude of the fcurve.
    """
    mod_name_prop_map: typing.Dict[str, typing.Tuple[bpy.types.FModifier, str]] = {}
    if action is None:
        return mod_name_prop_map

    for fcurve in action.fcurves:
        if len(fcurve.modifiers) < len(WIND_ANIMATION_FCURVE_UI_MODS):
            continue

        # We try to find the 'ENVELOPE' modifier, if not present it means that this fcurve cannot
        # be amplified by the envelope modifier to adjust animation strength
        envelope_mod = get_envelope_modifier(fcurve.modifiers)
        if envelope_mod is None:
            continue

        obj_modifier_name = infer_modifier_from_data_path(fcurve.data_path)

        if obj_modifier_name is not None:
            control_points = envelope_mod.control_points
            if len(control_points) == 0:
                continue
            mod_name_prop_map[obj_modifier_name] = (control_points[0], "max")

    return mod_name_prop_map


def copy_modifiers(source: bpy.types.Object, target: bpy.types.Object) -> None:
    """Copies modifiers from source object to target object while preserving existing modifiers
    and pushing them at the end of the stack.

    Having the original modifiers at the end guarantees there is no unnecessary evaluation of data,
    i.e. evaluating animation after Subdivision Surface modifier.
    """
    for mod in reversed(source.modifiers):
        # Use context override so we don't have to link source object to scene and mess with selection
        with bpy.context.temp_override(object=source, selected_objects=[target]):
            bpy.ops.object.modifier_copy_to_selected(modifier=mod.name)
        with bpy.context.temp_override(object=target):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=0)


def copy_animation_data(source: bpy.types.Object, target: bpy.types.Object) -> bpy.types.Action:
    assert source.animation_data is not None
    assert source.animation_data.action is not None
    if target.animation_data is None:
        target.animation_data_create()
    assert target.animation_data is not None
    target.animation_data.action = source.animation_data.action.copy()
    animation_type = source.animation_data.action.name.rsplit("_", 1)[0]
    target.animation_data.action.name = f"{animation_type}_Instance"
    return target.animation_data.action


def copy_driving_empties(
    modifier_stack: bpy.types.Object,
    target: bpy.types.Object,
    target_collection: bpy.types.Collection
) -> None:
    def parent_and_copy_animation_recursive(
        child: bpy.types.Object,
        parent: bpy.types.Object,
        target_collection: bpy.types.Collection
    ) -> typing.Dict[bpy.types.Object, bpy.types.Object]:

        ret = {}
        child_copy: bpy.types.Object = child.copy()
        polib.asset_pack_bpy.collection_add_object(target_collection, child_copy)
        child_copy.parent = parent
        ret[child] = child_copy
        if child.animation_data:
            copy_animation_data(child, child_copy)

        for nested_child in child.children:
            ret.update(parent_and_copy_animation_recursive(
                nested_child, child_copy, target_collection))

        return ret

    children_map = {}
    for child in modifier_stack.children:
        children_map.update(parent_and_copy_animation_recursive(child, target, target_collection))

    # We assume modifier stacks are the same, because they have been linked
    for mod in modifier_stack.modifiers:
        target_mod = target.modifiers.get(mod.name)
        if not target_mod:
            continue
        # We cant access the object directly but we can check if the pointer points to object
        for prop in mod.bl_rna.properties:
            if prop.type != 'POINTER':
                continue
            if prop.fixed_type.name != 'Object':
                continue
            driving_obj = getattr(mod, prop.identifier)
            if driving_obj is not None:
                setattr(target_mod, prop.identifier, children_map.get(driving_obj))


def is_bq_animation_modifier(modifier: bpy.types.Modifier) -> bool:
    assert modifier is not None
    return modifier.name.startswith("bq_")


def is_bq_animation_action(action: bpy.types.Action) -> bool:
    assert action is not None
    return action.name.startswith("bq_")


def has_6_6_or_older_action(obj: bpy.types.Object) -> bool:
    """Returns True if objects action was spawned from botaniq 6.6 or older.

    botaniq 6.7 introduced breaking changes of actions.
    """

    assert obj is not None
    anim_obj = get_instanced_mesh_object(obj)
    if anim_obj is None:
        return False

    if anim_obj.animation_data is None:
        return False

    if anim_obj.animation_data.action is None:
        return False

    return anim_obj.animation_data.action.name.startswith("bqa_")


def is_animated(obj: bpy.types.Object) -> bool:
    assert obj is not None
    if obj.animation_data is None:
        return False

    if obj.animation_data.action is None:
        return False

    return obj.animation_data.action.name.startswith("bq_")


def is_animated_muted(obj: bpy.types.Object) -> bool:
    assert obj is not None
    if obj.animation_data is None:
        return False

    # muted object doesn't have action assigned
    if obj.animation_data.action is not None:
        return False

    return MUTING_STORED_ACTION_NAME in obj


def get_animated_objects(
    objects: typing.Iterable[bpy.types.Object],
    include_muted: bool = False
) -> typing.Iterator[bpy.types.Object]:
    """Yields all botaniq animated objects from 'objects'

    'objects' list is the user selection in the scene. It can contain selected instances or particle
    systems or editable objects. This function unwraps those instances and particle systems to get
    the underlying animated objects. In case of instance it checks for the instanced objects and in
    case of particle system its instance collection objects are checked.
    """
    for obj in set(objects) | set(asset_helpers.gather_instanced_objects(objects)):
        anim_obj = get_instanced_mesh_object(obj)
        if anim_obj is None:
            continue

        if anim_obj.type != 'MESH':
            continue

        if not asset_helpers.is_asset_with_engon_feature(anim_obj, "botaniq"):
            continue

        if include_muted:
            if is_animated(anim_obj) or is_animated_muted(anim_obj):
                yield anim_obj
        else:
            if is_animated(anim_obj):
                yield anim_obj


def get_animated_objects_hierarchy(
    root_obj: bpy.types.Object,
    helper_object_names: typing.Set[str],
    include_root: bool = False
) -> typing.Iterator[bpy.types.Object]:
    """Yields animation helper objects from 'root_obj' based on 'helper_object_names'

    If 'include_root' parameter is provided 'root_obj' is also yielded back.
    Note: We pass 'helper_object_names' so the caller can load them from the library only once.
    """
    if include_root:
        yield root_obj

    hierarchy = polib.asset_pack_bpy.get_entire_object_hierarchy(root_obj)
    for obj in hierarchy:
        obj_name_clean = polib.utils_bpy.remove_object_duplicate_suffix(obj.name)
        if obj_name_clean in helper_object_names:
            yield obj


def get_frame_range(action: bpy.types.Action) -> typing.Optional[typing.Tuple[float, float]]:
    for fcurve in action.fcurves:
        if len(fcurve.keyframe_points) < 2:
            continue
        keyframes = fcurve.keyframe_points
        return keyframes[0].co.x, keyframes[-1].co.x
    return None


def set_animation_frame_range(
    obj: bpy.types.Object,
    frame_rate: float,
    new_frame_interval: int
) -> None:
    """Scale the action's fcurves so that the difference in x position between first and last
    keyframe equals the new frame interval or it's multiple. The first keyframes position is maintained.

    We do not stretch the fcurves over the entire interval, because that would change the speed of the
    animation. Instead we repeat the default animation multiple times if necessary with maximum
    stretch of 1/3 of the default animation interval.

    24fps
    interval = 120 -->  |------120-----|120         Stretch is 0
    interval = 150 -->  |--------150-------|150     Stretch is less than 1/3 of default interval
    interval = 180 -->  |----90----|----90----|180  Stretch is more than 1/3 of default interval

    In case of different fps we take that into account in order to maintain same speed of the
    animation. Meaning the animation interval and stretch between 30 and 60 fps will be doubled.
    The speed may vary according to stretch but will never be less than 2/3 of the default speed
    and more than 4/3 of the default speed

    24fps
    interval = 300 --> |---100---|---100---|---100---|300   Speed = 0.8x   Duration = 12.5s
    30fps
    interval = 300 --> |------150-----|------150-----|300   Speed = 1x     Duration = 10s
    60fps
    interval = 300 --> |--------------300------------|300   Speed = 1x     Duration = 5s
    """

    anim_obj: bpy.types.Object = get_instanced_mesh_object(obj)
    assert anim_obj.animation_data.action is not None
    anim_obj_action = anim_obj.animation_data.action
    current_frame_range = get_frame_range(anim_obj_action)

    if current_frame_range is None:
        return

    anim_obj_hierarchy = polib.asset_pack_bpy.get_entire_object_hierarchy(anim_obj)

    current_frame_interval = current_frame_range[1] - current_frame_range[0]
    fps_ratio = frame_rate / ANIMATION_DEFAULT_FPS
    interval_count, frames_overlap = divmod(
        new_frame_interval, ANIMATION_DEFAULT_INTERVAL * fps_ratio)
    multiplier = new_frame_interval / current_frame_interval

    if interval_count > 0:
        # We allow maximum 1/3 of the animation interval stretch,
        # i.e. default 120 frame interval at 24fps will be set between 80 and 160.
        if frames_overlap >= ANIMATION_DEFAULT_INTERVAL / 3:
            multiplier /= interval_count + 1
        else:
            multiplier /= interval_count

    for obj in anim_obj_hierarchy:
        if obj.animation_data is None or obj.animation_data.action is None:
            continue

        for fcurve in obj.animation_data.action.fcurves:
            # We need at least two keyframes to change animation interval
            if len(fcurve.keyframe_points) < 2:
                continue

            for keyframe in fcurve.keyframe_points:
                l_handle_distance = keyframe.co.x - keyframe.handle_left.x
                r_handle_distance = keyframe.co.x - keyframe.handle_right.x
                # Scale the keyframes x position by multiplier and offset back to starting position
                # of the first keyframe of the fcurve
                keyframe.co.x = keyframe.co.x * multiplier - \
                    (current_frame_range[0] * multiplier - current_frame_range[0])
                # Move and scale the handles as well to maintain the curvature ratio
                keyframe.handle_left.x = keyframe.co.x - (l_handle_distance * multiplier)
                keyframe.handle_right.x = keyframe.co.x - (r_handle_distance * multiplier)


def get_wind_style(action: bpy.types.Action) -> preferences.botaniq_preferences.WindStyle:
    """Infers animation style from looking at status of FCurve Noise modifier in stack.
    """
    for fcurve in action.fcurves:
        if len(fcurve.modifiers) < len(WIND_ANIMATION_FCURVE_STYLE_MODS):
            continue

        # Expected position of noise modifier in stack
        noise = fcurve.modifiers[2]
        if noise.type != 'NOISE':
            continue

        if noise.mute:
            return preferences.botaniq_preferences.WindStyle.LOOP
        return preferences.botaniq_preferences.WindStyle.PROCEDURAL

    return preferences.botaniq_preferences.WindStyle.UNKNOWN


def change_anim_style(
    obj: bpy.types.Object,
    helper_objs: typing.Iterable[bpy.types.Object],
    style: preferences.botaniq_preferences.WindStyle
) -> None:
    """Set animation style of given objects and its given helper empties.

    Animation style is set to their actions by changing the mute status on specific FCurves.

    Fails if given 'obj' doesn't have animation_data.action and only logs warning if some of the
    'helper_objs' doesn't have it.
    """
    def change_anim_style_of_action(action: bpy.types.Action, style: preferences.botaniq_preferences.WindStyle) -> None:
        """Set animation style of action to the provided one by changing the mute status on specific FCurves."""
        for fcurve in action.fcurves:
            if len(fcurve.modifiers) < len(WIND_ANIMATION_FCURVE_STYLE_MODS):
                continue

            # Cyclic - repeats first and last keyframe
            cyclic = fcurve.modifiers[0]
            # Generator - flattens the keyframes so noise can replace the value instead of adding
            generator = fcurve.modifiers[1]
            # Noise - creates procedural animation type
            noise = fcurve.modifiers[2]

            for i, modifier in enumerate([cyclic, generator, noise]):
                loop_mod_type, loop_mod_status = LOOPING_STACK_STATUS[i]
                if loop_mod_type != modifier.type:
                    continue
                if style == preferences.botaniq_preferences.WindStyle.LOOP:
                    modifier.mute = not loop_mod_status
                else:
                    modifier.mute = loop_mod_status

    assert obj.animation_data is not None and obj.animation_data.action is not None
    change_anim_style_of_action(obj.animation_data.action, style)
    for helper_obj in helper_objs:
        # Not all helper empties have actions
        if helper_obj.animation_data is not None and helper_obj.animation_data.action is not None:
            change_anim_style_of_action(helper_obj.animation_data.action, style)


def change_preset(obj: bpy.types.Object, preset: str, strength: float) -> int:
    """Changes preset of 'obj' by switching the action of the same animation type to 'preset'
    """
    anim_type, _ = parse_action_name(obj.animation_data.action)
    anim_library_path = preferences.get_preferences(
        bpy.context).botaniq_preferences.animation_data_path
    anim_library = bpy.data.libraries.get(os.path.basename(anim_library_path), None)
    if anim_library is None:
        anim_library, _, _ = link_animation_data(anim_type)

    assert anim_library is not None

    preset_action_name = f"bq_{anim_type}_{preset}"
    preset_action = bpy.data.actions.get((preset_action_name, anim_library.filepath), None)
    assert preset_action is not None

    old_frame_interval = ANIMATION_DEFAULT_INTERVAL

    if obj.animation_data is None:
        obj.animation_data_create()
        animation_style = preferences.botaniq_preferences.WindStyle.LOOP
    else:
        old_action = obj.animation_data.action
        animation_style = get_wind_style(old_action)
        old_frame_range = get_frame_range(old_action)
        if old_frame_range is not None:
            old_frame_interval = int(old_frame_range[1] - old_frame_range[0])

    # Reset the helper objects, as the main animated objects is reset to default by changing its action
    helper_objs = list(get_animated_objects_hierarchy(obj, load_helper_object_names()))
    for helper_obj in helper_objs:
        if helper_obj.animation_data is not None and helper_obj.animation_data.action is not None:
            set_animation_frame_range(helper_obj, ANIMATION_DEFAULT_FPS, ANIMATION_DEFAULT_INTERVAL)

    new_action = preset_action.copy()
    assert obj.animation_data is not None
    obj.animation_data.action = new_action

    set_animation_strength(new_action, strength)
    # We know here that helper_objs didn't change while changing preset thus they should have
    # the correct animation style. But let's not change API of change_anim_style because of this
    # corner case and let's set style of helper objects to be sure.
    change_anim_style(obj, helper_objs, animation_style)
    remove_orphan_actions()

    return old_frame_interval


class AnimationOperatorBase(bpy.types.Operator):
    @staticmethod
    def get_target_objects(context: bpy.types.Context) -> typing.Iterable[bpy.types.Object]:
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties

        if wind_properties.operator_target == 'SELECTED':
            target_objects = context.selected_objects
        elif wind_properties.operator_target == 'SCENE':
            target_objects = context.scene.objects
        elif wind_properties.operator_target == 'ALL':
            target_objects = bpy.data.objects
        else:
            raise ValueError(f"Unknown selection target '{wind_properties.operator_target}'")
        return target_objects

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        self.layout.prop(wind_properties, "operator_target", text="")


@polib.log_helpers_bpy.logged_operator
class AnimationAddWind(bpy.types.Operator):
    bl_idname = "engon.botaniq_animation_add_wind"
    bl_label = "Add Wind Animation"
    bl_description = "Adds wind animation to selected animable assets. " \
        "Applies only on objects that are editable"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and \
            next((obj for obj in context.selected_objects if obj.type == 'MESH'), None) is not None

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.use_property_split = True
        props = preferences.get_preferences(context).botaniq_preferences.wind_anim_properties
        layout.prop(props, "animation_type", text="Animation Type")
        layout.prop(props, "auto_make_instance")

    def save_state(self, context: bpy.types.Context) -> None:
        self.previous_selected_objects_names = {obj.name for obj in context.selected_objects}
        active_object = context.active_object
        self.previous_active_object_name = active_object.name if active_object else ""

    def restore_state(self, context: bpy.types.Context) -> None:
        for obj_name in self.previous_selected_objects_names:
            if obj_name not in bpy.data.objects:
                continue

            if obj_name in context.view_layer.objects:
                bpy.data.objects[obj_name].select_set(True)

        if self.previous_active_object_name in context.view_layer.objects:
            context.view_layer.objects.active = bpy.data.objects[self.previous_active_object_name]

    def is_animable(self, prefs: preferences.Preferences, obj: bpy.types.Object) -> bool:
        asset_provider = asset_registry.instance.master_asset_provider
        assert asset_provider is not None

        # currently we support animations only for assets converted to editable
        if obj.type != 'MESH':
            self.report(
                {'INFO'}, f"{obj.name} cannot add animation to a non-editable object!")
            return False

        if obj.library is not None:
            self.report({'INFO'}, f"{obj.name} cannot add animation to a linked object!")
            return False

        if obj.animation_data is not None:
            self.report({'INFO'}, f"{obj.name} already contains animation data!")
            return False

        if not asset_helpers.is_asset_with_engon_feature(obj, "botaniq"):
            return False

        asset_id = obj.get(mapr.blender_asset_spawner.ASSET_ID_PROP_NAME, None)
        if asset_id is None:
            self.report(
                {'INFO'},
                f"Object {obj.name} does not have the 'mapr_asset_id' property! Can't get its "
                f"metadata to be able to animate it!"
            )
            return False

        asset_meta = asset_provider.get_asset(asset_id)
        if asset_meta is None:
            self.report(
                {'INFO'},
                f"Object {obj.name} does have the 'mapr_asset_id' property ({asset_id}) but "
                f"the asset provider is not returning any asset metadata given this ID! "
                f"Can't animate."
            )
            return False

        animation_type_name = asset_meta.text_parameters.get("bq_animation_type")
        if animation_type_name is None:
            self.report(
                {'INFO'},
                f"bq_animation_type not found in metadata for asset id: '{asset_id}'! "
                f"Can't animate."
            )
            return False

        # This is available, but we want to show the error message to inform user
        if asset_helpers.is_object_from_seasons(obj, {"winter"}):
            self.report(
                {'INFO'}, f"{obj.name} is from the winter season. Winter season assets animations "
                "may require additional tweaking to achieve realistic looks.")
            return True

        return True

    def has_missing_6_7_anim_data(self, obj: bpy.types.Object) -> bool:
        """Returns True if object is missing animation data added in botaniq 6.7.

        botaniq 6.7 introduced breaking changes of animation modifier stack.
        """
        if obj.type != 'MESH':
            return False

        return "bq_leaves_gradient" not in obj.vertex_groups \
            or "bq_leaves_islands" not in obj.data.uv_layers

    def prepare_animation_data(
        self,
        unique_animation_types: typing.Set[str],
    ) -> typing.Dict[str, str]:
        """Loads animation data for 'unique_animation_types' and returns map to modifier stack names.

        Returns mapping of 'animation_type': 'modifier_stack_name'.
        """
        animation_type_data_map = {}
        modifier_container = None
        for animation_type in unique_animation_types:
            _, anim_collection, _ = link_animation_data(animation_type)
            for obj in anim_collection.objects:
                if obj.name.startswith(MODIFIER_STACK_NAME_PREFIX):
                    modifier_container = obj
                    break

            if modifier_container is None:
                logger.error(
                    f"Failed to find modifier container for animation type: '{animation_type}'")
                continue

            animation_type_data_map[animation_type] = modifier_container.name

        return animation_type_data_map

    def build_animation_type_objs_map(
        self,
        objects: typing.Iterable[bpy.types.Object],
        animation_type: str
    ) -> typing.Dict[str, typing.List[bpy.types.Object]]:
        """Returns a mapping of 'animation_type' to a unique subsets of 'objects' that use it.

        In case of  BEST FIT 'animation_type' there can be different 'animation_types' for different
        subset of 'objects' based on 'bq_animation_type' text_parameter.
        Otherwise the animation_type maps to all objects 'animation_type' -> [*objects].
        """
        # Return early with direct map of animation_type -> objects if selected animation type
        # is different from BEST_FIT
        if animation_type != preferences.botaniq_preferences.AnimationType.WIND_BEST_FIT.value:
            return {animation_type: list(objects)}

        animation_type_objs_map: typing.Dict[
            str, typing.List[bpy.types.Object]] = collections.defaultdict(list)

        asset_provider = asset_registry.instance.master_asset_provider
        assert asset_provider is not None

        for obj in objects:
            asset_id = obj.get(mapr.blender_asset_spawner.ASSET_ID_PROP_NAME, None)
            if asset_id is None:
                logger.error(
                    f"Object {obj.name} does not have the 'mapr_asset_id' property! Can't get its "
                    f"metadata to be able to animate it!"
                )
                continue

            asset_meta = asset_provider.get_asset(asset_id)
            if asset_meta is None:
                logger.error(
                    f"Object {obj.name} does have the 'mapr_asset_id' property ({asset_id}) but "
                    f"the asset provider is not returning any asset metadata given this ID! "
                    f"Can't animate."
                )
                continue

            animation_type_name = asset_meta.text_parameters.get("bq_animation_type")
            if animation_type_name is None:
                logger.error(
                    f"bq_animation_type not found in metadata for asset id: '{asset_id}'! "
                    f"Can't animate."
                )
                continue

            animation_type_objs_map[animation_type_name].append(obj)

        return animation_type_objs_map

    def animate_objects(
        self,
        context: bpy.types.Context,
        objs: typing.Iterable[bpy.types.Object],
        obj_source_map: asset_helpers.ObjectSourceMap,
        modifier_container_name: str,
        make_instance: bool
    ) -> typing.List[str]:
        animated_object_names: typing.List[str] = []

        modifier_container = bpy.data.objects.get(modifier_container_name)
        assert modifier_container is not None
        fps = get_scene_fps(context.scene.render.fps, context.scene.render.fps_base)
        fps_adjusted_interval = get_scene_fps_adjusted_interval(fps)

        for obj in objs:
            copy_modifiers(modifier_container, obj)
            # Copy animation data and empties from the container to the object
            copy_animation_data(modifier_container, obj)

            # We expect the obj_source_map to be constructed based on objs, but it is passed as
            # parameter to not construct it for each animation type. This way obj.name has to be
            # in obj_source_map.
            assert obj.name in obj_source_map
            # Switch the target collection for empties based on whether obj is in particle
            # system or not.
            if any(o[0] == asset_helpers.ObjectSource.particles for o in obj_source_map[obj.name]):
                empties_coll = asset_helpers.get_animation_empties_collection(context)
            else:
                assert len(obj.users_collection) > 0
                empties_coll = obj.users_collection[0]

            copy_driving_empties(modifier_container, obj, empties_coll)
            change_preset(obj, DEFAULT_PRESET.value, DEFAULT_WIND_STRENGTH)
            # Adjust the frame interval to scene fps to maintain default speed
            set_animation_frame_range(obj, fps, fps_adjusted_interval)
            helper_objs = get_animated_objects_hierarchy(obj, load_helper_object_names())
            change_anim_style(obj, helper_objs,
                              preferences.botaniq_preferences.WindStyle.PROCEDURAL)

            animated_object_names.append(obj.name)
            if make_instance:
                # Making instances creates new objects,
                # this needs to be reflected in the selection state
                self.previous_selected_objects_names.remove(obj.name)
                _, new_obj = AnimationMakeInstanced.wrap_to_instance_collection(
                    context, obj)
                self.previous_selected_objects_names.add(new_obj.name)
                # Check whether new instance object should be active
                # wrap_to_instance_collection prefixes object with Anim_
                # so we need to remove it for comparison
                sole_obj_name = new_obj.name[len(ANIMATED_INSTANCE_PREFIX):]
                if sole_obj_name == self.previous_active_object_name:
                    self.previous_active_object_name = new_obj.name

        return animated_object_names

    def report_missing_data(self, obj: bpy.types.Object) -> None:
        self.report(
            {'ERROR'},
            f"'Object {obj.name} was spawned from botaniq 6.6 or older and has "
            "non-compatible animation data, please respawn the asset or use "
            "'Convert to Linked' and 'Convert to Editable' to update the asset."
        )

    def report_old_action(self, obj: bpy.types.Object) -> None:
        self.report(
            {'ERROR'},
            f"'Object {obj.name} contains old animation added from botaniq 6.6 "
            "please remove old animation and re-apply new from the Animations panel."
        )

    def execute(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context).botaniq_preferences
        props = prefs.wind_anim_properties
        selected_objects = context.selected_objects
        auto_make_instance: bool = prefs.wind_anim_properties.auto_make_instance

        logger.info(
            f"Working on {[obj.name for obj in selected_objects]}, "
            f"auto make instance set to {auto_make_instance}")

        for obj in selected_objects:
            if any(polib.asset_pack_bpy.is_pps(ps.name) for ps in obj.particle_systems) and auto_make_instance:
                self.report(
                    {'ERROR'},
                    f"'Auto Make Instance' is not supported on particle systems, "
                    "please deselect particle system or turn off 'Auto Make Instance'"
                )
                return {'CANCELLED'}

            if self.is_animable(prefs, obj) and self.has_missing_6_7_anim_data(obj):
                self.report_missing_data(obj)
                return {'CANCELLED'}

        for instance_obj in asset_helpers.gather_instanced_objects(selected_objects):
            if not self.is_animable(prefs, instance_obj):
                continue

            if self.has_missing_6_7_anim_data(instance_obj):
                self.report_missing_data(instance_obj)
                return {'CANCELLED'}

            if has_6_6_or_older_action(instance_obj):
                self.report_old_action(instance_obj)
                return {'CANCELLED'}

        self.save_state(context)
        new_animated_object_names: typing.List[str] = []
        try:
            scatter_objs = asset_helpers.gather_instanced_objects(selected_objects)
            extended_selected_objects = set(selected_objects) | set(scatter_objs)
            animable_objects = {
                o for o in extended_selected_objects if self.is_animable(prefs, o)}

            # Source map has to be build out of all objects in the scene, so we can detect that
            # the newly animated asset is in particle system -> we can change the particle system
            # settings.
            objs_source_map = asset_helpers.get_obj_source_map(context.scene.objects)
            # Build map of animation type -> objs and prepare all the necessary
            # unique modifier stack objects.
            animation_type_objs_map = self.build_animation_type_objs_map(
                animable_objects,
                props.animation_type
            )
            animation_type_mod_container_name_map = self.prepare_animation_data(
                set(animation_type_objs_map))

            # Firstly deselect all
            polib.asset_pack_bpy.clear_selection(context)

            for animation_type, objs in animation_type_objs_map.items():
                mod_container_name = animation_type_mod_container_name_map.get(animation_type)
                assert mod_container_name is not None
                new_animated_object_names.extend(self.animate_objects(
                    context,
                    objs,
                    objs_source_map,
                    mod_container_name,
                    auto_make_instance
                ))

        finally:
            self.restore_state(context)

        logger.info(f"New animated objects: {new_animated_object_names}")
        return {'FINISHED'}


MODULE_CLASSES.append(AnimationAddWind)


@polib.log_helpers_bpy.logged_operator
class AnimationRemoveWind(bpy.types.Operator):
    bl_idname = "engon.botaniq_animation_remove_wind"
    bl_label = "Remove Wind Animation"
    bl_description = "Removes wind animation support from selected objects. " \
        "If object is instanced collection it removes animation " \
        "from the instanced object (all trees using the same collection)"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def get_objs_with_animation_leftovers(
        cls, objs: typing.Iterator[bpy.types.Object]
    ) -> typing.Iterator[bpy.types.Object]:
        """Returns botaniq objects which contain animation_data.
        """
        for obj in set(objs) | set(asset_helpers.gather_instanced_objects(objs)):
            anim_obj = get_instanced_mesh_object(obj)
            if anim_obj is None:
                continue

            if not asset_helpers.is_asset_with_engon_feature(anim_obj, "botaniq"):
                continue

            if anim_obj.animation_data is not None:
                yield anim_obj

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != 'OBJECT':
            return False

        return next(AnimationRemoveWind.get_objs_with_animation_leftovers(context.selected_objects), None) is not None

    @classmethod
    def remove_animation(
        cls,
        root_obj: bpy.types.Object,
        helper_object_names: typing.Set[str]
    ) -> None:
        """Removes botaniq wind animation and all its parts from object 'root_obj'.
        """
        # remove animation helper objects from botaniq 6.7 and newer
        helper_objects = get_animated_objects_hierarchy(root_obj, helper_object_names)
        for obj in helper_objects:
            bpy.data.objects.remove(obj)

        # remove animation helper objects that were spawned from botaniq older than 6.7
        hierarchy = list(polib.asset_pack_bpy.get_entire_object_hierarchy(root_obj))
        for obj in hierarchy:
            if obj.name.startswith("bqa_Empty_"):
                bpy.data.objects.remove(obj)

        for modifier in root_obj.modifiers:
            # remove also animation modifiers from older botaniq which starts with bqa_
            if is_bq_animation_modifier(modifier) or modifier.name.startswith("bqa_"):
                root_obj.modifiers.remove(modifier)

        if root_obj.animation_data is None:
            return

        # don't remove user defined animation
        # remove animations with:
        #   no action
        #   action from botaniq 6.7+ (gets picked up by is_bq_animation_action())
        #   action from older botaniq (action starts with bqa_)
        if root_obj.animation_data.action is None or \
                is_bq_animation_action(root_obj.animation_data.action) or \
                root_obj.animation_data.action.name.startswith("bqa_"):
            root_obj.animation_data_clear()

    def execute(self, context: bpy.types.Context):
        removed_animation_object_names = []
        helper_object_names = load_helper_object_names()

        logger.info(f"Working on {[obj.name for obj in context.selected_objects]}")

        anim_objs = AnimationRemoveWind.get_objs_with_animation_leftovers(
            context.selected_objects)
        # Filter out children animation empties - they are deleted
        # in AnimationRemoveWind.remove_animation together with parent object
        anim_root_objs = polib.asset_pack_bpy.find_polygoniq_root_objects(anim_objs)

        for obj in anim_root_objs:
            AnimationRemoveWind.remove_animation(obj, helper_object_names)
            removed_animation_object_names.append(obj.name)

        logger.info(f"Removed animations from objects: {removed_animation_object_names}")

        removed_orphan_action_names = remove_orphan_actions()
        logger.info(f"Removed orphan actions: {removed_orphan_action_names}")

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationRemoveWind)


@polib.log_helpers_bpy.logged_operator
class AnimationMute(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_mute"
    bl_label = "Mute Wind Animation"
    bl_description = "Mutes wind animation on botaniq objects, so it doesn't drop viewport FPS"

    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        name="Action",
        description="Choose if animation should be muted or unmuted",
        items=[
            ('MUTE', "Mute", "Mute botaniq animation"),
            ('UNMUTE', "Unmute", "Unmute botaniq animation"),
        ],
        default='MUTE',
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop_tabs_enum(self, "action")
        super().draw(context)

    def execute(self, context: bpy.types.Context):
        target_objects = AnimationMute.get_target_objects(context)
        botaniq_animated_objs = list(get_animated_objects(target_objects, include_muted=True))
        logger.info(f"Working on objects {[obj.name for obj in botaniq_animated_objs]}")
        helper_object_names = load_helper_object_names()
        for obj in botaniq_animated_objs:
            obj_anim_hierarchy = get_animated_objects_hierarchy(
                obj, helper_object_names, include_root=True)
            for anim_obj in obj_anim_hierarchy:
                # All objects from botaniq animation stack don't need to have animation_data.
                # Object can be parented to an animated object and not having animation_data itself.
                if anim_obj.animation_data is None:
                    continue
                if anim_obj.library is not None:
                    continue

                if self.action == 'MUTE':
                    if anim_obj.animation_data.action is None:
                        # This object was probably already muted, don't log error, skip it
                        continue
                    anim_obj[MUTING_STORED_ACTION_NAME] = anim_obj.animation_data.action.name
                    anim_obj.animation_data.action.use_fake_user = True
                    anim_obj.animation_data.action = None
                elif self.action == 'UNMUTE':
                    if MUTING_STORED_ACTION_NAME not in anim_obj:
                        # This object most probably wasn't previously muted, don't log error as it's
                        # valid use case to select all and click unmute to be sure nothing is muted
                        # before rendering. And this would spam logs a lot.
                        continue

                    stored_action_name = anim_obj[MUTING_STORED_ACTION_NAME]
                    del anim_obj[MUTING_STORED_ACTION_NAME]

                    if stored_action_name not in bpy.data.actions:
                        logger.error(f"Action '{stored_action_name}' wasn't found in "
                                     f"bpy.data.actions while unmuting '{anim_obj}'!")
                        continue

                    anim_obj.animation_data.action = bpy.data.actions[stored_action_name]
                else:
                    raise ValueError(f"Unknown operation '{self.action}', expected MUTE or UNMUTE!")

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationMute)


@polib.log_helpers_bpy.logged_operator
class AnimationApplyStrength(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_apply_strength"
    bl_label = "Apply Strength"
    bl_description = "Applies specified value of strength to selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        target_objects = AnimationOperatorBase.get_target_objects(context)
        animated_objects = list(get_animated_objects(target_objects))
        logger.info(
            f"Setting width strength to {wind_properties.strength} on "
            f"objects {[obj.name for obj in animated_objects]}"
        )

        for obj in animated_objects:
            set_animation_strength(
                obj.animation_data.action,
                wind_properties.strength
            )

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationApplyStrength)


@polib.log_helpers_bpy.logged_operator
class AnimationApplyPreset(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Applies specified preset to selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        target_objects = AnimationOperatorBase.get_target_objects(context)
        animated_objects = list(get_animated_objects(target_objects))
        logger.info(
            f"Applying preset {wind_properties.preset} on "
            f"objects {[obj.name for obj in animated_objects]}"
        )
        fps = get_scene_fps(context.scene.render.fps, context.scene.render.fps_base)

        for obj in animated_objects:
            old_frame_interval = change_preset(
                obj, wind_properties.preset, wind_properties.strength)
            set_animation_frame_range(obj, fps, old_frame_interval)

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationApplyPreset)


@polib.log_helpers_bpy.logged_operator
class AnimationApplyLoop(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_apply_loop"
    bl_label = "Apply Loop"
    bl_description = "Applies looping interval on animated objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        loop_value = wind_properties.looping

        target_objects = AnimationOperatorBase.get_target_objects(context)
        animated_objects = list(get_animated_objects(target_objects))
        logger.info(
            f"Applying looping interval {wind_properties.looping} on "
            f"objects {[obj.name for obj in animated_objects]}"
        )

        fps = get_scene_fps(context.scene.render.fps, context.scene.render.fps_base)
        for obj in animated_objects:
            set_animation_frame_range(obj, fps, loop_value)

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationApplyLoop)


@polib.log_helpers_bpy.logged_operator
class AnimationSetAnimStyle(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_set_anim_style"
    bl_label = "Set Animation Style"
    bl_description = "Switches animation style to loop or procedural"
    bl_options = {'REGISTER', 'UNDO'}

    style: bpy.props.EnumProperty(
        name="Style",
        description="Choose the desired animation style",
        items=[
            (
                preferences.botaniq_preferences.WindStyle.PROCEDURAL.name,
                preferences.botaniq_preferences.WindStyle.PROCEDURAL.value,
                "Procedural botaniq animation"
            ),
            (
                preferences.botaniq_preferences.WindStyle.LOOP.name,
                preferences.botaniq_preferences.WindStyle.LOOP.value,
                "Looping botaniq animation"
            ),
        ],
        default=preferences.botaniq_preferences.WindStyle.PROCEDURAL.name,
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop_tabs_enum(self, "style")
        super().draw(context)

    def execute(self, context: bpy.types.Context):
        if self.style == preferences.botaniq_preferences.WindStyle.PROCEDURAL.name:
            style_enum = preferences.botaniq_preferences.WindStyle.PROCEDURAL
        elif self.style == preferences.botaniq_preferences.WindStyle.LOOP.name:
            style_enum = preferences.botaniq_preferences.WindStyle.LOOP
        else:
            raise ValueError(f"Unknown operation '{self.style}', expected LOOP or PROCEDURAL!")

        target_objects = AnimationOperatorBase.get_target_objects(context)
        animated_objects = list(get_animated_objects(target_objects))
        logger.info(f"Working with objects {[obj.name for obj in animated_objects]}")
        for obj in animated_objects:
            helper_objs = get_animated_objects_hierarchy(obj, load_helper_object_names())
            change_anim_style(obj, helper_objs, style_enum)

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationSetAnimStyle)


@polib.log_helpers_bpy.logged_operator
class AnimationSetFrames(bpy.types.Operator):
    bl_idname = "engon.botaniq_set_scene_frames"
    bl_label = "Set Frames"
    bl_description = "Sets scene frames according to looping parameter"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        loop_value = wind_properties.looping

        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = loop_value

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationSetFrames)


@polib.log_helpers_bpy.logged_operator
class AnimationRandomizeOffset(AnimationOperatorBase):
    bl_idname = "engon.botaniq_animation_randomize_offset"
    bl_label = "Randomize Animation Offset"
    bl_description = "Randomizes offset of animations on selected botaniq assets"
    bl_options = {'REGISTER', 'UNDO'}

    def randomize_animation_offset(obj: bpy.types.Object) -> None:
        anim_obj: bpy.types.Object = get_instanced_mesh_object(obj)
        assert anim_obj.animation_data.action is not None
        current_frame_range = get_frame_range(anim_obj.animation_data.action)
        if current_frame_range is None:
            return

        frame_interval = current_frame_range[1] - current_frame_range[0]
        # get random offset from interval [-x, x], so in average keyframe values are not exploding
        # to big values when this operator is called multiple times
        random_offset = random.randint(-round(frame_interval / 2), round(frame_interval / 2))

        anim_obj_hierarchy = polib.asset_pack_bpy.get_entire_object_hierarchy(anim_obj)
        for obj in anim_obj_hierarchy:
            if obj.animation_data is None or obj.animation_data.action is None:
                continue

            for fcurve in obj.animation_data.action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.handle_left.x += random_offset
                    keyframe.co.x += random_offset
                    keyframe.handle_right.x += random_offset

                for modifier in fcurve.modifiers:
                    if modifier.type == 'NOISE':
                        modifier.offset += random_offset

    def execute(self, context: bpy.types.Context):
        target_objects = AnimationOperatorBase.get_target_objects(context)
        animated_objects = list(get_animated_objects(target_objects))
        logger.info(f"Working with objects {[obj.name for obj in animated_objects]}")
        for obj in animated_objects:
            AnimationRandomizeOffset.randomize_animation_offset(obj)

        return {'FINISHED'}


MODULE_CLASSES.append(AnimationRandomizeOffset)


def get_animation_instances_collection(context: bpy.types.Context) -> bpy.types.Collection:
    bq_collection = polib.asset_pack_bpy.collection_get(context, asset_helpers.BQ_COLLECTION_NAME)
    return polib.asset_pack_bpy.collection_get(context, ANIMATION_INSTANCES_COLLECTION, bq_collection)


@polib.log_helpers_bpy.logged_operator
class AnimationMakeInstanced(bpy.types.Operator):
    bl_idname = "engon.botaniq_animation_make_instanced"
    bl_label = "Make Instanced"
    bl_description = "Wraps active object into instance collection. Use this to create an " \
        "instanced object that can be duplicated multiple times in the scene to increase the " \
        "performance at the cost of customizability. Instanced collection is excluded from " \
        "view layer. This doesn't make the mesh linked!"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != 'OBJECT':
            return False

        if context.active_object is None:
            return False

        return is_animated(context.active_object) and context.active_object.type == 'MESH'

    @classmethod
    def wrap_to_instance_collection(
        cls,
        context: bpy.types.Context,
        obj: bpy.types.Object
    ) -> typing.Tuple[bpy.types.Collection, bpy.types.Object]:
        """Creates new collection containing 'obj' hierarchy and instances it on the
        previous location of 'obj'.
        """
        # Location has to be reset to origin so the instanced object lies at world origin too,
        # so all the objects are not offset by their transform and transform of the instance.
        prev_collection_users = list(obj.users_collection)
        prev_location = list(obj.location)
        obj.location = (0, 0, 0)

        instances_collection = get_animation_instances_collection(context)
        new_instance_coll: bpy.types.Collection = polib.asset_pack_bpy.collection_get(
            context, f"{ANIMATED_INSTANCE_PREFIX}{obj.name}", parent=instances_collection)
        polib.asset_pack_bpy.collection_link_hierarchy(new_instance_coll, obj)

        layer_collections = polib.asset_pack_bpy.get_hierarchy(
            context.view_layer.layer_collection)
        layer_collection = None
        for layer in layer_collections:
            if layer.collection is new_instance_coll:
                layer_collection = layer
                break

        if layer_collection is not None:
            layer_collection.exclude = True
        else:
            logger.error(
                f"View layer collection not found for {new_instance_coll}, "
                "excluding from viewport not possible"
            )

        bpy.ops.object.collection_instance_add(collection=new_instance_coll.name)
        instance_obj = context.active_object
        instance_obj.location = prev_location

        # Operator 'collection_instance_add' adds the new object into active collection
        # we need to remove the object from it first and link it to the collections
        # the original editable object was using before
        active_coll = instance_obj.users_collection[0]
        active_coll.objects.unlink(instance_obj)
        for coll in prev_collection_users:
            coll.objects.link(instance_obj)

        return new_instance_coll, instance_obj

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        logger.info(f"Working with object {active_object.name}")
        AnimationMakeInstanced.wrap_to_instance_collection(context, active_object)
        return {'FINISHED'}


MODULE_CLASSES.append(AnimationMakeInstanced)


@polib.log_helpers_bpy.logged_operator
class AnimationMakeInstanceUnique(bpy.types.Operator):
    bl_idname = "engon.botaniq_animation_make_instance_unique"
    bl_label = "Make Instance Unique"
    bl_description = "Creates new instance collection for active object with the same data." \
        "This enables having more animation variants of the same tree while the scene stays" \
        "optimized"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT' and context.active_object is not None and \
            context.active_object.instance_type == 'COLLECTION'

    @classmethod
    def duplicate_animation_instance(
        cls,
        original_collection: bpy.types.Collection
    ) -> bpy.types.Collection:
        """Makes new unique data from 'original_collection' and returns new collection containing that data
        """
        assert len(original_collection.objects) > 0

        # This code creates copy of the hierarchy of first instanced object and its animation data.
        # Copied hierarchy is unlinked from original collection. New collection is created and
        # data is linked into it. This new collection can be used for further instantiation.
        previous_object = original_collection.objects[0]
        new_object = polib.asset_pack_bpy.copy_object_hierarchy(previous_object)
        new_object.animation_data.action = new_object.animation_data.action.copy()

        new_collection = original_collection.copy()
        polib.asset_pack_bpy.collection_unlink_hierarchy(new_collection, previous_object)
        polib.asset_pack_bpy.collection_link_hierarchy(new_collection, new_object)
        return new_collection

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        instance_collection: bpy.types.Collection = active_object.instance_collection
        if instance_collection is None or len(instance_collection.objects) == 0:
            self.report({'WARNING'}, "Active object has none or invalid instance collection!")
            return {'CANCELLED'}

        # One user per instanced object + one user for scene collection link
        if instance_collection.users == 2:
            self.report({'INFO'}, "Active instance is already unique!")
            return {'CANCELLED'}

        new_collection = AnimationMakeInstanceUnique.duplicate_animation_instance(
            instance_collection)
        instances_collection = get_animation_instances_collection(context)
        instances_collection.children.link(new_collection)
        # Change the instance collection of the previous object to the new one with duplicated data
        active_object.instance_collection = new_collection

        view_layer_coll = polib.asset_pack_bpy.find_layer_collection(
            context.view_layer.layer_collection, new_collection)
        view_layer_coll.exclude = True

        logger.info(f"Turned {instance_collection.name} into {new_collection.name}")
        return {'FINISHED'}


MODULE_CLASSES.append(AnimationMakeInstanceUnique)


@polib.log_helpers_bpy.logged_operator
class AnimationBake(bpy.types.Operator):
    bl_idname = "engon.botaniq_animation_bake"
    bl_label = "Bake Animation"
    bl_description = "Bakes animation of active object to alembic format and adds data transfer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT' \
            and context.active_object is not None \
            and is_animated(context.active_object)

    def draw(self, context: bpy.types.Context):
        # TODO: calculate approx. file size
        self.layout.label(text=f"File size may be large, continue?")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def execute(self, context: bpy.types.Context):
        wind_properties = preferences.get_preferences(
            context).botaniq_preferences.wind_anim_properties
        bake_folder = wind_properties.bake_folder
        if not os.path.isdir(bake_folder):
            os.makedirs(bake_folder)
        bake_obj: bpy.types.Object = get_instanced_mesh_object(context.active_object)
        bake_filename = f"{bake_obj.name}.abc"
        bake_filepath = os.path.join(bake_folder, bake_filename)

        with context.temp_override(selected_objects=[bake_obj]):
            bpy.ops.wm.alembic_export(
                filepath=bake_filepath,
                face_sets=True,
                selected=True,
                flatten=True,
                global_scale=100
            )

        # Remove modifiers animation, because the new object is going to be using the .abc data
        AnimationRemoveWind.remove_animation(bake_obj, load_helper_object_names())
        mod = bake_obj.modifiers.new("bq_Baked", 'MESH_SEQUENCE_CACHE')
        mod.read_data = {'VERT'}

        cache_file = bpy.data.cache_files.get(bake_filename)
        # bpy.data.cache_files do not have .remove() method and simply overwriting the file that
        # is already loaded leads to crashing, so the cache file datablock needs to be removed using
        # bpy.data.batch_remove() that has been added to blender for this purpose
        # https://devtalk.blender.org/t/deleting-cache-file-datablocks-from-a-file/22559
        if cache_file is not None:
            bpy.data.batch_remove([cache_file])
        bpy.ops.cachefile.open(filepath=bake_filepath)
        cache_file = bpy.data.cache_files[bake_filename]

        assert cache_file is not None
        mod.cache_file = cache_file
        # Alembic files will change '.' to '_' in Object Path
        mod.object_path = f"/{bake_obj.name.replace('.', '_')}/{bake_obj.data.name.replace('.', '_')}"

        logger.info(f"Baked object {bake_obj.name}, results saved to '{bake_filepath}")
        return {'FINISHED'}


MODULE_CLASSES.append(AnimationBake)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
