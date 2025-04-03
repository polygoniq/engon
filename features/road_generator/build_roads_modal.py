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

# Module containing the main modal operator that transfers user input to building road system
# and also draws viewport overlays and can draw debug information.

import bpy
import os
import typing
import mathutils
import bpy_extras.view3d_utils
import logging
from ... import polib
from . import asset_helpers
from . import crossroad_builder
from . import road_builder
from . import props
from . import road_type

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES = []

HIGHLIGHT_COLOR = (0.991102, 0.258183, 0.0, 1.0)
OVERLAY_COLOR = (0.205079, 1.0, 1.0, 0.1)
CX_OVERLAY_COLOR = (0.012983, 0.174648, 0.982251, 1.0)
TEXT_COLOR = (0.8, 0.8, 0.8, 1.0)
TEXT_COLOR_BRIGHTER = (0.9, 0.9, 0.9, 1.0)
TEXT_HEADING_COLOR = (1.0, 1.0, 1.0, 1.0)
OVERLAY_Z = 0.0


@polib.log_helpers_bpy.logged_operator
class BuildRoads(bpy.types.Operator):
    """Modal operator converting user input to building of roads and crossroads

    This operator handles user input in the 'modal_exc_safe'. Based on the user input the
    information is passed to an instance of RoadBuilder that handles building of roads.

    We use two methods to draw additional user interface:
    - draw_px - to draw additional information in the user interface
    - draw_view - to draw overlays of the build points in the 3D scene
    """

    bl_idname = "engon.traffiq_road_generator_build"
    bl_label = "Build Roads"
    bl_description = "Build a road system consisting of multiple roads with crossroads"

    draw_3d_handler_ref = None
    draw_2d_handler_ref = None

    is_running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mouse_point: typing.Optional[road_builder.BuildPoint] = None
        self.first_point: typing.Optional[road_builder.BuildPoint] = None
        self.first_point_position: typing.Optional[mathutils.Vector] = None
        self.snapped_point = None

        self.grid_snap = False
        self.text_ui_origin = mathutils.Vector((50, 50))
        self.text_help_ui_origin = mathutils.Vector((60, 310))

        self.road_type_idx = -1
        self.road_types_len = 1

        self.curves: typing.Dict[str, bpy.types.Object] = {}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.region_data is not None and isinstance(
            context.region_data, bpy.types.RegionView3D
        )

    @staticmethod
    def remove_draw_handlers() -> None:
        if (
            hasattr(BuildRoads, "draw_3d_handler_ref")
            and BuildRoads.draw_3d_handler_ref is not None
        ):
            bpy.types.SpaceView3D.draw_handler_remove(BuildRoads.draw_3d_handler_ref, 'WINDOW')
            BuildRoads.draw_3d_handler_ref = None

        if (
            hasattr(BuildRoads, "draw_2d_handler_ref")
            and BuildRoads.draw_2d_handler_ref is not None
        ):
            bpy.types.SpaceView3D.draw_handler_remove(BuildRoads.draw_2d_handler_ref, 'WINDOW')
            BuildRoads.draw_2d_handler_ref = None

    def __del__(self):
        BuildRoads.remove_draw_handlers()

    def draw_roads_overlay(self) -> None:
        for segment, bezier_points in self.road_builder.get_spline_build_points():
            bezier_points_len = len(bezier_points)
            for i in range(bezier_points_len):
                if self.road_builder.is_active_build_point(segment.spline, i):
                    continue

                point_overlay_pos = self._to_overlay_pos(bezier_points[i].co)
                if i < bezier_points_len - 1:
                    polib.render_bpy.line(
                        point_overlay_pos,
                        self._to_overlay_pos(bezier_points[i + 1].co),
                        OVERLAY_COLOR,
                        1,
                    )

                if not self.road_builder.road_network.is_crossroad_endpoint(segment, i):
                    polib.render_bpy.circle(
                        point_overlay_pos, segment.type_.half_width, OVERLAY_COLOR, 32
                    )

        for crossroad in self.road_builder.get_crossroad_build_points():
            polib.render_bpy.circle(
                self._to_overlay_pos(crossroad.position), crossroad.radius, CX_OVERLAY_COLOR, 32
            )

        if self.snapped_point is not None:
            polib.render_bpy.circle(
                self._to_overlay_pos(self.snapped_point[0]),
                self.snapped_point[1],
                HIGHLIGHT_COLOR,
                32,
            )

        if self.first_point_position is not None and self.mouse_point is not None:
            polib.render_bpy.line(
                self.first_point_position, self.mouse_point.position, OVERLAY_COLOR, 1
            )

        if self.props.debug:
            if self.road_builder.provisional_spline_end_point:
                spline, idx = self.road_builder.provisional_spline_end_point
                polib.render_bpy.circle(spline.bezier_points[idx].co, 5.0, (0, 1, 0, 1), 5)
            if self.road_builder.provisional_cx is not None:
                polib.render_bpy.circle(
                    self.road_builder.provisional_cx.midpoint, 5.0, (1, 0, 0, 1), 5
                )
                if self.road_builder.provisional_cx.adj_point is not None:
                    polib.render_bpy.circle(
                        self.road_builder.provisional_cx.adj_point, 5.0, (0, 0, 1, 1), 5
                    )

    def draw_view(self) -> None:
        """Draws in the 3D world coordinate space"""
        self.draw_roads_overlay()

    def draw_px(self) -> None:
        """Draws in the 2D coordinate space after projection is applied"""
        region = bpy.context.region
        region_3d = bpy.context.space_data.region_3d
        current_road_type = self._get_current_road_type()

        info_text_style = polib.render_bpy.TextStyle(font_size=15, color=TEXT_COLOR)
        heading_text_style = polib.render_bpy.TextStyle(font_size=15, color=TEXT_HEADING_COLOR)
        # Draw modal information
        polib.render_bpy.text_box(
            self.text_ui_origin,
            10 * self.ui_scale,
            10 * self.ui_scale,
            (0, 0, 0, 0.5),
            [
                ("Build Roads Information", heading_text_style),
                (
                    f"Crossroad Road Offset: {self.props.crossroad.points_offset:.2f}",
                    info_text_style,
                ),
                ("Current Road", heading_text_style),
                (f"Road Type: {current_road_type.name}", info_text_style),
                (f"Total Width: {current_road_type.total_width:.2f}", info_text_style),
                (f"Road Width: {current_road_type.road_surface_width:.2f}", info_text_style),
            ],
        )

        # Draw guidance for user
        polib.render_bpy.text(
            self.text_help_ui_origin,
            (
                "Left Click - Start Segment"
                if self.first_point is None
                else "Left Click - Finish Segment"
            ),
            polib.render_bpy.TextStyle(font_size=20, color=TEXT_COLOR_BRIGHTER),
        )

        polib.render_bpy.text(
            self.text_help_ui_origin - mathutils.Vector((0, 25 * self.ui_scale)),
            "Q - Change Road Type",
            polib.render_bpy.TextStyle(font_size=17, color=TEXT_COLOR_BRIGHTER),
        )

        polib.render_bpy.text(
            self.text_help_ui_origin - mathutils.Vector((0, 50 * self.ui_scale)),
            "CTRL - Grid Snap is ON" if self.grid_snap else "CTRL - Snap To Grid (Hold)",
            polib.render_bpy.TextStyle(font_size=17, color=TEXT_COLOR_BRIGHTER),
        )
        polib.render_bpy.text(
            self.text_help_ui_origin - mathutils.Vector((0, 75 * self.ui_scale)),
            "ESC - Exit",
            polib.render_bpy.TextStyle(font_size=17, color=TEXT_COLOR_BRIGHTER),
        )

        if self.props.debug:
            dbg_style = polib.render_bpy.TextStyle()
            polib.render_bpy.text_box(
                self.text_ui_origin + mathutils.Vector((0, 300)),
                10,
                10,
                (0, 0, 0, 0.5),
                [
                    (f"First Point: {self.first_point}", dbg_style),
                    (f"Mouse Point: {self.mouse_point}", dbg_style),
                    (
                        f"Segments Count: {len(list(self.road_builder.road_network.segments))}",
                        dbg_style,
                    ),
                    (
                        f"CX Count: {len(list(self.road_builder.road_network.crossroads))}",
                        dbg_style,
                    ),
                ],
            )

            polib.render_bpy.text_box(
                self.text_ui_origin + mathutils.Vector((50, 600)),
                10,
                10,
                None,
                [("Road Network Debug", dbg_style), ("Segments:", dbg_style)]
                + [(str(seg), dbg_style) for seg in self.road_builder.road_network.segments]
                + [("Crossroads:", dbg_style)]
                + [(str(cx), dbg_style) for cx in self.road_builder.road_network.crossroads],
            )

            for segment in self.road_builder.road_network.segments:
                for i, bezier_point in enumerate(segment.spline.bezier_points):
                    is_endpoint = self.road_builder.road_network.is_crossroad_endpoint(segment, i)
                    polib.render_bpy.text_3d(
                        bezier_point.co,
                        f"{repr(segment.spline)[-3:]}[{i}]: {is_endpoint}",
                        dbg_style,
                        region,
                        region_3d,
                    )

    def _cleanup(
        self,
        context: bpy.types.Context,
        event: typing.Optional[bpy.types.Event] = None,
        exception: typing.Optional[Exception] = None,
    ) -> None:
        BuildRoads.remove_draw_handlers()
        context.area.tag_redraw()
        BuildRoads.is_running = False

    def execute(self, context: bpy.types.Context):
        # This is needed so the operator call without invoke does not throw an error
        return {'FINISHED'}

    @polib.utils_bpy.safe_modal(on_exception=_cleanup)
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        event_handled = False

        # Pass through all events that are not directly in the 3D viewport
        area, region = polib.ui_bpy.get_mouseovered_region(context, event)
        if (
            area is not None
            and area.type != 'VIEW_3D'
            or region is not None
            and region.type != 'WINDOW'
        ):
            return {'PASS_THROUGH'}

        # Filter navigation events.
        # MIDDLEMOUSE and shift movement is tilting of view, we allow only view from top-down,
        # because there is no raycasting to geometry implemented, as it's not possible to raycast
        # to geometry created by geometry nodes.
        if event.type == 'MIDDLEMOUSE' and event.shift:
            if event.value == 'PRESS':
                self.is_viewport_movement = True
            elif event.value == 'RELEASE':
                self.is_viewport_movement = False
            return {'PASS_THROUGH'}

        # Allow zoom in and out
        elif event.type in {'WHEELDOWNMOUSE', 'WHEELUPMOUSE'} and event.value == 'PRESS':
            return {'PASS_THROUGH'}

        self.grid_snap = event.ctrl
        if event.type == 'MOUSEMOVE':
            self._handle_snapping(context, event)
            event_handled = True

        if event.value == 'PRESS':
            event_handled = True
            if event.type == 'Q':
                self.props.cycle_road_type()
            elif event.type == 'LEFTMOUSE':
                if self.mouse_point is None:
                    return {'PASS_THROUGH'}
                current_road_type = self._get_current_road_type()
                if self.first_point is None:
                    self.first_point = self.mouse_point
                    self.first_point_position = self.mouse_point.position.copy()
                    self.road_builder.start_segment(self.mouse_point, current_road_type)
                else:
                    assert self.first_point is not None
                    self.road_builder.finish_segment(self.mouse_point)
                    self.first_point = None
                    self.first_point_position = None
            elif event.type == 'ESC':
                self._cleanup(context)
                return {'FINISHED'}

        context.area.tag_redraw()
        return {'RUNNING_MODAL'} if event_handled else {'PASS_THROUGH'}

    def cancel(self, context: bpy.types.Context) -> None:
        self._cleanup(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if BuildRoads.is_running:
            logger.error("Another instance of the operator is already running!")
            return {'CANCELLED'}

        polib.render_bpy.set_context(context)
        self.props = props.get_rg_props(context)
        # Save ui_scale and scale text origins
        self.ui_scale = context.preferences.system.ui_scale
        self.text_help_ui_origin *= self.ui_scale
        self.text_ui_origin *= self.ui_scale

        if not os.path.exists(self.props.roads_path):
            self.report({'ERROR'}, f"Road generator files do not exist at {self.props.roads_path}")
            self._cleanup(context)
            return {'CANCELLED'}

        road_type.loader.load_dir(props.get_rg_props(context).roads_path)

        collection = asset_helpers.get_road_collection(context)
        self.road_builder = road_builder.RoadBuilder(
            collection,
            crossroad_builder.CrossroadBuilder(
                collection,
                self.props.geonodes_lib_path,
                self.props.cx_geonodes_lib_path,
            ),
            self.props.geonodes_lib_path,
        )
        self.road_builder.clear_collection()
        self.road_builder.init_from_scene(context.scene, road_type.loader)

        # Register the draw handler for the 3D UI
        assert BuildRoads.draw_3d_handler_ref is None
        BuildRoads.draw_3d_handler_ref = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_view, (), 'WINDOW', 'POST_VIEW'
        )

        # Register the draw handler for the help UI
        assert BuildRoads.draw_2d_handler_ref is None
        BuildRoads.draw_2d_handler_ref = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_px, (), 'WINDOW', 'POST_PIXEL'
        )

        context.window_manager.modal_handler_add(self)
        bpy.ops.view3d.view_axis(type='TOP')
        polib.ui_bpy.tag_areas_redraw(context, {'VIEW_3D'})

        # Change the is_running state right before returning in case of any error happening
        # before which would lock the UI.
        BuildRoads.is_running = True
        return {'RUNNING_MODAL'}

    def _handle_snapping(self, context: bpy.types.Context, event: bpy.types.Event) -> None:
        self.mouse_pos_3d = self._mouse_to_3d(context, event.mouse_region_x, event.mouse_region_y)
        self.snapped_point = None

        if self.grid_snap:
            grid_scale = context.space_data.overlay.grid_scale * self.props.grid_scale_multiplier
            self.mouse_pos_3d = mathutils.Vector(
                (
                    grid_scale * round(self.mouse_pos_3d.x / grid_scale),
                    grid_scale * round(self.mouse_pos_3d.y / grid_scale),
                    self.mouse_pos_3d.z,
                )
            )

        self.mouse_point = road_builder.EmptyBuildPoint(self.mouse_pos_3d)
        for segment, bezier_points in self.road_builder.get_spline_build_points():
            for i, point in enumerate(bezier_points):
                # Do not snap to any of the currently active build points
                if self.road_builder.is_active_build_point(segment.spline, i):
                    continue

                # Snapping to crossroads is handled below, we don't want to snap to the
                # adjacent points.
                if self.road_builder.road_network.is_crossroad_endpoint(segment, i):
                    continue

                if (
                    self._to_overlay_pos(self.mouse_pos_3d - point.co).length
                    < segment.type_.half_width
                ):
                    self.snapped_point = (point.co, segment.type_.half_width)
                    self.mouse_point = road_builder.RoadSegmentBuildPoint(segment, i)
                    break

        for crossroad in self.road_builder.get_crossroad_build_points():
            if (
                self._to_overlay_pos(self.mouse_pos_3d - crossroad.position).length
                < crossroad.radius
            ):
                self.snapped_point = (crossroad.position, crossroad.radius)
                self.mouse_point = road_builder.CrossroadBuildPoint(crossroad.position, crossroad)
                break

        self.road_builder.update_provisional_end_point(self.mouse_point)

    def _get_current_road_type(self) -> road_type.RoadType:
        return road_type.loader.get_road_type_by_name(props.get_rg_props().current_road_type)

    def _mouse_to_3d(self, context: bpy.types.Context, x: int, y: int):
        # https://blender.stackexchange.com/questions/76464/how-to-get-the-mouse-coordinates-in-3space-relative-to-the-local-coordinates-of
        pos = (x, y)
        region = context.region
        region3d = context.space_data.region_3d
        view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, region3d, pos)
        return bpy_extras.view3d_utils.region_2d_to_location_3d(region, region3d, pos, view_vector)

    def _to_overlay_pos(self, pos: mathutils.Vector) -> mathutils.Vector:
        """Converts Z coordinate of 'pos' to position expected by overlay

        The overlay is defined at OVERLAY_Z position, as we do not have the information about
        depth buffer and cannot do proper depth calculation."""
        new_pos = pos.copy()
        new_pos[2] = OVERLAY_Z
        return new_pos


MODULE_CLASSES.append(BuildRoads)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    BuildRoads.remove_draw_handlers()
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
