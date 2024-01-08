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

import os
import bpy
import typing
import logging
import polib
from . import asset_helpers
logger = logging.getLogger(f"polygoniq.{__name__}")


class RoadType:
    """Road type is a specific set of geometry nodes modifiers loaded at runtime

    For example road type can represent highway, rural road, city road, ...

    Road type consist of multiple modifiers, that are applied to one curve object. Those can be
    profile modifiers defining the road mesh that's beveled on curves, instancing modifiers, road
    markings modifiers and others. Road types are defined in .blend files
    (check RoadTypeBlendLoader). This class loads information from the modifiers and stores it in
    member variables for future manipulation.

    Assumptions and conventions of road type modifier stack:
    - there is at least one profile marked with 'Surface Type' == 1
    - profiles after last road surface are considered outer, others are inner
    - road markings are considered as outer if they are offset further than 1/3 of road surface
    """

    def __init__(
        self,
        name: str,
        filepath: str,
        main_obj: bpy.types.Object,
        mods_input_map: typing.Dict[str, polib.geonodes_mod_utils_bpy.NodesModifierInput]
    ):
        self.name = name
        self.filepath = filepath
        self.source_obj = main_obj
        self.curve_obj: typing.Optional[bpy.types.Object] = None
        self.mods_input_map = mods_input_map
        self.total_width = 0.0
        self.road_surface_width = 0.0
        self.road_surface_height = 0.0
        # Mappings for each modifier and each of its input and values for profiles, outer profiles
        # and road markings. The inputs are 1:1 to the library.
        self.profiles: typing.List[typing.Dict[str, typing.Any]] = []
        self.road_markings: typing.List[typing.Dict[str, typing.Any]] = []
        self.first_road_surface_material: typing.Optional[bpy.types.Material] = None

        for mod_name in mods_input_map:
            mod_input = mods_input_map[mod_name]
            if mod_input.node_group.name == asset_helpers.RoadNodegroup.RoadProfile.value:
                self._parse_profile_input(mod_input.inputs)
            if mod_input.node_group.name == asset_helpers.RoadNodegroup.Markings.value:
                self._parse_road_mark_input(mod_input.inputs)

        self.half_width = self.total_width / 2.0
        self._calculate_road_surface_properties()

        # Outer profiles are the last ones after road surface in horizontal cut
        self.outer_profiles: typing.List[typing.Dict[str, typing.Any]] = []
        for profile in reversed(self.profiles):
            # Skip profiles excluded from width stack that are offset by less than road width
            if profile["Exclude From Width Stack"] and \
               profile["Horizontal Offset"] < self.road_surface_width / 2.0:
                continue

            # If any road surface is found, then no longer consider profiles as outer
            if profile["Surface Type"] == 1:
                break

            self.outer_profiles.insert(0, profile)

        self.road_surface_materials = [
            p["Material"] for p in self.profiles if p["Surface Type"] == 1]
        self.road_markings.sort(key=lambda x: x.get("Offset", 0.0))

    def has_outer_road_markings(self) -> bool:
        """Return true if this road type has any outer markings."""
        # Consider any road markings as outer, if they are offset by at least third of
        # total road width.
        return any(m.get("Offset", 0.0) > self.road_surface_width / 3.0 for m in self.road_markings)

    def apply_to_curve(self, curve_obj: bpy.types.Object) -> None:
        """Applies modifiers of this road type to specified 'curve_obj'"""
        assert curve_obj.type == 'CURVE'
        curve_obj.modifiers.clear()
        curve_obj[asset_helpers.ROAD_TYPE_PROPERTY] = self.name
        for mod_name in self.mods_input_map:
            mod_input = self.mods_input_map[mod_name]
            mod: bpy.types.NodesModifier = curve_obj.modifiers.new(mod_name, type='NODES')
            mod.node_group = mod_input.node_group
            for input_id, (_, value) in mod_input.inputs.items():
                mod[input_id] = value

            # Reassign the nodegroup to prevent type errors from assigning integer (0-1)
            # to a boolean type input above 3.6.
            mod.node_group = mod_input.node_group

    def get_curve_obj(
        self,
        collection: typing.Optional[bpy.types.Collection] = None
    ) -> bpy.types.Object:
        """Returns curve object for this road type.

        If no object is present the object is created and linked into 'collection'."""
        if self.curve_obj is None:
            curve_data = bpy.data.curves.new(self.name, type='CURVE')
            curve_data.dimensions = '3D'
            self.curve_obj = bpy.data.objects.new(self.name, curve_data)
            self.apply_to_curve(self.curve_obj)
            if collection is not None:
                collection.objects.link(self.curve_obj)

        return self.curve_obj

    def compare_outer_cross_section(self, other: 'RoadType') -> bool:
        """Compares if this and 'other' RoadType has the the same outer profiles.

        For example this is used to decide whether we connect profiles on crossroads
        """
        if self == other:
            return True

        if len(self.outer_profiles) != len(other.outer_profiles):
            return False

        for i, outer_profile in enumerate(self.outer_profiles):
            for input_name, value in outer_profile.items():
                if input_name in {"Surface Type", "UV Scale", "UV Offset", "Auto Smooth", "Ending Length"}:
                    continue

                if other.outer_profiles[i][input_name] != value:
                    return False

        return True

    def _parse_profile_input(self, inputs: polib.geonodes_mod_utils_bpy.NodeGroupInputs) -> None:
        layer_width = 0.0
        profile_inputs = {}
        is_both_sided = False
        for input_name, value in inputs.values():
            profile_inputs[input_name] = value
            if input_name == "Width":
                layer_width += value
            elif input_name == "Gap":
                layer_width += value
            elif input_name == "Sides Generation Mode":
                is_both_sided = int(value) == 0

        # Only double the width if it is not the first layer, which always has only one side
        if is_both_sided and len(self.profiles) > 0:
            layer_width *= 2

        profile_inputs["Total Width"] = layer_width

        self.profiles.append(profile_inputs)
        self.total_width += layer_width

    def _parse_road_mark_input(self, inputs: polib.geonodes_mod_utils_bpy.NodeGroupInputs) -> None:
        marking_inputs = {}
        for input_name, value in inputs.values():
            marking_inputs[input_name] = value

        self.road_markings.append(marking_inputs)

    def _calculate_road_surface_properties(self) -> None:
        self.road_surface_width = 0.0
        self.road_surface_height = 0.0
        # Road surface width is total width of road surfaces until first non-road surface is found
        was_road_surface = False
        for i, profile in enumerate(self.profiles):
            # Surface Type value of 1 marks road surface
            is_road_surface = int(profile["Surface Type"]) == 1
            is_both_sided = int(profile["Sides Generation Mode"]) == 0
            if was_road_surface and not is_road_surface:
                break

            profile_width = profile["Width"]
            if is_both_sided and i != 0:
                profile_width *= 2

            self.road_surface_width += profile_width
            was_road_surface = is_road_surface

            # Consider last profile height
            self.road_surface_height = profile["Height"]

    def __repr__(self):
        return f"{self.__class__.__name__}: '{self.name}'"


