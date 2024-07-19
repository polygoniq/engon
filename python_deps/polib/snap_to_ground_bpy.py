#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import mathutils
import typing
import math
import copy
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


if "linalg_bpy" not in locals():
    from . import linalg_bpy
    from . import utils_bpy
else:
    import importlib

    linalg_bpy = importlib.reload(linalg_bpy)
    utils_bpy = importlib.reload(utils_bpy)


def find_bounding_wheels(wheels: typing.List[bpy.types.Object]) -> typing.List[bpy.types.Object]:
    # we take first front wheels and then find maximum index of rear wheels and return it as a list
    assert len(wheels) > 4

    frontmost_wheels = []
    rearmost_wheels = {}
    for wheel_obj in wheels:
        _, position, wheel_number = utils_bpy.remove_object_duplicate_suffix(wheel_obj.name).split(
            "_"
        )[-3:]
        if position.endswith("F"):
            if int(wheel_number) == 0:
                frontmost_wheels.append(wheel_obj)
        else:
            if position not in rearmost_wheels:
                rearmost_wheels[position] = (wheel_obj, wheel_number)
            else:
                if wheel_number > rearmost_wheels[position][1]:
                    rearmost_wheels[position] = (wheel_obj, wheel_number)
    rearmost_wheels_list = [v[0] for v in rearmost_wheels.values()]
    return frontmost_wheels + rearmost_wheels_list


def get_wheel_contact_points(
    wheels: typing.List[bpy.types.Object], instance: bpy.types.Object, debug: bool = False
) -> typing.List[mathutils.Vector]:
    wheel_contact_points = []
    one_track_vehicle = True if len(wheels) == 2 else False

    # when vehicle has more than 4 wheels take only the outer ones
    if len(wheels) > 4:
        wheels = find_bounding_wheels(wheels)

    for wheel_obj in wheels:
        wheel_center = wheel_obj.location
        radius = wheel_obj.dimensions.y / 2
        contact_point = wheel_center - mathutils.Vector((0, 0, radius))

        contact_point_world_space = instance.matrix_world @ contact_point
        wheel_contact_points.append(contact_point_world_space)

        # hack-fix for one track vehicles, just pretend it has another 2
        # wheels nearby so we can raycast the plane
        if one_track_vehicle:
            fixture_contact_point_ws = (
                instance.matrix_world @ mathutils.Matrix.Translation((0.1, 0, 0)) @ contact_point
            )
            wheel_contact_points.append(fixture_contact_point_ws)

        if debug:
            bpy.ops.object.empty_add(location=contact_point_world_space)
            obj = bpy.context.object
            obj.name = "B: " + wheel_obj.name
            obj.show_name = True

    return wheel_contact_points


GetRayCastedPlaneCallable = typing.Callable[
    [], typing.Tuple[typing.List[mathutils.Vector], typing.Optional[typing.List[mathutils.Vector]]]
]


