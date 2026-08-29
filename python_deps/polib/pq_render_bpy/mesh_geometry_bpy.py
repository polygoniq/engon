# copyright (c) 2018- polygoniq xyz s.r.o.

"""Helpers for producing renderable geometry from ``bmesh`` topology."""

import bmesh
import itertools
import math
import mathutils
import typing


class CornerBasis(typing.NamedTuple):
    """Geometric basis of a face corner for describing a corner arc.

    All vectors are in the local (object) space of the bmesh the corner came from. `dir_a`
    and `dir_b` together with `origin` define the plane the arc lives in. The sweep direction
    matches walking `face.loops` from the loop's next loop toward its previous loop.
    """

    # Corner vertex position in object space (i.e. `loop.vert.co`).
    origin: mathutils.Vector
    # Unit direction from `origin` along `loop.edge` toward `loop.link_loop_next.vert`.
    dir_a: mathutils.Vector
    # Unit direction from `origin` along `loop.link_loop_prev.edge` toward
    # `loop.link_loop_prev.vert`.
    dir_b: mathutils.Vector
    # Arc radius
    radius: float
    # Unit normal of the plane the arc sweeps in. Used to disambiguate the slerp
    # rotation axis when adjacent arc directions are (anti-)parallel; for non-degenerate
    # pairs the implicit cross product determines the axis and this field is ignored.
    # `loop.face.normal` is the natural choice — it's perpendicular to all directions
    # that live in the face plane (`dir_a`, `dir_b`, and the split directions).
    plane_normal: mathutils.Vector
    # Unit directions from `origin` toward face vertices connected to the corner vertex
    # by an internal tessellation edge. Ordered from `dir_a` toward `dir_b`.
    split_directions: tuple[mathutils.Vector, ...]


def compute_corner_basis(
    loop: bmesh.types.BMLoop,
    radius_fraction: float,
    max_size: float,
    split_verts: list[bmesh.types.BMVert] | None = None,
) -> CornerBasis | None:
    """Compute geometric basis for a loop's corner arc.

    Args:
        loop: Corner whose basis is being computed. The corner vertex is `loop.vert`;
            the two bounding edges are `loop.edge` and `loop.link_loop_prev.edge`.
        radius_fraction: Fraction of the shorter adjacent edge to use as the arc radius
            before clamping by `max_size`.
        max_size: Hard upper bound on the arc radius in object-space units.
        split_verts: Face vertices connected to `loop.vert` by an internal tessellation
            edge, ordered from `dir_a` toward `dir_b` (as produced by
            `bmesh_utils_bpy.get_corner_split_verts`). When `None` or empty, no split
            directions are collected and the arc will be a single slerp from `dir_a`
            to `dir_b`.
    """
    vert_co = loop.vert.co
    edge_a_other = loop.edge.other_vert(loop.vert).co
    edge_b_other = loop.link_loop_prev.edge.other_vert(loop.vert).co

    vec_a = edge_a_other - vert_co
    vec_b = edge_b_other - vert_co
    len_a = vec_a.length
    len_b = vec_b.length
    if len_a < 1e-9 or len_b < 1e-9:
        # Degenerate corner: one of the edges is too short to define a direction
        return None

    dir_a = vec_a / len_a
    dir_b = vec_b / len_b
    radius = min(radius_fraction * min(len_a, len_b), max_size)

    split_directions: list[mathutils.Vector] = []
    if split_verts is not None:
        for w in split_verts:
            diag = w.co - vert_co
            if diag.length_squared > 1e-18:
                # Only add split directions that are not degenerate (i.e. the split vertex is not at the corner vertex)
                split_directions.append(diag.normalized())

    return CornerBasis(vert_co, dir_a, dir_b, radius, loop.face.normal, tuple(split_directions))


def slerp_arc(
    dir_start: mathutils.Vector,
    dir_end: mathutils.Vector,
    origin: mathutils.Vector,
    radius: float,
    segments: int,
    fallback_axis: mathutils.Vector | None = None,
) -> list[mathutils.Vector]:
    """Sample `segments+1` points on a circular arc anchored at `origin`.

    The arc starts at `origin + dir_start * radius`, ends at `origin + dir_end * radius`,
    and stays at the same radius from `origin` throughout. `dir_start` and `dir_end` must
    be unit vectors.

    When `dir_start` and `dir_end` are (nearly) anti-parallel the rotation plane is
    ambiguous; `fallback_axis` picks the great-circle plane.
    Without `fallback_axis`, an arbitrary perpendicular is chosen.
    """
    dot = max(-1.0, min(1.0, dir_start.dot(dir_end)))
    cross = dir_start.cross(dir_end)
    if cross.length_squared < 1e-12:
        # Parallel or anti-parallel: cross product can't define the rotation axis.
        if dot > 0.0:
            # `dir_start` and `dir_end` point in the same direction
            return [origin + dir_start * radius for _ in range(segments + 1)]
        rot_axis = (
            fallback_axis.normalized()
            if fallback_axis is not None
            else dir_start.orthogonal().normalized()
        )
    else:
        rot_axis = cross.normalized()

    angle = math.acos(dot)
    q_start = mathutils.Quaternion()
    q_end = mathutils.Quaternion(rot_axis, angle)
    points: list[mathutils.Vector] = []
    for i in range(segments + 1):
        t = i / segments
        d = q_start.slerp(q_end, t) @ dir_start
        points.append(origin + d * radius)
    return points


def compute_corner_arc_points(basis: CornerBasis, segments: int) -> list[mathutils.Vector]:
    """Build an object-space polyline approximating the corner highlight arc.

    The arc is composed of `len(split_directions) + 1` slerp pieces joined at the split
    directions, so every piece lies in a single rendered triangle. With no split
    directions this collapses to a single slerp from `dir_a` to `dir_b`.
    The final count of `segments` might be slightly higher than requested so the segments
    are nicely distributed among the pieces.
    """
    directions = (basis.dir_a, *basis.split_directions, basis.dir_b)
    n_pieces = len(directions) - 1
    if n_pieces == 1:
        # Single piece: just slerp from `dir_a` to `dir_b`.
        return slerp_arc(
            basis.dir_a,
            basis.dir_b,
            basis.origin,
            basis.radius,
            segments,
            basis.plane_normal,
        )

    # Distribute segments proportionally to each piece's arc angle so wider pieces get
    # more samples. Each piece gets at least 1 segment; the total may differ from
    # `segments` by a few due to rounding, which is fine for a visual approximation.
    angles = [
        math.acos(max(-1.0, min(1.0, directions[i].dot(directions[i + 1]))))
        for i in range(n_pieces)
    ]
    total_angle = sum(angles) or 1.0
    counts = [max(1, round(segments * a / total_angle)) for a in angles]

    points: list[mathutils.Vector] = []
    for i in range(n_pieces):
        piece = slerp_arc(
            directions[i],
            directions[i + 1],
            basis.origin,
            basis.radius,
            counts[i],
            basis.plane_normal,
        )
        # Previous piece ended where this one starts; skip the duplicate joining point
        points.extend(piece if i == 0 else itertools.islice(piece, 1, None))
    return points