class RoadTypeBlendLoader:
    """Loads RoadType(s) from .blend files and stores them."""

    def __init__(self):
        self.road_type_data: typing.Dict[str, RoadType] = {}

    def load_dir(self, dir_path: str) -> None:
        """Load road types from 'dir_path'

        .blend file is considered as road type if it:
        - starts with 'tq_' prefix
        - is present in the 'roads' folder
        """
        if not os.path.isdir(dir_path):
            logger.error(f"Invalid directory in load_dir {dir_path}")
            return

        for path, _, files in os.walk(dir_path):
            for f in files:
                full_path = os.path.join(path, f)
                if not self._is_road_blend(full_path):
                    continue

                try:
                    self.load_blend(full_path)
                except AssertionError:
                    logging.exception(f"'{full_path}' is not a valid road type .blend!")
                    continue

    def load_blend(self, blend_path: str):
        """Loads single road type blend file from 'blend_path'.

        Road type is loaded from modifiers of object matching the basename of the file."""
        basename_no_ext, _ = os.path.splitext(os.path.basename(blend_path))

        # Load the main object named the same as the .blend, this links all
        # dependency datablocks into current .blend
        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
            assert basename_no_ext in data_from.objects
            data_to.objects = [basename_no_ext]

        main_obj = data_to.objects[0]

        self.road_type_data[basename_no_ext] = RoadType(
            basename_no_ext,
            blend_path,
            main_obj,
            polib.geonodes_mod_utils_bpy.get_modifiers_inputs_map(main_obj.modifiers)
        )

    def get_road_type_by_name(self, name: str) -> typing.Optional[RoadType]:
        return self.road_type_data.get(name, None)

    def get_road_types(self) -> typing.List[RoadType]:
        return list(self.road_type_data.values())

    def get_road_types_as_enum_items(self) -> typing.List[typing.Tuple[str, str, str]]:
        enum_items = []
        for name, data in self.road_type_data.items():
            nice_name = name.replace("tq_", "").replace("_", " ")
            enum_items.append((
                name,
                nice_name,
                f"Road: '{nice_name}' with road surface width of '{data.road_surface_width:.0f}' "
                f"and a total width '{data.total_width:.0f}'"
            ))

        return enum_items

    def _is_road_blend(self, blend_path: str) -> bool:
        basename = os.path.basename(blend_path)
        return basename.endswith(".blend") and \
            "roads" in blend_path and \
            basename.startswith("tq_") and \
            not polib.asset_pack.is_library_blend(blend_path)


loader = RoadTypeBlendLoader()
