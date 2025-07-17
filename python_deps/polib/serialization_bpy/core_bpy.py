# copyright (c) 2018- polygoniq xyz s.r.o.

from . import errors
import abc
import typing


SimpleJSONConvertible = typing.Union[str, int, float, bool]

JSONConvertible = typing.Union[
    SimpleJSONConvertible,
    typing.List['JSONConvertible'],
    typing.Dict[str, 'JSONConvertible'],
]

T = typing.TypeVar('T')
VectorT = typing.TypeVar("VectorT", bool, int, float)
VectorSize = typing.TypeVar("VectorSize", bound=typing.List[int])


class VectorProp(typing.Generic[VectorT, VectorSize], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"{cls.__name__} is intended to be used as a type and cannot be instantiated"
        )


class CollectionProp(typing.Generic[T], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"{cls.__name__} is intended to be used as a type and cannot be instantiated"
        )


class PointerProp(typing.Generic[T], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"{cls.__name__} is intended to be used as a type and cannot be instantiated"
        )


class EnumFlagProp(abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"{cls.__name__} is intended to be used as a type and cannot be instantiated"
        )


def _serialize_simple(attr: typing.Any, serialization_type: typing.Type) -> SimpleJSONConvertible:
    assert serialization_type in typing.get_args(
        SimpleJSONConvertible
    ), f"Serialization type '{serialization_type}' is not a simple type"
    assert isinstance(
        attr, serialization_type
    ), f"'{attr}' is not of type '{serialization_type.__name__}'"

    return attr


def _serialize_enum_flag(attr: typing.Any, serialization_type: typing.Type) -> typing.List[str]:
    assert (
        serialization_type is EnumFlagProp
    ), f"Serialization type '{serialization_type}' is not a flag enum type"
    assert isinstance(attr, set), f"'{attr}' is not of type '{serialization_type.__name__}'"
    assert all(isinstance(x, str) for x in attr), f"'{attr}' is not a set of strings"

    return list(attr)


def _serialize_vector(
    attr: typing.Any, serialization_type: typing.Type
) -> typing.List[JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is VectorProp
    ), f"Serialization type '{serialization_type}' is not a vector type"

    item_type, size = typing.get_args(serialization_type)
    assert len(attr) == size[0], f"Vector length mismatch: expected {size[0]}, got {len(attr)}"
    if len(size) == 1:
        assert all(
            isinstance(x, item_type) for x in attr
        ), f"Vector contains invalid types: expected {item_type}, got {set(map(type, attr))}"
        return list(attr)
    else:
        subvector_size = size[1:]
        return [_serialize_vector(x, VectorProp[item_type, subvector_size]) for x in attr]


def _serialize_collection(
    attr: typing.Any, serialization_type: typing.Type
) -> typing.List[JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is CollectionProp
    ), f"Serialization type '{serialization_type}' is not a collection type"

    item_type = typing.get_args(serialization_type)[0]
    assert all(
        isinstance(x, item_type) for x in attr
    ), f"Collection contains invalid types: expected {item_type}, got {set(map(type, attr))}"

    return [serialize_instance(x) for x in attr]


def _serialize_pointer(
    attr: typing.Any, serialization_type: typing.Type
) -> typing.Dict[str, JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is PointerProp
    ), f"Serialization type '{serialization_type}' is not a pointer type"

    pointer_type = typing.get_args(serialization_type)[0]
    assert isinstance(attr, pointer_type), f"'{attr}' is not of type '{pointer_type.__name__}'"

    return serialize_instance(attr)


# type origin: function for serialization of that type
SERIALIZE_FUNCTION_MAP: typing.Dict[
    typing.Type, typing.Callable[[typing.Any, typing.Type], JSONConvertible]
] = {
    bool: _serialize_simple,
    float: _serialize_simple,
    int: _serialize_simple,
    str: _serialize_simple,
    EnumFlagProp: _serialize_enum_flag,  # type: ignore
    VectorProp: _serialize_vector,
    CollectionProp: _serialize_collection,
    PointerProp: _serialize_pointer,
}


