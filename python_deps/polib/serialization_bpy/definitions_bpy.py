# copyright (c) 2018- polygoniq xyz s.r.o.

import collections
import bpy
from . import core_bpy
import typing
import collections.abc
import dataclasses
import functools
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


@dataclasses.dataclass
class SerializedPropertyInfo:
    """Annotation object to mark a `bpy.prop` as serializable."""

    serialization_type: type
    bpy_prop: typing.Any


# Name of the bpy property: serialization type
PROP_TO_SIMPLE_SERIALIZATION_TYPE_MAP: dict[str, type] = {
    "BoolProperty": bool,
    "FloatProperty": float,
    "IntProperty": int,
    "StringProperty": str,
}

# Name of the bpy vector property: item serialization type
PROP_TO_SERIALIZATION_VECTOR_MAP: dict[str, type] = {
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


def _internal_on_serialized_property_update(
    self, context: bpy.types.Context, property_name: str
) -> None:
    """Internal callback for serialized property updates.

    This method is called when a serialized property is updated.
    `on_serialized_property_update(self, context, prop_name)` will be called first if it exists.
    After that the update is propagated to owners of the serialized property if the class supports it.
    """
    if hasattr(self, "on_serialized_property_update"):
        # Call the instance method if it exists
        self.on_serialized_property_update(context, property_name)
    if hasattr(self, "_on_serialized_property_update_propagator"):
        # Propagate the update to the owner instance
        self._on_serialized_property_update_propagator(context, property_name)


def _register_on_serialized_property_update(
    annotation: SerializedPropertyInfo, property_name: str
) -> None:
    """Register `self._internal_on_serialized_property_update(context, property)`
    as an update callback of the bpy.props property from the annotation.

    Note that the propagation of the update from within collection or pointer properties
    is not propagated by default.
    """
    # CollectionProperty doesn't support update callbacks.
    if typing.get_origin(annotation.serialization_type) == core_bpy.CollectionProp:
        return

    # All other properties can have an update callback
    if "update" in annotation.bpy_prop.keywords:
        # There is already an update callback => wrap it
        original_update = annotation.bpy_prop.keywords["update"]

        def wrapped_update(self, context):
            original_update(self, context)
            self._internal_on_serialized_property_update(context, property_name=property_name)

        annotation.bpy_prop.keywords["update"] = wrapped_update
    else:
        # No update callback => register the on_serialized_property_update callback
        annotation.bpy_prop.keywords["update"] = lambda self, context: (
            self._internal_on_serialized_property_update(context, property_name)
        )


def serializable_class(cls):
    """Decorator to extend a `bpy.types.PropertyGroup` class with serialization api.

    - Use this decorator in combination with `Serialize()` wrapper to mark properties as serializable.
    - Use this in combination with `Savable` class to add saving and loading methods.

    If the class implements `on_serialized_property_update(self, context, prop_name)` callback,
    it will be called every time any serialized value is updated. Note that by default
    the update won't be propagated from within the collection or pointer properties
    (see `preferences_propagate_property_update`).

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
    cls._internal_on_serialized_property_update = _internal_on_serialized_property_update

    # Add serialization info to the class
    cls._serialized_properties: dict[str, type] = {}
    for prop_name, annotation in cls.__annotations__.items():
        if isinstance(annotation, SerializedPropertyInfo):
            # Store serialization info about the property
            cls._serialized_properties[prop_name] = annotation.serialization_type
            # Register `_internal_on_serialized_property_update` as an update callback
            _register_on_serialized_property_update(annotation, prop_name)
            # "Revert" the annotation to the original bpy.props property annotation
            # so bpy can generate properties
            cls.__annotations__[prop_name] = annotation.bpy_prop

    # Add serialization methods to the class
    cls._serialize = core_bpy.serialize_instance
    cls._deserialize = core_bpy.deserialize_instance

    return cls


@functools.cache
def _serialized_property_name_resolve(
    prop_instance: bpy.types.PropertyGroup, owner: bpy.types.bpy_struct
) -> str | None:
    """Find name of the property in the owner instance, where `prop_instance` is stored.

    - Owner must implement `_serialized_properties` dictionary and the property storing
      `prop_instance` must be serialized.
    - The computation can be expensive as it has to iterate over all serialized properties
      of the owner instance (including all instances stored in collection properties).
    """
    # TODO: We can cache the result and recompute only when validation fails (the validation is required!)
    serialized_properties = getattr(owner, "_serialized_properties", None)
    if serialized_properties is None:
        raise TypeError(
            f"Owner instance {owner} does not have _serialized_properties attribute. "
            f"Did you forget to decorate the owner class with `serializable_class`?"
        )
    serialized_properties = typing.cast(dict[str, type], serialized_properties)
    for prop_name, prop_type in serialized_properties.items():
        # Check all PropertyGroup and CollectionProp properties with the same type as `self`
        if prop_type is core_bpy.PointerProp[type(prop_instance)]:
            prop_in_owner = getattr(owner, prop_name, None)
            assert (
                prop_in_owner is not None
            ), f"Property '{prop_name}' expected in {owner} but not found."
            assert isinstance(prop_in_owner, bpy.types.PropertyGroup), "PropertyGroup expected"
            if prop_in_owner.as_pointer() == prop_instance.as_pointer():
                return prop_name
        elif prop_type is core_bpy.CollectionProp[type(prop_instance)]:
            prop_in_owner = getattr(owner, prop_name, None)
            assert (
                prop_in_owner is not None
            ), f"Property '{prop_name}' expected in {owner} but not found."
            assert isinstance(
                prop_in_owner, bpy.types.bpy_prop_collection
            ), "Collection property expected"
            # Try to find the property in the collection
            for i, item in enumerate(prop_in_owner):
                if prop_instance.as_pointer() == item.as_pointer():
                    return f"{prop_name}[{i}]"
    raise ValueError(f"Property '{prop_instance}' not found in owner {owner}")


def preferences_propagate_property_update(
    owner_getter: collections.abc.Callable[[bpy.types.Context], bpy.types.bpy_struct],
):
    """Class decorator to add property update propagation to the owner instance.

    This will allow to propagate property updates from the instances of this class to the owner
    instance (instance holding reference to this instance). This decorator is intended to be used
    with `bpy.types.AddonPreferences` subclasses. It implements custom logic to get the owner
    instance for update propagation as `instance.id_data` is not supported for
    `bpy.types.AddonPreferences` instances and data stored in them.

    Warning: although property changes will be propagated from within collection or pointer
    properties, adding, removing, or reordering items in a collection property will not trigger the
    update. (It seems that there is no reliable way to detect these changes in Blender API without
    requiring periodic checks.)
    When manipulating with collection properties, call
    `owner_instance._internal_on_serialized_property_update(context, property_name)` manually!


    - `owner_getter` is a callable that takes a `bpy.types.Context` and returns the owner instance.
        - The owner is expected to contain a reference to the instance of the decorated class.
        - The reference must be marked as serializable

    Example usage:
    ```
        def get_preferences(context: bpy.types.Context) -> MyAddonPreferences:
            return context.preferences.addons["my_addon"].preferences

        @serializable_class
        @polib.serialization_bpy.preferences_propagate_property_update(get_preferences)
        class MySubPropertyGroup(bpy.types.PropertyGroup):
            my_int_property: Serialize(
                bpy.props.IntProperty(name="My Int")
            )

        @serializable_class
        class MyAddonPreferences((bpy.types.AddonPreferences, Savable):
            addon_name = "my_addon"
            save_version = 1

            @property
            def config_name(self) -> str:
                return "my_config"

            @property
            def auto_save(self) -> bool:
                return True

            my_sub_property_group: Serialize(
                bpy.props.PointerProperty(type=MySubPropertyGroup)
            )
    ```
    """

    def _on_serialized_property_update_propagator(
        self, context: bpy.types.Context, property_name: str
    ) -> None:
        """Instance method that will attempt to propagate the property update to the owner instance.

        We need to find the 'owner' instance that contains this property. Unfortunately,
        `bpy.types.AddonPreferences` instances don't support standard bpy data paths, so we
        need to use a custom getter function to get the owner instance from the context.
        """
        owner_instance = owner_getter(context)
        if not owner_instance:
            raise RuntimeError(
                "Unable to get owner instance from context. "
                "The property update will not be propagated."
            )
        prop_update_callback = getattr(
            owner_instance, "_internal_on_serialized_property_update", None
        )
        if prop_update_callback is None:
            raise TypeError(
                f"Owner instance {owner_instance} does not have a method "
                f"for property update handling. The property update will not be propagated. "
                f"Did you forget to decorate the owner class with `serializable_class`?"
            )
        self_name_in_owner = _serialized_property_name_resolve(self, owner_instance)
        # Only propagate if the property is found in the owner instance
        if self_name_in_owner is None:
            raise RuntimeError(
                f"Unable to resolve property name of {self} in owner {owner_instance}. "
                f"The property update will not be propagated."
            )
        prop_update_callback(context, f"{self_name_in_owner}.{property_name}")

    def decorator(cls):
        cls._on_serialized_property_update_propagator = _on_serialized_property_update_propagator
        return cls

    return decorator
