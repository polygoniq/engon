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

# This module provides UI implementation for the 'mapr.filters'. This adds state to the filters
# and the ability to draw them in the Blender UI based on what assets are present in current view.
# The core class is DynamicFilters - it holds all the filters and has the ability to reconstruct
# them. Individual filters are implemented as PropertyGroups and their properties OVERRIDE the
# properties of the base `mapr.filters` counterparts.

import bpy
import typing
import logging
import mapr
import math
import mathutils
import polib
import threading
from .. import asset_registry
from .. import preferences
from . import utils
from . import previews
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES = []
USE_THREADED_QUERY = True


class DataRepository:
    """Data repository encapsulates querying access providers for the browser.

    Queries are executed in a separate thread if `USE_THREADED_QUERY` is True,
    query being performed is indicated by `is_loading` member variable.
    """

    def __init__(self, asset_provider: mapr.asset_provider.AssetProvider):
        self.asset_provider = asset_provider
        self.is_loading = False
        self.last_view: typing.Optional[mapr.asset_provider.DataView] = None

    def query(
        self,
        query: mapr.query.Query,
        on_complete: typing.Optional[typing.Callable[[mapr.asset_provider.DataView], None]] = None
    ) -> None:
        def _query():
            logger.debug(f"Performing query against category {query.category_id}")
            # We are fine here in a separate thread if we don't access any Blender data, the only
            # thing how we touch blender is loading previews and tagging redraw
            self.last_view = self.asset_provider.query(query)
            previews.ensure_loaded_previews(self.last_view.assets)
            self.is_loading = False
            utils.tag_prefs_redraw(bpy.context)
            if on_complete is not None:
                on_complete(self.last_view)

        self.is_loading = True
        utils.tag_prefs_redraw(bpy.context)
        if USE_THREADED_QUERY:
            thread = threading.Thread(target=_query)
            thread.start()
        else:
            _query()

    def update_provider(self, asset_provider: mapr.asset_provider.AssetProvider) -> None:
        """Updates the provider used for the repository, clears caches and reconstructs filters

        If there is a DataView saved from previous queries, it is queried again with the new
        provider.
        We don't query if there wasn't any DataView saved, as we don't want to query assets
        if we know that the browser wasn't opened yet - this wastes resources and start-up time.
        """
        self.asset_provider = asset_provider
        self.clear_cache()

        if self.last_view is not None:
            self.query(self.last_view.used_query, lambda _: get_filters(
                bpy.context).clear_and_reconstruct())

    def clear_cache(self) -> None:
        if isinstance(self.asset_provider, mapr.asset_provider.CachedAssetProviderMultiplexer):
            self.asset_provider.clear_cache()

    @property
    def current_category_id(self) -> mapr.category.CategoryID:
        return self.last_view.used_query.category_id if self.last_view is not None \
            else mapr.category.DEFAULT_ROOT_CATEGORY.id_

    @property
    def current_view(self) -> mapr.asset_provider.DataView:
        return self.last_view if self.last_view is not None else mapr.asset_provider.EmptyDataView()

    @property
    def current_assets(self) -> typing.List[mapr.asset.Asset]:
        return self.last_view.assets if self.last_view is not None else []


asset_repository = DataRepository(asset_registry.instance.master_asset_provider)


class BrowserFilter:
    """Mixin adding frontend functionality and controls for mapr filters"""
    # Filter is enabled when it is relevant for the filtering - when the matching tags or
    # parameters are in the current view, or all the time - special case like SearchFilter or
    # AssetTypesFilter.
    enabled: bpy.props.BoolProperty(options={'HIDDEN'})
    name_without_type: bpy.props.StringProperty(options={'HIDDEN'})

    def init(self, parameter_meta: typing.Any) -> None:
        """Initializes this filter based on one parameter meta information."""
        raise NotImplementedError()

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        raise NotImplementedError()

    def reset(self) -> None:
        self.enabled = True

    def is_default(self) -> bool:
        """Returns True if the filter has its values set to the default ones, False otherwise."""
        raise NotImplementedError()

    def is_applied(self) -> bool:
        """Returns True if the filter is enabled and the values are not default."""
        if not self.enabled:
            return False

        return not self.is_default()

    def is_drawn(self):
        """Returns True if the filter is drawn in the UI, False otherwise."""
        # The filter is drawn if it is enabled - it is relevant for the current view or if the
        # filter values were changed from default - user needs to have ability to reset  the filter
        # in any view.
        return self.enabled or not self.is_default()

    def get_nice_name(self) -> str:
        return mapr.known_metadata.format_parameter_name(self.name_without_type)


