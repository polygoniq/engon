#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import dataclasses
import typing
import functools
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
NumericParameters = typing.Dict[str, typing.Union[float, int]]
# vector parameters consist of same-length vector values for each parameter. Can be compared and
# sorted. For example "released_in" > (5, 4, 0). The vector parameters can also contain
# color parameters (RGB), sorting for those doesn't make sense, but proximity querying like (give
# me all assets where color is close to red) does.
VectorParameters = typing.Dict[str, typing.Union[typing.Tuple[float, ...], typing.Tuple[int, ...]]]
# text parameters can have values that can only be compared for equality. for example
# "Genus" = "Abies concolor", then you can query all assets where Genus = "Abies concolor".
TextParameters = typing.Dict[str, str]


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
    preview_file: typing.Optional[file_provider.FileID] = None

    tags: typing.Set[Tag] = dataclasses.field(default_factory=set)
    numeric_parameters: NumericParameters = dataclasses.field(default_factory=dict)
    vector_parameters: VectorParameters = dataclasses.field(default_factory=dict)
    text_parameters: TextParameters = dataclasses.field(default_factory=dict)

    @functools.cached_property
    def parameters(self) -> typing.Dict[str, typing.Any]:
        """Numeric, text and vector parameters combined in one dictionary."""
        return {**self.numeric_parameters, **self.text_parameters, **self.vector_parameters}

    @functools.cached_property
    def search_matter(self) -> typing.DefaultDict[str, float]:
        """Return a dictionary of lowercase text searchable tokens, each mapped to its search weight

        Search weight 0 means excluded from search. Weight 1 is the default. Since tokens with
        weight 0 never contribute to the search we exclude them. We guarantee all tokens to map to
        weight > 0.
        """

        ret: typing.DefaultDict[str, float] = self.type_.search_matter
        ret[self.title.lower()] = max(1.0, ret[self.title.lower()])

        # The title tokens are weighted individually
        title_tokens = self.title.lower().split(" ")
        for kw in title_tokens:
            ret[kw] = max(1.0, ret[kw])

        for tag in self.tags:
            search_weight = float(known_metadata.TAGS.get(tag, {}).get("search_weight", 1.0))
            if search_weight <= 0.0:
                continue
            token = tag.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.text_parameters.items():
            search_weight = float(
                known_metadata.TEXT_PARAMETERS.get(name, {}).get("search_weight", 1.0)
            )
            if search_weight <= 0.0:
                continue
            token = value.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.numeric_parameters.items():
            search_weight = float(
                known_metadata.NUMERIC_PARAMETERS.get(name, {}).get("search_weight", 1.0)
            )
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.vector_parameters.items():
            search_weight = float(
                known_metadata.VECTOR_PARAMETERS.get(name, {}).get("search_weight", 1.0)
            )
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        return ret

    def clear_search_matter_cache(self) -> None:
        self.__dict__.pop("search_matter", None)
