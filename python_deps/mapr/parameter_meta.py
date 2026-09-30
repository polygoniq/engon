# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import functools
from . import asset


class NumericParameterMeta:
    def __init__(self, name: str, value: float | int):
        self.name: str = name
        self.min_: float | int = value
        self.max_: float | int = value

    def register_value(self, value: float | int) -> None:
        self.min_ = min(value, self.min_)
        self.max_ = max(value, self.max_)

    def __repr__(self):
        return f"{self.name}: ({self.min_}, {self.max_})"


class TextParameterMeta:
    def __init__(self, name: str, value: str):
        self.name: str = name
        self.unique_values: set[str] = {value}

    def register_value(self, value: str) -> None:
        self.unique_values.add(value)

    def __repr__(self):
        return f"{self.name}: {self.unique_values}"


class VectorParameterMeta:
    def __init__(self, name: str, value: typing.Sequence[float]):
        self.name: str = name
        self.length = len(value)
        self.min_: list[float] = list(value)
        self.max_: list[float] = list(value)

    def register_value(self, value: typing.Sequence[float]) -> None:
        # The vector length should be the same for all values of one parameter
        assert len(value) == self.length
        min_, max_ = self.min_, self.max_
        for i in range(self.length):
            v = value[i]
            if v < min_[i]:
                min_[i] = v
            elif v > max_[i]:
                max_[i] = v

    def __repr__(self):
        return f"{self.name}: Length: {self.length} Min: {self.min_} Max: {self.max_}"


class LocationParameterMeta:
    def __init__(self, name: str, value: tuple[tuple[float, ...,], ...]) -> None:  # fmt: skip
        self.name: str = name

    def register_value(self, value: tuple[tuple[float, ...], ...]) -> None:
        # nothing to do here, keep the function for consistency
        pass

    def __repr__(self) -> str:
        return f"{self.name}"


class ParameterRanges(typing.NamedTuple):
    numeric: dict[str, NumericParameterMeta]
    text: dict[str, TextParameterMeta]
    vector: dict[str, VectorParameterMeta]
    location: dict[str, LocationParameterMeta]


class AssetParametersMeta:
    """Stores and provides meta (ranges, values, ...) information about parameters and tags.

    All parameters or tags present here are prefixed by a string describing their respective type
    so the information isn't lost when working with the parameter names only. E. g.:
    - 'num:width', 'num:image_count'
    - 'text:bpy.data.version'
    - 'tag:outdoor'
    - 'scoped_tag:style::modernism'

    The unique parameter names and tags are constructed right away. The expensive per-parameter
    metadata are constructed lazily on demand and cached.

    Tags are split into 'unique_tags' (unscoped, prefixed 'tag:') and 'unique_scoped_tags'
    (prefixed 'scoped_tag:') - see 'asset.parse_scoped_tag' for the "scope::value" tag format.
    'unique_scopes' additionally holds just the scopes (prefixed 'scoped_tag:') of
    'unique_scoped_tags', with no value - e.g. 'scoped_tag:style' for 'scoped_tag:style::modernism'.
    This is included in 'unique_parameter_names' so that scope-grouping filters can be matched by
    name the same way as any other filter, without having to special-case them by type.
    """

    def __init__(self, assets: typing.Sequence[asset.Asset]):
        # This references the original assets from DataView if it a tuple is passed in.
        # If a list is passed in, we make a tuple copy to ensure immutability.
        self._assets: tuple[asset.Asset, ...] = tuple(assets)

        # Collect raw names first, then construct the unique names with prefixes.
        # This way we don't have to check for the existence of the unique name in the loop and
        # can just construct it directly as a set operation.
        numeric_names: set[str] = set()
        text_names: set[str] = set()
        vector_names: set[str] = set()
        location_names: set[str] = set()
        tags: set[str] = set()
        for asset_ in self._assets:
            numeric_names.update(asset_.numeric_parameters)
            text_names.update(asset_.text_parameters)
            vector_names.update(asset_.vector_parameters)
            location_names.update(asset_.location_parameters)
            tags.update(asset_.tags)

        self.unique_tags: set[str] = set()
        self.unique_scoped_tags: set[str] = set()
        self.unique_scopes: set[str] = set()
        for tag in tags:
            scope, _ = asset.parse_scoped_tag(tag)
            if scope is None:
                self.unique_tags.add(f"tag:{tag}")
            else:
                self.unique_scoped_tags.add(f"scoped_tag:{tag}")
                self.unique_scopes.add(f"scoped_tag:{scope}")

        self.unique_parameter_names: set[str] = set()
        self.unique_parameter_names.update(f"num:{n}" for n in numeric_names)
        self.unique_parameter_names.update(f"text:{n}" for n in text_names)
        self.unique_parameter_names.update(f"vec:{n}" for n in vector_names)
        self.unique_parameter_names.update(f"loc:{n}" for n in location_names)
        self.unique_parameter_names.update(self.unique_tags)
        self.unique_parameter_names.update(self.unique_scoped_tags)
        self.unique_parameter_names.update(self.unique_scopes)

    @functools.cached_property
    def _ranges(self) -> ParameterRanges:
        numeric: dict[str, NumericParameterMeta] = {}
        text: dict[str, TextParameterMeta] = {}
        vector: dict[str, VectorParameterMeta] = {}
        location: dict[str, LocationParameterMeta] = {}

        for asset_ in self._assets:
            for param, value in asset_.numeric_parameters.items():
                unique_name = f"num:{param}"
                if unique_name not in numeric:
                    numeric[unique_name] = NumericParameterMeta(unique_name, value)
                else:
                    numeric[unique_name].register_value(value)

            for param, value in asset_.text_parameters.items():
                unique_name = f"text:{param}"
                if unique_name not in text:
                    text[unique_name] = TextParameterMeta(unique_name, value)
                else:
                    text[unique_name].register_value(value)

            for param, value in asset_.vector_parameters.items():
                unique_name = f"vec:{param}"
                if unique_name not in vector:
                    vector[unique_name] = VectorParameterMeta(unique_name, value)
                else:
                    vector[unique_name].register_value(value)

            for param, value in asset_.location_parameters.items():
                unique_name = f"loc:{param}"
                if unique_name not in location:
                    location[unique_name] = LocationParameterMeta(unique_name, value)
                else:
                    location[unique_name].register_value(value)

        return ParameterRanges(numeric, text, vector, location)

    @property
    def numeric(self) -> dict[str, NumericParameterMeta]:
        return self._ranges.numeric

    @property
    def text(self) -> dict[str, TextParameterMeta]:
        return self._ranges.text

    @property
    def vector(self) -> dict[str, VectorParameterMeta]:
        return self._ranges.vector

    @property
    def location(self) -> dict[str, LocationParameterMeta]:
        return self._ranges.location

    def __repr__(self) -> str:
        import pprint

        pp = pprint.PrettyPrinter(depth=4)
        return (
            f"{self.__class__.__name__} at {id(self)}:\n"
            f"{pp.pformat(self.numeric)}\n{pp.pformat(self.text)}\n"
            f"{pp.pformat(self.vector)}\n{pp.pformat(self.location)}\n"
            f"{self.unique_tags}\nUnique Names: {self.unique_parameter_names}"
        )


def remove_type_from_name(name: str) -> str:
    """Returns parameter name without the type prefix.

    For example:
    'tag:Outdoor' -> 'Outdoor'
    """
    return ":".join(name.split(":")[1:])
