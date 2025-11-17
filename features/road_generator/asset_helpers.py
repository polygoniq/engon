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
import enum
import typing

# We mark all spawned roads or crossroads with the following string property to detect what in the
# scene is our content.
ROAD_TYPE_PROPERTY = "tq_road_type"
# This value is present in ROAD_TYPE_PROPERTY in case of object being a generated crossroad
ROAD_TYPE_CROSSROAD_VALUE = "CROSSROAD"
# We store the crossroad position on the crossroad object, so we do not have to calculate
# estimated intersection of roads in the curve tangent direction.
CROSSROAD_POSITION_PROPERTY = "tq_cx_position"
ROAD_COLLECTION_NAME = "traffiq roads"

CROSSROAD_PREFIX = "tq_crossroad"
ROAD_PREFIX = "tq_road"


class RoadNodegroup(enum.StrEnum):
    Input = "tq_InputCurve"
    Markings = "tq_RoadMark"
    Distribute = "tq_Distribute"
    RoadProfile = "tq_Profile"
    Scatter = "tq_Scatter"
    Crosswalk = "tq_Crosswalk"
    Cleanup = "tq_Cleanup"


class CrossroadNodegroup(enum.StrEnum):
    Register = "tq_CX_RegisterAdjacency"
    Profile = "tq_CX_Profile"
    Build = "tq_CX_Build"
    Instance = "tq_CX_Instance"


def get_road_collection(context: bpy.types.Context) -> bpy.types.Collection:
    """Returns collection that stores all road generator objects"""
    coll = bpy.data.collections.get(ROAD_COLLECTION_NAME, None)
    if coll is None:
        coll = bpy.data.collections.new(ROAD_COLLECTION_NAME)

    coll.color_tag = 'COLOR_02'
    if ROAD_COLLECTION_NAME not in context.scene.collection.children:
        context.scene.collection.children.link(coll)

    return coll


def get_modifiers_enum_items() -> list[tuple[str, str, str]]:
    return [
        (
            RoadNodegroup.Input,
            "Input",
            "The first road generator modifier - this should be present in every road modifier "
            "stack. Handles resampling, filleting and setups required attributes of the curve",
        ),
        (
            RoadNodegroup.RoadProfile,
            "Profile",
            "Adds geometry to road modifier stack - can be used to create curbs, sidewalks, etc",
        ),
        (RoadNodegroup.Markings, "Road Markings", "Adds road markings to road surface"),
        (
            RoadNodegroup.Distribute,
            "Distribute Objects",
            "Distributes selected objects with an offset on the input curve",
        ),
        (
            RoadNodegroup.Scatter,
            "Scatter To Target",
            "Scatters assets to objects from selected collections near the road",
        ),
        (RoadNodegroup.Crosswalk, "Crosswalk", "Adds a customizable crosswalk to the road"),
        (
            RoadNodegroup.Cleanup,
            "Cleanup",
            "Merges vertices and can realize instances for convert to mesh",
        ),
    ]


def load_geometry_nodes(lib_path: str, node_group_names: set[str]) -> None:
    with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
        for name in node_group_names:
            # We expect caller to know what node groups are present in his lib
            assert name in data_from.node_groups
            # Only load the node group if it was not loaded before, if it is loaded it will be
            # reloaded with next Blender startup
            if bpy.data.node_groups.get(name, None) is None:
                data_to.node_groups.append(name)


def is_road_generator_obj(obj: bpy.types.Object) -> bool:
    return ROAD_TYPE_PROPERTY in obj


def is_crossroad_obj(obj: bpy.types.Object) -> bool:
    return is_road_generator_obj(obj) and obj[ROAD_TYPE_PROPERTY] == ROAD_TYPE_CROSSROAD_VALUE
