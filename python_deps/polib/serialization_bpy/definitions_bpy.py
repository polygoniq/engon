# copyright (c) 2018- polygoniq xyz s.r.o.

from . import core_bpy
import typing
import dataclasses
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


@dataclasses.dataclass
class SerializedPropertyInfo:
    """Annotation object to mark a `bpy.prop` as serializable."""

    serialization_type: typing.Type
    bpy_prop: typing.Any


# Name of the bpy property: serialization type
PROP_TO_SIMPLE_SERIALIZATION_TYPE_MAP: typing.Dict[str, typing.Type] = {
    "BoolProperty": bool,
    "FloatProperty": float,
    "IntProperty": int,
    "StringProperty": str,
}

# Name of the bpy vector property: item serialization type
PROP_TO_SERIALIZATION_VECTOR_MAP: typing.Dict[str, typing.Type] = {
    "BoolVectorProperty": bool,
    "FloatVectorProperty": float,
    "IntVectorProperty": int,
}


def Serialize(
    prop: typing.Any,
) -> SerializedPropertyInfo:
    """Annotation wrapper to mark a `bpy.prop` as serializable for `serializable_class` decorator.

    All properties of a `bpy.types.PropertyGroup` marked with this annotation will be serialized.
    The class must be decorated with `serializable_class` decorator
    to generate a valid `bpy.types.PropertyGroup` class!

    Example usage:
    ```
        @serializable_class
        class MyPropertyGroup(bpy.types.PropertyGroup):
            my_int_property: Serialize(
                bpy.props.IntProperty(name="My Int")
            )
    """
    if not hasattr(prop, "function") or not hasattr(prop, "keywords"):
        raise TypeError("Property must be a bpy.props property")

    prop_name = prop.function.__name__
    if prop_name in PROP_TO_SIMPLE_SERIALIZATION_TYPE_MAP:
        # Simple property type
        return SerializedPropertyInfo(
            PROP_TO_SIMPLE_SERIALIZATION_TYPE_MAP[prop_name],
            prop,
        )
    if prop_name in PROP_TO_SERIALIZATION_VECTOR_MAP:
        # Vector property type
        vector_type = PROP_TO_SERIALIZATION_VECTOR_MAP[prop_name]
        assert "size" in prop.keywords, "VectorProperty must have a 'size' keyword argument"
        vector_size = (
            [prop.keywords["size"]]
            if isinstance(prop.keywords["size"], int)
            else prop.keywords["size"]
        )
        return SerializedPropertyInfo(
            core_bpy.VectorProp[vector_type, vector_size],
            prop,
        )
    if prop_name == "EnumProperty":
        # Enum property type
        if "options" in prop.keywords and 'ENUM_FLAG' in prop.keywords["options"]:
            return SerializedPropertyInfo(
                core_bpy.EnumFlagProp,
                prop,
            )
        return SerializedPropertyInfo(
            str,
            prop,
        )
    if prop_name == "CollectionProperty":
        # Collection/Pointer property type
        assert "type" in prop.keywords, "CollectionProperty must have a 'type' keyword argument"
        return SerializedPropertyInfo(
            core_bpy.CollectionProp[prop.keywords["type"]],
            prop,
        )
    if prop_name == "PointerProperty":
        # Pointer property type
        assert "type" in prop.keywords, "PointerProperty must have a 'type' keyword argument"
        return SerializedPropertyInfo(
            core_bpy.PointerProp[prop.keywords["type"]],
            prop,
        )

    raise ValueError(f"Unsupported property type: {prop_name}")


def _register_on_serialized_property_update(
    annotation: SerializedPropertyInfo, property_name: str
) -> None:
    """Register `self.on_serialized_property_update(context, property)` as an update callback
    of the bpy.props property from the annotation.
    """
    # TODO: add support for PointerProperty and CollectionProperty
    if annotation.serialization_type in (core_bpy.PointerProp, core_bpy.CollectionProp):
        logger.warning(
            f"Property '{property_name}' is a {annotation.serialization_type.__name__}, "
            "on_serialized_property_update callback will not be registered."
        )

    # All other properties can have an update callback
    if "update" in annotation.bpy_prop.keywords:
        # There is already an update callback => wrap it
        original_update = annotation.bpy_prop.keywords["update"]

        def wrapped_update(self, context):
            original_update(self, context)
            self.on_serialized_property_update(context, property_name=property_name)

        annotation.bpy_prop.keywords["update"] = wrapped_update
    else:
        # No update callback => register the on_serialized_property_update callback
        annotation.bpy_prop.keywords["update"] = lambda self, context: (
            self.on_serialized_property_update(context, property_name)
        )


def serializable_class(cls):
    """Decorator to extend a `bpy.types.PropertyGroup` class with serialization api.

    - Use this decorator in combination with `Serialize()` wrapper to mark properties as serializable.
    - Use this in combination with `Savable` class to add saving and loading methods.

    If the class implements `on_serialized_property_update(self, context, prop_name)` callback
    it will be every time any serialized value is updated.

    Note: This decorator can be used in combination with `Savable` class, but does not require it.
    This allows to create nested `bpy.types.PropertyGroup` classes that are serialized into one
    config file (only the top-level class should inherit from `Savable`).

    Example usage with nested property groups:
    ```
        @serializable_class
        class MySubPropertyGroup(bpy.types.PropertyGroup):
            my_int_property: Serialize(
                bpy.props.IntProperty(name="My Int")
            )

        @serializable_class
        class MyPropertyGroup(bpy.types.PropertyGroup, Savable):
            addon_name = "my_addon"
            save_version = 1

            @property
            def config_name(self) -> str:
                return "my_config"

            my_sub_property_group: Serialize(
                bpy.props.PointerProperty(type=MySubPropertyGroup)
            )

            def on_serialized_property_update(self, context: bpy.types.Context, property_name: str):
                print(f"Property '{property_name}' updated in {self.bl_idname} preferences")
    ```
    """

    # Add serialization info to the class
    cls._serialized_properties = {}
    for prop_name, annotation in cls.__annotations__.items():
        if isinstance(annotation, SerializedPropertyInfo):
            # Store serialization info about the property
            cls._serialized_properties[prop_name] = annotation.serialization_type
            # If the `cls` has a `on_serialized_property_update` method,
            # register it as a callback for the property
            if hasattr(cls, "on_serialized_property_update"):
                _register_on_serialized_property_update(annotation, prop_name)
            # "Revert" the annotation to the original bpy.props property annotation
            # so bpy can generate properties
            cls.__annotations__[prop_name] = annotation.bpy_prop

    # Add serialization methods to the class
    cls._serialize = core_bpy.serialize_instance
    cls._deserialize = core_bpy.deserialize_instance

    return cls
