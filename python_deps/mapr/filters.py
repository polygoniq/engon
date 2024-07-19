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

    def as_dict(self) -> typing.Dict:
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

    def as_dict(self) -> typing.Dict:
        return {self.name: {"min": self.range_start, "max": self.range_end}}


class TagFilter(Filter):
    def __init__(self, name: str):
        super().__init__(name)
        # If one instantiates the base TagFilter, they mean to filter by this tag.
        self.include = True

    def filter_(self, asset_: asset.Asset) -> bool:
        return self.name_without_type in asset_.tags

    def as_dict(self) -> typing.Dict:
        return {self.name: self.include}


class TextParameterFilter(Filter):
    def __init__(self, name: str, values: typing.Set[str]):
        super().__init__(name)
        self.values = values

    def filter_(self, asset_: asset.Asset) -> bool:
        value = asset_.text_parameters.get(self.name_without_type, None)
        if value is None:
            return False

        return value in self.values

    def as_dict(self) -> typing.Dict:
        return {self.name: list(self.values)}


class VectorComparator(abc.ABC):
    @abc.abstractmethod
    def compare(self, value: mathutils.Vector) -> bool:
        pass

    @abc.abstractmethod
    def as_dict(self) -> typing.Dict:
        """The dict representation of the comparator, has to be unique for each comparator type."""
        pass


DistanceFunction = typing.Callable[[mathutils.Vector, mathutils.Vector], float]
NamedDistanceFunction = typing.Tuple[DistanceFunction, str]


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
        distance_function: typing.Optional[NamedDistanceFunction] = None,
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

    def as_dict(self) -> typing.Dict:
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

    def as_dict(self) -> typing.Dict:
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

    def as_dict(self) -> typing.Dict:
        return {"min": tuple(self.min_), "max": tuple(self.max_), "method": "component-wise"}


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

    def as_dict(self) -> typing.Dict:
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

    def as_dict(self) -> typing.Dict:
        return {self.name: self._all}

    @property
    def _all(self) -> typing.Tuple:
        return (
            self.model,
            self.material,
            self.particle_system,
            self.scene,
            self.world,
            self.geometry_nodes,
        )


class SearchFilter(Filter):
    def __init__(self, search: str):
        super().__init__("builtin:search")
        self.search = search
        self.needle_keywords = SearchFilter.keywords_from_search(search)

    def filter_(self, asset_: asset.Asset) -> bool:
        # we make sure all needle keywords are present in given haystack for the haystack not to be
        # filtered

        if len(self.needle_keywords) == 0:
            return True

        match_found = False
        for needle_keyword in self.needle_keywords:
            for haystack_keyword, haystack_keyword_weight in asset_.search_matter.items():
                # TODO: We want to do relevancy scoring in the future but for that the entire
                #       mechanism has be moved into MAPR API

                # this is guaranteed by the API
                assert haystack_keyword_weight > 0.0

                if haystack_keyword.find(needle_keyword) >= 0:
                    match_found = True
                    break

            if match_found:
                break

        return match_found

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def keywords_from_search(search: str) -> typing.Set[str]:
        """Returns a set of lowercase keywords to search for in the assets"""

        def translate_keywords(keywords: typing.Set[str]) -> typing.Set[str]:
            # Be careful when adding new keywords as it will make impossible to find anything using the original keyword.
            # E.g. if we'd have tag `hdr` it would not be possible to find it now. Or anything named `hdr_something` cannot be find by `hdr`
            translator = {"hdri": "world", "hdr": "world"}

            ret: typing.Set[str] = set()
            for kw in keywords:
                ret.add(translator.get(kw, kw))

            return ret

        return translate_keywords({kw.lower() for kw in re.split(r"[ ,_\-]+", search) if kw != ""})

    def as_dict(self) -> typing.Dict:
        return {self.name: self.search}