def serialize_instance(instance) -> typing.Dict[str, JSONConvertible]:
    """Serialize an instance of a class that has its own serialization rules"""
    instance_type = type(instance)
    serialized_properties = getattr(instance_type, "_serialized_properties", None)
    if serialized_properties is None:
        raise errors.SerializationError(
            f"The '{instance_type.__name__}' class must have a '_serialized_properties' attribute. "
            "Is this class supposed to be serialized? "
            "Does it have the `serializable_class` decorator?"
        )

    # Attempt to serialize each property specified in '_serialized_properties'
    serialized_data: typing.Dict[str, JSONConvertible] = {}
    for prop_name, serialization_type in serialized_properties.items():
        if not hasattr(instance, prop_name):
            raise errors.SerializationError(
                f"Property '{prop_name}' not found in the '{instance.__name__}' object"
            )

        # Get the correct serialization function for the 'serialization_type'
        serialization_type_origin = typing.get_origin(serialization_type)
        serialize_function = SERIALIZE_FUNCTION_MAP.get(
            (
                serialization_type_origin
                if serialization_type_origin is not None
                else serialization_type
            ),
            None,
        )
        if serialize_function is None:
            raise errors.SerializationError(
                f"Serialization type '{serialization_type}' is not supported"
            )

        # Serialize the attribute
        attr = getattr(instance, prop_name)
        try:
            serialized_data[prop_name] = serialize_function(attr, serialization_type)
        except errors.SerializationError as e:
            raise errors.SerializationError(
                f"Failed to serialize '{prop_name}' of type '{serialization_type}'"
            ) from e
    return serialized_data


def _deserialize_simple(
    instance: typing.Any, attr_name: str, data: typing.Any, serialization_type: typing.Type
) -> None:
    assert serialization_type in typing.get_args(
        SimpleJSONConvertible
    ), f"Serialization type '{serialization_type}' is not a simple type"
    assert hasattr(
        instance, attr_name
    ), f"'{attr_name}' is not an attribute of '{instance.__name__}'"

    if serialization_type is float:
        expected_types = (float, int)  # Allow to deserialize int into float property
    else:
        expected_types = serialization_type

    if not isinstance(data, expected_types):
        raise errors.DeserializationError(
            f"Data '{data}' is not of type '{serialization_type.__name__}'"
        )
    setattr(instance, attr_name, data)


def _deserialize_enum_flag(
    instance: typing.Any, attr_name: str, data: typing.Any, serialization_type: typing.Type
) -> None:
    assert (
        serialization_type is EnumFlagProp
    ), f"Serialization type '{serialization_type}' is not a flag enum type"
    assert hasattr(
        instance, attr_name
    ), f"'{attr_name}' is not an attribute of '{instance.__name__}'"

    if not isinstance(data, list):
        raise errors.DeserializationError(
            f"Expected a list for '{attr_name}', got '{type(data).__name__}'"
        )

    if not all(isinstance(x, str) for x in data):
        raise errors.DeserializationError(
            f"Expected a list of strings for '{attr_name}', got list of '{set(map(type, data))}'"
        )

    setattr(instance, attr_name, set(data))


def _deserialize_vector_rec(
    data: typing.Any, size: typing.List[int], item_type: typing.Type
) -> typing.Tuple:
    assert len(size) > 0, "Unsupported vector size: '{size}'"

    if not isinstance(data, list):
        raise errors.DeserializationError(
            f"Expected a list for vector of size {size[0]}, got '{type(data).__name__}'"
        )
    if len(data) != size[0]:
        raise errors.DeserializationError(
            f"Vector size mismatch: expected {size[0]}, got {len(data)}"
        )

    if len(size) == 1:
        if not all(isinstance(x, item_type) for x in data):
            raise errors.DeserializationError(
                f"Vector contains invalid types: expected {item_type}, got {set(map(type, data))}"
            )
        return tuple(data)
    else:
        subvector_size = size[1:]
        return tuple(_deserialize_vector_rec(x, subvector_size, item_type) for x in data)


def _deserialize_vector(
    instance: typing.Any, attr_name: str, data: typing.Any, serialization_type: typing.Type
) -> None:
    assert (
        typing.get_origin(serialization_type) is VectorProp
    ), f"Serialization type '{serialization_type}' is not a vector type"
    assert hasattr(
        instance, attr_name
    ), f"'{attr_name}' is not an attribute of '{instance.__name__}'"

    item_type, size = typing.get_args(serialization_type)
    deserialized_vector = _deserialize_vector_rec(data, size, item_type)
    setattr(instance, attr_name, deserialized_vector)


