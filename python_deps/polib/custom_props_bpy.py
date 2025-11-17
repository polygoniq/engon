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
    bool,
    int,
    float,
    tuple[bool, ...],
    tuple[int, ...],
    tuple[float, ...],
    list[bool],
    list[int],
    list[float],
]


class CustomPropertyNames:
    """Lists names of properties that control shader features through attributes."""

    # properties on all assets
    COPYRIGHT = "copyright"
    POLYGONIQ_ADDON = "polygoniq_addon"
    POLYGONIQ_ADDON_BLEND_PATH = "polygoniq_addon_blend_path"
    MAPR_ASSET_ID = "mapr_asset_id"
    MAPR_ASSET_DATA_ID = "mapr_asset_data_id"
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
    # controlls traffic lights, not an engon feature yet
    TQ_TRAFFIC_LIGHT_STATUS = "tq_traffic_light_status"
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
    # aesthetiq_wear feature
    PQ_WEAR_BUGHOLES_AREA = "pq_wear_bugholes_area"
    PQ_WEAR_BUGHOLES_MAPPING_SCALE = "pq_wear_bugholes_mapping_scale"
    PQ_WEAR_BUGHOLES_STRENGTH = "pq_wear_bugholes_strength"
    PQ_WEAR_FRACTURES_AREA = "pq_wear_fractures_area"
    PQ_WEAR_FRACTURES_THICKNESS = "pq_wear_fractures_thickness"
    PQ_WEAR_FRACTURES_STRENGTH = "pq_wear_fractures_strength"
    PQ_WEAR_MAPCRACKS_AREA = "pq_wear_mapcracks_area"
    PQ_WEAR_MAPCRACKS_STRENGTH = "pq_wear_mapcracks_strength"
    PQ_WEAR_MAPCRACKS_MAPPING_SCALE = "pq_wear_mapcracks_mapping_scale"
    PQ_DIRT_DENSITY = "pq_dirt_density"
    # pictorial_wear feature
    PQ_PICTORIAL_WEAR_PAINT_CHIPPING = "pq_pictorial_wear_paint_chipping"
    PQ_PICTORIAL_WEAR_PRINT_TEAR = "pq_pictorial_wear_print_tear"
    # pictorial_adjustments feature
    PQ_PICTORIAL_ADJUSTMENT_CONTRAST = "pq_pictorial_adjustment_contrast"
    PQ_PICTORIAL_ADJUSTMENT_SATURATION = "pq_pictorial_adjustment_saturation"
    PQ_PICTORIAL_ADJUSTMENT_VALUE = "pq_pictorial_adjustment_value"
    # colorize_feature
    PQ_PRIMARY_COLOR = "pq_primary_color"
    PQ_PRIMARY_COLOR_FACTOR = "pq_primary_color_factor"
    PQ_SECONDARY_COLOR = "pq_secondary_color"
    PQ_SECONDARY_COLOR_FACTOR = "pq_secondary_color_factor"
    PQ_PRIMARY_SECONDARY_SWITCH = "pq_primary_secondary_switch"
    # light_adjustment feature
    PQ_LIGHT_USE_RGB = "pq_light_use_rgb"
    PQ_LIGHT_KELVIN = "pq_light_kelvin"
    PQ_LIGHT_RGB = "pq_light_rgb"
    PQ_LIGHT_STRENGTH = "pq_light_strength"
    # engon scatter custom property defined for particle systems. This is API defined in runtime
    # but fallbacks to custom property if the defining API is not enabled.
    PPS_DENSITY = "pps_density"
    # parallax_feature
    PQ_PARALLAX = "pq_parallax"
    PQ_PARALLAX_LIGHTS = "pq_parallax_lights"
    PQ_PARALLAX_COVERINGS = "pq_parallax_coverings"
    PQ_PARALLAX_COVERING_TYPES = "pq_parallax_covering_types"
    PQ_PARALLAX_COVERING_SCALE = "pq_parallax_covering_scale"
    PQ_PARALLAX_TRANSPARENCY = "pq_parallax_transparency"
    # decay feature
    PQ_DECAY = "pq_decay"
    PQ_DIRT = "pq_dirt"

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
    def is_known_property(cls, prop: str) -> bool:
        """Check if the property is one of the known custom properties."""
        return prop in cls._all() or prop.startswith(
            cls.TQ_WHEEL_ROTATION
        )  # Wheel rotation prop has different suffix for each wheel

    @classmethod
    @functools.lru_cache(maxsize=1)
    def _all(cls) -> set[str]:
        """Returns all custom property names defined in this class.

        Note that this set doesn't represent all known custom properties.
        E.g., `TQ_WHEEL_ROTATION` can contain different suffixes for each wheel.
        To test if a property is known, use `is_known_property()` method.

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
    value_condition: typing.Callable[[typing.Any], bool] | None = None,
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
    update_tag_refresh: set[str] = {'OBJECT'},
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