def snap_to_ground_iterate(
    instance: bpy.types.Object,
    obj: bpy.types.Object,
    instance_old_matrix_world: mathutils.Matrix,
    get_ray_casted_plane: GetRayCastedPlaneCallable,
    debug: bool = False,
) -> None:
    """Snap to ground iteratively, we first estimate final rotation until angular delta
    is lower than our tolerance. Only then we can get an accurate raycast position delta.
    """
    ANGULAR_DELTA_TOLERANCE = math.radians(1)
    MAXIMUM_ITERATIONS = 10

    iteration = 1
    while True:
        bottom_corners, altered_bottom_corners = get_ray_casted_plane()
        if altered_bottom_corners is None:
            if debug:
                logger.debug(
                    f"Failed to raycast all corners while estimating rotation "
                    f"for {obj.name}, instance={instance.name}. Skipping..."
                )
            instance.matrix_world = instance_old_matrix_world
            return

        orig_plane_normal, _, orig_plane_centroid = linalg_bpy.fit_plane_to_points(bottom_corners)
        altered_plane_normal, _, altered_plane_centroid = linalg_bpy.fit_plane_to_points(
            altered_bottom_corners
        )
        if debug:
            orig_plane_rotation = mathutils.Vector([0, 0, 1]).rotation_difference(orig_plane_normal)
            altered_plane_rotation = mathutils.Vector([0, 0, 1]).rotation_difference(
                altered_plane_normal
            )
            bpy.ops.mesh.primitive_plane_add(
                location=orig_plane_centroid, rotation=orig_plane_rotation.to_euler(), size=3
            )
            bpy.ops.mesh.primitive_plane_add(
                location=altered_plane_centroid, rotation=altered_plane_rotation.to_euler(), size=3
            )

        delta_rotation = mathutils.Vector(orig_plane_normal).rotation_difference(
            altered_plane_normal
        )

        # Since matrix_world is composed as location @ rotation @ scale, we need to decompose it
        # into separate matrices, multiply only rotation and then compose it back.
        # See https://blender.stackexchange.com/a/44783
        # We could also use e.g. instance.rotation_quaternion but we would need to call
        # bpy.context.view_layer.update() after each change to update matrix_world, which is slower.
        orig_loc, orig_rot, orig_scale = instance.matrix_world.decompose()
        orig_loc_mat = mathutils.Matrix.Translation(orig_loc)
        orig_rot_mat = orig_rot.to_matrix().to_4x4()
        delta_rot_mat = delta_rotation.to_matrix().to_4x4()
        orig_scale_mat = mathutils.Matrix.Diagonal(orig_scale).to_4x4()
        # assemble the new matrix
        instance.matrix_world = orig_loc_mat @ delta_rot_mat @ orig_rot_mat @ orig_scale_mat

        if debug:
            logger.debug(f"iteration: {iteration}, angular error: {delta_rotation.angle}")
        if abs(delta_rotation.angle) < ANGULAR_DELTA_TOLERANCE:
            break
        iteration += 1
        if iteration > MAXIMUM_ITERATIONS:
            break

    bottom_corners, altered_bottom_corners = get_ray_casted_plane()
    if altered_bottom_corners is None:
        if debug:
            logger.debug(
                f"Failed to raycast all corners while estimating position "
                f"for {obj.name}, instance={instance.name}. Skipping..."
            )
        instance.matrix_world = instance_old_matrix_world
        return

    orig_plane_normal, _, orig_plane_centroid = linalg_bpy.fit_plane_to_points(bottom_corners)
    altered_plane_normal, _, altered_plane_centroid = linalg_bpy.fit_plane_to_points(
        altered_bottom_corners
    )
    delta_location = altered_plane_centroid - orig_plane_centroid
    instance.matrix_world = mathutils.Matrix.Translation(delta_location) @ instance.matrix_world


def ray_cast_plane(
    ground_objects: typing.Iterable[bpy.types.Object],
    bottom_corners: typing.List[mathutils.Vector],
    grace_padding: float = 0.1,
    debug: bool = False,
) -> typing.Tuple[typing.List[mathutils.Vector], typing.Optional[typing.List[mathutils.Vector]]]:
    """Raycast from 'bottom_corners' points downwards to 'ground_objects'.
    Return 'bottom_corners' and list of intersection points closest to each bottom_corner point.
    """
    altered_bottom_corners = copy.deepcopy(bottom_corners)
    altered_bottom_distances = [math.inf for _ in bottom_corners]
    for ground_object in ground_objects:
        for i, bottom_corner in enumerate(bottom_corners):
            if debug:
                logger.debug("Raycast from: " + str(bottom_corner))
            bottom_corner_obj_space = ground_object.matrix_world.inverted() @ (
                bottom_corner + mathutils.Vector([0, 0, grace_padding])
            )
            bottom_corner2_obj_space = ground_object.matrix_world.inverted() @ (
                bottom_corner + mathutils.Vector([0, 0, grace_padding - 1])
            )
            direction_obj_space = bottom_corner2_obj_space - bottom_corner_obj_space
            try:
                result, new_bottom_corner_obj_space, _, _ = ground_object.ray_cast(
                    bottom_corner_obj_space, direction_obj_space
                )
            except:
                logger.exception("Uncaught exception while raycasting to the ground")
                result = None
                new_bottom_corner_obj_space = bottom_corner_obj_space

            if not result:
                continue
            new_bottom_corner = ground_object.matrix_world @ new_bottom_corner_obj_space
            distance = (bottom_corners[i] - new_bottom_corner).length
            if distance < altered_bottom_distances[i]:
                altered_bottom_corners[i] = new_bottom_corner
                if debug:
                    bpy.ops.object.empty_add(type="SINGLE_ARROW", location=new_bottom_corner)
                altered_bottom_distances[i] = distance

    if math.inf in altered_bottom_distances:
        return bottom_corners, None
    else:
        return bottom_corners, altered_bottom_corners


