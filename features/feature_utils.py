# copyright (c) 2018- polygoniq xyz s.r.o.

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import typing
import bpy
import itertools
import random
from .. import polib
from .. import asset_registry
from .. import asset_helpers
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")

MODULE_CLASSES: typing.List[typing.Type] = []


# Older asset packs only implemented one feature - themselves.
# For backwards compatibility, we need to map features to the old asset packs.
# Features prefixed with asset pack name are still tightly coupled to the asset pack,
# usually via assetpack-specific propeties.
# Features without prefix are sufficiently uncoupled that they possibly
# make sense on their own or within another asset pack.
BACKWARDS_COMPATIBILITY_ASSET_PACKS_MAP = {
    "traffiq_paint_adjustments": {"traffiq"},
    "traffiq_lights_settings": {"traffiq"},
    "traffiq_wear": {"traffiq"},
    "traffiq_rigs": {"traffiq"},
    "emergency_lights": {"traffiq"},
    "road_generator": {"traffiq"},
    "botaniq_adjustments": {"botaniq"},
    "botaniq_animations": {"botaniq"},
    "vine_generator": {"botaniq"},
    "river_generator": {"aquatiq"},
    "rain_generator": {"aquatiq"},
    "puddles": {"aquatiq"},
    "aquatiq_paint_mask": {"aquatiq"},
    "aquatiq_material_limitation_warning": {"aquatiq"},
}


class RandomizePropertyOperator(bpy.types.Operator):
    """Base class for operators that randomize properties on engon property feautres"""

    bl_description = "Set random value for a custom property of selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    custom_property_name: bpy.props.StringProperty(options={'HIDDEN'})
    engon_feature_name: bpy.props.StringProperty(options={'HIDDEN'})

    def get_affected_assets(self, context: bpy.types.Context) -> typing.Iterable[bpy.types.ID]:
        feature: type(EngonAssetFeatureControlPanelMixin) = NAME_FEATURE_MAP.get(
            self.engon_feature_name
        )
        assert issubclass(feature, EngonAssetFeatureControlPanelMixin)
        return feature.get_multiedit_adjustable_assets(context)

    def get_random_value(self) -> polib.custom_props_bpy.CustomAttributeValueType:
        raise NotImplementedError("This method must be overriden and implemented in a subclass")

    def execute(self, context: bpy.types.Context):
        affected_assets = list(self.get_affected_assets(context))
        for asset in self.get_affected_assets(context):
            custom_prop = asset.get(self.custom_property_name, None)
            if custom_prop is None:
                continue

            polib.custom_props_bpy.update_custom_prop(
                context,
                [asset],
                self.custom_property_name,
                self.get_random_value(),
            )

        self.report(
            {'INFO'},
            f"Randomized {self.custom_property_name} on {len(affected_assets)} "
            f"asset{'s' if len(affected_assets) > 1 else ''}",
        )
        return {'FINISHED'}


@polib.log_helpers_bpy.logged_operator
class RandomizeFloatPropertyOperator(RandomizePropertyOperator):
    bl_idname = "engon.randomize_float_property"
    bl_label = "Randomize Float Property"

    float_min: bpy.props.FloatProperty(
        name="Minimum Value",
        description="Minimum value for randomization",
        default=0.0,
        soft_min=0.0,
        soft_max=1.0,
    )
    float_max: bpy.props.FloatProperty(
        name="Maximum Value",
        description="Maximum value for randomization",
        default=1.0,
        soft_min=0.0,
        soft_max=1.0,
    )

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.prop(self, "float_min", slider=True)
        layout.prop(self, "float_max", slider=True)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def get_random_value(self) -> polib.custom_props_bpy.CustomAttributeValueType:
        return random.uniform(self.float_min, self.float_max)


MODULE_CLASSES.append(RandomizeFloatPropertyOperator)


@polib.log_helpers_bpy.logged_operator
class RandomizeIntegerPropertyOperator(RandomizePropertyOperator):
    bl_idname = "engon.randomize_integer_property"
    bl_label = "Randomize Integer Property"

    int_min: bpy.props.IntProperty(
        name="Minimum Value",
        description="Minimum value for randomization",
        default=0,
        min=0,
        # only temperature of light adjustments is using RandomizeIntegerProperty, let's cater to it for now
        soft_max=12_000,
    )
    int_max: bpy.props.IntProperty(
        name="Maximum Value",
        description="Maximum value for randomization",
        default=12_000,
        min=0,
        soft_max=12_000,
    )

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.prop(self, "int_min", slider=True)
        layout.prop(self, "int_max", slider=True)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def get_random_value(self) -> polib.custom_props_bpy.CustomAttributeValueType:
        return random.uniform(self.int_min, self.int_max)


