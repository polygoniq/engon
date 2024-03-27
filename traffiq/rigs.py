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

# This module was inspired by the awesome rigacar addon which we also used
# to rig our cars. Thanks!
# Check http://digicreatures.net/articles/rigacar.html


import bpy
import bpy_extras.anim_utils
import math
import typing
import itertools
import mathutils
import collections
import logging
import polib
from .. import preferences
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


class GroundSensorsManipulator:
    def __init__(self, pose: bpy.types.Pose):
        self.ground_sensors = self.__find_ground_sensors(pose)
        self.ground_sensors_constraints: typing.Dict[str, bpy.types.Constraint] = \
            self.__get_ground_sensors_constraints(self.ground_sensors)

    def __find_ground_sensors(self, pose: bpy.types.Pose) -> typing.Set[bpy.types.PoseBone]:
        ground_sensors = set()
        for bone in pose.bones:
            if bone.name.startswith("GroundSensor_"):
                ground_sensors.add(bone)

        return ground_sensors

    def __get_ground_sensors_constraints(
        self,
        ground_sensors: typing.Set[bpy.types.PoseBone]
    ) -> typing.Dict[str, typing.Optional[bpy.types.ShrinkwrapConstraint]]:
        ground_sensor_constraints: typing.Dict[str,
                                               bpy.types.Constraint] = collections.defaultdict(None)
        for ground_sensor in ground_sensors:
            for constraint in ground_sensor.constraints:
                if constraint.type != 'SHRINKWRAP':
                    continue

                ground_sensor_constraints[ground_sensor.name] = constraint
                break

        return ground_sensor_constraints

    def set_ground_object(self, obj: bpy.types.Object) -> None:
        assert obj is not None
        for shrinkwrap_constraint in self.ground_sensors_constraints.values():
            shrinkwrap_constraint.target = obj

    def set_projection_mode(self, mode: str) -> None:
        assert mode in {'NEAREST_SURFACE', 'PROJECT', 'NEAREST_VERTEX', 'TARGET_PROJECT'}
        for shrinkwrap_constraint in self.ground_sensors_constraints.values():
            shrinkwrap_constraint.shrinkwrap_type = mode

    def remove_ground_object(self) -> None:
        for shrinkwrap_constraint in self.ground_sensors_constraints.values():
            shrinkwrap_constraint.target = None


def bone_name(prefix: str, position: str, side: str, index: int) -> str:
    return f"{prefix}_{position}{side}_{index}"


def bone_name_range(bones, name_prefix: str, position: str, side: str):
    for index in itertools.count():
        name = bone_name(name_prefix, position, side, index)
        if name in bones:
            yield bones[name]
        else:
            break


def clear_object_animation_property(obj: bpy.types.Object, property_name: str):
    """Removes fcurve based on data path constructed from property name and
    resets the corresponding custom property
    """

    if obj.animation_data and obj.animation_data.action:
        fcurve_datapath = f'["{property_name}"]'
        action = obj.animation_data.action
        fcurve = action.fcurves.find(fcurve_datapath)
        if fcurve is not None:
            action.fcurves.remove(fcurve)
    obj[property_name] = 0.0


def create_fcurve(action: bpy.types.Action, property_name: str) -> bpy.types.FCurve:
    """Creates fcurve in 'action' with property_name wrapped as data path
    """

    return action.fcurves.new(f'["{property_name}"]', index=0, action_group="tq_WheelRotation")


def check_rig_drivers(obj: bpy.types.Object) -> bool:
    if obj.animation_data is None:
        return False

    # Checking whether all the drivers are the correct one
    # is complicated, because only way to infer that is to
    # build the datapaths of the fcurves. Instead of this
    # we use this simpler approach which checks the minimal
    # expected set of drivers (Steering, 4 wheels, 2 Axis)
    return len(obj.animation_data.drivers) >= 7


class FCurvesEvaluator:
    """Encapsulates a bunch of FCurves for vector animations"""

    def __init__(self, fcurves: typing.Iterable[bpy.types.FCurve], default_value: typing.Any):
        self.default_value = default_value
        self.fcurves = fcurves

    def evaluate(self, frame: float) -> typing.List[float]:
        result = []
        for fcurve, value in zip(self.fcurves, self.default_value):
            if fcurve is not None:
                result.append(fcurve.evaluate(frame))
            else:
                result.append(value)
        return result