def filters_updated_bulk_query() -> None:
    filters_properties = get_filters()
    # Repurpose existing view category_id, as we know it didn't change
    asset_repository.query(
        mapr.query.Query(
            asset_repository.current_category_id,
            filters_properties.filters.values(),
            filters_properties.sort_mode
        ),
        on_complete=lambda _: filters_properties.reenable()
    )


def _any_filter_updated_event():
    # Each filter update re-registers a timer that will trigger the expensive operation - querying
    # based on filter parameters only after a certain delay
    if bpy.app.timers.is_registered(filters_updated_bulk_query):
        bpy.app.timers.unregister(filters_updated_bulk_query)

    bpy.app.timers.register(filters_updated_bulk_query, first_interval=0.3)


class BrowserNumericParameterFilter(
    bpy.types.PropertyGroup,
    mapr.filters.NumericParameterFilter,
    BrowserFilter
):
    is_int: bpy.props.BoolProperty()
    range_start_float: bpy.props.FloatProperty(
        get=lambda self: self.range_start,
        set=lambda self, value: self._range_start_set(value),
        default=-1.0
    )
    range_end_float: bpy.props.FloatProperty(
        get=lambda self: self.range_end,
        set=lambda self, value: self._range_end_set(value),
        default=1.0
    )

    range_start_int: bpy.props.IntProperty(
        get=lambda self: self.range_start,
        set=lambda self, value: self._range_start_set(value),
        default=-1
    )
    range_end_int: bpy.props.IntProperty(
        get=lambda self: self.range_end,
        set=lambda self, value: self._range_end_set(value),
        default=1
    )

    range_min: bpy.props.FloatProperty(options={'HIDDEN'})
    range_max: bpy.props.FloatProperty(options={'HIDDEN'})

    def init(self, parameter_meta: mapr.parameter_meta.NumericParameterMeta) -> None:
        self.name = parameter_meta.name
        self.name_without_type = mapr.parameter_meta.remove_type_from_name(self.name)
        # Filter should be enabled by default after initializing
        self.enabled = True
        # Infer the numeric type from the parameter meta (False means float)
        self.is_int = isinstance(parameter_meta.min_, int) and isinstance(parameter_meta.max_, int)
        # Store meta information of min max to the filter
        self.range_min = parameter_meta.min_
        self.range_max = parameter_meta.max_
        # Initialize user facing properties to min max, those have to be initialized after
        # the ranges, so the set methods do not clamp to 0.0
        self._range_start_set(parameter_meta.min_)
        self._range_end_set(parameter_meta.max_)

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        col = layout.column(align=True)
        row = col.row()
        # Draw label as disabled
        sub = row.column()
        sub.enabled = False
        unit = mapr.known_metadata.PARAMETER_UNITS.get(self.name_without_type, None)
        unit_str = f" ({unit})" if unit is not None else ""
        sub.label(text=f"{self.get_nice_name()}{unit_str}")
        # Draw Reset button
        if self.is_applied() or self.enabled is False:
            row.operator(
                MAPR_BrowserResetFilter.bl_idname,
                text="",
                icon='PANEL_CLOSE',
                emboss=False
            ).filter_name = self.name

        row = col.row(align=True)
        row.prop(self, self._range_start_name(), text="Min")
        row.prop(self, self._range_end_name(), text="Max")

    def is_default(self):
        return math.isclose(self.range_start, self.range_min) and \
            math.isclose(self.range_end, self.range_max)

    def reset(self):
        super().reset()
        self._range_start_set(self.range_min)
        self._range_end_set(self.range_max)

    def filter_(self, asset: mapr.asset.Asset) -> bool:
        # Include asset if the values for this filter are default
        if self.is_default():
            return True

        return super().filter_(asset)

    def _convert_to_num_type(self, value: typing.Union[int, float]) -> typing.Union[int, float]:
        return int(value) if self.is_int else float(value)

    def _range_start_name(self) -> str:
        num_type = "int" if self.is_int else "float"
        return f"range_start_{num_type}"

    def _range_end_name(self) -> str:
        num_type = "int" if self.is_int else "float"
        return f"range_end_{num_type}"

    def _range_start_set(self, value: float):
        if value < self.range_min:
            value = self.range_min

        if value > self.range_max:
            value = self.range_max

        self[self._range_start_name()] = self._convert_to_num_type(value)
        _any_filter_updated_event()

    def _range_end_set(self, value: float):
        if value > self.range_max:
            value = self.range_max
        if value < self.range_min:
            value = self.range_min

        self[self._range_end_name()] = self._convert_to_num_type(value)
        _any_filter_updated_event()

    @property
    def range_start(self):
        # OVERRIDES 'range_start' from 'mapr.filters.NumericParameterFilter'
        return self._convert_to_num_type(self.get(self._range_start_name(), -1.0))

    @property
    def range_end(self):
        # OVERRIDES 'range_end' from 'mapr.filters.NumericParameterFilter'
        return self._convert_to_num_type(self.get(self._range_end_name(), 1.0))