MODULE_CLASSES.append(RandomizeIntegerPropertyOperator)


@polib.log_helpers_bpy.logged_operator
class RandomizeColorPropertyOperator(RandomizePropertyOperator):
    # It does not make sense to set a min-max for color properties,
    # at least not in RGB space as it is a very unintuitive way to define a "range" of colors.
    # HSL might work, but such controls are hard to implement in blender.
    bl_idname = "engon.randomize_color_property"
    bl_label = "Randomize Color Property"

    def get_random_value(self) -> polib.custom_props_bpy.CustomAttributeValueType:
        return [random.uniform(0.0, 1.0), random.uniform(0.0, 1.0), random.uniform(0.0, 1.0)]


MODULE_CLASSES.append(RandomizeColorPropertyOperator)


class EngonFeaturePanelMixin:
    """Abstract base mixin for engon features panels.

    Features are defined on asset packs. Engon feature panel appears (polls true)
    if and only if the feature is implemented in at least one asset pack.

    This class is meant to be used as a abstract mixin for classes inheriting from bpy.types.Panel.
    Due to both `abc.ABCMeta` and `bpy_types.RNAMeta` implementing their own `register` methods,
    it is not possible to simultaneously inherit from `abc.ABCMeta` and `bpy_types.RNAMeta`.
    This class and it's children use `raise NotImplementedError()` instead of `@absctractmethod`,
    as the decorators do not work without inheriting from `abc.ABCMeta`.
    """

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    feature_name: str

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        backwards_compatibility_packs = BACKWARDS_COMPATIBILITY_ASSET_PACKS_MAP.get(
            cls.feature_name, []
        )

        is_implemented = (
            len(asset_registry.instance.get_packs_by_engon_feature(cls.feature_name)) > 0
        )
        is_implemented_with_backwards_compatibility = any(
            map(
                lambda pack: len(asset_registry.instance.get_packs_by_engon_feature(pack)) > 0,
                backwards_compatibility_packs,
            )
        )

        return is_implemented or is_implemented_with_backwards_compatibility

    @classmethod
    def get_feature_name_readable(cls) -> str:
        return cls.feature_name.replace("_", " ")


NAME_FEATURE_MAP: typing.Dict[str, type(EngonFeaturePanelMixin)] = dict()
PROPERTY_FEATURE_PROPERTIES_MAP: typing.Dict[str, typing.Set[str]] = dict()


def register_feature(cls: type(EngonFeaturePanelMixin)):
    """Registers a feature in NAME_FEATURE_MAP"""
    if not hasattr(cls, "feature_name"):
        raise AttributeError(
            f"EngonFeaturePanelMixin {cls.__name__} does not have a 'feature_name' attribute."
        )

    feature_name = cls.feature_name
    if NAME_FEATURE_MAP.get(feature_name, None) is not None:
        raise ValueError(
            f"Feature '{feature_name}' is already registered by '{NAME_FEATURE_MAP[feature_name].__name__}'."
        )
    NAME_FEATURE_MAP[feature_name] = cls

    if issubclass(cls, PropertyAssetFeatureControlPanelMixin):
        if not hasattr(cls, "related_custom_properties"):
            raise AttributeError(
                f"PropertyAssetFeatureControlPanelMixin {cls.__name__} does not have a 'related_custom_properties' attribute."
            )

        PROPERTY_FEATURE_PROPERTIES_MAP[feature_name] = cls.related_custom_properties

    return cls


def has_engon_property_feature(
    datablock: bpy.types.ID,
    feature: str,
    include_editable: bool = True,
    include_linked: bool = True,
) -> bool:
    if not polib.asset_pack_bpy.is_polygoniq_object(datablock):
        return False

    # check if obj has at least one of the given properties of the property features
    feature_properties = PROPERTY_FEATURE_PROPERTIES_MAP.get(feature, [])

    for feature_property in feature_properties:
        if polib.custom_props_bpy.has_property(
            datablock,
            feature_property,
            include_editable=include_editable,
            include_linked=include_linked,
        ):
            return True
    return False