class VectorFCurvesEvaluator:
    def __init__(self, fcurves_evaluator: FCurvesEvaluator):
        self.fcurves_evaluator = fcurves_evaluator

    def evaluate(self, frame: float) -> typing.List[float]:
        return mathutils.Vector(self.fcurves_evaluator.evaluate(frame))


class EulerToQuaternionFCurvesEvaluator:
    def __init__(self, fcurves_evaluator: FCurvesEvaluator):
        self.fcurves_evaluator = fcurves_evaluator

    def evaluate(self, frame: float) -> typing.List[float]:
        return mathutils.Euler(self.fcurves_evaluator.evaluate(frame)).to_quaternion()


class QuaternionFCurvesEvaluator:
    def __init__(self, fcurves_evaluator: FCurvesEvaluator):
        self.fcurves_evaluator = fcurves_evaluator

    def evaluate(self, frame: float) -> typing.List[float]:
        return mathutils.Quaternion(self.fcurves_evaluator.evaluate(frame))


class BakingOperatorBase:
    frame_start: bpy.props.IntProperty(name="Start Frame", min=1, default=1)
    frame_end: bpy.props.IntProperty(name="End Frame", min=1, default=250)
    keyframe_tolerance: bpy.props.FloatProperty(name="Keyframe tolerance", min=0, default=.01)

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return polib.rigs_shared_bpy.is_object_rigged(context.object) and \
            context.object.mode in {'POSE', 'OBJECT'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if context.object.animation_data is None:
            context.object.animation_data_create()
            assert context.object.animation_data is not None
        if context.object.animation_data.action is None:
            context.object.animation_data.action = bpy.data.actions.new(
                f"{context.object.name}_Action")

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        self.layout.prop(self, "frame_start")
        self.layout.prop(self, "frame_end")
        self.layout.prop(self, "keyframe_tolerance")

    def _create_euler_evaluator(self, action: bpy.types.Action, source_bone: bpy.types.Bone):
        fcurve_name = f'pose.bones["{source_bone.name}"].rotation_euler'
        fc_root_rot = [action.fcurves.find(fcurve_name, index=i) for i in range(3)]
        return EulerToQuaternionFCurvesEvaluator(FCurvesEvaluator(fc_root_rot, default_value=(0.0, 0.0, 0.0)))

    def _create_quaternion_evaluator(self, action: bpy.types.Action, source_bone: bpy.types.Bone):
        fcurve_name = f'pose.bones["{source_bone.name}"].rotation_quaternion'
        fc_root_rot = [action.fcurves.find(fcurve_name, index=i) for i in range(4)]
        return QuaternionFCurvesEvaluator(
            FCurvesEvaluator(fc_root_rot, default_value=(1.0, 0.0, 0.0, 0.0))
        )

    def _create_location_evaluator(self, action: bpy.types.Action, source_bone: bpy.types.Bone):
        fcurve_name = f'pose.bones["{source_bone.name}"].location'
        fc_root_loc = [action.fcurves.find(fcurve_name, index=i) for i in range(3)]
        return VectorFCurvesEvaluator(
            FCurvesEvaluator(fc_root_loc, default_value=(0.0, 0.0, 0.0))
        )

    def _create_scale_evaluator(self, action: bpy.types.Action, source_bone: bpy.types.Bone):
        fcurve_name = f'pose.bones["{source_bone.name}"].scale'
        fc_root_loc = [action.fcurves.find(fcurve_name, index=i) for i in range(3)]
        return VectorFCurvesEvaluator(
            FCurvesEvaluator(fc_root_loc, default_value=(1.0, 1.0, 1.0))
        )

    def _bake_action(self, context: bpy.types.Context, source_bones: typing.Iterable[bpy.types.Bone]):
        action = context.object.animation_data.action
        nla_tweak_mode = getattr(context.object, "use_tweak_mode", False)

        # Save context
        selected_bones = [b for b in context.object.data.bones if b.select]
        mode = context.object.mode
        for bone in selected_bones:
            bone.select = False

        bpy.ops.object.mode_set(mode='OBJECT')
        source_bones_matrix_basis = []
        for source_bone in source_bones:
            source_bones_matrix_basis.append(
                context.object.pose.bones[source_bone.name].matrix_basis.copy())
            source_bone.select = True

        baked_action = bpy_extras.anim_utils.bake_action(
            context.object,
            action=None,
            frames=range(self.frame_start, self.frame_end + 1),
            only_selected=True,
            do_pose=True,
            do_object=False,
            do_visual_keying=True,
        )

        # Restore context
        for source_bone, matrix_basis in zip(source_bones, source_bones_matrix_basis):
            context.object.pose.bones[source_bone.name].matrix_basis = matrix_basis
            source_bone.select = False

        for bone in selected_bones:
            bone.select = True

        bpy.ops.object.mode_set(mode=mode)

        if nla_tweak_mode:
            context.object.animation_data.use_tweak_mode = nla_tweak_mode
        else:
            context.object.animation_data.action = action

        return baked_action


@polib.log_helpers_bpy.logged_operator
class BakeWheelRotation(bpy.types.Operator, BakingOperatorBase):
    bl_idname = "engon.traffiq_rig_bake_wheels_rotation"
    bl_label = "Bake Wheels Rotation"
    bl_description = "Automatically generates wheels animation based on Root bone animation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        logger.info(f"Working on target object: {context.object.name}")
        context.object[polib.rigs_shared_bpy.TraffiqRigProperties.WHEELS_Y_ROLLING] = False
        if not check_rig_drivers(context.object):
            self.report({'ERROR'}, f"Corrupted animation drivers in '{context.object.name}'")
            return {'CANCELLED'}

        self._bake_wheels_rotation(context)
        return {'FINISHED'}

    def _bake_wheels_rotation(self, context: bpy.types.Context):
        bones = context.object.data.bones

        wheel_bones = []
        brake_bones = []
        for side, position in itertools.product(("L", "R"), ("F", "B")):
            for index, wheel_bone in enumerate(bone_name_range(bones, "MCH_WheelRotation", position, side)):
                wheel_bones.append(wheel_bone)
                brake_bones.append(bones.get(bone_name("Brake", position, side, index), wheel_bone))

        for property_name in map(lambda wheel_bone: wheel_bone.name.replace("MCH_", "tq_"), wheel_bones):
            clear_object_animation_property(context.object, property_name)

        bones = set(wheel_bones + brake_bones)
        baked_action = self._bake_action(context, bones)
        if baked_action is None:
            self.report({'WARNING'}, "Existing action failed to bake. Won't bake wheel rotation")
            return

        try:
            for wheel_bone, brake_bone in zip(wheel_bones, brake_bones):
                self._bake_wheel_rotation(context, baked_action, wheel_bone, brake_bone)
        finally:
            bpy.data.actions.remove(baked_action)

    def _evaluate_distance_per_frame(
        self,
        action: bpy.types.Action,
        bone: bpy.types.Bone,
        brake_bone: bpy.types.Bone
    ) -> typing.Generator[typing.Tuple[int, float], None, None]:
        loc_evaluator = self._create_location_evaluator(action, bone)
        rot_evaluator = self._create_euler_evaluator(action, bone)
        brake_evaluator = self._create_scale_evaluator(action, brake_bone)

        radius = bone.length if bone.length > 0.0 else 1.0
        bone_init_vector = (bone.head_local - bone.tail_local).normalized()
        prev_pos = loc_evaluator.evaluate(self.frame_start)
        prev_speed = 0.0
        distance = 0.0
        yield self.frame_start, distance
        for frame in range(self.frame_start + 1, self.frame_end):
            pos = loc_evaluator.evaluate(frame)
            speed_vector = pos - prev_pos
            speed_vector *= 2 * brake_evaluator.evaluate(frame).y - 1
            rotation_quaternion = rot_evaluator.evaluate(frame)
            bone_orientation = rotation_quaternion @ bone_init_vector
            speed = math.copysign(speed_vector.magnitude, bone_orientation.dot(speed_vector))
            speed /= radius
            drop_keyframe = False
            if speed == 0.0:
                drop_keyframe = prev_speed == speed
            elif prev_speed != 0.0:
                drop_keyframe = abs(1 - prev_speed / speed) < self.keyframe_tolerance / 10
            if not drop_keyframe:
                prev_speed = speed
                yield frame - 1, distance
            distance += speed
            prev_pos = pos
        yield self.frame_end, distance

    def _bake_wheel_rotation(
        self,
        context: bpy.types.Context,
        baked_action: bpy.types.Action,
        bone: bpy.types.Bone,
        brake_bone: bpy.types.Bone
    ) -> None:
        fc_rot = create_fcurve(
            context.object.animation_data.action,
            bone.name.replace("MCH_", "tq_")
        )

        # Reset the transform of the wheel bone, otherwise baking yields wrong results
        pb: bpy.types.PoseBone = context.object.pose.bones[bone.name]
        pb.matrix_basis.identity()

        for f, distance in self._evaluate_distance_per_frame(baked_action, bone, brake_bone):
            kf = fc_rot.keyframe_points.insert(f, distance)
            kf.interpolation = 'LINEAR'
            kf.type = 'JITTER'


MODULE_CLASSES.append(BakeWheelRotation)


@polib.log_helpers_bpy.logged_operator
class BakeSteering(bpy.types.Operator, BakingOperatorBase):
    bl_idname = "engon.traffiq_rig_bake_steering"
    bl_label = "Bake Car Steering"
    bl_description = "Automatically generates steering animation based on Root bone animation"
    bl_options = {'REGISTER', 'UNDO'}

    rotation_factor: bpy.props.FloatProperty(name="Rotation factor", min=0.1, default=1)

    def draw(self, context: bpy.types.Context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        self.layout.prop(self, "frame_start")
        self.layout.prop(self, "frame_end")
        self.layout.prop(self, "rotation_factor")
        self.layout.prop(self, "keyframe_tolerance")

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        if not check_rig_drivers(active_object):
            self.report({'ERROR'}, f"Corrupted animation drivers in '{active_object.name}'")
            return {'CANCELLED'}

        if self.frame_end > self.frame_start:
            if "Steering" in active_object.data.bones and \
               "MCH_SteeringRotation" in active_object.data.bones:
                steering = active_object.data.bones["Steering"]
                mch_steering_rotation = active_object.data.bones["MCH_SteeringRotation"]
                bone_offset = abs(steering.head_local.y - mch_steering_rotation.head_local.y)
                self._bake_steering_rotation(context, bone_offset, mch_steering_rotation)
                logger.info(f"Steering baked on target object {context.object.name}")

        return {'FINISHED'}

    def _evaluate_rotation_per_frame(
        self,
        action: bpy.types.Action,
        bone_offset: float,
        bone: bpy.types.Bone
    ) -> typing.Generator[typing.Tuple[int, float], None, None]:
        loc_evaluator = self._create_location_evaluator(action, bone)
        rot_evaluator = self._create_quaternion_evaluator(action, bone)

        distance_threshold = pow(bone_offset * max(self.keyframe_tolerance, 0.001), 2)
        steering_threshold = bone_offset * self.keyframe_tolerance * 0.1
        bone_direction_vector = (bone.head_local - bone.tail_local).normalized()
        bone_normal_vector = mathutils.Vector((1, 0, 0))

        current_pos = loc_evaluator.evaluate(self.frame_start)
        previous_steering_position = None
        for frame in range(self.frame_start, self.frame_end - 1):
            next_pos = loc_evaluator.evaluate(frame + 1)
            steering_direction_vector = next_pos - current_pos

            if steering_direction_vector.length_squared < distance_threshold:
                continue

            rotation_quaternion = rot_evaluator.evaluate(frame)
            world_space_bone_direction_vector = rotation_quaternion @ bone_direction_vector
            world_space_bone_normal_vector = rotation_quaternion @ bone_normal_vector

            projected_steering_direction = steering_direction_vector.dot(
                world_space_bone_direction_vector)
            if projected_steering_direction == 0:
                continue

            length_ratio = bone_offset * self.rotation_factor / projected_steering_direction
            steering_direction_vector *= length_ratio

            steering_position = mathutils.geometry.distance_point_to_plane(
                steering_direction_vector, world_space_bone_direction_vector, world_space_bone_normal_vector)

            if previous_steering_position is not None \
               and abs(steering_position - previous_steering_position) < steering_threshold:
                continue

            yield frame, steering_position
            current_pos = next_pos
            previous_steering_position = steering_position

    def _bake_steering_rotation(
        self,
        context: bpy.types.Context,
        bone_offset: float,
        bone: bpy.types.Bone
    ) -> None:
        clear_object_animation_property(
            context.object, polib.rigs_shared_bpy.TraffiqRigProperties.STEERING)
        fc_rot = create_fcurve(
            context.object.animation_data.action,
            polib.rigs_shared_bpy.TraffiqRigProperties.STEERING
        )
        baked_action = self._bake_action(context, [bone])
        if baked_action is None:
            self.report({'WARNING'}, "Existing action failed to bake. Won't bake steering rotation")
            return

        try:
            # Reset the transform of the steering bone, because baking action manipulates the transform
            # and evaluate_rotation_frame expects it at it's default position
            pb: bpy.types.PoseBone = context.object.pose.bones[bone.name]
            pb.matrix_basis.identity()

            for f, steering_pos in self._evaluate_rotation_per_frame(baked_action, bone_offset, bone):
                kf = fc_rot.keyframe_points.insert(f, steering_pos)
                kf.type = 'JITTER'
                kf.interpolation = 'LINEAR'
        finally:
            bpy.data.actions.remove(baked_action)


MODULE_CLASSES.append(BakeSteering)


@polib.log_helpers_bpy.logged_operator
class SetGroundSensors(bpy.types.Operator):
    bl_idname = "engon.traffiq_rig_set_ground_sensors"
    bl_label = "Set All Ground Sensors"
    bl_description = "Sets Ground Object as ground for all ground sensors"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode in {'OBJECT', 'POSE'} and \
            polib.rigs_shared_bpy.is_object_rigged(context.active_object)

    def execute(self, context: bpy.types.Context):
        if context.scene.tq_ground_object is None:
            self.report({'INFO'}, "No ground object selected!")
            return {'CANCELLED'}

        sensors_manipulator = GroundSensorsManipulator(context.active_object.pose)
        sensors_manipulator.set_ground_object(context.scene.tq_ground_object)

        logger.info(
            f"Set ground sensors, ground_object: {context.scene.tq_ground_object.name}, "
            f"active object: {context.active_object.name}"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(SetGroundSensors)


@polib.log_helpers_bpy.logged_operator
class FollowPath(bpy.types.Operator):
    bl_idname = "engon.traffiq_rig_follow_path"
    bl_label = "Follow Path"
    bl_description = "Creates a follow path animation on active object. " \
        "Animation is based on Ground and Path properties"

    bl_options = {'REGISTER', 'UNDO'}

    CONSTRAINT_NAME = "tq_follow_path"

    @staticmethod
    def get_offset_data_path(root_bone_name: str, fp_constraint_name: str) -> str:
        # Data path has to have double string quotes inside to work correctly
        return f'pose.bones["{root_bone_name}"].constraints["{fp_constraint_name}"].offset_factor'

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT' and \
            polib.rigs_shared_bpy.is_object_rigged(context.active_object)

    def draw(self, context: bpy.types.Context):
        rig_properties = preferences.prefs_utils.get_preferences(
            context).traffiq_preferences.rig_properties
        layout = self.layout
        layout.prop(rig_properties, "auto_bake_steering", text="Bake Steering")
        layout.prop(rig_properties, "auto_bake_wheels", text="Bake Wheel Rotation")
        layout.prop(rig_properties, "auto_reset_transforms", text="Reset Transforms")
        col = layout.column(align=True)
        col.alert = True
        if rig_properties.auto_reset_transforms:
            col.label(text="Warning: Asset transforms will be reset!")
        else:
            col.label(text="Make sure assets have valid transforms!")
            col = layout.column(align=True)
            col.label(text="Car's location acts like an offset. (0, 0, 0) = On Path.")
            col.label(text="Curve needs applied scale, otherwise it deforms the car.")
            col.label(text="Ground needs applied scale for the ground sensors.")
            col.label(text="For more info check Follow Path Constraint Blender docs.")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context):
        rig_properties = preferences.prefs_utils.get_preferences(
            context).traffiq_preferences.rig_properties
        target_path = context.scene.tq_target_path_object
        if target_path is None:
            self.report({'ERROR'}, "No target path selected!")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='POSE')
        active_object = context.view_layer.objects.active
        if not check_rig_drivers(active_object):
            self.report({'ERROR'}, f"Corrupted animation drivers in '{active_object.name}'")
            return {'CANCELLED'}

        root_bone: bpy.types.PoseBone = active_object.pose.bones.get("Root", None)
        if root_bone is None:
            self.report({'ERROR'}, f"Could not find root bone in {active_object.name}")
            return {'CANCELLED'}

        follow_path_constraint = self.setup_follow_path_constraint(
            root_bone,
            target_path
        )

        ground_object = context.scene.tq_ground_object
        if rig_properties.auto_reset_transforms:
            self.reset_transforms(active_object, target_path, ground_object)

        offset_factor_data_path = FollowPath.get_offset_data_path(
            root_bone.name,
            follow_path_constraint.name
        )

        follow_path_constraint.offset_factor = 1.0
        active_object.keyframe_insert(offset_factor_data_path, frame=context.scene.frame_start)

        follow_path_constraint.offset_factor = 0.0
        active_object.keyframe_insert(offset_factor_data_path, frame=context.scene.frame_end)

        sensors_manipulator = GroundSensorsManipulator(active_object.pose)
        if ground_object is not None:
            sensors_manipulator.set_ground_object(ground_object)
            sensors_manipulator.set_projection_mode('PROJECT')

        if rig_properties.auto_bake_wheels:
            bpy.ops.engon.traffiq_rig_bake_wheels_rotation('INVOKE_DEFAULT')

        if rig_properties.auto_bake_steering:
            bpy.ops.engon.traffiq_rig_bake_steering('INVOKE_DEFAULT')

        bpy.ops.object.mode_set(mode='OBJECT')

        logger.info(
            f"Follow path set for active_object {context.active_object.name}, "
            f"ground_object: {'N/A' if ground_object is None else ground_object.name}, "
            f"auto_bake_steering: {rig_properties.auto_bake_steering}, "
            f"auto_bake_wheels: {rig_properties.auto_bake_wheels}"
        )
        return {'FINISHED'}

    def setup_follow_path_constraint(
        self,
        root_bone: bpy.types.PoseBone,
        target_obj: bpy.types.Object
    ) -> bpy.types.FollowPathConstraint:
        follow_path_constraint: typing.Optional[bpy.types.FollowPathConstraint] = \
            root_bone.constraints.get(FollowPath.CONSTRAINT_NAME, None)
        if follow_path_constraint is None:
            follow_path_constraint = root_bone.constraints.new(type='FOLLOW_PATH')
            assert follow_path_constraint is not None
            follow_path_constraint.name = FollowPath.CONSTRAINT_NAME

        follow_path_constraint.target = target_obj
        follow_path_constraint.use_fixed_location = True
        follow_path_constraint.use_curve_follow = True
        return follow_path_constraint

    def reset_transforms(
        self,
        owner: bpy.types.Object,
        path: bpy.types.Object,
        ground: typing.Optional[bpy.types.Object] = None,
    ) -> None:
        # prepare objects used in follow path constraints according to
        # https://docs.blender.org/manual/en/latest/animation/constraints/relationship/follow_path.html
        owner.location = (0.0, 0.0, 0.0)
        owner.rotation_euler = (0.0, 0.0, 0.0)
        path.scale = (1.0, 1.0, 1.0)

        # ground has to have uniform scale for ground sensors to work correctly
        if ground is not None:
            ground.scale = (1.0, 1.0, 1.0)


MODULE_CLASSES.append(FollowPath)


@polib.log_helpers_bpy.logged_operator
class ChangeFollowPathSpeed(bpy.types.Operator):
    bl_idname = "engon.traffiq_rig_change_speed"
    bl_label = "Change Speed"
    bl_description = "Recalculates the follow path keyframes based on desired speed"
    bl_options = {'REGISTER', 'UNDO'}

    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        min=0
    )

    target_speed: bpy.props.FloatProperty(
        name="Target Speed",
        default=10.0,
        min=0.1
    )

    unit: bpy.props.EnumProperty(
        name="Unit",
        items=[
            ('KMH', "km/h", "Kilometers per hour"),
            ('MPH', "mph", "Miles per hour"),
            ('MPS', "m/s", "Meters per second")
        ]
    )

    reverse: bpy.props.BoolProperty(
        name="Reverse",
        description="Make the car go backwards",
        default=False,
    )

    rebake: bpy.props.BoolProperty(
        name="Rebake",
        description="Open wheel and steering rotation bake operators after changing speed",
        default=True
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return polib.rigs_shared_bpy.is_object_rigged(context.active_object)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        active_object: bpy.types.Object = context.active_object
        self.root_bone: bpy.types.PoseBone = active_object.pose.bones.get("Root", None)
        if self.root_bone is None:
            self.report({'ERROR'}, "No root bone found")
            return {'CANCELLED'}

        self.fp_constraint: bpy.types.FollowPathConstraint = self.root_bone.constraints.get(
            FollowPath.CONSTRAINT_NAME)
        if self.fp_constraint is None:
            self.report({'ERROR'}, f"Follow path constraint not found on '{active_object.name}'")
            return {'CANCELLED'}

        curve = self.fp_constraint.target
        if curve is None:
            self.report({'ERROR'}, f"'{active_object.name}' doesn't have target curve!")
            return {'CANCELLED'}

        scene = context.scene
        self.fps = scene.render.fps / scene.render.fps_base
        # Only first spline is used for the follow path constraint
        self.spline_len = curve.data.splines[0].calc_length()
        self.start_frame = context.scene.frame_start
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "start_frame")
        row = layout.row(align=True)
        row.prop(self, "target_speed")
        sub_row = row.row(align=True)
        sub_row.alignment = 'RIGHT'
        sub_row.prop(self, "unit", text="")

        layout.prop(self, "reverse")
        animation_frames = ChangeFollowPathSpeed.get_animation_frames(
            self.spline_len, self.target_speed_ms, self.fps)
        row = layout.row()
        row.label(text=f"Frames: {round(animation_frames)}")
        row.label(text=f"Duration: {animation_frames / self.fps:.2f}s")
        row.label(text=f"End Frame: {round(self.start_frame + animation_frames)}")

        layout.prop(self, "rebake")

    @staticmethod
    def get_animation_frames(spline_length: float, target_velocity: float, fps: float) -> float:
        return (spline_length / target_velocity) * fps

    def execute(self, context: bpy.types.Context):
        if not hasattr(self, "spline_len"):
            self.report(
                {'ERROR'}, "This operator requires 'invoke' to be called before 'execute'!")
            return {'CANCELLED'}

        active_object: bpy.types.Object = context.active_object
        logger.info(f"Working on active object {active_object.name}")
        required_frames = ChangeFollowPathSpeed.get_animation_frames(
            self.spline_len, self.target_speed_ms, self.fps)
        end_frame = self.start_frame + required_frames

        self.fp_constraint.forward_axis = 'TRACK_NEGATIVE_Y' if self.reverse else 'FORWARD_Y'
        self.fp_constraint.offset_factor = 0.0
        offset_factor_data_path = FollowPath.get_offset_data_path(
            self.root_bone.name, self.fp_constraint.name)

        fcurve = active_object.animation_data.action.fcurves.find(offset_factor_data_path)
        if fcurve is not None and len(fcurve.keyframe_points) == 2:
            kf = fcurve.keyframe_points[-1]
            kf.co = (end_frame, 0.0)

            kf = fcurve.keyframe_points[0]
            kf.co = (self.start_frame, 1.0)
            fcurve.update()

        start_frame_int = round(self.start_frame)
        end_frame_int = round(end_frame)
        if self.rebake:
            bpy.ops.engon.traffiq_rig_bake_wheels_rotation(
                'INVOKE_DEFAULT', frame_start=start_frame_int, frame_end=end_frame_int)

            bpy.ops.engon.traffiq_rig_bake_steering(
                'INVOKE_DEFAULT', frame_start=start_frame_int, frame_end=end_frame_int)

        return {'FINISHED'}

    @property
    def target_speed_ms(self) -> float:
        if self.unit == 'KMH':
            return self.target_speed / 3.6
        elif self.unit == 'MPS':
            return self.target_speed
        elif self.unit == 'MPH':
            return self.target_speed * 0.44704
        else:
            raise ValueError(f"Unknown speed unit '{self.unit}'")


