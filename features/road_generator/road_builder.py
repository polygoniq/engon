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
import abc
import typing
import math
import dataclasses
import mathutils
import logging
from ... import polib
from . import road_network
from . import road_type
from . import props
from . import crossroad_builder
from . import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


@dataclasses.dataclass
class BuildPoint(abc.ABC):
    """Abstract point where road can be built"""

    position: mathutils.Vector


@dataclasses.dataclass
class EmptyBuildPoint(BuildPoint):
    """Build point without any other data, just empty position"""


@dataclasses.dataclass
class CrossroadBuildPoint(BuildPoint):
    """Build point where there is existing crossroad"""

    position: mathutils.Vector
    crossroad: road_network.Crossroad


@dataclasses.dataclass
class RoadSegmentBuildPoint(BuildPoint):
    """Build point on a bezier point of a spline from a road segment"""

    position: mathutils.Vector = dataclasses.field(init=False)
    segment: road_network.RoadSegment
    point_idx: int
    is_any_endpoint: bool = dataclasses.field(init=False)
    is_start_endpoint: bool = dataclasses.field(init=False)

    def __post_init__(self):
        self.position = self.segment.spline.bezier_points[self.point_idx].co
        self.is_any_endpoint = (
            self.point_idx == 0 or self.point_idx == len(self.segment.spline.bezier_points) - 1
        )
        self.is_start_endpoint = self.point_idx == 0

    def get_point(self):
        return self.segment.spline.bezier_points[self.point_idx]


def move_point_towards_other_point(
    p1: mathutils.Vector, p2: mathutils.Vector, s: float
) -> mathutils.Vector:
    """Offsets 'p1' towards 'p2' by 's'"""
    dir_ = p2 - p1
    dir_.normalize()
    return p1 + dir_ * s


def get_endpoint_neighbor_idx(idx: int) -> int:
    """Returns 1 or idx - 1 if idx == 0, assumes idx is index of endpoint of spline"""
    return 1 if idx == 0 else idx - 1


@dataclasses.dataclass
class ProvisionalCrossroadInfo:
    """Information about crossroad that building has started, but is not finished yet.

    This is used when we split road segment and start creating a new crossroad, but we do not
    know where the new adjacency will be located, as the segment was not build yet.
    """

    adjacencies: list[road_network.SegmentAdjacency]
    midpoint: mathutils.Vector
    adj_point: mathutils.Vector | None


@dataclasses.dataclass
class ProvisionalSegment:
    """Segment that started building, but its final position is not decided yet"""

    curve_obj: bpy.types.Object
    spline: bpy.types.Spline
    endpoint_idx: int
    road_type: road_type.RoadType


