#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import dataclasses
import typing
import functools
import collections
from . import file_provider
from . import asset_data
from . import known_metadata
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


AssetID = str
# assets can have any number of tags - e.g. "European" car, "Coupe" car,
# then you can combine them in queries: I want "European" "Coupe" car.
Tag = str
# numeric parameters have values that can be sorted and compared - e.g. "Car Length" of 4.6 meters
# then you can query all cars where a parameter is equal to something, in a certain range, lower
# or higher than something, etc... For example I want a car with "Car Length" < 5 meters.
NumericParameters = dict[str, float | int]
# vector parameters consist of same-length vector values for each parameter. Can be compared and
# sorted. For example "released_in" > (5, 4, 0). The vector parameters can also contain
# color parameters (RGB), sorting for those doesn't make sense, but proximity querying like (give
# me all assets where color is close to red) does.
VectorParameters = dict[str, tuple[float, ...] | tuple[int, ...]]
# text parameters can have values that can only be compared for equality. for example
# "Genus" = "Abies concolor", then you can query all assets where Genus = "Abies concolor".
TextParameters = dict[str, str]
# location parameters are a list of tuples, each tuple is a pair of floats. The tuple represents a
# location in 2D space. For example, "native_observations" = [(43.0, -98.4), (19.3, -70.3)].
# contains lat/lon pairs of native plant observations.
LocationParameters = dict[str, tuple[tuple[float, ...], ...]]


@dataclasses.dataclass(frozen=True)
class Asset:
    """Asset represents metadata of one separated, reusable piece that can be spawned into a scene

    This is usually a model, material, entire scene, node group or something else, depending on the
    target software. Asset itself contains metadata such as title, tags, previews, it is contained
    in a category, ... It does not know anything about the actual piece that will be spawned to the
    scene. That data is contained in AssetData. AssetData are owned/contained in exactly 1 Asset.
    The mapping is Asset --- 1..N --- AssetData. One Asset can have 0 or more AssetData.

    Both Asset and AssetData instances are provided by the AssetProvider.
    """

    id_: AssetID = ""
    title: str = ""
    # TODO: type_ is here as well as in asset_data that's referencing this
    type_: asset_data.AssetDataType = asset_data.AssetDataType.unknown
    preview_file: file_provider.FileID | None = None

    tags: set[Tag] = dataclasses.field(default_factory=set)
    numeric_parameters: NumericParameters = dataclasses.field(default_factory=dict)
    vector_parameters: VectorParameters = dataclasses.field(default_factory=dict)
    text_parameters: TextParameters = dataclasses.field(default_factory=dict)
    location_parameters: LocationParameters = dataclasses.field(default_factory=dict)
    # Search matter that's not coming from this asset e.g. category search matter
    foreign_search_matter: dict[str, float] = dataclasses.field(default_factory=dict)

    @functools.cached_property
    def parameters(self) -> dict[str, typing.Any]:
        """Numeric, text, vector and location parameters combined in one dictionary."""
        return {
            **self.numeric_parameters,
            **self.text_parameters,
            **self.vector_parameters,
            **self.location_parameters,
        }

    @functools.cached_property
    def search_matter(self) -> collections.defaultdict[str, float]:
        """Return a dictionary of lowercase text searchable tokens, each mapped to its search weight

        Search weight 0 means excluded from search. Since tokens with weight 0 never contribute to
        the search we exclude them. We guarantee all tokens to map to weight > 0.
        """
        TITLE_DEFAULT_WEIGHT = 2.0
        TAG_DEFAULT_WEIGHT = 1.0
        PARAMETERS_DEFAULT_WEIGHT = 0.0

        ret: collections.defaultdict[str, float] = self.type_.search_matter
        ret[self.title.lower()] = max(1.0, ret[self.title.lower()])

        # The title tokens are weighted individually
        title_tokens = self.title.lower().split(" ")
        for kw in title_tokens:
            ret[kw] = max(TITLE_DEFAULT_WEIGHT, ret[kw])

        for foreign_search_matter, weight in self.foreign_search_matter.items():
            ret[foreign_search_matter.lower()] = max(weight, ret[foreign_search_matter.lower()])

        for tag in self.tags:
            search_weight = float(
                known_metadata.TAGS.get(tag, {}).get("search_weight", TAG_DEFAULT_WEIGHT)
            )
            if search_weight <= 0.0:
                continue
            token = tag.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.text_parameters.items():
            search_weight = float(
                known_metadata.TEXT_PARAMETERS.get(name, {}).get(
                    "search_weight", PARAMETERS_DEFAULT_WEIGHT
                )
            )
            if search_weight <= 0.0:
                continue
            token = value.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.numeric_parameters.items():
            search_weight = float(
                known_metadata.NUMERIC_PARAMETERS.get(name, {}).get(
                    "search_weight", PARAMETERS_DEFAULT_WEIGHT
                )
            )
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.vector_parameters.items():
            search_weight = float(
                known_metadata.VECTOR_PARAMETERS.get(name, {}).get(
                    "search_weight", PARAMETERS_DEFAULT_WEIGHT
                )
            )
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.location_parameters.items():
            search_weight = float(
                known_metadata.LOCATION_PARAMETERS.get(name, {}).get(
                    "search_weight", PARAMETERS_DEFAULT_WEIGHT
                )
            )
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        return ret

    def clear_search_matter_cache(self) -> None:
        self.__dict__.pop("search_matter", None)