MODULE_CLASSES.append(BrowserNumericParameterFilter)


class BrowserTagFilter(
    bpy.types.PropertyGroup,
    mapr.filters.TagFilter,
    BrowserFilter
):
    # OVERRIDES 'include' from 'mapr.filters.TagFilter'
    include: bpy.props.BoolProperty(
        update=lambda self, context: _any_filter_updated_event()
    )

    def init(self, name: str):
        self.name = name
        self.name_without_type = mapr.parameter_meta.remove_type_from_name(self.name)

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        # We do not show the 'ResetFilter' button for the tag filters, as resetting can be done
        # by toggling the property.
        row = layout.row(align=True)
        row.prop(self, "include", text=self.get_nice_name(), toggle=1)

    def is_default(self) -> bool:
        return self.include is False

    def reset(self) -> None:
        super().reset()
        self.include = False

    def filter_(self, asset: mapr.asset.Asset) -> bool:
        # Include asset if the values for this filter are default
        if self.is_default():
            return True

        return super().filter_(asset)


MODULE_CLASSES.append(BrowserTagFilter)


class TextParameterValue(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    include: bpy.props.BoolProperty(
        update=lambda self, context: _any_filter_updated_event(),
        default=False
    )


MODULE_CLASSES.append(TextParameterValue)


class BrowserTextParameterFilter(
    bpy.types.PropertyGroup,
    mapr.filters.TextParameterFilter,
    BrowserFilter
):
    # Number of items when the text parameter filter becomes collapsible
    COLLAPSIBLE_DISPLAY_MIN_COUNT = 5
    # Max number of items before drawing is switched to column format
    ROW_DISPLAY_MAX_COUNT = 3

    param_values: bpy.props.CollectionProperty(type=TextParameterValue)
    collapse: bpy.props.BoolProperty(
        name="Collapse",
        description="Collapses the text parameter display, not all values are shown in collapsed view",
        default=True
    )

    def init(self, parameter_meta: mapr.parameter_meta.TextParameterMeta):
        self.name = parameter_meta.name
        self.name_without_type = mapr.parameter_meta.remove_type_from_name(self.name)
        sorted_unique_values = sorted(list(parameter_meta.unique_values))
        for value in sorted_unique_values:
            item = self.param_values.add()
            item.name = value
            item.include = False

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        col = layout.column()
        row = col.row()
        # Draw label as disabled
        sub = row.column()
        sub.enabled = False
        sub.label(text=self.get_nice_name())
        # Draw reset button
        if self.is_applied() or self.enabled is False:
            row.operator(
                MAPR_BrowserResetFilter.bl_idname,
                text="",
                icon='PANEL_CLOSE',
                emboss=False
            ).filter_name = self.name

        drawn_text_parameters = len(self.param_values) if not self.collapse else \
            BrowserTextParameterFilter.COLLAPSIBLE_DISPLAY_MIN_COUNT
        not_shown_text_parameters_count = len(self.param_values) - drawn_text_parameters

        # Switch between row and column for small number of items
        if len(self.param_values) <= BrowserTextParameterFilter.ROW_DISPLAY_MAX_COUNT:
            items_layout = col.row(align=True)
        else:
            items_layout = col.column(align=True)

        for item in self.param_values[:drawn_text_parameters]:
            items_layout.prop(item, "include", text=item.name, toggle=True)

        if not_shown_text_parameters_count > 0 or self.collapse is False:
            items_layout.separator()
            row = items_layout.row()
            label = f"... and {not_shown_text_parameters_count} more" if \
                not_shown_text_parameters_count > 0 else "collapse"
            row.prop(
                self,
                "collapse",
                text=label,
                icon='RIGHTARROW' if self.collapse else 'MARKER',
                emboss=False
            )

    def is_default(self) -> bool:
        return all(not x.include for x in self.param_values)

    def reset(self) -> None:
        super().reset()
        for item in self.param_values:
            item.include = False

    def filter_(self, asset: mapr.asset.Asset) -> bool:
        if self.is_default():
            return True

        return super().filter_(asset)

    @property
    def values(self):
        # OVERRIDES the 'mapr.filters.TextParameterFilter.values' based on the current state
        return {v.name for v in self.param_values.values() if v.include}


MODULE_CLASSES.append(BrowserTextParameterFilter)


class BrowserVectorParameterFilter(
    bpy.types.PropertyGroup,
    mapr.filters.VectorParameterFilter,
    BrowserFilter
):
    """Filters vector parameters. Provides user interface for various vector parameter types.

    Vectors are filtered differently based on the vector type:
    - Color - filtered based on perceptual color distance from the desired color
    - Float - individual components filtered separately
    - Int - filtered lexicographically

    As bpy doesn't allow to dynamically change size of defined vector property this parameter filter
    is limited to Vec3 parameters only. To support other vector sizes this has to be extended with
    properties matching the desired size and logic switching between them based on the actual
    parameter size.
    """
    DEFAULT_VALUE = (1.0, 1.0, 1.0)
    DEFAULT_DISTANCE = 0.2

    # one of mapr.known_metadata.VectorType
    type_: bpy.props.EnumProperty(
        items=[
            (mapr.known_metadata.VectorType.FLOAT, "Float", "Float"),
            (mapr.known_metadata.VectorType.INT, "Integer", "Integer"),
            (mapr.known_metadata.VectorType.COLOR, "Color", "Color"),
        ],
        options={'HIDDEN'}
    )
    color_value: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        min=0.0,
        max=1.0,
        default=DEFAULT_VALUE,
        update=lambda self, context: _any_filter_updated_event()
    )
    distance: bpy.props.FloatProperty(
        name="Tolerance",
        min=0.0,
        max=1.0,
        default=DEFAULT_DISTANCE,
        update=lambda self, context: _any_filter_updated_event(),
        description="Distance from desired to compared color as computed by CIEDE2000 formula.",
    )

    range_start: bpy.props.FloatVectorProperty(
        get=lambda self: self._range_start_get(),
        set=lambda self, value: self._range_start_set(value)
    )
    range_end: bpy.props.FloatVectorProperty(
        get=lambda self: self._range_end_get(),
        set=lambda self, value: self._range_end_set(value),
    )

    range_min: bpy.props.FloatVectorProperty(options={'HIDDEN'})
    range_max: bpy.props.FloatVectorProperty(options={'HIDDEN'})

    def init(self, parameter_meta: mapr.parameter_meta.VectorParameterMeta):
        self.name = parameter_meta.name
        self.name_without_type = mapr.parameter_meta.remove_type_from_name(self.name)
        known_parameter = mapr.known_metadata.VECTOR_PARAMETERS.get(self.name_without_type, None)
        if known_parameter is not None:
            self.type_ = known_parameter.get("type", mapr.known_metadata.VectorType.FLOAT)
        else:
            self.type_ = mapr.known_metadata.VectorType.FLOAT

        self.range_min = parameter_meta.min_
        self.range_max = parameter_meta.max_
        self._range_start_set(self.range_min)
        self._range_end_set(self.range_max)

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        col = layout.column()
        row = col.row()
        # Draw label as disabled
        sub = row.column()
        sub.enabled = False
        sub.label(text=self.get_nice_name())
        # Draw reset button
        if self.is_applied() or self.enabled is False:
            row.operator(
                MAPR_BrowserResetFilter.bl_idname,
                text="",
                icon='PANEL_CLOSE',
                emboss=False
            ).filter_name = self.name

        if self.type_ == mapr.known_metadata.VectorType.COLOR:
            col.prop(self, "color_value", text="")
            col.prop(self, "distance")
        elif self.type_ in {mapr.known_metadata.VectorType.FLOAT, mapr.known_metadata.VectorType.INT}:
            col.prop(self, "range_start", text="Min")
            col.prop(self, "range_end", text="Max")

    def is_default(self) -> bool:
        # For some reason I had to lower the 'rel_tol' for the self.distance 'isclose' check to pass
        if self.type_ == mapr.known_metadata.VectorType.COLOR:
            return tuple(self.color_value) == BrowserVectorParameterFilter.DEFAULT_VALUE and \
                math.isclose(
                    self.distance, BrowserVectorParameterFilter.DEFAULT_DISTANCE, rel_tol=1e-6)
        elif self.type_ in {mapr.known_metadata.VectorType.FLOAT, mapr.known_metadata.VectorType.INT}:
            return math.isclose(self.range_start[0], self.range_min[0]) and \
                math.isclose(self.range_start[1], self.range_min[1]) and \
                math.isclose(self.range_start[2], self.range_min[2]) and \
                math.isclose(self.range_end[0], self.range_max[0]) and \
                math.isclose(self.range_end[1], self.range_max[1]) and \
                math.isclose(self.range_end[2], self.range_max[2])
        else:
            raise ValueError(f"Unknown vector type {self.type_}")

    def reset(self) -> None:
        super().reset()
        self.color_value = BrowserVectorParameterFilter.DEFAULT_VALUE
        self.distance = BrowserVectorParameterFilter.DEFAULT_DISTANCE
        self._range_start_set(self.range_min)
        self._range_end_set(self.range_max)

    def filter_(self, asset: mapr.asset.Asset) -> bool:
        # Include asset if the values for this filter are close to default
        if self.is_default():
            return True

        return super().filter_(asset)

    def _clamp_value(self, value: mathutils.Vector) -> mathutils.Vector:
        # Clamp values to range min, max
        for i in range(len(value)):
            if value[i] < self.range_min[i]:
                value[i] = self.range_min[i]

            if value[i] > self.range_max[i]:
                value[i] = self.range_max[i]

        return value

    def _range_start_get(self):
        return self.get("range_start", mathutils.Vector((-1.0, -1.0, -1.0)))

    def _range_end_get(self):
        return self.get("range_end", mathutils.Vector((1.0, 1.0, 1.0)))

    def _range_start_set(self, value: typing.Tuple):
        self["range_start"] = self._clamp_value(mathutils.Vector(value))
        _any_filter_updated_event()

    def _range_end_set(self, value: typing.Tuple):
        self["range_end"] = self._clamp_value(mathutils.Vector(value))
        _any_filter_updated_event()

    @property
    def comparator(self) -> mapr.filters.VectorComparator:
        # OVERRIDES 'comparator' from 'mapr.filters.VectorParameterFilter'
        if self.type_ == mapr.known_metadata.VectorType.COLOR:
            return mapr.filters.VectorDistanceComparator(
                self.color_value,
                self.distance,
                (polib.color_utils.perceptual_color_distance, "perceptual_color")
            )
        elif self.type_ == mapr.known_metadata.VectorType.INT:
            return mapr.filters.VectorLexicographicComparator(self.range_start, self.range_end)
        elif self.type_ == mapr.known_metadata.VectorType.FLOAT:
            return mapr.filters.VectorComponentWiseComparator(self.range_start, self.range_end)
        else:
            raise ValueError(f"Unsupported vector type {self.type_}")


