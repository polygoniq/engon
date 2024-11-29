#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import bpy_extras
import collections
import math
import mathutils
import numpy
import unittest
import typing


def plane_from_points(points):
    assert len(points) == 3
    p1, p2, p3 = points

    v1 = p3 - p1
    v2 = p2 - p1

    normal = numpy.cross(v1, v2)
    normal_magnitude = numpy.linalg.norm(normal)
    normal /= normal_magnitude
    offset = numpy.dot(normal, p3)
    centroid = numpy.sum(points, 0) / len(points)

    return (normal, offset, centroid)


def fit_plane_to_points(points):
    assert len(points) >= 3
    return plane_from_points(points[:3])

    # TODO: This is borked :-(
    centroid = numpy.sum(points, 0) / len(points)
    centered_points = points - centroid
    svd = numpy.linalg.svd(numpy.transpose(centered_points))
    plane_normal = svd[0][2]
    # now that we have the normal let's fit the centroid to the plane to find the offset
    offset = numpy.dot(plane_normal, centroid)
    return (plane_normal, offset, centroid)


def is_obj_flat(obj: bpy.types.Object) -> bool:
    return any(math.isclose(d, 0.0) for d in obj.dimensions)


def mean_position(vs: typing.Iterable[mathutils.Vector]) -> mathutils.Vector:
    sum_v = mathutils.Vector()
    n = 0
    for v in vs:
        n += 1
        sum_v += v

    return sum_v / n


RaycastHit = collections.namedtuple("RaycastHit", ["object", "position", "normal"])


def raycast_screen_to_world(
    context: bpy.types.Context,
    screen_position: typing.Tuple[int, int],
    excluded_objects_names: typing.Optional[typing.Set[str]] = None,
    raycast_collection: typing.Optional[bpy.types.Collection] = None,
    skip_particle_instances: bool = True,
) -> typing.Optional[RaycastHit]:
    """Get the 3D position of the mouse cursor in the scene based on 'context' and 'screen_position'.

    Use 'excluded_objects_names' to provide a set of object names to exclude from the raycast
    (e. g. self, or self instances).

    Use 'raycast_collection' to define collection of objects to raycast against. If None,
    all objects are raycast. Useful when working with large scenes and you want to raycast only
    against a subset of objects.

    'skip_particle_instances' is a flag that determines whether instances coming from a particle
    systems are skipped for performance gain.
    """
    # This code was taken from operator_modal_view3d_raycast.py Blender python template and adjusted
    # to our use case.

    if excluded_objects_names is None:
        excluded_objects_names = set()

    # get the context arguments
    region = context.region
    region_3d = context.region_data

    # get the ray from the viewport and mouse
    view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, region_3d, screen_position)
    ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, region_3d, screen_position)

    ray_target = ray_origin + view_vector

    def get_visible_objects_and_instances() -> (
        typing.Iterable[typing.Tuple[bpy.types.Object, mathutils.Matrix]]
    ):
        """Get (Object, Matrix) pairs of all the objects and instanced objects in the scene"""
        depsgraph = context.evaluated_depsgraph_get()
        for dup in depsgraph.object_instances:
            if dup.is_instance:  # Real dupli instance
                if dup.is_instance and dup.particle_system is not None and skip_particle_instances:
                    continue

                obj = dup.instance_object
                matrix = dup.matrix_world.copy()
                # If there is instanced object and both its instancer and the object it instances
                # are in excluded_object_names, exclude it.
                if (
                    dup.instance_object.name in excluded_objects_names
                    and dup.parent is not None
                    and dup.parent.name in excluded_objects_names
                ):
                    continue

                # If the instancer isn't in the raycast collection we consider it not visible.
                # The instanced object doesn't have to be in it, it can live only in bpy.data.
                if (
                    raycast_collection is not None
                    and dup.parent is not None
                    and dup.parent.name not in raycast_collection.all_objects
                ):
                    continue

            else:  # Usual object
                obj = dup.object
                matrix = obj.matrix_world.copy()
                if obj.name in excluded_objects_names:
                    continue

                # If the object isn't in the raycast collection, we don't consider it visible.
                if (
                    raycast_collection is not None
                    and obj.name not in raycast_collection.all_objects
                ):
                    continue

            yield (obj, matrix)

    def obj_ray_cast(
        obj: bpy.types.Object, matrix: mathutils.Matrix
    ) -> typing.Tuple[typing.Optional[mathutils.Vector], typing.Optional[mathutils.Vector]]:
        """Raycasts a ray in object's local space, returns result in world space."""

        # get the ray relative to the object
        matrix_inv = matrix.inverted()
        ray_origin_obj = matrix_inv @ ray_origin
        ray_target_obj = matrix_inv @ ray_target
        ray_direction_obj = ray_target_obj - ray_origin_obj

        # cast the ray
        success, location, normal, _ = obj.ray_cast(ray_origin_obj, ray_direction_obj)

        if success:
            # Move the normal to world space
            _, rotation, _ = matrix.decompose()
            normal: mathutils.Vector = normal.normalized()
            normal.rotate(rotation)
            return location, normal
        else:
            return None, None

    # cast rays and find the closest object that was hit
    best_length_squared = math.inf
    best_hit_obj = None
    best_hit_world = None
    best_normal = None

    for obj, matrix in get_visible_objects_and_instances():
        if obj.type not in {'MESH', 'CURVE'}:
            continue

        hit, normal = obj_ray_cast(obj, matrix)
        if hit is not None:
            hit_world = matrix @ hit
            length_squared = (hit_world - ray_origin).length_squared
            if length_squared < best_length_squared:
                best_length_squared = length_squared
                best_hit_world = hit_world
                best_normal = normal
                best_hit_obj = obj

    if best_hit_obj is None:
        return None

    return RaycastHit(best_hit_obj, best_hit_world, best_normal)


