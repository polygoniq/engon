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
import os
import typing

from . import road_type
from ... import asset_registry


MODULE_CLASSES = []


class CrossroadType:
    BLANK = 'BLANK'
    TRAFFIC_LIGHTS = 'TRAFFIC_LIGHTS'
    YIELD = 'YIELD'
    STOP = 'STOP'


class CrossroadYieldMethod:
    NARROW_ROAD = 'NARROW_ROAD'
    SHORTER_SEGMENT = 'SHORTER_SEGMENT'


class FilletProps(bpy.types.PropertyGroup):
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        default=True,
        description="Only selected objects will have their modifiers affected",
    )

    value: bpy.props.FloatProperty(
        name="Target Value",
        default=3.0,
        description="All Fillet Radius values will be set to value of this field",
    )


MODULE_CLASSES.append(FilletProps)


class ResampleProps(bpy.types.PropertyGroup):
    include_input: bpy.props.BoolProperty(
        name="Input Curves", default=True, description="If True then input curves are resampled"
    )
    include_markings: bpy.props.BoolProperty(
        name="Road Markings", default=True, description="If True then road markings are resampled"
    )
    include_profile: bpy.props.BoolProperty(
        name="Road Profiles", default=True, description="If True then road profiles are resampled"
    )
    include_register: bpy.props.BoolProperty(
        name="Crossroad Arc Curves",
        default=True,
        description="If True then crossroad arcs are resampled",
    )
    value: bpy.props.FloatProperty(
        name="Target Value",
        default=3.0,
        description="All included road modifiers will be resampled to this value. Lower value "
        "results in finer geometry while smaller values create cheaper geometry",
    )
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        default=True,
        description="Only selected objects will have their modifiers affected",
    )


MODULE_CLASSES.append(ResampleProps)


class CrossroadProps(bpy.types.PropertyGroup):
    points_offset: bpy.props.FloatProperty(
        name="Crossroad Points Offset (m)", default=15.0, min=1.0
    )

    build_crosswalks: bpy.props.BoolProperty(
        name="Build Crosswalks",
        default=True,
        description="If True then crosswalks for crossroads are built automatically",
    )

    type_: bpy.props.EnumProperty(
        name="Crossroad Type",
        items=[
            (CrossroadType.BLANK, "Blank", "Blank"),
            (CrossroadType.TRAFFIC_LIGHTS, "Traffic Lights", "Traffic Lights"),
            (CrossroadType.YIELD, "Yield", "Yield"),
            (CrossroadType.STOP, "Stop", "Stop"),
        ],
    )

    yield_method: bpy.props.EnumProperty(
        name="Yield Method",
        items=[
            (
                CrossroadYieldMethod.NARROW_ROAD,
                "Narrow Road",
                "Narrower roads will have yield signs",
            ),
            (
                CrossroadYieldMethod.SHORTER_SEGMENT,
                "Shorter Segment",
                "Shorter roads will have yield signs",
            ),
        ],
    )


MODULE_CLASSES.append(CrossroadProps)


class RoadGeneratorProps(bpy.types.PropertyGroup):
    grid_scale_multiplier: bpy.props.FloatProperty(
        name="Snapping Grid Scale",
        default=10.0,
        description="Multiplier of overlay grid scale for building roads operator",
    )

    debug: bpy.props.BoolProperty(
        name="Debug", description="If True then additional debug information will be displayed"
    )

    current_road_type: bpy.props.EnumProperty(
        items=lambda _, __: road_type.loader.get_road_types_as_enum_items()
    )

    current_road_height: bpy.props.FloatProperty(
        name="New Segment Height",
        description="Value of Z coordinate in the world space the new points will be built with",
    )

    crossroad: bpy.props.PointerProperty(type=CrossroadProps)
    fillet: bpy.props.PointerProperty(type=FilletProps)
    resample: bpy.props.PointerProperty(type=ResampleProps)

    def cycle_road_type(self):
        enum_items_names = [x[0] for x in road_type.loader.get_road_types_as_enum_items()]
        self.current_road_type = enum_items_names[
            (enum_items_names.index(self.current_road_type) + 1)
            % len(road_type.loader.road_type_data)
        ]

    # TODO: This whole paths part should be changed to work directly from MAPR, we should
    # return the file at call site and handle it there.
    @property
    def blends_path(self) -> str:
        for pack in asset_registry.instance.get_packs_by_engon_feature("traffiq"):
            expected_path = os.path.join(pack.install_path, "blends")
            if os.path.isdir(expected_path):
                return expected_path

        raise RuntimeError("Failed to find paths to blend files for traffiq!")

    @property
    def roads_path(self) -> str:
        return os.path.join(self.blends_path, "geonodes", "roads")

    @property
    def cx_geonodes_lib_path(self) -> str:
        return os.path.join(self.roads_path, "tq_Library_Crossroads-Geonodes.blend")

    @property
    def geonodes_lib_path(self) -> str:
        return os.path.join(self.roads_path, "tq_Library_Road-Geonodes.blend")


MODULE_CLASSES.append(RoadGeneratorProps)


def get_rg_props(context: bpy.types.Context | None = None) -> RoadGeneratorProps:
    if context is None:
        context = bpy.context

    return context.window_manager.tq_rg


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.tq_rg = bpy.props.PointerProperty(type=RoadGeneratorProps)


def unregister():
    del bpy.types.WindowManager.tq_rg

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