def snap_to_ground_separate_wheels(
    instance: bpy.types.Object,
    obj: bpy.types.Object,
    wheels: typing.List[bpy.types.Object],
    ground_objects: typing.List[bpy.types.Object],
    debug: bool = False,
) -> None:
    instance_old_matrix_world = copy.deepcopy(instance.matrix_world)

    def get_ray_casted_plane() -> (
        typing.Tuple[typing.List[mathutils.Vector], typing.Optional[typing.List[mathutils.Vector]]]
    ):
        bottom_corners = get_wheel_contact_points(wheels, instance, debug)
        return ray_cast_plane(ground_objects, bottom_corners)

    snap_to_ground_iterate(instance, obj, instance_old_matrix_world, get_ray_casted_plane, debug)


def snap_to_ground_adjust_rotation(
    instance: bpy.types.Object,
    obj: bpy.types.Object,
    ground_objects: typing.List[bpy.types.Object],
    debug: bool = False,
) -> None:
    instance_old_matrix_world = copy.deepcopy(instance.matrix_world)

    def get_ray_casted_plane():
        # get bounding box corners in world space
        bbox_corners = [
            instance.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box
        ]
        # I hope Blender never changes this, it's quite difficult to autodetect
        bottom_corners = [bbox_corners[0], bbox_corners[3], bbox_corners[4], bbox_corners[7]]
        return ray_cast_plane(ground_objects, bottom_corners)

    snap_to_ground_iterate(instance, obj, instance_old_matrix_world, get_ray_casted_plane, debug)


def snap_to_ground_no_rotation(
    instance: bpy.types.Object,
    obj: bpy.types.Object,
    ground_objects: typing.List[bpy.types.Object],
    debug: bool = False,
) -> None:
    def get_ray_casted_point(
        grace_padding: float = 0.1,
    ) -> typing.Tuple[mathutils.Vector, mathutils.Vector]:
        if obj.data is None:
            # obj is not 'MESH', it can be 'EMPTY' for example, don't do anything with it
            return None, None
        # get lowest point in world space
        obj_lowest_vertex = min(obj.data.vertices, key=lambda v: (instance.matrix_world @ v.co).z)
        obj_lowest_point = instance.matrix_world @ obj_lowest_vertex.co
        altered_highest_point = None
        altered_highest_point_distance = math.inf

        for ground_object in ground_objects:
            if debug:
                logger.debug("Raycast from: " + str(obj_lowest_point))
            lowest_point_obj_space = ground_object.matrix_world.inverted() @ (
                obj_lowest_point + mathutils.Vector([0, 0, grace_padding])
            )
            lowest_point2_obj_space = ground_object.matrix_world.inverted() @ (
                obj_lowest_point + mathutils.Vector([0, 0, grace_padding - 1])
            )
            direction_obj_space = lowest_point2_obj_space - lowest_point_obj_space
            try:
                result, altered_point_obj_space, _, _ = ground_object.ray_cast(
                    lowest_point_obj_space, direction_obj_space
                )
            except Exception as e:
                logger.exception("Uncaught exception while raycasting to the ground")
                result = None
                altered_point_obj_space = lowest_point_obj_space

            if not result:
                continue
            altered_point = ground_object.matrix_world @ altered_point_obj_space
            distance = (obj_lowest_point - altered_point).length
            if distance < altered_highest_point_distance:
                altered_highest_point = altered_point
                if debug:
                    bpy.ops.object.empty_add(location=altered_point)
                altered_highest_point_distance = distance

        if math.isinf(altered_highest_point_distance):
            return obj_lowest_point, None
        else:
            return obj_lowest_point, altered_highest_point

    obj_lowest_point, altered_highest_point = get_ray_casted_point()
    if altered_highest_point is None:
        if debug:
            logger.debug(
                f"Failed to raycast the highest altered point while estimating position "
                f"for {obj.name}, instance={instance.name}. Skipping..."
            )
        return

    delta_location = altered_highest_point - obj_lowest_point
    instance.matrix_world = mathutils.Matrix.Translation(delta_location) @ instance.matrix_world
