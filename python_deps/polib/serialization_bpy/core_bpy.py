# copyright (c) 2018- polygoniq xyz s.r.o.

from . import errors
import abc
import typing
import bpy
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


SimpleJSONConvertible = str | int | float | bool

JSONConvertible = typing.Union[
    SimpleJSONConvertible,
    list['JSONConvertible'],
    list[str],  # This is already covered, but type checkers are not smart enough
    dict[str, 'JSONConvertible'],
]

T = typing.TypeVar('T')
VectorT = typing.TypeVar("VectorT", bool, int, float)
VectorSize = typing.TypeVar("VectorSize", bound=list[int])


class VectorProp(typing.Generic[VectorT, VectorSize], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(f"{cls} is intended to be used as a type and cannot be instantiated")


class CollectionProp(typing.Generic[T], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(f"{cls} is intended to be used as a type and cannot be instantiated")


class PointerProp(typing.Generic[T], abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(f"{cls} is intended to be used as a type and cannot be instantiated")


class EnumFlagProp(abc.ABC):
    def __new__(cls, *args, **kwargs):
        raise TypeError(f"{cls} is intended to be used as a type and cannot be instantiated")


def _serialize_simple(attr: typing.Any, serialization_type: type) -> SimpleJSONConvertible:
    assert serialization_type in typing.get_args(
        SimpleJSONConvertible
    ), f"Serialization type '{serialization_type}' is not a simple type"

    # Ensure strict int type (bool is also an int)
    if serialization_type is int:
        if not isinstance(attr, int) or isinstance(attr, bool):
            raise errors.SerializationError(attr, f"'{attr}' is not of type {int}")
    # Other types can be checked directly
    elif not isinstance(attr, serialization_type):
        raise errors.SerializationError(attr, f"'{attr}' is not of type '{serialization_type}'")
    return attr


def _serialize_enum_flag(attr: typing.Any, serialization_type: type) -> list[str]:
    assert (
        serialization_type is EnumFlagProp
    ), f"Serialization type '{serialization_type}' is not a flag enum type"
    if not isinstance(attr, set):
        raise errors.SerializationError(attr, f"'{attr}' is not of type {set}")
    if not all(isinstance(x, str) for x in attr):
        raise errors.SerializationError(attr, f"'{attr}' is not a {set[str]}")
    return list(attr)


def _serialize_vector(attr: typing.Any, serialization_type: type) -> list[JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is VectorProp
    ), f"Serialization type '{serialization_type}' is not a vector type"
    if not isinstance(attr, bpy.types.bpy_prop_array):
        raise errors.SerializationError(attr, f"'{attr}' is not of type {bpy.types.bpy_prop_array}")
    item_type, size = typing.get_args(serialization_type)
    if len(attr) != size[0]:
        raise errors.SerializationError(
            attr, f"Vector length mismatch: expected {size[0]} items, got {len(attr)}"
        )
    if len(size) == 1:
        # 1D vector or last dimension of a multi-dimensional vector
        if any(not isinstance(x, item_type) for x in attr):
            raise errors.SerializationError(
                attr,
                f"Vector contains invalid types: expected {item_type}, "
                f"got {set(map(type, attr))}",
            )
        return list(attr)
    else:
        # Multi-dimensional vector
        subvector_size = size[1:]
        return [_serialize_vector(x, VectorProp[item_type, subvector_size]) for x in attr]


def _serialize_collection(attr: typing.Any, serialization_type: type) -> list[JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is CollectionProp
    ), f"Serialization type '{serialization_type}' is not a collection type"
    item_type = typing.get_args(serialization_type)[0]
    if any(not isinstance(x, item_type) for x in attr):
        raise errors.SerializationError(
            attr,
            f"Collection contains invalid types: expected {item_type}, "
            f"got {set(map(type, attr))}",
        )
    return [serialize_instance(x) for x in attr]


def _serialize_pointer(attr: typing.Any, serialization_type: type) -> dict[str, JSONConvertible]:
    assert (
        typing.get_origin(serialization_type) is PointerProp
    ), f"Serialization type '{serialization_type}' is not a pointer type"
    pointer_type = typing.get_args(serialization_type)[0]
    if not isinstance(attr, pointer_type):
        raise errors.SerializationError(attr, f"'{attr}' is not of type {pointer_type}")
    return serialize_instance(attr)


# type origin: function for serialization of that type
SERIALIZE_FUNCTION_MAP: dict[type, typing.Callable[[typing.Any, type], JSONConvertible]] = {
    bool: _serialize_simple,
    float: _serialize_simple,
    int: _serialize_simple,
    str: _serialize_simple,
    EnumFlagProp: _serialize_enum_flag,
    VectorProp: _serialize_vector,
    CollectionProp: _serialize_collection,
    PointerProp: _serialize_pointer,
}


def serialize_instance(instance) -> dict[str, JSONConvertible]:
    """Serialize an instance of a class that has its own serialization rules"""
    instance_type = type(instance)
    serialized_properties = getattr(instance_type, "_serialized_properties", None)
    if serialized_properties is None:
        raise errors.SerializationError(
            instance,
            f"The {instance_type} class must have a '_serialized_properties' attribute. "
            "Is this class supposed to be serialized? "
            "Does it have the 'serializable_class' decorator?",
        )

    # Attempt to serialize each property specified in '_serialized_properties'
    serialized_data: dict[str, JSONConvertible] = {}
    for prop_name, serialization_type in serialized_properties.items():
        if not hasattr(instance, prop_name):
            raise errors.AttributeSerializationError(
                instance,
                prop_name,
                f"Property '{prop_name}' not found in the {instance}",
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
            raise errors.AttributeSerializationError(
                instance,
                prop_name,
                f"Serialization type {serialization_type} is not supported",
            )

        # Serialize the attribute
        attr = getattr(instance, prop_name)
        try:
            serialized_data[prop_name] = serialize_function(attr, serialization_type)
        except Exception as e:
            raise errors.AttributeSerializationError(
                instance,
                prop_name,
                f"Failed to serialize '{prop_name}' of type {serialization_type}",
            ) from e
    return serialized_data


def _deserialize_simple(
    instance: typing.Any,
    attr_name: str,
    data: typing.Any,
    serialization_type: type,
    strict_mode: bool,
) -> None:
    assert serialization_type in typing.get_args(
        SimpleJSONConvertible
    ), f"Serialization type '{serialization_type}' is not a simple type"

    # Check attribute type
    attr = getattr(instance, attr_name, None)
    assert attr is not None, f"'{attr_name}' attribute not found in '{type(instance).__name__}'"
    if not isinstance(attr, serialization_type):
        raise errors.DeserializationError(attr, f"'{attr}' is not of type {serialization_type}")

    # Check data type
    if serialization_type is float:
        expected_types = (float, int)  # Allow to deserialize int into float property
    else:
        expected_types = (serialization_type,)
    if not isinstance(data, expected_types):
        raise errors.DataDeserializationError(
            instance,
            attr_name,
            f"Expected {serialization_type}, got {type(data)}",
        )
    setattr(instance, attr_name, data)


def _deserialize_enum_flag(
    instance: typing.Any,
    attr_name: str,
    data: typing.Any,
    serialization_type: type,
    strict_mode: bool,
) -> None:
    assert (
        serialization_type is EnumFlagProp
    ), f"Serialization type '{serialization_type}' is not a flag enum type"

    # Check attribute type
    attr = getattr(instance, attr_name, None)
    assert attr is not None, f"'{attr_name}' attribute not found in {type(instance)}"
    if not isinstance(attr, set):
        raise errors.DeserializationError(attr, f"'{attr}' is not of type {set}.")

    # Check data type
    if not isinstance(data, list):
        raise errors.DataDeserializationError(
            instance,
            attr_name,
            f"Expected a {list[str]} for enum flag deserialization, got {type(data)}",
        )
    if not all(isinstance(x, str) for x in data):
        raise errors.DataDeserializationError(
            instance,
            attr_name,
            f"Expected a {list[str]} for enum flag deserialization, "
            f"got list of {set(map(type, data))}",
        )

    setattr(instance, attr_name, set(data))


def _deserialize_vector_rec(data: typing.Any, size: list[int], item_type: type) -> tuple:
    assert len(size) > 0, "Unsupported vector size: '{size}'"

    # Note: we don't have enough information for proper DataDeserializationError here,
    # the proper exception will be re-raised by the '_deserialize_vector' function
    if not isinstance(data, list):
        raise errors.DataDeserializationError(
            None, "", f"Expected a {list} for vector deserialization, got {type(data)}"
        )
    if len(data) != size[0]:
        raise errors.DataDeserializationError(
            None, "", f"Vector size mismatch: expected {size[0]} items, data has {len(data)}"
        )

    if len(size) == 1:
        if not all(isinstance(x, item_type) for x in data):
            raise errors.DataDeserializationError(
                None,
                "",
                f"Vector data contains invalid types: expected {item_type}, "
                f"got {set(map(type, data))}",
            )
        return tuple(data)
    else:
        subvector_size = size[1:]
        return tuple(_deserialize_vector_rec(x, subvector_size, item_type) for x in data)


def _deserialize_vector(
    instance: typing.Any,
    attr_name: str,
    data: typing.Any,
    serialization_type: type,
    strict_mode: bool,
) -> None:
    assert (
        typing.get_origin(serialization_type) is VectorProp
    ), f"Serialization type '{serialization_type}' is not a vector type"

    item_type, size = typing.get_args(serialization_type)

    # Check attribute type
    attr = getattr(instance, attr_name, None)
    assert attr is not None, f"'{attr_name}' attribute not found in '{type(instance).__name__}'"
    if not isinstance(attr, bpy.types.bpy_prop_array):
        raise errors.DeserializationError(attr, f"'{attr}' is not a {bpy.types.bpy_prop_array}")
    attr_item = attr[0]
    while type(attr_item) is bpy.types.bpy_prop_array:
        attr_item = attr_item[0]
    if not isinstance(attr_item, item_type):
        raise errors.DeserializationError(
            attr,
            f"'{attr}' is not a vector of {item_type}",
        )

    # Deserialize the vector data
    try:
        deserialized_vector = _deserialize_vector_rec(data, size, item_type)
    except errors.DataDeserializationError as e:
        # Fill in relevant information for the exception
        e.serialized_obj = instance
        e.attribute_name = attr_name
        raise e
    setattr(instance, attr_name, deserialized_vector)


def _deserialize_collection(
    instance: typing.Any,
    attr_name: str,
    data: typing.Any,
    serialization_type: type,
    strict_mode: bool,
) -> None:
    assert (
        typing.get_origin(serialization_type) is CollectionProp
    ), f"Serialization type '{serialization_type}' is not a collection type"

    item_type = typing.get_args(serialization_type)[0]

    # Check attribute type
    collection = getattr(instance, attr_name)
    assert (
        collection is not None
    ), f"'{attr_name}' attribute not found in '{type(instance).__name__}'"
    if not isinstance(collection, bpy.types.bpy_prop_collection):
        raise errors.DeserializationError(collection, f"'{collection}' is not a collection")
    if not hasattr(collection, "add") or not hasattr(collection, "clear"):
        raise errors.DeserializationError(
            collection, f"'{collection}' is not a user defined collection"
        )
    if not isinstance(collection.add(), item_type):  # type: ignore
        raise errors.DeserializationError(
            collection, f"'{collection}' is not a user defined collection of {item_type}"
        )

    # Check data type (item type is checked in the deserialization loop)
    if not isinstance(data, list):
        raise errors.DataDeserializationError(
            instance, attr_name, f"Expected a {list} for '{attr_name}', got {type(data)}"
        )

    # Clear the collection and insert new deserialized items
    deserialization_errors = []
    collection.clear()  # type: ignore
    for i, item_data in enumerate(data):
        collection_item = collection.add()  # type: ignore
        try:
            if not isinstance(collection_item, item_type):
                raise errors.DataDeserializationError(
                    instance,
                    attr_name,
                    f"Collection item is not a {item_type}",
                )
            deserialize_instance(collection_item, item_data, strict_mode)
        except Exception as e:
            error = errors.AttributeDeserializationError(
                collection,
                str(i),
                f"Failed to deserialize collection item of type {item_type}",
            )
            error.__cause__ = e
            deserialization_errors.append(error)

    if len(deserialization_errors) > 0:
        raise errors.DeserializationErrorGroup(
            collection,
            f"One or more deserialization errors occurred while deserializing collection.",
            deserialization_errors,
        )


def _deserialize_pointer(
    instance: typing.Any,
    attr_name: str,
    data: typing.Any,
    serialization_type: type,
    strict_mode: bool,
) -> None:
    assert (
        typing.get_origin(serialization_type) is PointerProp
    ), f"Serialization type '{serialization_type}' is not a pointer type"

    pointer_type = typing.get_args(serialization_type)[0]

    # Check attribute type
    attr = getattr(instance, attr_name)
    assert attr is not None, f"'{attr_name}' attribute not found in '{type(instance).__name__}'"
    if not isinstance(attr, pointer_type):
        raise errors.DeserializationError(attr, f"'{attr}' is not of type {pointer_type}")

    # Check data type
    if not isinstance(data, dict):
        raise errors.DataDeserializationError(
            instance,
            attr_name,
            f"Expected a dictionary data, got {type(data)}",
        )

    deserialize_instance(attr, data, strict_mode)


# type origin: function for serialization of that type
DESERIALIZE_FUNCTION_MAP: dict[
    type, typing.Callable[[typing.Any, str, typing.Any, type, bool], None]
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


def deserialize_instance(
    instance, data: dict[str, JSONConvertible], strict_mode: bool = True
) -> None:
    """Deserialize an instance of a class that has its own serialization rules

    Args:
        instance: The instance to deserialize into. Must have a '_serialized_properties' attribute
                  (generated e.g. by the 'serializable_class' decorator) specifying
                  which properties to deserialize.
        data: Dictionary with data to deserialize
        strict_mode: If True, all properties specified in '_serialized_properties' must be present
                     in the 'data' dictionary. If False, missing properties will be ignored and left
                     unchanged.
    """
    instance_type = type(instance)
    serialized_properties = getattr(instance_type, "_serialized_properties", None)
    if serialized_properties is None:
        raise errors.DeserializationError(
            instance,
            f"The {instance_type} must have a '_serialized_properties' attribute. "
            "Is this class supposed to be serialized? "
            "Does it have the 'serializable_class' decorator?",
        )

    # Attempt to deserialize each property specified in '_serialized_properties'
    deserialization_errors = []
    for prop_name, serialization_type in serialized_properties.items():
        try:
            if not hasattr(instance, prop_name):
                raise errors.AttributeDeserializationError(
                    instance,
                    prop_name,
                    f"Property '{prop_name}' not found in the {instance_type}",
                )
            if prop_name not in data:
                if strict_mode:
                    raise errors.DataDeserializationError(
                        instance,
                        prop_name,
                        f"Data for property '{prop_name}' not found in the provided data",
                    )
                else:
                    # Skip missing property in non-strict mode
                    logger.warning(f"Skipping missing property '{prop_name}' in non-strict mode")
                    continue

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
                raise errors.AttributeDeserializationError(
                    instance,
                    prop_name,
                    f"Serialization type {serialization_type} is not supported",
                )

            try:
                # Deserialize the attribute
                deserialize_function(
                    instance, prop_name, data[prop_name], serialization_type, strict_mode
                )
            except Exception as e:
                raise errors.AttributeDeserializationError(
                    instance,
                    prop_name,
                    f"Failed to deserialize '{prop_name}' of type {serialization_type}",
                ) from e
        except Exception as e:
            deserialization_errors.append(e)

    if len(deserialization_errors) > 0:
        raise errors.DeserializationErrorGroup(
            instance,
            "One or more deserialization errors occurred while deserializing attributes of "
            f"{instance_type}",
            deserialization_errors,
        )
