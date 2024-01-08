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
import typing
import math
import mathutils
import polib
from . import road_network
from . import props
from . import asset_helpers


class CrossroadBuilder:
    """
    Class responsible for handling crossroad geonodes and setting up scene objects so they create
    crossroads between different segments. Main method of this class is the 'build_crossroad'.

    This class doesn't handle updates to the 'road_network', this has to be handled by the caller.

    Limitations:
    - Crossroad objects have to have location set to (0, 0, 0)
    - If segment adjacent to crossroad is moved, it's no longer considered connected
    """
    # Class variable keeping track of current count of crossroads in the scene
    # this is used to create unique id.
    crossroad_count = 0

    def __init__(
        self,
        main_collection: bpy.types.Collection,
        geonodes_lib_path: str,
        cx_geonodes_lib_path: str,
    ):
        self.main_collection = main_collection
        asset_helpers.load_geometry_nodes(cx_geonodes_lib_path, {
            x.value for x in asset_helpers.CrossroadNodegroup
        })
        asset_helpers.load_geometry_nodes(geonodes_lib_path, {
            x.value for x in asset_helpers.RoadNodegroup
        })

        self.cx_register_ng = bpy.data.node_groups.get(
            asset_helpers.CrossroadNodegroup.Register.value)
        self.cx_profile_ng = bpy.data.node_groups.get(
            asset_helpers.CrossroadNodegroup.Profile.value)
        self.cx_build_ng = bpy.data.node_groups.get(asset_helpers.CrossroadNodegroup.Build.value)
        self.cx_instance_ng = bpy.data.node_groups.get(
            asset_helpers.CrossroadNodegroup.Instance.value)
        self.road_markings_ng = bpy.data.node_groups.get(asset_helpers.RoadNodegroup.Markings.value)
        self.crosswalk_ng = bpy.data.node_groups.get(asset_helpers.RoadNodegroup.Crosswalk.value)
        self.cleanup_ng = bpy.data.node_groups.get(asset_helpers.RoadNodegroup.Cleanup.value)

    def build_crossroad(
        self,
        input_adjacencies: typing.List[road_network.SegmentAdjacency],
        position: typing.Optional[mathutils.Vector] = None
    ) -> road_network.Crossroad:
        """Builds crossroad geometry out of 'input_adjacencies'

        If given a 'position', the argument is used for the position of the crossroad and is
        passed to the 'road_network'.
        Creates a new crossroad object and constructs crossroad. Copies values
        from adjacent segment into crossroad modifiers so the constructed geometry
        is aware of it's surrounding road segments. Decides what road profiles
        will be used in the crossroads and how road markings will be used."""

        id_ = CrossroadBuilder.crossroad_count
        cx_props = props.get_rg_props(bpy.context).crossroad
        cx_name = f"{asset_helpers.CROSSROAD_PREFIX}-{id_}"
        # 1. New CX collection, New CX object
        cx_coll = bpy.data.collections.new(cx_name)
        self.main_collection.children.link(cx_coll)
        empty_mesh = bpy.data.meshes.new(cx_name)
        cx_root_obj = bpy.data.objects.new(cx_name, empty_mesh)
        cx_root_obj[asset_helpers.ROAD_TYPE_PROPERTY] = asset_helpers.ROAD_TYPE_CROSSROAD_VALUE
        cx_coll.objects.link(cx_root_obj)

        # Sort adjacencies counter clockwise so we apply geonodes in correct order
        ccw_adjacencies = self._sort_adjacencies_ccw(input_adjacencies)

        # 2. For each input add input geonodes layer
        for i in range(len(ccw_adjacencies)):
            self._create_adjacency_nodes(
                ccw_adjacencies[i], ccw_adjacencies[(i + 1) % len(ccw_adjacencies)], cx_root_obj, i)

        # 3. Add the Build CX node group
        mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(f"Build Crossroad", type='NODES')
        mod.node_group = self.cx_build_ng
        # Use widest adjacency first road material as a material for crossroad
        widest_adj_segment = max(ccw_adjacencies, key=lambda x: x.segment.type_.total_width).segment
        cx_mod_inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
        road_surface_materials = widest_adj_segment.type_.road_surface_materials
        if len(road_surface_materials) > 0:
            cx_mod_inputs_view.set_material_input_value("Material", road_surface_materials[0].name)

        # 4. Add road markings
        self._add_road_markings(ccw_adjacencies, widest_adj_segment, cx_root_obj)

        # 5. Optionally add crosswalks, don't create crosswalks for road merging
        if cx_props.build_crosswalks and len(ccw_adjacencies) > 2:
            for i in range(len(ccw_adjacencies)):
                self._create_crosswalk(cx_root_obj, i)

        # 6. Optionally add sign instances, don't create signs for road merging
        # TODO: Reenable when MAPR and browser API is refactored, so we don't make another workaround
        # solution...
        # if cx_props.type_ != 'BLANK' and len(ccw_adjacencies) > 2:
        #     self._create_signs(cx_root_obj, ccw_adjacencies, cx_props.type_, cx_props.yield_method)

        if position is None:
            position = polib.linalg_bpy.mean_position(
                adj.adjacent_point.co for adj in input_adjacencies)
        crossroad = road_network.Crossroad(
            id_, cx_coll, cx_root_obj, set(input_adjacencies), position)

        cleanup_mod = cx_root_obj.modifiers.new("Cleanup", type='NODES')
        cleanup_mod.node_group = self.cleanup_ng

        CrossroadBuilder.crossroad_count += 1
        cx_root_obj[asset_helpers.CROSSROAD_POSITION_PROPERTY] = position
        cx_root_obj.update_tag()
        return crossroad

    def _sort_adjacencies_ccw(
        self,
        adjacencies: typing.List[road_network.SegmentAdjacency]
    ) -> typing.List[road_network.SegmentAdjacency]:
        """Sorts segment adjacencies counter-clockwise based on their mean position"""

        X = mathutils.Vector((1, 0, 0))
        Y = mathutils.Vector((0, 1, 0))

        pos = polib.linalg_bpy.mean_position([adj.adjacent_point.co for adj in adjacencies])

        obj_angles = []
        for adj in adjacencies:
            co = pos - adj.adjacent_point.co
            a = X.dot(co)
            b = Y.dot(co)
            obj_angles.append((math.atan2(b, a), adj))

        return [o[1] for o in sorted(obj_angles, key=lambda o: o[0])]

    def _create_adjacency_nodes(
        self,
        start_adjacency: road_network.SegmentAdjacency,
        end_adjacency: road_network.SegmentAdjacency,
        cx_root_obj: bpy.types.Object,
        adj_idx: int
    ) -> None:
        adj = start_adjacency.segment
        adj_next = end_adjacency.segment
        p_co = start_adjacency.adjacent_point.co
        p_next_co = end_adjacency.adjacent_point.co

        mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(
            f"Adjacent Road {adj_idx}", type='NODES')
        mod.node_group = self.cx_register_ng
        inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
        inputs_view.set_obj_input_value("Road 1", adj.curve_object.name)
        inputs_view.set_obj_input_value("Road 2", adj_next.curve_object.name)

        inputs_view.set_input_value("Road 1 Width", adj.type_.road_surface_width)
        inputs_view.set_input_value("Road 2 Width", adj_next.type_.road_surface_width)

        inputs_view.set_input_value("Road 1 Height", adj.type_.road_surface_height)
        inputs_view.set_input_value("Road 2 Height", adj_next.type_.road_surface_height)

        inputs_view.set_array_input_value("End Point 1", p_co)
        inputs_view.set_array_input_value("End Point 2", p_next_co)

        # If the outer profiles of the cross section are not the same, do not generate any
        # outer profiles for this adjacency
        if not adj.type_.compare_outer_cross_section(adj_next.type_):
            return

        for j, profile in enumerate(adj.type_.outer_profiles):
            profile_mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(
                f"Crossroad Profile {adj_idx}-{j}", type='NODES')
            profile_mod.node_group = self.cx_profile_ng
            profile_inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(
                profile_mod)
            profile_inputs_view.set_obj_input_value("Road 1", adj.curve_object.name)
            profile_inputs_view.set_obj_input_value("Road 2", adj_next.curve_object.name)
            profile_inputs_view.set_input_value(
                "Adjacent Roads Snap", min(profile["Width"], profile["Height"]))
            for name, value in profile.items():
                if name not in profile_inputs_view:
                    continue

                if isinstance(value, bpy.types.Material):
                    profile_inputs_view.set_material_input_value(name, value.name)
                elif isinstance(value, bpy.types.Object):
                    profile_inputs_view.set_obj_input_value(name, value.name)
                else:
                    profile_inputs_view.set_input_value(name, value)

            if not math.isclose(profile["Horizontal Offset"], 0.0):
                profile_inputs_view.set_input_value(
                    "Horizontal Offset",
                    adj.type_.road_surface_width / 2.0 - profile["Horizontal Offset"])

    def _add_road_markings(
        self,
        ccw_adjacencies: typing.List[road_network.SegmentAdjacency],
        base_segment: road_network.RoadSegment,
        cx_root_obj: bpy.types.Object
    ) -> None:
        # Use road markings based on the widest road, only add markings if they are present in
        # all of adjacencies. Add after Build CX so the road markings snap to the built surface
        if len(base_segment.type_.road_markings) > 0 and \
           all(adj.segment.type_.has_outer_road_markings() for adj in ccw_adjacencies):
            base_road_markings = base_segment.type_.road_markings[-1]
            markings_mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(
                "Road Markings", type='NODES')
            markings_mod.node_group = self.road_markings_ng
            markings_inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(
                markings_mod)
            markings_inputs_view.set_input_value("Width", base_road_markings.get("Width", 0.1))
            markings_inputs_view.set_input_value(
                "Marking Length", base_road_markings.get("Marking Length", 0.0))
            markings_inputs_view.set_input_value(
                "Space Length", base_road_markings.get("Space Length", 0.0))
            markings_inputs_view.set_input_value(
                "Offset",
                base_segment.type_.road_surface_width / 2.0 - base_road_markings.get("Offset", 0.0))
            markings_inputs_view.set_input_value("Mirror", False)

            material = base_road_markings.get("Material")
            if material is not None:
                markings_inputs_view.set_material_input_value("Material", material.name)

    def _create_crosswalk(self, cx_root_obj: bpy.types.Object, i: int) -> None:
        # Create crosswalk with sensible default settings
        # TODO: Use some material from Material Library to set the material right
        mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(f"Crosswalk {i}", type='NODES')
        mod.node_group = self.crosswalk_ng
        mod_inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
        mod_inputs_view.set_input_value("Crossroad Point Index", i)
        mod_inputs_view.set_input_value("Width", 3.5)
        mod_inputs_view.set_input_value("Position Offset", 1.75)
        # mod_inputs_view.set_material_input_value("Material", get from library)

    def _create_signs(
        self,
        cx_root_obj: bpy.types.Object,
        adjacencies: typing.List[road_network.SegmentAdjacency],
        cx_type: props.CrossroadType,
        yield_method: props.CrossroadYieldMethod
    ) -> None:

        sorted_adjacencies = list(enumerate(adjacencies))
        if yield_method == props.CrossroadYieldMethod.NARROW_ROAD:
            sorted_adjacencies = sorted(
                sorted_adjacencies, key=lambda adj: adj[1].segment.type_.road_surface_width)
        elif yield_method == props.CrossroadYieldMethod.SHORTER_SEGMENT:
            sorted_adjacencies = sorted(
                sorted_adjacencies, key=lambda adj: adj[1].segment.spline.calc_length())
        else:
            raise ValueError(
                f"Unsupported yield method for creating crossroad signs {yield_method}")

        # First two of the sorted adjacencies are the major road, other are the second
        for i, adj in sorted_adjacencies:
            mod: bpy.types.NodesModifier = cx_root_obj.modifiers.new(
                f"Control Sign {i}", type='NODES')
            mod.node_group = self.cx_instance_ng
            mod_inputs_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
            # Offset by a meter of the road surface width
            mod_inputs_view.set_input_value(
                "Offset", (adj.segment.type_.road_surface_width / 2.0) + 1)
            mod_inputs_view.set_input_value("Point Index", len(sorted_adjacencies) - i - 1)
            # In case of traffic lights we put them on each of the adjacent roads
            if cx_type == props.CrossroadType.TRAFFIC_LIGHTS:
                mod_inputs_view.set_collection_input_value(
                    "Collection", "StreetElement_Traffic-Light_3+3-570cm")
                continue

            # Add priority signs to the first two roads (as the other ones are narrower or
            # have smaller segments), and additional roads will have either yield or stop signs
            if i <= 1:
                mod_inputs_view.set_collection_input_value(
                    "Collection", "StreetSign_Priority_Priority-Road")
            else:
                if cx_type == props.CrossroadType.YIELD:
                    mod_inputs_view.set_collection_input_value(
                        "Collection", "StreetSign_Priority_Yield")
                elif cx_type == props.CrossroadType.STOP:
                    mod_inputs_view.set_collection_input_value(
                        "Collection", "StreetSign_Priority_Stop")
                # Traffic Lights should be already handled and skipped at this point
                else:
                    raise ValueError(f"Unknown CrossroadType {cx_type}")