MODULE_CLASSES.append(BrowserVectorParameterFilter)


class BrowserAssetTypesFilter(
    bpy.types.PropertyGroup,
    mapr.filters.AssetTypesFilter,
    BrowserFilter
):
    enabled: bpy.props.BoolProperty(
        get=lambda _: True,
        set=lambda _, __: None
    )

    # OVERRIDES 'model' from 'mapr.filters.AssetTypesFilter'
    model: bpy.props.BoolProperty(
        name="Model",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )
    # OVERRIDES 'material' from 'mapr.filters.AssetTypesFilter'
    material: bpy.props.BoolProperty(
        name="Material",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )
    # OVERRIDES 'particle_system' from 'mapr.filters.AssetTypesFilter'
    particle_system: bpy.props.BoolProperty(
        name="Particle System",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )
    # OVERRIDES 'scene' from 'mapr.filters.AssetTypesFilter'
    scene: bpy.props.BoolProperty(
        name="Scene",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )
    # OVERRIDES 'world' from 'mapr.filters.AssetTypesFilter'
    world: bpy.props.BoolProperty(
        name="World",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )
    # OVERRIDES 'geometry_nodes' from 'mapr.filters.AssetTypesFilter'
    geometry_nodes: bpy.props.BoolProperty(
        name="Geometry Nodes",
        default=False,
        update=lambda self, context: _any_filter_updated_event()
    )

    def init(self):
        self.enabled = True
        self.name = "builtin:asset_types"

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        layout.prop(self, "model", icon_only=True, icon='OBJECT_DATA')
        layout.prop(self, "material", icon_only=True, icon='MATERIAL')
        layout.prop(self, "particle_system", icon_only=True, icon='PARTICLES')
        layout.prop(self, "scene", icon_only=True, icon='SCENE_DATA')
        layout.prop(self, "world", icon_only=True, icon='WORLD')
        layout.prop(self, "geometry_nodes", icon_only=True, icon='GEOMETRY_NODES')
        if self.is_applied():
            layout.operator(
                MAPR_BrowserResetFilter.bl_idname,
                text="",
                icon='PANEL_CLOSE',
                emboss=False
            ).filter_name = self.name

    def filter_(self, asset: mapr.asset.Asset) -> bool:
        if self.is_default():
            return True

        return super().filter_(asset)

    def reset(self):
        super().reset()
        self.model = False
        self.material = False
        self.particle_system = False
        self.scene = False
        self.world = False
        self.geometry_nodes = False

    def is_default(self) -> bool:
        return not any(self._all)


