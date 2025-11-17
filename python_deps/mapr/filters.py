# copyright (c) 2018- polygoniq xyz s.r.o.

# Base classes for filters which can be used in a query against asset provider to get assets
# based on their parameters. For example one can use:
# - NumericParameterFilter("num:width", 0.0, 10.0) - assets with '0.0 < "width" < 10.0'
# - TextParameterFilter("text:country_of_origin", {"Czechia", "Poland"}) - assets containing
#   "country_of_origin" either "Czechia" or "Poland"
# The filters defined here provide the minimal functionality needed for filtering and can be used
# without 'bpy'. The filters in `engon.browser` are their more complex implementation based
# on 'bpy' with UI state and other functionality

import abc
import functools
import typing
import mathutils
import re
import math
from . import asset
from . import asset_data
from . import parameter_meta


class Filter:
    def __init__(self, name: str):
        self.name = name
        self.name_without_type = parameter_meta.remove_type_from_name(self.name)

    def filter_(self, asset_: asset.Asset) -> bool:
        """Decides if the 'asset' should be filtered.

        Returns True if asset passes the filter, False otherwise.
        NOTE: This should consider also filtering out assets which don't have any value of the
        corresponding parameter present.
        """
        raise NotImplementedError()

    def as_dict(self) -> dict:
        """Returns a dict entry representing this filter - {key: filter-parameters}.

        The 'key' has to be unique across all the filters! The self.name is mostly used
        for that as it is prefixed by the 'type:' based on the filter.
        """
        raise NotImplementedError()


class NumericParameterFilter(Filter):
    def __init__(self, name: str, range_start: float, range_end: float):
        super().__init__(name)
        self.range_start = range_start
        self.range_end = range_end

    def filter_(self, asset_: asset.Asset) -> bool:
        if self.name_without_type not in asset_.numeric_parameters:
            return False

        return self.range_start < asset_.numeric_parameters[self.name_without_type] < self.range_end

    def as_dict(self) -> dict:
        return {self.name: {"min": self.range_start, "max": self.range_end}}


class TagFilter(Filter):
    def __init__(self, name: str):
        super().__init__(name)
        # If one instantiates the base TagFilter, they mean to filter by this tag.
        self.include = True

    def filter_(self, asset_: asset.Asset) -> bool:
        return self.name_without_type in asset_.tags

    def as_dict(self) -> dict:
        return {self.name: self.include}


class TextParameterFilter(Filter):
    def __init__(self, name: str, values: set[str]):
        super().__init__(name)
        self.values = values

    def filter_(self, asset_: asset.Asset) -> bool:
        value = asset_.text_parameters.get(self.name_without_type, None)
        if value is None:
            return False

        return value in self.values

    def as_dict(self) -> dict:
        return {self.name: list(self.values)}


class VectorComparator(abc.ABC):
    @abc.abstractmethod
    def compare(self, value: mathutils.Vector) -> bool:
        pass

    @abc.abstractmethod
    def as_dict(self) -> dict:
        """The dict representation of the comparator, has to be unique for each comparator type."""
        pass


DistanceFunction = typing.Callable[[mathutils.Vector, mathutils.Vector], float]
NamedDistanceFunction = tuple[DistanceFunction, str]


class VectorDistanceComparator(VectorComparator):
    """Compares distance of point to other point (represented as vectors) to a distance threshold.

    If the 'distance_function' is provided, then it is a tuple of the distance function and a name
    of the function. The name is used in `as_dict` representation of the comparator which is used
    for caching. Name needs to be unique otherwise cache can return incorrect results for queries
    that filter out different assets but have the same `as_dict` representation.
    """

    def __init__(
        self,
        value: mathutils.Vector,
        distance: float,
        distance_function: NamedDistanceFunction | None = None,
    ):
        self.value = value
        self.distance = distance
        if distance_function is None:
            self.distance_function = VectorDistanceComparator._euclidean_distance
            self.distance_function_name = "euclidean"
        else:
            self.distance_function = distance_function[0]
            self.distance_function_name = distance_function[1]

    def compare(self, value: mathutils.Vector) -> bool:
        if len(value) != len(self.value):
            raise ValueError("Vector length mismatch")

        return self.distance_function(value, self.value) <= self.distance

    def as_dict(self) -> dict:
        return {
            "value": tuple(self.value),
            "distance": self.distance,
            "function": self.distance_function_name,
        }

    @staticmethod
    def _euclidean_distance(a: mathutils.Vector, b: mathutils.Vector) -> float:
        return (a - b).length