class EngonAssetFeatureControlPanelMixin(EngonFeaturePanelMixin):
    """Abstract mixin for displaying engon asset features in panels.

    Asset feature is a feature that controls spawned assets, e.g. asset's materials, rigs, lights...
    """

    @classmethod
    def has_pps(cls, obj: bpy.types.Object) -> bool:
        if not hasattr(obj, "particle_systems"):
            return False
        for particle_system in obj.particle_systems:
            if polib.asset_pack.is_pps_name(particle_system.name):
                return True
        return False

    @classmethod
    def extend_with_active_object(
        cls,
        context: bpy.types.Context,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        if context.active_object is not None:
            possible_assets = set(possible_assets)
            possible_assets.add(context.active_object)
        return possible_assets

    @classmethod
    def get_possible_assets(cls, context: bpy.types.Context) -> typing.Iterable[bpy.types.ID]:
        return cls.extend_with_active_object(context, context.selected_objects)

    @classmethod
    def get_multiedit_adjustable_assets(
        cls, context: bpy.types.Context
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets(cls.get_possible_assets(context))

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        raise NotImplementedError("This method must be overriden and implemented in a subclass")

    @classmethod
    def has_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> bool:
        return len(list(cls.filter_adjustable_assets(possible_assets))) > 0

    @classmethod
    def has_adjustable_active_object(
        cls,
        context: bpy.types.Context,
    ) -> bool:
        adjustable_objects = set()
        if context.active_object is not None:
            adjustable_objects.add(context.active_object)
        return cls.has_adjustable_assets(adjustable_objects)

    def draw_multiedit_header(self, layout: bpy.types.UILayout):
        row = layout.row(align=True)
        row.enabled = False
        row.label(text="Edit all selected:")

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        raise NotImplementedError("This method must be overriden and implemented in a subclass")

    def conditionally_draw_warning_no_adjustable_assets(
        self,
        possible_assets: typing.Iterable[bpy.types.ID],
        layout: bpy.types.UILayout,
        warning_text: typing.Optional[str] = None,
    ) -> bool:
        if warning_text is None:
            warning_text = f"No assets with {self.get_feature_name_readable()} feature selected!"
        if not self.has_adjustable_assets(possible_assets):
            layout.label(text=warning_text)
            return True
        return False

    def conditionally_draw_warning_no_adjustable_active_object(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        warning_text: typing.Optional[str] = None,
        include_children: bool = False,
    ) -> bool:
        if warning_text is None:
            warning_text = (
                f"Active object is not an asset with {self.get_feature_name_readable()} feature!"
            )
        adjustable_objects = set()
        if context.active_object is not None:
            if include_children:
                adjustable_objects.update(
                    polib.asset_pack_bpy.get_entire_object_hierarchy(context.active_object)
                )
            else:
                adjustable_objects.add(context.active_object)
        return self.conditionally_draw_warning_no_adjustable_assets(
            adjustable_objects, layout, warning_text
        )

    def conditionally_draw_warning_not_cycles(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
    ) -> bool:
        if context.scene.render.engine != 'CYCLES':
            row = layout.row()
            row.alert = True
            row.label(
                text=f"{self.get_feature_name_readable().capitalize()} feature is only supported in Cycles!",
                icon='ERROR',
            )
            return True
        return False


class GeonodesAssetFeatureControlPanelMixin(
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
    EngonAssetFeatureControlPanelMixin,
):
    """Abstract mixin for displaying geometry nodes asset controls in panels.

    Geometry nodes assets are assets defined by primarily using a geometry nodes generator,
    e.g. rain, river, vines generator...
    """

    """Primary node group of the geometry nodes generator."""
    node_group_name: str
    exact_match: bool = True

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return filter(
            lambda a: isinstance(a, bpy.types.Object)
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    a, cls.node_group_name, cls.exact_match
                )
            )
            > 0,
            possible_assets,
        )

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        raise NotImplementedError()


class GeoNodesAssetFeatureSecondaryControlPanelMixin(
    GeonodesAssetFeatureControlPanelMixin,
):
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return cls.has_adjustable_active_object(context)