MODULE_CLASSES.append(BrowserAssetTypesFilter)


class BrowserSearchFilter(
    bpy.types.PropertyGroup,
    mapr.filters.SearchFilter,
    BrowserFilter
):
    """Filters out items based on text input from user"""
    enabled: bpy.props.BoolProperty(
        get=lambda _: True,
        set=lambda _, __: None
    )

    # OVERRIDES 'search' from 'mapr.filters.SearchFilter'
    search: bpy.props.StringProperty(
        name="Search",
        description="Space separated keywords to search for",
        update=lambda self, context: self.search_updated(context)
    )

    recent_search: bpy.props.EnumProperty(
        name="Recent Search",
        description="Recent searches history, select one to search it again",
        items=lambda self, context: self.get_recent_search_enum_items(context),
        update=lambda self, context: self.recent_search_updated(context)
    )

    def init(self):
        self.enabled = True
        self.name = "builtin:search"

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        layout.prop_menu_enum(self, "recent_search", text="", icon='DOWNARROW_HLT')
        sub = layout.row(align=True)
        sub.scale_x = 1.2
        sub.prop(self, "search", text="",
                 icon_value=polib.ui_bpy.icon_manager.get_icon_id("icon_engon_search"))

        if self.is_applied():
            layout.operator(
                MAPR_BrowserResetFilter.bl_idname,
                text="",
                icon='PANEL_CLOSE',
                emboss=False
            ).filter_name = self.name

    def reset(self):
        super().reset()
        self.search = ""

    def is_default(self):
        return self.search == ""

    def search_updated(self, context: bpy.types.Context) -> None:
        # We store search history as class variable, we assume one instance of this class existing
        # at any point.
        cls = type(self)
        if not hasattr(cls, "search_history"):
            cls.search_history = []

        # If existing entry is present in the search history pop it out
        if self.search in cls.search_history:
            cls.search_history.remove(self.search)

        cls.search_history.append(self.search)
        history_count = preferences.get_preferences(context).mapr_preferences.search_history_count
        while len(type(self).search_history) > history_count:
            cls.search_history.pop(0)

        _any_filter_updated_event()

    def get_recent_search_enum_items(
        self,
        context: bpy.types.Context
    ) -> typing.Iterable[typing.Tuple[str, str, str]]:
        ret = []
        for search in reversed(getattr(type(self), "search_history", [])):
            ret.append((search, search, search))

        if len(ret) == 0:
            ret.append(("", "Search history is empty", ""))

        return ret

    def recent_search_updated(self, context: bpy.types.Context) -> None:
        if self.recent_search != "":
            self.search = self.recent_search

    @property
    def needle_keywords(self):
        # OVERRIDES 'needle_keywords' from 'mapr.filters.SearchFilter'
        return mapr.filters.SearchFilter.keywords_from_search(self.search)


