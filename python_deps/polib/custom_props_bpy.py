# copyright (c) 2018- polygoniq xyz s.r.o.

# Module containing functionality relevant to custom properties and how we use them to
# control shader features in Blender.

import bpy
import inspect
import functools
import typing

from . import ui_bpy


CustomAttributeValueType = typing.Union[
    str,
    int,
    float,
    typing.Tuple[int, ...],
    typing.Tuple[float, ...],
    typing.List[int],
    typing.List[float],
]


class CustomPropertyNames:
    """Lists names of properties that control shader features through attributes."""

    # traffiq_wear feature
    TQ_DIRT = "tq_dirt"
    TQ_SCRATCHES = "tq_scratches"
    TQ_BUMPS = "tq_bumps"
    # traffiq_paint feature
    TQ_PRIMARY_COLOR = "tq_primary_color"
    TQ_FLAKES_AMOUNT = "tq_flakes_amount"
    TQ_CLEARCOAT = "tq_clearcoat"
    # traffiq_lights feature
    TQ_LIGHTS = "tq_main_lights"
    # botaniq_adjustments feature
    BQ_BRIGHTNESS = "bq_brightness"
    BQ_RANDOM_PER_BRANCH = "bq_random_per_branch"
    BQ_RANDOM_PER_LEAF = "bq_random_per_leaf"
    BQ_SEASON_OFFSET = "bq_season_offset"
    # traffiq_rigs feature
    TQ_WHEEL_ROTATION = "tq_WheelRotation"
    TQ_STEERING = "tq_SteeringRotation"
    TQ_SUSPENSION_FACTOR = "tq_SuspensionFactor"
    TQ_SUSPENSION_ROLLING_FACTOR = "tq_SuspensionRollingFactor"
    TQ_WHEELS_Y_ROLLING = "tq_WheelsYRolling"
    TQ_CAR_RIG = "tq_Car_Rig"
    # colorize_feature
    PQ_PRIMARY_COLOR = "pq_primary_color"
    PQ_PRIMARY_COLOR_FACTOR = "pq_primary_color_factor"
    PQ_SECONDARY_COLOR = "pq_secondary_color"
    PQ_SECONDARY_COLOR_FACTOR = "pq_secondary_color_factor"
    # light_adjustment feature
    PQ_LIGHT_USE_RGB = "pq_light_use_rgb"
    PQ_LIGHT_KELVIN = "pq_light_kelvin"
    PQ_LIGHT_RGB = "pq_light_rgb"
    PQ_LIGHT_STRENGTH = "pq_light_strength"
    # engon scatter custom property defined for particle systems. This is API defined in runtime
    # but fallbacks to custom property if the defining API is not enabled.
    PPS_DENSITY = "pps_density"

    @classmethod
    def is_rig_property(cls, prop: str) -> bool:
        if prop.startswith(cls.TQ_WHEEL_ROTATION):
            return True

        return prop in {
            cls.TQ_CAR_RIG,
            cls.TQ_WHEELS_Y_ROLLING,
            cls.TQ_STEERING,
            cls.TQ_WHEEL_ROTATION,
            cls.TQ_SUSPENSION_FACTOR,
            cls.TQ_SUSPENSION_ROLLING_FACTOR,
        }

    @classmethod
    @functools.lru_cache(maxsize=1)
    def all(cls) -> typing.Set[str]:
        """Returns all custom property names defined in this class.

        This is cached, as we don't expect the number of properties to change during runtime.
        """
        return {
            value
            for name, value in inspect.getmembers(cls)
            if not name.startswith("__") and isinstance(value, str)
        }


def has_property(
    datablock: bpy.types.ID,
    property_name: str,
    value_condition: typing.Optional[typing.Callable[[typing.Any], bool]] = None,
    include_editable: bool = True,
    include_linked: bool = True,
) -> bool:
    has_correct_value = (
        value_condition is None
        or property_name in datablock
        and value_condition(datablock[property_name])
    )

    if include_editable and (
        # Non-object ID types cannot link, so they are always editable
        not isinstance(datablock, bpy.types.Object)
        or datablock.instance_collection is None
    ):
        # only non-'EMPTY' objects can be considered editable
        return property_name in datablock and has_correct_value
    if (
        include_linked
        and isinstance(datablock, bpy.types.Object)
        and datablock.instance_collection is not None
    ):
        # the object is linked and the custom properties are in the linked collection
        # in most cases there will be exactly one linked object but we want to play it
        # safe and will check all of them. if any linked object is a polygoniq object
        # we assume the whole instance collection is
        for linked_obj in datablock.instance_collection.objects:
            if has_property(linked_obj, property_name, value_condition):
                return True
    return False


def update_custom_prop(
    context: bpy.types.Context,
    datablocks: typing.Iterable[bpy.types.ID],
    prop_name: str,
    value: CustomAttributeValueType,
    update_tag_refresh: typing.Set[str] = {'OBJECT'},
) -> None:
    """Update custom properties of given datablocks and force 3D view to redraw

    When we set values of custom properties from code, affected datablocks don't get updated in 3D View
    automatically. We need to call obj.update_tag() and then refresh 3D view areas manually.

    'update_tag_refresh' set of enums {'OBJECT', 'DATA', 'TIME'}, updating DATA is really slow
    as it forces Blender to recompute the whole mesh, we should use 'OBJECT' wherever it's enough.
    """
    for datablock in datablocks:
        if prop_name in datablock:
            datablock[prop_name] = value
            datablock.update_tag(refresh=update_tag_refresh)

    ui_bpy.tag_areas_redraw(context, {'VIEW_3D'})


def is_api_defined_prop(datablock: bpy.types.ID, property_name: str) -> bool:
    """Check if the property is defined by the API."""
    prop = datablock.bl_rna.properties.get(property_name, None)
    if prop is None:
        return False

    return prop.is_runtime