class VectorLexicographicComparator(VectorComparator):
    """Compares vectors lexicographically, the min_ and max_ are inclusive"""

    def __init__(self, min_: mathutils.Vector, max_: mathutils.Vector):
        self.min_ = min_
        self.max_ = max_

    def compare(self, value: mathutils.Vector) -> bool:
        return tuple(self.min_) <= tuple(value) <= tuple(self.max_)

    def as_dict(self) -> dict:
        return {"min": tuple(self.min_), "max": tuple(self.max_), "method": "lexicographic"}


class VectorComponentWiseComparator(VectorComparator):
    """Compares vectors component-wise - each component separately, the min_ and max_ are inclusive"""

    def __init__(self, min_: mathutils.Vector, max_: mathutils.Vector):
        self.min_ = min_
        self.max_ = max_

    def compare(self, value: mathutils.Vector) -> bool:
        if len(value) != len(self.min_) != len(self.max_):
            raise ValueError("Vector length mismatch")

        # Use component wise comparison, the default comparison operators for vector compare lengths
        for i in range(len(value)):
            if not self.min_[i] <= value[i] <= self.max_[i]:
                return False

        return True

    def as_dict(self) -> dict:
        return {"min": tuple(self.min_), "max": tuple(self.max_), "method": "component-wise"}


class MapProjection(abc.ABC):
    """Projects from latitude and longitude to XY coordinates on a fixed-sized grid"""

    @property
    @abc.abstractmethod
    def max_x(self) -> int:
        pass

    @property
    @abc.abstractmethod
    def max_y(self) -> int:
        pass

    # due to rounding in the location data, we have repeated values, we can cache where possible
    @abc.abstractmethod
    def project(self, latitude: float, longitude: float) -> tuple[int, int]:
        """Projects latitude and longitude to XY coordinates on the grid"""
        pass

    @property
    @abc.abstractmethod
    def crop(self) -> tuple[int, int, int, int]:
        """Returns the crop of the map projection - top, bottom, left, right"""
        return (0, 0, 0, 0)


class MercatorProjection(MapProjection):
    """Implements 16x16 grid Mercator projection between 85S and 85N."""

    @property
    def max_x(self) -> int:
        return 16

    @property
    def max_y(self) -> int:
        return 16

    @property
    def crop(self) -> tuple[int, int, int, int]:
        """Returns the crop of the map projection - top, bottom, left, right"""
        return (0, 4, 0, 0)  # bottom - antarctica

    # due to rounding in the location data, we have repeated values, we can use caching
    @functools.cache
    def project_x(self, longitude: float) -> int:
        """Projects longitude to X coordinate on the grid."""
        if longitude < -180 or longitude > 180:
            longitude = max(-180, min(180, longitude))

        return int((longitude + 180) / 360 * self.max_x)

    # due to rounding in the location data, we have repeated values, we can use caching
    @functools.cache
    def project_y(self, latitude: float) -> int:
        """Projects latitude to Y coordinate on the grid."""
        if latitude < -85 or latitude > 85:
            latitude = max(-85, min(85, latitude))

        lat_rads = math.radians(latitude)
        return int(
            (1 - math.log(math.tan(lat_rads) + 1 / math.cos(lat_rads)) / math.pi) / 2 * self.max_y
        )

    def project(self, latitude: float, longitude: float) -> tuple[int, int]:
        """Projects latitude and longitude to XY coordinates on the grid.

        Implements Mercator projection, see https://en.wikipedia.org/wiki/Mercator_projection.
        The projection is clamped to +/-85 degrees latitude. Median is 0 degrees (greenwich).

        """

        return self.project_x(longitude), self.project_y(latitude)


