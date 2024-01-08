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

# Module containing features used to track state of scene objects representing a network of roads

import bpy
import mathutils
import typing
import dataclasses
import logging
from . import road_type
logger = logging.getLogger(f"polygoniq.{__name__}")


@dataclasses.dataclass(frozen=True, eq=True)
class RoadSegment:
    """Road segment is the smallest part of road network - part of road connected to other parts
    only using its endpoints.

    Road segment is subset of 'curve_object.data.splines' - one concrete spline that can have
    arbitrary amount of points.
    """
    curve_object: bpy.types.Object
    spline: bpy.types.Spline
    type_: road_type.RoadType

    def is_corrupted(self) -> bool:
        try:
            self.spline.path_from_id()
        except ReferenceError:
            return True
        return False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False

        return self.spline == other.spline

    def __hash__(self) -> int:
        return hash(self.spline)

    def __repr__(self) -> str:
        try:
            return f"{self.curve_object.name}.{self.spline.path_from_id()}; {self.type_.name}"
        except ReferenceError:
            return "Segment: INVALID: Reference Error"


class SegmentAdjacency:
    """Represents adjacency of stored segment endpoint to a crossroad"""

    def __init__(
        self,
        segment: RoadSegment,
        point_idx: int = 0,
        first_point: typing.Optional[bool] = None
    ):
        self.segment = segment
        if first_point is not None:
            self.is_first_point = first_point
        else:
            bezier_points_last_idx = len(segment.spline.bezier_points) - 1
            assert point_idx == 0 or point_idx == bezier_points_last_idx, \
                "Only first or last point can be adjacent to crossroad!"
            self.is_first_point = point_idx == 0

    @property
    def adjacent_point(self) -> bpy.types.BezierSplinePoint:
        return self.segment.spline.bezier_points[0 if self.is_first_point else - 1]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False

        return self.segment == other.segment and self.is_first_point == other.is_first_point

    def __hash__(self):
        return hash((self.segment, self.is_first_point))

    def __repr__(self):
        try:
            return f"{self.segment.curve_object.name}.{self.segment.spline.path_from_id()};{self.is_first_point}"
        except ReferenceError:
            return "Segment Adjacency: INVALID: Reference Error"


@dataclasses.dataclass
class Crossroad:
    """Crossroad represents connection of >= 2 road segments.

    Road segments can be of different road_type - have different curve_object. Adjacency
    is stored in 'SegmentAdjacency' for each road segment endpoint connected to the crossroad.

    Crossroad.obj is a Blender object that has specific modifier stack that creates geometry
    between different RoadSegments. This object has to have position always set to (0, 0, 0).
    """
    id_: int
    collection: bpy.types.Collection
    obj: bpy.types.Object
    adjacencies: typing.Set[SegmentAdjacency]
    position: mathutils.Vector
    radius: float = dataclasses.field(init=False)

    def __post_init__(self):
        assert len(self.adjacencies) >= 2
        # Compute the crossroad position by computing the average position from adjacent segments
        position_sum = mathutils.Vector([0, 0, 0])
        for adj in self.adjacencies:
            position_sum += adj.adjacent_point.co

        self.radius = max(
            (self.position - adj.adjacent_point.co).length for adj in self.adjacencies)

    def __hash__(self) -> int:
        return hash(self.id_)

    def __repr__(self) -> str:
        try:
            return f"{self.id_}:{self.collection.name}, {self.position}; {self.adjacencies}"
        except ReferenceError:
            return "Crossroad: INVALID: Reference Error"