MODULE_CLASSES.append(BrowserSearchFilter)


class FilterGroup(bpy.types.PropertyGroup):
    """Contains name of the filter group and its collapsed state.

    Instances of Filter have to be retrieved separately in DynamicFilters, this only stores the
    group meta information and knows how to draw filter group given the filters.
    """
    # name is a default parameter of PropertyGroup, so we don't define it
    collapsed: bpy.props.BoolProperty(name="Collapsed", default=True)

    def get_nice_name(self) -> str:
        return mapr.known_metadata.format_parameter_name(self.name)

    def draw(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        filters_: typing.List[BrowserFilter]
    ) -> None:
        box = layout.box()
        row = box.row()
        row.alignment = 'LEFT'
        row.prop(
            self,
            "collapsed",
            text=self.get_nice_name(),
            emboss=False,
            icon='RIGHTARROW' if self.collapsed else 'DOWNARROW_HLT'
        )

        # Skip drawing filters if group is collapsed
        if self.collapsed:
            return

        for filter_ in filters_:
            filter_.draw(context, box.box())


MODULE_CLASSES.append(FilterGroup)


class GroupedParametrizationFilters:
    """Holds information about parametrization groups and filters to be drawn.

    NOTE: Draws everything that's given to it, doesn't add any additional logic.
    """

    def __init__(self):
        self.groups: typing.Dict[FilterGroup, BrowserFilter] = {}
        self.ungrouped_filters: typing.List[BrowserFilter] = []

    def draw(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        if len(self.filters) == 0:
            row = layout.row()
            row.enabled = False
            row.label(text="No applicable filters", icon='PANEL_CLOSE')
        else:
            layout.label(text="Filters")
            col = layout.column()
            col.enabled = not asset_repository.is_loading
            for group, filters_ in self.groups.items():
                group.draw(context, col, filters_)

            for filter_ in sorted(self.ungrouped_filters, key=lambda x: x.name_without_type):
                filter_.draw(context, col.box())

    @property
    def filters(self) -> typing.List[BrowserFilter]:
        return list(self.groups.values()) + self.ungrouped_filters


class DynamicFilters(bpy.types.PropertyGroup):
    numeric_filters: bpy.props.CollectionProperty(type=BrowserNumericParameterFilter)
    tag_filters: bpy.props.CollectionProperty(type=BrowserTagFilter)
    text_filters: bpy.props.CollectionProperty(type=BrowserTextParameterFilter)
    vector_filters: bpy.props.CollectionProperty(type=BrowserVectorParameterFilter)
    search: bpy.props.PointerProperty(type=BrowserSearchFilter)
    asset_types: bpy.props.PointerProperty(type=BrowserAssetTypesFilter)

    filter_groups: bpy.props.CollectionProperty(type=FilterGroup)

    # We define sort mode here, as it is related to the filtering closely.
    # It cannot be defined in preferences, as we need to query the data repository
    # when the sort mode updates - this would result in circular dep between filters and preferences
    sort_mode: bpy.props.EnumProperty(
        name="Sort Mode",
        description="Select mode by which to sort the result",
        items=[
            (mapr.query.SortMode.ALPHABETICAL_ASC, "Name (A to Z)",
             "Alphabetical order from A to Z", 'SORT_ASC', 0),
            (mapr.query.SortMode.ALPHABETICAL_DESC, "Name (Z to A)",
             "Reversed alphabetical order from Z to A", 'SORT_DESC', 1),
        ],
        update=lambda self, _: self._sort_mode_updated()
    )

    def query_and_reconstruct(self, category_id: mapr.category.CategoryID) -> None:
        def _on_complete(view: mapr.asset_provider.DataView):
            self.reconstruct()
            self.reenable()

        asset_repository.query(
            mapr.query.Query(
                category_id,
                self.filters.values(),
                self.sort_mode
            ),
            on_complete=_on_complete
        )

    def reconstruct(self):
        """Reconstructs dynamic filters based on current view of global cache"""
        # Construct all the filters based on unique parameters available in current data view
        # TODO: Currently we don't call this method and reconstruct ranges or any filters content
        # when another filter is applied - this triggers infinite update loop. If filters range is
        # updated it is considered as update to the value, which means that filters should
        # reconstruct. This won't happen until we have something like 'init mode' for the filters
        # and their callbacks.
        self.search.init()
        self.asset_types.init()

        current_view = asset_repository.current_view
        filters_def = [
            (current_view.parameters_meta.numeric, self.numeric_filters, "NUMERIC_PARAMETERS"),
            (current_view.parameters_meta.text, self.text_filters, "TEXT_PARAMETERS"),
            (current_view.parameters_meta.vector, self.vector_filters, "VECTOR_PARAMETERS"),
            # Convert set of tags to mapping tag: tag, so we can use the same API
            ({tag: tag for tag in current_view.parameters_meta.unique_tags}, self.tag_filters, "TAGS")
        ]
        for params_meta, collection, known_metadata_field in filters_def:
            known_params_dict = getattr(mapr.known_metadata, known_metadata_field)
            for param_name, param_meta in params_meta.items():
                param_name_without_type = mapr.parameter_meta.remove_type_from_name(param_name)
                if not known_params_dict.get(param_name_without_type, {}).get("show_filter", True):
                    assert collection.get(param_name, None) is None
                    continue

                filter_ = collection.get(param_name, None)
                if filter_ is None:
                    filter_ = collection.add()
                    filter_.init(param_meta)

    def reenable(self):
        current_view = asset_repository.current_view
        for filter_ in self.filters.values():
            filter_.enabled = filter_.name in current_view.parameters_meta.unique_parameter_names

    def clear(self):
        """Clears all dynamically constructed parametrization filters"""
        self.numeric_filters.clear()
        self.tag_filters.clear()
        self.text_filters.clear()
        self.vector_filters.clear()

    def clear_and_reconstruct(self):
        """Clears the parametrization filters and reconstructs based on last view in repository"""
        self.clear()
        self.reconstruct()

    def reset(self):
        """Resets all filters into the default state"""
        for filter_ in self.filters.values():
            filter_.reset()

    def get_param_filter(self, filter_name: str) -> typing.Optional[BrowserFilter]:
        return self.filters.get(filter_name, None)

    def get_grouped_parametrization_filters(self) -> GroupedParametrizationFilters:
        """Returns grouped parametrization filters that are supposed to be drawn based on state.

        If the group would be empty, it isn't created at all.
        """
        grouped_filters = GroupedParametrizationFilters()
        parametrization_filters = self.parametrization_filters
        grouped_param_names = set()
        for group_name, parameter_names in mapr.known_metadata.PARAMETER_GROUPING.items():
            group = self.filter_groups.get(group_name, None)
            if group is None:
                group = self.filter_groups.add()
                group.name = group_name

            this_group_filters = []
            for param in parameter_names:
                filter_ = parametrization_filters.get(param, None)
                # Not all filters might be available in all situations, as all asset packs don't
                # contain all the parameters.
                if filter_ is None:
                    continue
                if filter_.is_drawn():
                    this_group_filters.append(filter_)
                    grouped_param_names.add(param)

            if len(this_group_filters) > 0:
                grouped_filters.groups[group] = this_group_filters

        for filtered_param, filter_ in parametrization_filters.items():
            # If already drawn as grouped, don't draw additionally
            if filtered_param in grouped_param_names:
                continue

            if filter_.is_drawn():
                grouped_filters.ungrouped_filters.append(filter_)

        return grouped_filters

    @property
    def filters(self) -> typing.Dict[str, BrowserFilter]:
        return {
            self.asset_types.name: self.asset_types,
            self.search.name: self.search,
            **self.tag_filters,
            **self.parametrization_filters
        }

    @property
    def parametrization_filters(self) -> typing.Dict[str, BrowserFilter]:
        return {
            **self.numeric_filters,
            **self.text_filters,
            **self.vector_filters
        }

    def _sort_mode_updated(self) -> None:
        # We use previous query, and adjust the sort mode parameter, if there is no previous
        # query, we do nothing. This can only happen, if the sort mode would be updated before
        # the browser is initialized.
        last_query = asset_repository.last_query
        if last_query is None:
            return

        # Replicate last query with a different sorting method
        asset_repository.query(mapr.query.Query(
            last_query.category_id,
            last_query.filters,
            sort_mode=self.sort_mode,
            recursive=last_query.recursive
        ))


MODULE_CLASSES.append(DynamicFilters)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserResetFilter(bpy.types.Operator):
    bl_idname = "engon.browser_reset_filter"
    bl_label = "Reset Filter"
    bl_description = "Resets all or a selected filter in polygoniq asset browser"

    filter_name: bpy.props.StringProperty()
    reset_all: bpy.props.BoolProperty(default=False)

    def execute(self, context: bpy.types.Context):
        dyn_filters = get_filters(context)
        if self.reset_all:
            for filter_ in dyn_filters.filters.values():
                filter_.reset()

            self.reset_all = False
            return {'FINISHED'}
        filter_ = dyn_filters.get_param_filter(self.filter_name)
        if filter_ is not None:
            filter_.reset()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserResetFilter)