class LocationParameterFilter(Filter):
    """Checks if the location contains at least one of the selected tiles"""

    map_projection = MercatorProjection()

    def __init__(
        self,
        name: str,
        selected_tiles: list[list[bool]],
    ):
        super().__init__(name)
        self.selected_tiles = selected_tiles

    def filter_(self, asset_: asset.Asset) -> bool:
        projection = LocationParameterFilter.map_projection
        asset_locations = asset_.location_parameters.get(self.name_without_type)

        if asset_locations is None:
            return False

        selected_tiles = self.selected_tiles
        for lat, lon in asset_locations:
            x, y = projection.project(lat, lon)
            if selected_tiles[y][x]:
                return True

        return False

    def as_dict(self) -> dict:
        return {self.name: self.selected_tiles}


class VectorParameterFilter(Filter):
    def __init__(
        self,
        name: str,
        comparator: VectorComparator,
    ):
        super().__init__(name)
        self.comparator = comparator

    def filter_(self, asset_: asset.Asset) -> bool:
        value = asset_.vector_parameters.get(self.name_without_type, None)
        if value is None:
            return False

        return self.comparator.compare(mathutils.Vector(value))

    def as_dict(self) -> dict:
        return {self.name: self.comparator.as_dict()}


class AssetTypesFilter(Filter):
    def __init__(
        self,
        model: bool = True,
        material: bool = True,
        particle_system: bool = True,
        scene: bool = True,
        world: bool = True,
        geometry_nodes: bool = True,
    ):
        super().__init__("builtin:asset_types")
        self.model = model
        self.material = material
        self.particle_system = particle_system
        self.scene = scene
        self.world = world
        self.geometry_nodes = geometry_nodes

    def filter_(self, asset_: asset.Asset) -> bool:
        type_ = asset_.type_
        return any(
            [
                type_ == asset_data.AssetDataType.blender_model and self.model,
                type_ == asset_data.AssetDataType.blender_material and self.material,
                type_ == asset_data.AssetDataType.blender_particle_system and self.particle_system,
                type_ == asset_data.AssetDataType.blender_scene and self.scene,
                type_ == asset_data.AssetDataType.blender_world and self.world,
                type_ == asset_data.AssetDataType.blender_geometry_nodes and self.geometry_nodes,
            ]
        )

    def as_dict(self) -> dict:
        return {self.name: self._all}

    @property
    def _all(self) -> tuple:
        return (
            self.model,
            self.material,
            self.particle_system,
            self.scene,
            self.world,
            self.geometry_nodes,
        )


SEARCH_ASSET_SCORE: dict[str, float] = {}