class PropertyAssetFeatureControlPanelMixin(EngonAssetFeatureControlPanelMixin):
    """Abstract mixin for displaying engon asset features based on properties."""

    related_custom_properties: typing.Set[str]

    @classmethod
    def get_selected_particle_system_targets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        objects = set(possible_assets)
        return filter(lambda obj: cls.has_pps(obj), objects)

    @classmethod
    def filter_adjustable_assets_simple(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        """Filter assets out of possible assets that have the property feature."""
        return set(
            filter(
                lambda obj: has_engon_property_feature(obj, cls.feature_name),
                possible_assets,
            )
        )

    @classmethod
    def filter_adjustable_assets_hierarchical(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        """Filter assets out of possible assets and their children that have the property feature."""
        possible_assets_and_children = itertools.chain(
            possible_assets, *(polib.asset_pack_bpy.get_hierarchy(obj) for obj in possible_assets)
        )
        # Empties that don't instance anything are a leftover after making compound assets editable.
        # They inherit properties from parent but don't control anything, let's filter them out.
        possible_assets_and_children = filter(
            lambda obj: obj.type != 'EMPTY' or obj.instance_type != 'NON',
            possible_assets_and_children,
        )

        return cls.filter_adjustable_assets_simple(possible_assets_and_children)

    @classmethod
    def filter_adjustable_assets_in_pps(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return set(cls.get_selected_particle_system_targets(possible_assets))

    def draw_property(
        self,
        datablock: bpy.types.ID,
        layout: bpy.types.UILayout,
        prop_name: str,
        text: str = "",
    ) -> None:
        if prop_name in datablock:
            layout.prop(datablock, f'["{prop_name}"]', text=text)
        else:
            layout.label(text="-")

    def draw_adjustable_assets_property_table_header(
        self,
        property_names: typing.Iterable[str],
        layout: bpy.types.UILayout,
    ) -> typing.Tuple[bpy.types.UILayout, bpy.types.UILayout]:
        row = layout.row()

        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)

        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")

        row = right_col.row(align=True)
        row.enabled = False

        for prop_name in property_names:
            row.label(text=prop_name)

        return (left_col, right_col)

    def draw_adjustable_assets_property_table_body(
        self,
        possible_assets: typing.Iterable[bpy.types.ID],
        left_col: bpy.types.UILayout,
        right_col: bpy.types.UILayout,
        draw_property_func: typing.Callable[[bpy.types.UILayout, bpy.types.ID], None],
        max_displayed_assets: int = 10,
        indent: int = 0,
    ) -> None:
        displayable_objects = list(self.filter_adjustable_assets(possible_assets))
        displayable_pps = filter(self.has_pps, displayable_objects)
        displayable_assets = list(filter(lambda obj: not self.has_pps(obj), displayable_objects))
        displayed_assets = 0
        for obj in displayable_assets:
            row = left_col.row()
            if displayed_assets >= max_displayed_assets:
                row.label(
                    text=f"... and {len(displayable_assets) - displayed_assets} additional asset(s)"
                )
                break
            row.label(text=f"{' ' * 4 * indent}{obj.name}")
            row = right_col.row(align=True)
            draw_property_func(row, obj)
            displayed_assets += 1
        for pps in displayable_pps:
            row = left_col.row()
            row.label(text=pps.name, icon='PARTICLES')
            row = right_col.row()  # empty
            row.label(text="")
            self.draw_adjustable_assets_property_table_body(
                set(asset_helpers.gather_instanced_objects([pps])),
                left_col,
                right_col,
                draw_property_func,
                # passing the original max_displayed_assets value
                # effectively resets the limit for this particular particle system
                max_displayed_assets=max_displayed_assets,
                indent=indent + 1,
            )

    def draw_adjustable_assets_property_table(
        self,
        possible_assets: typing.Iterable[bpy.types.ID],
        property_names: typing.Iterable[str],
        layout: bpy.types.UILayout,
        draw_property_func: typing.Callable[[bpy.types.UILayout, bpy.types.ID], None],
        max_displayed_assets: int = 10,
    ) -> None:
        left_col, right_col = self.draw_adjustable_assets_property_table_header(
            property_names, layout
        )
        self.draw_adjustable_assets_property_table_body(
            possible_assets, left_col, right_col, draw_property_func, max_displayed_assets
        )

    def draw_randomize_property_operator(
        self,
        property_name: str,
        randomize_operator: type[RandomizePropertyOperator],
        layout: bpy.types.UILayout,
    ):
        op = layout.operator(randomize_operator.bl_idname, text="", icon='FILE_3D')
        op.custom_property_name = property_name
        op.engon_feature_name = self.feature_name


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in MODULE_CLASSES:
        bpy.utils.unregister_class(cls)