class RoadBuilder:
    """Class that provides high level API for building road systems

    This class is responsible for combining segments, adding single segments or creating
    mergings between road types of different width. This happens by creating multiple objects
    with geometry node modifiers and passing inputs and outputs between each other to preserve
    continuity. Building is segment based, where each segment is a spline in Blender. There can
    be multiple splines inside one curve.

    Building starts and finishes with call to 'start_segment' and 'finish_segment'. If
    used in modal operator, then method 'update_provisional_endpoint' can be used to
    update the internal values before user finishes building the segment.

    Limitations:
    - Road type objects with reset location (0, 0, 0) are considered when building only
    """

    def __init__(
        self,
        main_collection: bpy.types.Collection,
        cx_builder: crossroad_builder.CrossroadBuilder,
        lib_path: str,
    ):
        self.road_network = road_network.RoadNetwork()
        self.main_collection = main_collection
        self.cx_builder = cx_builder
        self.props = props.get_rg_props()
        self.is_building = False
        self.start_build_point: BuildPoint | None = None
        # Provisional adjacencies of crossroad that is going to be build when the next segment
        # is built.
        self.provisional_cx: ProvisionalCrossroadInfo | None = None
        self.provisional_segment: ProvisionalSegment | None = None

        asset_helpers.load_geometry_nodes(lib_path, {x for x in asset_helpers.RoadNodegroup})

    def clear_collection(self):
        """Clears the main road generator collection from empty children collections"""
        bpy.data.batch_remove(c for c in self.main_collection.children if len(c.all_objects) == 0)

    def init_from_scene(
        self, scene: bpy.types.Scene, loader: road_type.RoadTypeBlendLoader
    ) -> None:
        """Initializes road network based on content of current scene"""
        for obj in scene.objects:
            if not asset_helpers.is_road_generator_obj(obj):
                continue
            if obj.type == 'CURVE' and not asset_helpers.is_crossroad_obj(obj):
                road_type_name = obj[asset_helpers.ROAD_TYPE_PROPERTY]
                type_ = loader.get_road_type_by_name(road_type_name)
                if type_ is None:
                    logger.warning(f"Unknown road type present on object: '{obj.name}'")
                    continue

                # Only consider world positions, otherwise geometry nodes for crossroads don't
                # work correctly.
                if not (
                    math.isclose(obj.location.x, 0.0, rel_tol=1e-6)
                    and math.isclose(obj.location.y, 0.0, rel_tol=1e-6)
                    and math.isclose(obj.location.z, 0.0, rel_tol=1e-6)
                ):
                    logger.warning(
                        f"Skipping road curve {obj.name}, because it is not at center location!"
                    )
                    continue
                type_.curve_obj = obj
                for spline in obj.data.splines:
                    self.road_network.add_segment(road_network.RoadSegment(obj, spline, type_))

            if obj.type == 'MESH' and asset_helpers.is_crossroad_obj(obj):
                _, id_ = obj.name.split("-")
                id_ = int(polib.utils_bpy.remove_object_duplicate_suffix(id_))
                coll = bpy.data.collections.get(obj.name)
                if coll is None:
                    continue

                searched_positions = set()
                searched_curves = set()
                for mod in obj.modifiers:
                    if mod.type != 'NODES':
                        continue
                    if mod.node_group != self.cx_builder.cx_register_ng:
                        continue

                    mod_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
                    searched_positions.add(mod_view.get_input_value("End Point 1"))
                    searched_positions.add(mod_view.get_input_value("End Point 2"))
                    searched_curves.add(mod_view.get_input_value("Road 1"))
                    searched_curves.add(mod_view.get_input_value("Road 2"))

                # TODO: This considers all points of neighbors curves based on the cx
                # modifier stack. It would be better to store the indexes to have direct access
                # to which curve, spline and point corresponds to the input even if it is useless
                # for geometry nodes.
                cx_adjacencies = []
                for curve in searched_curves:
                    type_ = loader.get_road_type_by_name(
                        curve.get(asset_helpers.ROAD_TYPE_PROPERTY)
                    )
                    if type_ is None:
                        logger.warning(f"Unknown road type present on curve: '{curve.name}'")
                        continue
                    for spline in curve.data.splines:
                        for i, bp in enumerate(spline.bezier_points):
                            for pos in searched_positions:
                                if (
                                    math.isclose(bp.co[0], pos[0], rel_tol=1e-6)
                                    and math.isclose(bp.co[1], pos[1], rel_tol=1e-6)
                                    and math.isclose(bp.co[2], pos[2], rel_tol=1e-6)
                                ):
                                    cx_adjacencies.append(
                                        road_network.SegmentAdjacency(
                                            road_network.RoadSegment(curve, spline, type_), i
                                        )
                                    )

                if len(cx_adjacencies) >= 2:
                    # If the position of crossroad is stored we reuse it. Otherwise calculate
                    # from mean position of adjacencies.
                    if asset_helpers.CROSSROAD_POSITION_PROPERTY in obj:
                        position = mathutils.Vector(obj[asset_helpers.CROSSROAD_POSITION_PROPERTY])
                    else:
                        position = polib.linalg_bpy.mean_position(
                            adj.adjacent_point.co for adj in cx_adjacencies
                        )
                    self.road_network.add_crossroad(
                        road_network.Crossroad(id_, coll, obj, set(cx_adjacencies), position)
                    )

                    crossroad_builder.CrossroadBuilder.crossroad_count = max(
                        id_, crossroad_builder.CrossroadBuilder.crossroad_count
                    )
                    crossroad_builder.CrossroadBuilder.crossroad_count += 1
                else:
                    logger.error("Not enough adjacencies found for this crossroad!")

    def start_segment(self, start_build_point: BuildPoint, type_: road_type.RoadType) -> None:
        """Start building segment on 'start_build_point' with a specific 'type_'"""
        self.start_build_point = start_build_point
        self.is_building = True

        this_curve_obj = type_.get_curve_obj(self.main_collection)
        this_curve_data: bpy.types.Curve = this_curve_obj.data
        # If start build point is empty, we change the position based on the user settings
        if isinstance(start_build_point, EmptyBuildPoint):
            start_build_point.position[2] = self.props.current_road_height
            self._start_fresh_segment(start_build_point, this_curve_obj, this_curve_data, type_)
        elif isinstance(start_build_point, RoadSegmentBuildPoint):
            if start_build_point.is_any_endpoint:
                if start_build_point.segment.type_ == type_:
                    self._start_followup_segment(start_build_point, this_curve_obj, type_)
                else:
                    self._start_road_type_merge(
                        start_build_point, this_curve_obj, this_curve_data, type_
                    )
            else:
                self._start_crossroad(start_build_point, this_curve_obj, this_curve_data, type_)
        elif isinstance(start_build_point, CrossroadBuildPoint):
            self._start_new_crossroad_input(
                start_build_point, this_curve_obj, this_curve_data, type_
            )
        else:
            raise ValueError("Unknown start point!")

    def update_provisional_end_point(self, point: BuildPoint):
        if not self.is_building:
            return

        if self.provisional_segment is not None:
            # Update endpoint Z position based on the user settings, if it is an empty point
            if isinstance(point, EmptyBuildPoint):
                point.position[2] = self.props.current_road_height
            spline, idx = self.provisional_segment.spline, self.provisional_segment.endpoint_idx
            if spline is not None:
                spline.bezier_points[idx].co = point.position
            if self.provisional_cx:
                self.provisional_cx.adj_point = move_point_towards_other_point(
                    self.provisional_cx.midpoint, point.position, self._get_crossroad_point_offset()
                )
                spline.bezier_points[-1 if idx == 0 else 0].co = self.provisional_cx.adj_point

    def is_active_build_point(self, spline: bpy.types.Spline, i: int) -> bool:
        """Return true if point with index 'i' on 'spline' is in process of building

        In process of building means if the point is considered a part of a yet un-built crossroad
        or a segment currently being built.
        """

        if not self.is_building:
            return False

        # Points that are directly adjacent to provisional crossroad are active until the
        # provisional crossroad is built.
        if self.provisional_cx is not None:
            for adj in self.provisional_cx.adjacencies:
                is_same_spline = adj.segment.spline == spline
                if is_same_spline and adj.is_first_point and i == 0:
                    return True

                if is_same_spline and not adj.is_first_point and i == len(spline.bezier_points) - 1:
                    return True

        return (spline, i) == (
            self.provisional_segment.spline,
            self.provisional_segment.endpoint_idx,
        )

    def get_spline_build_points(
        self,
    ) -> typing.Iterable[tuple[road_network.RoadSegment, bpy.types.BezierSplinePoint]]:
        for segment in self.road_network.segments:
            # Don't allow connecting to the same spline
            if (
                isinstance(self.start_build_point, RoadSegmentBuildPoint)
                and self.start_build_point.segment.spline == segment.spline
            ):
                continue
            else:
                yield (segment, segment.spline.bezier_points)

    def get_crossroad_build_points(self) -> typing.Iterable[road_network.Crossroad]:
        return self.road_network.crossroads

    def reset_state(self) -> None:
        self.start_build_point = None
        self.provisional_segment = None
        self.provisional_cx = None
        self.is_building = False

    def finish_segment(self, end_build_point: BuildPoint) -> None:
        assert self.provisional_segment is not None
        assert self.start_build_point is not None

        this_curve_obj, this_spline, this_type_ = (
            self.provisional_segment.curve_obj,
            self.provisional_segment.spline,
            self.provisional_segment.road_type,
        )
        if isinstance(end_build_point, EmptyBuildPoint):
            # Add the segment into road_network, the position was updated in
            # 'update_provisional_end_point' dynamically
            self.road_network.add_segment(
                road_network.RoadSegment(this_curve_obj, this_spline, this_type_)
            )
        elif isinstance(end_build_point, RoadSegmentBuildPoint):
            if end_build_point.is_any_endpoint:
                if end_build_point.segment.type_ == this_type_:
                    self._end_join_same_segments(end_build_point)
                else:
                    self._end_road_type_merge(end_build_point)
            else:
                self._end_create_crossroad(end_build_point)
        elif isinstance(end_build_point, CrossroadBuildPoint):
            self._end_add_new_crossroad_input(end_build_point)
        else:
            raise ValueError("Unknown end point!")

        if self.provisional_cx is not None:
            self._finish_provisional_cx(end_build_point)

        self.reset_state()

    def _begin_provisional_cx(
        self,
        adjacencies: list[road_network.SegmentAdjacency],
        position: mathutils.Vector | None = None,
    ) -> None:
        """Begins provisional crossroad, which geometry isn't constructed yet.

        Use when it is not known where the crossroad outgoing segment is and it's position
        is going to change."""
        if position:
            position = position.copy()
        else:
            position = polib.linalg_bpy.mean_position(adj.adjacent_point.co for adj in adjacencies)

        self.provisional_cx = ProvisionalCrossroadInfo(adjacencies, position, None)

    def _finish_provisional_cx(self, end_point: BuildPoint) -> None:
        """Construct geometry for previously saved provisional crossroad"""
        assert self.provisional_cx is not None

        self.road_network.add_crossroad(
            self.cx_builder.build_crossroad(
                self.provisional_cx.adjacencies, self.provisional_cx.midpoint
            )
        )

        self.provisional_cx = None

    def _start_fresh_segment(
        self,
        build_point: EmptyBuildPoint,
        curve_obj: bpy.types.Object,
        curve: bpy.types.Curve,
        type_: road_type.RoadType,
    ) -> None:
        # Starting a fresh spline
        spline, _ = polib.spline_utils_bpy.new_bezier_spline(curve, build_point.position, 'VECTOR')
        polib.spline_utils_bpy.add_bezier_point_to_spline(spline, build_point.position)
        self.provisional_segment = ProvisionalSegment(curve_obj, spline, 1, type_)

    def _start_followup_segment(
        self,
        build_point: RoadSegmentBuildPoint,
        curve_obj: bpy.types.Object,
        type_: road_type.RoadType,
    ) -> None:
        # Adding point to a existing spline
        polib.spline_utils_bpy.add_bezier_point_to_spline(
            build_point.segment.spline, build_point.position, prepend=build_point.point_idx == 0
        )
        # In case of point_idx, the provisional index is 0, because the point
        # was prepended.
        idx = 0 if build_point.point_idx == 0 else build_point.point_idx + 1
        self.provisional_segment = ProvisionalSegment(
            curve_obj, build_point.segment.spline, idx, type_
        )

    def _start_road_type_merge(
        self,
        build_point: RoadSegmentBuildPoint,
        curve_obj: bpy.types.Object,
        curve: bpy.types.Curve,
        type_: road_type.RoadType,
    ) -> None:
        # Endpoint but different road type
        start_bezier_point = build_point.get_point()

        # Estimate normal direction (TODO: consider handles?)
        neighbor_idx = get_endpoint_neighbor_idx(build_point.point_idx)

        crossroad_point_offset = self._get_crossroad_point_offset()
        start_bezier_point.co = move_point_towards_other_point(
            start_bezier_point.co,
            build_point.segment.spline.bezier_points[neighbor_idx].co,
            crossroad_point_offset,
        )

        # Create the connecting object
        spline, _ = polib.spline_utils_bpy.new_bezier_spline(
            curve,
            move_point_towards_other_point(
                start_bezier_point.co,
                build_point.segment.spline.bezier_points[neighbor_idx].co,
                # Offset 2 times backwards, so the future crossroad location is exactly
                # in the expected middle.
                -2 * crossroad_point_offset,
            ),
            'VECTOR',
        )
        polib.spline_utils_bpy.add_bezier_point_to_spline(spline, build_point.position)
        self.provisional_segment = ProvisionalSegment(curve_obj, spline, 1, type_)

        self._begin_provisional_cx(
            [
                road_network.SegmentAdjacency(build_point.segment, build_point.point_idx),
                road_network.SegmentAdjacency(
                    road_network.RoadSegment(curve_obj, spline, type_), 0
                ),
            ]
        )

    def _start_crossroad(
        self,
        build_point: RoadSegmentBuildPoint,
        curve_obj: bpy.types.Object,
        curve: bpy.types.Curve,
        type_: road_type.RoadType,
    ) -> None:
        # Splitting original spline and creating a crossing
        s12_curve_obj = build_point.segment.curve_object
        original_spline = build_point.segment.spline
        s1, s2 = polib.spline_utils_bpy.split_spline(
            s12_curve_obj.data, build_point.segment.spline, build_point.point_idx
        )

        seg1 = road_network.RoadSegment(s12_curve_obj, s1, build_point.segment.type_)
        seg2 = road_network.RoadSegment(s12_curve_obj, s2, build_point.segment.type_)
        self.road_network.split_segment(build_point.segment, seg1, seg2)
        build_point.position = build_point.position.copy()
        spline1_point = s1.bezier_points[len(s1.bezier_points) - 1]
        spline2_point = s2.bezier_points[0]

        # Replace the original segment with two new ones
        self.road_network.add_segment(
            road_network.RoadSegment(
                build_point.segment.curve_object, s1, build_point.segment.type_
            )
        )
        self.road_network.add_segment(
            road_network.RoadSegment(
                build_point.segment.curve_object, s2, build_point.segment.type_
            )
        )

        # Create the 3rd spline connecting to the crossroad
        s3, spline3_point = polib.spline_utils_bpy.new_bezier_spline(
            curve, build_point.position, 'VECTOR'
        )
        crossroad_point_offset = self._get_crossroad_point_offset()
        spline1_point.co = move_point_towards_other_point(
            spline1_point.co, s1.bezier_points[len(s1.bezier_points) - 2].co, crossroad_point_offset
        )
        spline2_point.co = move_point_towards_other_point(
            spline2_point.co, s2.bezier_points[1].co, crossroad_point_offset
        )

        self._begin_provisional_cx(
            [
                road_network.SegmentAdjacency(seg1, len(s1.bezier_points) - 1),
                road_network.SegmentAdjacency(seg2, 0),
                road_network.SegmentAdjacency(road_network.RoadSegment(curve_obj, s3, type_), 0),
            ],
            build_point.position,
        )

        polib.spline_utils_bpy.add_bezier_point_to_spline(s3, spline3_point.co)
        self.provisional_segment = ProvisionalSegment(curve_obj, s3, 1, type_)

        # Remove the original spline after all modifications to road network happened,
        # otherwise there can be ReferenceErrors
        s12_curve_obj.data.splines.remove(original_spline)

    def _start_new_crossroad_input(
        self,
        build_point: CrossroadBuildPoint,
        curve_obj: bpy.types.Object,
        curve: bpy.types.Curve,
        type_: road_type.RoadType,
    ) -> None:
        # Add input to existing crossroad
        spline, _ = polib.spline_utils_bpy.new_bezier_spline(curve, build_point.position, 'VECTOR')
        existing_adjacencies = list(build_point.crossroad.adjacencies)
        existing_adjacencies.append(
            road_network.SegmentAdjacency(road_network.RoadSegment(curve_obj, spline, type_), 0)
        )
        self.road_network.remove_crossroad(build_point.crossroad)
        bpy.data.objects.remove(build_point.crossroad.obj)

        polib.spline_utils_bpy.add_bezier_point_to_spline(spline, build_point.position)
        self.provisional_segment = ProvisionalSegment(curve_obj, spline, 1, type_)
        self._begin_provisional_cx(existing_adjacencies, build_point.crossroad.position)

    def _end_join_same_segments(self, build_point: RoadSegmentBuildPoint) -> None:
        assert self.provisional_segment is not None

        s1 = self.provisional_segment.spline
        s1_idx = self.provisional_segment.endpoint_idx
        started_curve_obj = self.provisional_segment.curve_obj
        started_type = self.provisional_segment.road_type

        s2 = build_point.segment.spline
        s1_is_end = s1_idx == len(s1.bezier_points) - 1
        s2_is_end = build_point.is_start_endpoint is False

        reverse, prepend = False, False
        start_cx, end_cx = None, None
        # There are multiple cases of joining segments, the new segment can start in empty space
        # or on an existing segment and ends on existing segment. We need to get information about
        # adjacent crossroads based on what end the segment is.
        if s1_is_end and s2_is_end:
            reverse = True
            if isinstance(self.start_build_point, RoadSegmentBuildPoint):
                start_cx = self.road_network.get_endpoints_connections(
                    self.start_build_point.segment
                )[0]
            end_cx = self.road_network.get_endpoints_connections(build_point.segment)[0]
        elif not s1_is_end and s2_is_end:
            s1, s2 = s2, s1
            if isinstance(self.start_build_point, RoadSegmentBuildPoint):
                end_cx = self.road_network.get_endpoints_connections(
                    self.start_build_point.segment
                )[1]
            start_cx = self.road_network.get_endpoints_connections(build_point.segment)[0]

        elif s1_is_end and not s2_is_end:
            reverse, prepend = False, False
            if isinstance(self.start_build_point, RoadSegmentBuildPoint):
                start_cx = self.road_network.get_endpoints_connections(
                    self.start_build_point.segment
                )[0]
            end_cx = self.road_network.get_endpoints_connections(build_point.segment)[1]
        else:
            reverse, prepend = True, True
            if isinstance(self.start_build_point, RoadSegmentBuildPoint):
                start_cx = self.road_network.get_endpoints_connections(
                    self.start_build_point.segment
                )[1]
            end_cx = self.road_network.get_endpoints_connections(build_point.segment)[1]

        new_spline = polib.spline_utils_bpy.join_splines(
            started_curve_obj.data, s1, s2, reverse, prepend
        )
        new_segment = road_network.RoadSegment(started_curve_obj, new_spline, started_type)
        self.road_network.add_segment(new_segment)
        # If provisional CX is already built, we need to replace the last provisional adjacency
        # with the new one, before it gets built.
        if self.provisional_cx is not None and self.provisional_segment is not None:
            old_adj = self.provisional_cx.adjacencies[-1]
            self.provisional_cx.adjacencies.remove(old_adj)
            self.provisional_cx.adjacencies.append(
                road_network.SegmentAdjacency(new_segment, first_point=True)
            )
            if isinstance(self.start_build_point, RoadSegmentBuildPoint):
                # In case the start segment was the same as the end segment, we need to replace
                # one more adjacency, because the crossroad will be connected with one adjacent
                # segment from its both sides.
                assert self.start_build_point.segment.type_ == build_point.segment.type_
                old_adj_next = self.provisional_cx.adjacencies[-2]
                self.provisional_cx.adjacencies.remove(old_adj_next)
                self.provisional_cx.adjacencies.append(
                    road_network.SegmentAdjacency(new_segment, first_point=False)
                )
            self.road_network.remove_segment(build_point.segment)
        elif isinstance(self.start_build_point, RoadSegmentBuildPoint):
            self.road_network.remove_segment(self.start_build_point.segment)
            self.road_network.remove_segment(build_point.segment)
            if start_cx:
                self.road_network.add_adjacency(
                    start_cx, road_network.SegmentAdjacency(new_segment, first_point=True)
                )
            if end_cx:
                self.road_network.add_adjacency(
                    end_cx, road_network.SegmentAdjacency(new_segment, first_point=False)
                )
        else:
            self.road_network.replace_segment(build_point.segment, new_segment, reverse)

        # Remove the splines at the last point to avoid ReferenceErrors
        started_curve_obj.data.splines.remove(s1)
        started_curve_obj.data.splines.remove(s2)

    def _end_road_type_merge(self, build_point: RoadSegmentBuildPoint) -> None:
        assert self.provisional_segment is not None
        started_curve_obj, started_type = (
            self.provisional_segment.curve_obj,
            self.provisional_segment.road_type,
        )
        position = build_point.position.copy()
        bp1 = build_point.get_point()
        neighbor_idx = get_endpoint_neighbor_idx(build_point.point_idx)
        bp1.co = move_point_towards_other_point(
            bp1.co,
            build_point.segment.spline.bezier_points[neighbor_idx].co,
            self._get_crossroad_point_offset(),
        )
        s2, i = self.provisional_segment.spline, self.provisional_segment.endpoint_idx
        s2.bezier_points[i].co = move_point_towards_other_point(
            s2.bezier_points[i].co,
            self.start_build_point.position,
            self._get_crossroad_point_offset(),
        )

        self.road_network.add_crossroad(
            self.cx_builder.build_crossroad(
                [
                    road_network.SegmentAdjacency(build_point.segment, build_point.point_idx),
                    road_network.SegmentAdjacency(
                        road_network.RoadSegment(started_curve_obj, s2, started_type), i
                    ),
                ],
                position,
            )
        )

    def _end_create_crossroad(self, build_point: RoadSegmentBuildPoint) -> None:
        assert self.provisional_segment is not None
        # Splitting original spline and creating a crossing
        started_curve_obj, started_type = (
            self.provisional_segment.curve_obj,
            self.provisional_segment.road_type,
        )
        s12_curve_obj = build_point.segment.curve_object
        original_spline = build_point.segment.spline
        s1, s2 = polib.spline_utils_bpy.split_spline(
            s12_curve_obj.data, original_spline, build_point.point_idx
        )
        seg1 = road_network.RoadSegment(s12_curve_obj, s1, build_point.segment.type_)
        seg2 = road_network.RoadSegment(s12_curve_obj, s2, build_point.segment.type_)
        self.road_network.split_segment(build_point.segment, seg1, seg2)
        # If there is a provisional CX, and the split spline ends in it, we need to update the
        # adjacencies too
        if self.provisional_cx:
            start_adj = road_network.SegmentAdjacency(build_point.segment, first_point=True)
            end_adj = road_network.SegmentAdjacency(build_point.segment, first_point=False)
            if start_adj in self.provisional_cx.adjacencies:
                self.provisional_cx.adjacencies.remove(start_adj)
                self.provisional_cx.adjacencies.append(
                    road_network.SegmentAdjacency(seg1, first_point=True)
                )

            if end_adj in self.provisional_cx.adjacencies:
                self.provisional_cx.adjacencies.remove(end_adj)
                self.provisional_cx.adjacencies.append(
                    road_network.SegmentAdjacency(seg1, first_point=False)
                )

        spline1_point = s1.bezier_points[len(s1.bezier_points) - 1]
        spline2_point = s2.bezier_points[0]

        # Create the 3rd spline connecting to the crossroad
        s3, i = self.provisional_segment.spline, self.provisional_segment.endpoint_idx
        point_offset = self._get_crossroad_point_offset()
        spline1_point.co = move_point_towards_other_point(
            spline1_point.co, s1.bezier_points[len(s1.bezier_points) - 2].co, point_offset
        )
        spline2_point.co = move_point_towards_other_point(
            spline2_point.co, s2.bezier_points[1].co, point_offset
        )
        s3.bezier_points[i].co = move_point_towards_other_point(
            s3.bezier_points[i].co, s3.bezier_points[get_endpoint_neighbor_idx(i)].co, point_offset
        )

        self.road_network.add_crossroad(
            self.cx_builder.build_crossroad(
                [
                    road_network.SegmentAdjacency(seg1, len(s1.bezier_points) - 1),
                    road_network.SegmentAdjacency(seg2, 0),
                    road_network.SegmentAdjacency(
                        road_network.RoadSegment(started_curve_obj, s3, started_type), i
                    ),
                ]
            )
        )

        # Remove the original spline after all modifications to road network happened,
        # otherwise there can be ReferenceErrors
        s12_curve_obj.data.splines.remove(original_spline)

    def _end_add_new_crossroad_input(self, build_point: CrossroadBuildPoint) -> None:
        # add input to crossroad
        assert self.provisional_segment is not None
        started_curve_obj, started_type = (
            self.provisional_segment.curve_obj,
            self.provisional_segment.road_type,
        )
        spline, idx = self.provisional_segment.spline, self.provisional_segment.endpoint_idx
        neighbor_point = spline.bezier_points[get_endpoint_neighbor_idx(idx)]
        spline.bezier_points[idx].co = move_point_towards_other_point(
            spline.bezier_points[idx].co, neighbor_point.co, self._get_crossroad_point_offset()
        )
        adjacencies = list(build_point.crossroad.adjacencies)
        adjacencies.append(
            road_network.SegmentAdjacency(
                road_network.RoadSegment(started_curve_obj, spline, started_type), idx
            )
        )
        self.road_network.remove_crossroad(build_point.crossroad)
        self.road_network.add_crossroad(
            self.cx_builder.build_crossroad(adjacencies, build_point.crossroad.position)
        )
        bpy.data.objects.remove(build_point.crossroad.obj)

    def _get_crossroad_point_offset(self):
        """Returns value by how much the points should be offset from the crossroad midpoint"""
        return self.props.crossroad.points_offset

    def _debug_points(self, prefix: str, points: typing.Iterable[mathutils.Vector]) -> None:
        if not self.props.debug:
            return

        context = bpy.context
        for i, point in enumerate(points):
            text = bpy.data.curves.new("Text", type='FONT')
            text.body = f"{prefix}: {i}, {point}"
            obj = bpy.data.objects.new("DBG", text)
            obj.location = point
            context.collection.objects.link(obj)