class SearchFilter(Filter):
    def __init__(self, search: str):
        super().__init__("builtin:search")
        self.search = search
        self.needle_keywords = SearchFilter.keywords_from_search(search)

    def filter_(self, asset_: asset.Asset) -> bool:
        EXACT_MATCH_COEFFICIENT = 5.0
        PREFIX_MATCH_COEFFICIENT = 3.0
        INFIX_MATCH_COEFFICIENT = 2.0
        SUFFIX_MATCH_COEFFICIENT = 2.0

        SUBSEQUENT_MATCH_COEFFICIENT = 5.0
        MULTIPLE_MATCH_COEFFICIENT = 1.0

        def get_affix_score(
            needle_keyword: str,
            haystack_keyword: str,
            haystack_keyword_weight: float,
            require_exact_match: bool,
        ) -> float:
            affix_score = 0.0
            if require_exact_match:
                if haystack_keyword == needle_keyword[1:-1]:
                    affix_score = haystack_keyword_weight * EXACT_MATCH_COEFFICIENT
                return affix_score

            index = haystack_keyword.find(needle_keyword)
            if index == -1:
                # no match
                return affix_score
            if index == 0 and len(haystack_keyword) == len(needle_keyword):
                # bump exact matches even if exact match not requested
                affix_score = EXACT_MATCH_COEFFICIENT * haystack_keyword_weight
            elif index == 0:
                # prefix match
                affix_score = PREFIX_MATCH_COEFFICIENT * haystack_keyword_weight
            elif index < len(haystack_keyword) - len(needle_keyword):
                # infix match
                affix_score = INFIX_MATCH_COEFFICIENT * haystack_keyword_weight
            else:
                # suffix match
                affix_score = SUFFIX_MATCH_COEFFICIENT * haystack_keyword_weight
            return affix_score

        def get_multiplicity_score(
            subsequent_match_count: float, multiple_match_count: float
        ) -> float:
            multiplicity_score = 1.0
            if subsequent_match_count <= 1 and multiple_match_count <= 1:
                return multiplicity_score
            if max_subsequent_matches >= multiple_match_count:
                multiplicity_score = SUBSEQUENT_MATCH_COEFFICIENT * max_subsequent_matches
            else:
                multiplicity_score = MULTIPLE_MATCH_COEFFICIENT * multiple_match_count
            return multiplicity_score

        # we make sure all needle keywords are present in given haystack for the haystack not to be
        # filtered

        if len(self.needle_keywords) == 0:
            return True

        max_relevancy_score = 0.0
        multiple_match_count = 0
        subsequent_match_count = 0
        max_subsequent_matches = 0

        for needle_keyword in self.needle_keywords:
            match_flag = False
            require_exact_match = needle_keyword.startswith('"') and needle_keyword.endswith('"')
            for haystack_keyword, haystack_keyword_weight in asset_.search_matter.items():
                relevancy_score = 0.0
                # this is guaranteed by the API
                assert haystack_keyword_weight > 0.0
                relevancy_score = get_affix_score(
                    needle_keyword, haystack_keyword, haystack_keyword_weight, require_exact_match
                )
                match_flag = relevancy_score > 0.0 or match_flag
                max_relevancy_score = max(max_relevancy_score, relevancy_score)

            if require_exact_match and not match_flag:
                # exclude results which do not contain keywords in quotation marks (even if other keywords would match)
                SEARCH_ASSET_SCORE[asset_.id_] = 0.0
                return False

            if match_flag:
                subsequent_match_count += 1
                multiple_match_count += 1
                max_subsequent_matches = max(max_subsequent_matches, subsequent_match_count)
            else:
                subsequent_match_count = 0

        max_relevancy_score *= get_multiplicity_score(max_subsequent_matches, multiple_match_count)

        SEARCH_ASSET_SCORE[asset_.id_] = max_relevancy_score
        return max_relevancy_score > 0.0

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def keywords_from_search(search: str) -> list[str]:
        """Returns a list of lowercase keywords to search for in the assets"""

        def translate_keywords(keywords: list[str]) -> list[str]:
            # Be careful when adding new keywords as it will make impossible to find anything using the original keyword.
            # E.g. if we'd have tag `hdr` it would not be possible to find it now. Or anything named `hdr_something` cannot be find by `hdr`

            translator = {"hdri": "world", "hdr": "world"}

            ret: list[str] = []
            for kw in keywords:
                ret.append(translator.get(kw, kw))

            return ret

        # put search keywords to a dictionary first to prevent duplicate keywords while keeping the order in which they were searched
        keywords = {kw.lower(): None for kw in re.split(r"[ ,_\-]+", search) if kw != ""}
        return translate_keywords(list(keywords.keys()))

    def as_dict(self) -> dict:
        return {self.name: self.search}
