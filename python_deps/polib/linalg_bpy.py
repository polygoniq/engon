#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
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