class RoadNetwork:
    """Representation of road network consisting of crossroads and segments.

    This class is useful for gathering information about current state. It doesn't handle
    manipulation of objects, geometry or node trees.
    """

    def __init__(self):
        self._crossroads: typing.Set[Crossroad] = set()
        self._segments: typing.Set[RoadSegment] = set()
        self._endpoint_cx_map: typing.Dict[SegmentAdjacency, Crossroad] = {}

    def add_segment(self, segment: RoadSegment) -> None:
        if segment not in self._segments:
            self._segments.add(segment)

    def add_crossroad(self, crossroad: Crossroad) -> None:
        for adj in crossroad.adjacencies:
            self.add_segment(adj.segment)
            self._endpoint_cx_map[adj] = crossroad

        self._crossroads.add(crossroad)

    def remove_crossroad(self, crossroad: Crossroad) -> None:
        self._crossroads.remove(crossroad)
        for adj in crossroad.adjacencies:
            if adj in self._endpoint_cx_map:
                del self._endpoint_cx_map[adj]

    def get_endpoints_connections(
        self,
        segment: RoadSegment
    ) -> typing.Tuple[typing.Optional[Crossroad], typing.Optional[Crossroad]]:
        return (
            self._endpoint_cx_map.get(SegmentAdjacency(segment, first_point=True), None),
            self._endpoint_cx_map.get(SegmentAdjacency(segment, first_point=False), None)
        )

    def remove_segment(self, segment: RoadSegment) -> None:
        self._segments.remove(segment)
        # Check if the segment was connected to any crossroad, if yes, then remove
        # the entry from point_cx_map and update the crossroad adjacency
        start_cx, end_cx = self.get_endpoints_connections(segment)
        if start_cx is not None:
            start_cx_adj = SegmentAdjacency(segment, first_point=True)
            start_cx.adjacencies.remove(start_cx_adj)
            del self._endpoint_cx_map[start_cx_adj]

        if end_cx is not None:
            end_cx_adj = SegmentAdjacency(segment, first_point=False)
            end_cx.adjacencies.remove(end_cx_adj)
            del self._endpoint_cx_map[end_cx_adj]

    def replace_segment(self, original: RoadSegment, new: RoadSegment, reverse: bool = False) -> None:
        start_cx, end_cx = self.get_endpoints_connections(original)
        logger.debug(f"Replacing segment {original} with {new}, reverse: {reverse}")
        if start_cx is not None:
            self._replace_crossroad_adjacency(
                start_cx,
                SegmentAdjacency(original, first_point=True),
                SegmentAdjacency(new, first_point=not reverse)
            )

        if end_cx is not None:
            self._replace_crossroad_adjacency(
                end_cx,
                SegmentAdjacency(original, first_point=False),
                SegmentAdjacency(new, first_point=reverse)
            )

        self.remove_segment(original)
        self.add_segment(new)

    def add_adjacency(self, cx: Crossroad, adj: SegmentAdjacency) -> None:
        cx.adjacencies.add(adj)
        self._endpoint_cx_map[adj] = cx

    def split_segment(self, original: RoadSegment, head: RoadSegment, tail: RoadSegment) -> None:
        start_cx, end_cx = self.get_endpoints_connections(original)
        logger.debug(f"Splitting segment {original} to {head} and {tail}")
        if start_cx:
            self._replace_crossroad_adjacency(
                start_cx,
                SegmentAdjacency(original, first_point=True),
                SegmentAdjacency(head, first_point=True))

        if end_cx:
            self._replace_crossroad_adjacency(
                end_cx,
                SegmentAdjacency(original, first_point=False),
                SegmentAdjacency(tail, first_point=False))

        self.remove_segment(original)
        self.add_segment(head)
        self.add_segment(tail)

    def is_crossroad_endpoint(self, segment: RoadSegment, point_idx: int) -> bool:
        # i isn't an endpoint index
        bezier_points_last_idx = len(segment.spline.bezier_points) - 1
        if point_idx > 0 and point_idx < bezier_points_last_idx:
            return False

        # Check whether point_idx in segment is start point connected to a crossroad
        if point_idx == 0 and SegmentAdjacency(segment, first_point=True) in self._endpoint_cx_map:
            return True

        # Check whether point_idx in segment is end point connected to a crossroad
        if point_idx == bezier_points_last_idx and SegmentAdjacency(segment, first_point=False) in self._endpoint_cx_map:
            return True

        return False

    def _replace_crossroad_adjacency(
        self,
        crossroad: Crossroad,
        removed_adj: SegmentAdjacency,
        new_adj: SegmentAdjacency
    ) -> None:
        crossroad.adjacencies.remove(removed_adj)
        crossroad.adjacencies.add(new_adj)

        assert removed_adj in self._endpoint_cx_map
        del self._endpoint_cx_map[removed_adj]
        self._endpoint_cx_map[new_adj] = crossroad

    @property
    def segments(self) -> typing.Iterator[RoadSegment]:
        yield from self._segments

    @property
    def crossroads(self) -> typing.Iterator[Crossroad]:
        yield from self._crossroads