class PlaneFittingTest(unittest.TestCase):
    def test_3pts(self):
        # unit plane - (0, 0, 1), 0
        normal, offset, _ = fit_plane_to_points([(1, -1, 0), (-1, 0, 0), (0, 1, 0)])
        self.assertAlmostEqual(normal[0], 0)
        self.assertAlmostEqual(normal[1], 0)
        self.assertAlmostEqual(normal[2], 1)
        self.assertAlmostEqual(offset, 0)

        normal, offset, _ = fit_plane_to_points([(2, -2, 0), (-1, 0, 0), (0, 1, 0)])
        self.assertAlmostEqual(normal[0], 0)
        self.assertAlmostEqual(normal[1], 0)
        self.assertAlmostEqual(normal[2], 1)
        self.assertAlmostEqual(offset, 0)

        # offset unit plane - (0, 0, 1), 1
        normal, offset, _ = fit_plane_to_points([(2, -2, 1), (-1, 0, 1), (0, 1, 1)])
        self.assertAlmostEqual(normal[0], 0)
        self.assertAlmostEqual(normal[1], 0)
        self.assertAlmostEqual(normal[2], 1)
        self.assertAlmostEqual(offset, 1)

    def test_4pts(self):
        # unit plane - (0, 0, 1), 0
        normal, offset, _ = fit_plane_to_points([(1, -1, 0), (-1, 0, 0), (0, 1, 0), (1, 1, 0)])
        self.assertAlmostEqual(normal[0], 0)
        self.assertAlmostEqual(normal[1], 0)
        self.assertAlmostEqual(normal[2], 1)
        self.assertAlmostEqual(offset, 0)

        # can't fit precisely! unit plane - (0, 0, 1), 0
        large = 100000000000
        normal, offset, _ = fit_plane_to_points(
            [
                (-large, -large, 0.1),
                (-large, large, -0.1),
                (large, -large, 0.1),
                (large, large, -0.1),
            ]
        )
        self.assertAlmostEqual(normal[0], 0)
        self.assertAlmostEqual(normal[1], 0)
        self.assertAlmostEqual(normal[2], 1)
        self.assertAlmostEqual(offset, 0)


if __name__ == "__main__":
    unittest.main()
