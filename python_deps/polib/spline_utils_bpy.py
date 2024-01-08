# copyright (c) 2018- polygoniq xyz s.r.o.
# Module containing various utilities and wrappers around bpy to ease work with bpy bezier splines

import bpy
import mathutils
import typing


def copy_bezier_point(src: bpy.types.BezierSplinePoint, dst: bpy.types.BezierSplinePoint) -> None:
    dst.co = src.co
    dst.handle_left = src.handle_left
    dst.handle_left_type = src.handle_left_type
    dst.handle_right = src.handle_right
    dst.handle_right_type = src.handle_right_type
    dst.tilt = src.tilt
    dst.radius = src.radius


def add_bezier_point_to_spline(
    spline: bpy.types.Spline,
    position: mathutils.Vector,
    prepend: bool = False,
    handle_type: str = 'VECTOR'
) -> bpy.types.BezierSplinePoint:
    assert spline.type == 'BEZIER'
    spline.bezier_points.add(1)
    new_point = spline.bezier_points[-1]
    if prepend:
        # It is not possible to prepend points, thus we move the data of the other points...
        # We could also extrude, but that would introduce bpy.ops overhead here.
        for i in range(len(spline.bezier_points) - 1, 0, -1):
            copy_bezier_point(spline.bezier_points[i - 1], spline.bezier_points[i])

        new_point = spline.bezier_points[0]

    new_point.co = position
    new_point.handle_left_type = handle_type
    new_point.handle_right_type = handle_type
    return new_point


def remove_bezier_point(
    curve_obj: bpy.types.Object,
    spline: bpy.types.Spline,
    remove_idx: int
) -> None:
    """Removes bezier point from a spline by changing selection and calling bpy.ops.curve.delete"""
    bpy.context.view_layer.objects.active = curve_obj
    bpy.ops.curve.select_all(action='DESELECT')
    for i, bezier_point in enumerate(spline.bezier_points):
        bezier_point.select_control_point = i == remove_idx

    if 'FINISHED' not in bpy.ops.curve.delete(type='VERT'):
        raise RuntimeError(f"Failed to remove bezier point from '{repr(spline)}' on {remove_idx}")


def join_splines(
    curve: bpy.types.Curve,
    spline1: bpy.types.Spline,
    spline2: bpy.types.Spline,
    reverse: bool = False,
    prepend: bool = False,
) -> bpy.types.Spline:
    """Joins splines 'spline1' and 'spline2' into a new spline in 'curve', new spline is returned."""
    points = reversed(spline2.bezier_points) if reverse else spline2.bezier_points
    l1 = len(spline1.bezier_points)
    l2 = len(spline2.bezier_points)
    new_spline = curve.splines.new(type='BEZIER')
    new_spline.bezier_points.add(l1 + l2 - 2)
    dst_start_idx = 0 if prepend else l1 - 1
    if prepend:
        # Copy the original point after the prepended point, so it is not lost
        for i, point in reversed(list(enumerate(spline1.bezier_points[:l1]))):
            copy_bezier_point(point, new_spline.bezier_points[l2 - 1 + i])
    else:
        # Copy the original values before the appended ones
        for i, point in enumerate(spline1.bezier_points):
            copy_bezier_point(point, new_spline.bezier_points[i])

    for i, bezier_point in enumerate(points):
        copy_bezier_point(bezier_point, new_spline.bezier_points[dst_start_idx + i])

    return new_spline


def split_spline(
    curve: bpy.types.Curve,
    spline: bpy.types.Spline,
    split_idx: int
) -> typing.Tuple[bpy.types.Spline, bpy.types.Spline]:
    """Splits bezier spline 'spline' into two splines inside 'curve' on 'split_idx'

    Point on 'split_idx' will become present on both splines. Original spline has to be removed
    by caller.
    """
    left = curve.splines.new(type='BEZIER')
    right = curve.splines.new(type='BEZIER')
    left.bezier_points.add(split_idx)
    right.bezier_points.add(len(spline.bezier_points) - split_idx - 1)

    for i in range(len(spline.bezier_points)):
        if i < split_idx:
            copy_bezier_point(spline.bezier_points[i], left.bezier_points[i])
        elif i == split_idx:
            copy_bezier_point(spline.bezier_points[i], left.bezier_points[i])
            copy_bezier_point(spline.bezier_points[i], right.bezier_points[i - split_idx])
        else:
            copy_bezier_point(spline.bezier_points[i], right.bezier_points[i - split_idx])

    return left, right


def new_bezier_spline(
    curve_obj: bpy.types.Object,
    position: mathutils.Vector,
    handle_type: str
) -> typing.Tuple[bpy.types.Spline, bpy.types.BezierSplinePoint]:
    """Creates new spline on 'curve_obj', returns new spline and its first bezier point

    Arguments 'position' and 'handle_type' apply to the 0th created point that's in each
    new created spline in Blender.
    """
    spline = curve_obj.splines.new(type='BEZIER')
    bezier_point = spline.bezier_points[0]
    bezier_point.co = position
    bezier_point.handle_left_type = handle_type
    bezier_point.handle_right_type = handle_type
    return spline, bezier_point