def _draw_tags(context: bpy.types.Context, layout: bpy.types.UILayout):
    """Draws dynamic filter tags to 'layout' as pills that adjust width based on the region size"""
    dyn_filters = get_filters(context)
    tag_filters: typing.List[BrowserTagFilter] = [
        x for x in dyn_filters.tag_filters if x.is_drawn()]

    if len(tag_filters) == 0:
        row = layout.row()
        row.enabled = False
        row.label(text="No tags found", icon='PANEL_CLOSE')
        return

    layout.label(text="Tags")
    col = layout.column()
    col.enabled = not asset_repository.is_loading
    row = col.row()
    row.alignment = 'LEFT'

    ui_scale = context.preferences.system.ui_scale
    estimated_row_width_px = 0
    for tag_filter in tag_filters:
        # 20 is a margin for each drawn prop
        estimated_row_width_px += ui_scale * (
            len(tag_filter.name_without_type) * utils.EST_LETTER_WIDTH_PX + 20)

        # 150 is a width from where we display tags always on a single row
        if estimated_row_width_px > context.region.width or context.region.width < 150:
            estimated_row_width_px = 0
            row = col.row()
            row.alignment = 'LEFT'

        row.enabled = tag_filter.enabled or not tag_filter.is_default()
        tag_filter.draw(context, row)