def _deserialize_collection(
    instance: typing.Any, attr_name: str, data: typing.Any, serialization_type: typing.Type
) -> None:
    assert (
        typing.get_origin(serialization_type) is CollectionProp
    ), f"Serialization type '{serialization_type}' is not a collection type"
    assert hasattr(
        instance, attr_name
    ), f"'{attr_name}' is not an attribute of '{instance.__name__}'"

    if not isinstance(data, list):
        raise errors.DeserializationError(
            f"Expected a list for '{attr_name}', got '{type(data).__name__}'"
        )
    if not all(isinstance(x, dict) for x in data):
        raise errors.DeserializationError(
            f"Expected a list of dictionaries for '{attr_name}', got list of '{set(map(type, data))}'"
        )

    collection = getattr(instance, attr_name)
    assert collection is not None, f"'{attr_name}' attribute not found in '{instance.__name__}'"

    item_type = typing.get_args(serialization_type)[0]
    assert all(
        isinstance(x, item_type) for x in collection
    ), f"Collection contains invalid types: expected {item_type}, got {set(map(type, collection))}"

    collection.clear()
    for item_data in data:
        collection_item = collection.add()
        deserialize_instance(collection_item, item_data)


def _deserialize_pointer(
    instance: typing.Any, attr_name: str, data: typing.Any, serialization_type: typing.Type
) -> None:
    assert (
        typing.get_origin(serialization_type) is PointerProp
    ), f"Serialization type '{serialization_type}' is not a pointer type"
    assert hasattr(
        instance, attr_name
    ), f"'{attr_name}' is not an attribute of '{instance.__name__}'"

    if not isinstance(data, dict):
        raise errors.DeserializationError(
            f"Expected a dictionary for '{attr_name}', got '{type(data).__name__}'"
        )

    attr = getattr(instance, attr_name)
    assert attr is not None, f"'{attr_name}' attribute not found in '{instance.__name__}'"

    pointer_type = typing.get_args(serialization_type)[0]
    assert isinstance(attr, pointer_type), f"'{attr}' is not of type '{pointer_type.__name__}'"

    deserialize_instance(attr, data)


# type origin: function for serialization of that type
DESERIALIZE_FUNCTION_MAP: typing.Dict[
    type, typing.Callable[[typing.Any, str, typing.Any, typing.Type], None]
] = {
    bool: _deserialize_simple,
    float: _deserialize_simple,
    int: _deserialize_simple,
    str: _deserialize_simple,
    EnumFlagProp: _deserialize_enum_flag,
    VectorProp: _deserialize_vector,
    CollectionProp: _deserialize_collection,
    PointerProp: _deserialize_pointer,
}


def deserialize_instance(instance, data: typing.Dict[str, JSONConvertible]) -> None:
    """Deserialize an instance of a class that has its own serialization rules"""
    instance_type = type(instance)
    serialized_properties = getattr(instance_type, "_serialized_properties", None)
    if serialized_properties is None:
        raise errors.DeserializationError(
            f"The '{instance_type.__name__}' class must have a '_serialized_properties' attribute. "
            "Is this class supposed to be serialized? "
            "Does it have the `serializable_class` decorator?"
        )

    # Attempt to deserialize each property specified in '_serialized_properties'
    for prop_name, serialization_type in serialized_properties.items():
        if not hasattr(instance, prop_name):
            raise errors.DeserializationError(
                f"Property '{prop_name}' not found in the '{instance.__name__}' object"
            )

        # Get the correct deserialization function for the 'serialization_type'
        serialization_type_origin = typing.get_origin(serialization_type)
        deserialize_function = DESERIALIZE_FUNCTION_MAP.get(
            (
                serialization_type_origin
                if serialization_type_origin is not None
                else serialization_type
            ),
            None,
        )
        if deserialize_function is None:
            raise errors.DeserializationError(
                f"Serialization type '{serialization_type}' is not supported"
            )

        # Deserialize the attribute
        try:
            deserialize_function(instance, prop_name, data[prop_name], serialization_type)
        except errors.DeserializationError as e:
            raise errors.DeserializationError(
                f"Failed to deserialize '{prop_name}' of type '{serialization_type}'"
            ) from e