MODULE_CLASSES.append(ChangeFollowPathSpeed)


@polib.log_helpers_bpy.logged_operator
class RemoveAnimation(bpy.types.Operator):
    bl_idname = "engon.traffiq_rig_remove_animation"
    bl_label = "Remove Animation"
    bl_description = "Removes all traffiq animation from active object"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode in {'OBJECT', 'POSE'} and \
            polib.rigs_shared_bpy.is_object_rigged(context.active_object)

    def remove_follow_path_keyframes(self, obj: bpy.types.Object) -> None:
        """Tries to remove root motion related fcurve from 'obj'"""
        if obj.animation_data is None or obj.animation_data.action is None:
            return

        root_bone = obj.pose.bones.get("Root", None)
        fp_constraint = root_bone.constraints.get(FollowPath.CONSTRAINT_NAME, None)
        if root_bone is None or fp_constraint is None:
            return

        offset_factor_data_path = FollowPath.get_offset_data_path(
            root_bone.name,
            fp_constraint.name
        )

        action = obj.animation_data.action
        fcurve = action.fcurves.find(offset_factor_data_path)
        if fcurve is not None:
            action.fcurves.remove(fcurve)

    def remove_constraints(self, obj: bpy.types.Object) -> None:
        """Removes ground and follow path constraints created with `FollowPath` operator.

        Follow path constraint holds `obj` on (or with relative offset to) the path, ground
        constraints adjust object position vertically, so it sticks to the ground. With these
        constraints it's not possible to freely move the `obj`.

        This shouldn't move `obj`.
        """
        # Remove constraints to ground object
        sensors_manipulator = GroundSensorsManipulator(obj.pose)
        sensors_manipulator.remove_ground_object()

        # Move and rotate object according to the bones which are driven by FollowPathConstraint.
        # Root bone doesn't contain translation according to the ground sensor.
        # Not really sure why specifically DEF_Body bone is the correct one or if it's the only one.
        body_bone: bpy.types.PoseBone = obj.pose.bones.get("DEF_Body", None)
        if body_bone is not None:
            obj.matrix_world = obj.matrix_world @ body_bone.matrix

        # Remove follow path constraint
        root_bone = obj.pose.bones.get("Root", None)
        if root_bone is None:
            return
        follow_path_constraint = root_bone.constraints.get(FollowPath.CONSTRAINT_NAME, None)
        if follow_path_constraint is not None:
            root_bone.constraints.remove(follow_path_constraint)

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        logger.info(f"Working on active object {active_object.name}")
        for prop in active_object.keys():
            if not polib.rigs_shared_bpy.TraffiqRigProperties.is_rig_property(prop):
                continue

            clear_object_animation_property(active_object, prop)

        self.remove_follow_path_keyframes(active_object)
        self.remove_constraints(active_object)

        return {'FINISHED'}


MODULE_CLASSES.append(RemoveAnimation)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.tq_target_path_object = bpy.props.PointerProperty(
        name="Follow Path Target",
        description="Path which rigged car should follow",
        poll=lambda self, obj: obj.type == 'CURVE',
        type=bpy.types.Object,
    )

    bpy.types.Scene.tq_ground_object = bpy.props.PointerProperty(
        name="Ground Object",
        description="Object representing the ground to be used in animation of rigged car",
        type=bpy.types.Object,
    )


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.tq_ground_object
    del bpy.types.Scene.tq_target_path_object