def draw(context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
    dyn_filters = get_filters(context)
    row = layout.row()
    applied_count = sum(f.is_applied() for f in dyn_filters.filters.values())
    if applied_count > 0:
        col = row.column()
        col.enabled = False
        col.label(text=f"Applied {applied_count} filter(s)")
        row.operator(MAPR_BrowserResetFilter.bl_idname, text="",
                     icon='PANEL_CLOSE').reset_all = True

    _draw_tags(context, layout)

    parametrization_filters = dyn_filters.get_grouped_parametrization_filters()
    parametrization_filters.draw(context, layout)


def get_filters(context: typing.Optional[bpy.types.Context] = None) -> DynamicFilters:
    if context is None:
        context = bpy.context

    return context.window_manager.pq_mapr_filters_v2


def on_registry_update():
    asset_repository.update_provider(asset_registry.instance.master_asset_provider)


@bpy.app.handlers.persistent
def on_load_post(_):
    # We need to reset the filters and reconstruct on loading the blend file, because
    # the filter properties in 'pq_mapr_filters_v2' reset and the filters state wouldn't correspond
    # to the browser state.
    filters_ = get_filters()
    filters_.reset()
    filters_.query_and_reconstruct(asset_repository.current_category_id)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.pq_mapr_filters_v2 = bpy.props.PointerProperty(type=DynamicFilters)
    asset_registry.instance.on_refresh.append(on_registry_update)
    bpy.app.handlers.load_post.append(on_load_post)


def unregister():
    del bpy.types.WindowManager.pq_mapr_filters_v2

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)

    asset_registry.instance.on_refresh.remove(on_registry_update)
    bpy.app.handlers.load_post.remove(on_load_post)
