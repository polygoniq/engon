# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import mathutils
from . import asset


class NumericParameterMeta:
    def __init__(self, name: str, value: typing.Union[float, int]):
        self.name: str = name
        self.min_: typing.Union[float, int] = value
        self.max_: typing.Union[float, int] = value

    def register_value(self, value: typing.Union[float, int]) -> None:
        self.min_ = min(value, self.min_)
        self.max_ = max(value, self.max_)

    def __repr__(self):
        return f"{self.name}: ({self.min_}, {self.max_})"


class TextParameterMeta:
    def __init__(self, name: str, value: str):
        self.name: str = name
        self.unique_values: typing.Set[str] = {value}

    def register_value(self, value: str) -> None:
        self.unique_values.add(value)

    def __repr__(self):
        return f"{self.name}: {self.unique_values}"


class VectorParameterMeta:
    def __init__(self, name: str, value: mathutils.Vector):
        self.name: str = name
        self.length = len(value)
        self.min_ = value
        self.max_ = value

    def register_value(self, value: mathutils.Vector) -> None:
        # The vector length should be the same for all values of one parameter
        assert len(value) == self.length
        self.min_ = mathutils.Vector(min(value[i], self.min_[i]) for i in range(self.length))
        self.max_ = mathutils.Vector(max(value[i], self.max_[i]) for i in range(self.length))

    def __repr__(self):
        return f"{self.name}: Length: {self.length} Min: {self.min_} Max: {self.max_}"


class AssetParametersMeta:
    """Stores and provides meta (ranges, values, ...) information about parameters and tags.

    All parameters or tags present here are prefixed by a string describing their respective type
    so the information isn't lost when working with the parameter names only. E. g.:
    - 'num:width', 'num:image_count'
    - 'text:bpy.data.version'
    - 'tag:outdoor'
    """

    def __init__(self, assets: typing.Iterable[asset.Asset]):
        self.numeric: typing.Dict[str, NumericParameterMeta] = {}
        self.text: typing.Dict[str, TextParameterMeta] = {}
        self.vector: typing.Dict[str, VectorParameterMeta] = {}
        self.unique_tags: typing.Set[str] = set()
        self.unique_parameter_names: typing.Set[str] = set()

        for asset_ in assets:
            for param, value in asset_.numeric_parameters.items():
                unique_name = f"num:{param}"
                if unique_name not in self.numeric:
                    self.numeric[unique_name] = NumericParameterMeta(unique_name, value)
                else:
                    self.numeric[unique_name].register_value(value)

            for param, value in asset_.text_parameters.items():
                unique_name = f"text:{param}"
                if unique_name not in self.text:
                    self.text[unique_name] = TextParameterMeta(unique_name, value)
                else:
                    self.text[unique_name].register_value(value)

            for param, value in asset_.vector_parameters.items():
                unique_name = f"vec:{param}"
                if unique_name not in self.vector:
                    self.vector[unique_name] = VectorParameterMeta(
                        unique_name, mathutils.Vector(value))
                else:
                    self.vector[unique_name].register_value(mathutils.Vector(value))

            self.unique_tags.update({f"tag:{t}" for t in asset_.tags})

        self.unique_parameter_names.update(self.text)
        self.unique_parameter_names.update(self.numeric)
        self.unique_parameter_names.update(self.vector)
        self.unique_parameter_names.update(self.unique_tags)

    def __repr__(self) -> str:
        import pprint
        pp = pprint.PrettyPrinter(depth=4)
        return f"{self.__class__.__name__} at {id(self)}:\n" \
            f"{pp.pformat(self.numeric)}\n{pp.pformat(self.text)}\n{pp.pformat(self.vector)}\n"\
            f"{self.unique_tags}\nUnique Names: {self.unique_parameter_names}"


def remove_type_from_name(name: str) -> str:
    """Returns parameter name without the type prefix.

    For example:
    'tag:Outdoor' -> 'Outdoor'
    """
    return ":".join(name.split(":")[1:])
