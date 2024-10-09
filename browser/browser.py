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

import bpy
import gpu
import os
import shutil
import typing
import logging
from .. import mapr
from .. import polib
from . import filters
from . import previews
from . import spawn
from . import categories
from . import what_is_new
from . import utils
from . import dev
from .. import preferences
from .. import asset_registry
from .. import __package__ as base_package

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []
IS_KNOWN_BROWSER = "pq_is_known_browser"
IS_KNOWN_BROWSER_POPUP = "pq_is_known_browser_popup"
# Path where Blender stores thumbnails that failed to load, this can happen e. g. when the source file
# cannot be further read after opened and isn't considered valid image.
FAILED_THUMBNAILS_PATH = os.path.expanduser(os.path.join("~", ".thumbnails", "fail", "blender"))

# Sets of asset ids that were introduced prior to the introduction of the 'Drawable' tag in engon
# 1.1.0. The tag is used to decide whether to display the draw button. We don't know based
# on the asset data itself, so we need to hardcode it here, at least until the assets metadata
# are updated in future pack releases. NOTE: This way we support this feature on older assets with
# engon update.
DRAWABLE_GEONODES_ASSET_IDS = {
    # traffiq
    # tq_EU_2-Lanes-Highway
    "24c8e509-b316-4a76-9479-d556607a81bb",
    # tq_EU_2-Lanes-Highway-Barrier
    "d99aa7ec-dc86-45fd-9761-074efe5157bf",
    # tq_EU_3-Lanes-Highway
    "f6e7451c-02ff-4066-a8df-93c3fde30836",
    # tq_EU_3-Lanes-Highway-Barrier
    "215d5ba9-1ee6-4ce4-b95c-256289bc25a0",
    # tq_EU_Country
    "77db6620-c0d5-4460-9aad-9bf3f2352f6e",
    # tq_EU_Street-Tree-Alley
    "4e28d3bb-019c-4a16-a789-3f26d1e0f08e",
    # tq_EU_Street-Tree-Alley-Median
    "e2caec75-763d-42bc-868d-79dd27333716",
    # tq_Generic_Dirt-Road
    "fce8c3c6-b71d-41b2-90b4-56dc269dd253",
    # tq_Generic_Forest-Road
    "fee52bca-cd86-4146-bf09-ded78171a628",
    # tq_US_Country
    "d043cefc-ff97-4369-8adc-f8d7055ed77c",
    # botaniq
    # bq_Vines_Vitis-vinifera_A_spring-summer
    "cd6b5586-2460-4e95-ae3e-b1cbebb1fc00",
    # aquatiq
    # aq_Generator_River
    "65e0c167-58c8-4f2e-8892-160c5cc979be",
}

# Owner object of the message bus that we subscribe to in the register method
_MSGBUS_OWNER = object()


@polib.log_helpers_bpy.logged_panel
class MAPR_BrowserPreferencesPopoverPanel(bpy.types.Panel):
    bl_idname = "PREFERENCES_PT_browser_preferences"
    bl_label = "Preferences"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'HEADER'

    def draw_debug_info(self, layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        col = layout.column()
        col.operator(dev.MAPR_BrowserDeleteCache.bl_idname)
        col.operator(dev.MAPR_BrowserReconstructFilters.bl_idname)
        col.separator()
        col.label(text="Asset Providers:")
        sub_col = col.column(align=True)
        for provider in asset_registry.instance.master_asset_provider._asset_providers:
            sub_col.label(text=str(provider))

        col.separator()
        col.label(text="Preview Manager:")
        col.label(text=str(previews.preview_manager))

        col.separator()
        col.label(text="Polygoniq Global:")
        col.label(text=str(getattr(bpy, "polygoniq_global", None)))

        col.separator()
        col.label(text="Seen Assets (for What's New):")
        what_is_new_pref = preferences.prefs_utils.get_preferences(context).what_is_new_preferences

        for seen_pack in what_is_new_pref.latest_seen_asset_packs:
            col.label(text=f"{seen_pack.name}: {'.'.join(map(str, seen_pack.version))}")

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        col = layout.column()
        col.prop(prefs, "search_history_count")
        col.prop(prefs, "use_pills_nav")
        col.separator()
        col.operator(MAPR_BrowserReloadPreviews.bl_idname, icon='FILE_REFRESH')
        col.separator()
        col.prop(prefs, "debug")
        if prefs.debug:
            self.draw_debug_info(layout, context)


MODULE_CLASSES.append(MAPR_BrowserPreferencesPopoverPanel)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserReloadPreviews(bpy.types.Operator):
    bl_idname = "engon.browser_reload_previews"
    bl_label = "Reload Previews"
    bl_description = (
        f"Deletes the {FAILED_THUMBNAILS_PATH} directory and forces asset previews to reload"
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(
            text="This will delete the following directory to force Blender to reload previews"
        )
        col.label(text=f"{FAILED_THUMBNAILS_PATH}")

        layout.label(text="Are you sure you want to continue?")

        row = layout.row()
        row.enabled = False
        row.label(text="Restart Blender if previews are stuck afterwards.")

    def execute(self, context: bpy.types.Context):
        # Blender caches thumbnails that failed to load in the following directory. Blender reloads
        # the directory, if the source file for the previews changes. We remove the directory to
        # force Blender to reload the previews even without changes.
        if os.path.isdir(FAILED_THUMBNAILS_PATH):
            logger.info(f"Removing the failed thumbnails path '{FAILED_THUMBNAILS_PATH}'")
            shutil.rmtree(FAILED_THUMBNAILS_PATH, ignore_errors=True)

        previews.preview_manager.clear()
        utils.tag_prefs_redraw(context)
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # In case of popup we want the user to confirm the deletion of the folder.
        if os.path.isdir(FAILED_THUMBNAILS_PATH):
            return context.window_manager.invoke_props_dialog(self, width=500)
        else:
            return self.execute(context)


MODULE_CLASSES.append(MAPR_BrowserReloadPreviews)


@polib.log_helpers_bpy.logged_operator
class MAPR_ShowAssetDetail(bpy.types.Operator):
    bl_idname = "engon.browser_show_asset_detail"
    bl_label = "Show Asset Detail"

    asset_id: bpy.props.StringProperty(
        name="Asset ID", description="ID of asset to spawn into scene", options={'HIDDEN'}
    )

    groups_collapse: bpy.props.BoolVectorProperty(
        size=len(mapr.known_metadata.PARAMETER_GROUPING),
        default=[True] * len(mapr.known_metadata.PARAMETER_GROUPING),
    )

    def draw_parameters(self, layout: bpy.types.UILayout) -> None:
        box = layout.box()
        heading = box.row()
        heading.enabled = False

        all_parameters = self.asset.parameters
        if len(all_parameters) == 0:
            heading.label(text="No parameters found")
            return

        heading.label(text="Parameters")
        already_considered_parameters: typing.Set[str] = set()
        for i, (group_name, group_parameters) in enumerate(
            mapr.known_metadata.PARAMETER_GROUPING.items()
        ):
            asset_parameters: typing.List[str] = []
            for param_name in group_parameters:
                param_name = mapr.parameter_meta.remove_type_from_name(param_name)
                value = all_parameters.get(param_name, None)
                if value is None:
                    continue
                asset_parameters.append(param_name)

            # Skip drawing for groups that are empty
            if len(asset_parameters) == 0:
                continue

            group_box = box.box()
            row = group_box.row()
            row.alignment = 'LEFT'
            collapse = self.groups_collapse[i]
            row.prop(
                self,
                "groups_collapse",
                index=i,
                text=mapr.known_metadata.format_group_name(group_name),
                emboss=False,
                icon='RIGHTARROW' if collapse else 'DOWNARROW_HLT',
            )
            already_considered_parameters.update(asset_parameters)
            if collapse:
                continue

            col = group_box.column(align=True)
            for param_name in asset_parameters:
                value = all_parameters[param_name]
                param_unit = mapr.known_metadata.PARAMETER_UNITS.get(param_name, "")
                if isinstance(value, float):
                    # Format value with up to 2 decimal places without trailing zeros
                    value = int(value) if value % 1 == 0 else float(f"{value:.2f}")
                col.label(
                    text=f"{mapr.known_metadata.format_parameter_name(param_name)}: {value} {param_unit}"
                )

        not_yet_drawn = set(all_parameters) - already_considered_parameters

        col = box.column(align=True)
        for param_name in sorted(not_yet_drawn):
            value = all_parameters[param_name]
            col.label(text=f"{mapr.known_metadata.format_parameter_name(param_name)}: {value}")

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        if self.asset is None:
            layout.label(text=f"Asset with {self.asset_id} not found!")
            return

        box = layout.box()
        title = box.row()
        title.label(text=f"{self.asset.title}")
        layout.template_icon(previews.preview_manager.get_icon_id(self.asset.id_), scale=12.0)
        box = layout.box()
        heading = box.row()
        heading.enabled = False
        if len(self.asset.tags) > 0:
            heading.label(text="Tags")
            col = box.column()
            for tag in sorted(self.asset.tags):
                col.label(text=tag)
        else:
            heading.label(text="No tags found")

        self.draw_parameters(layout)

        row = layout.box().row()
        row.enabled = False
        row.label(text=f"Asset ID: {self.asset.id_}")

        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        if prefs.debug:
            layout.separator()
            box = layout.box()
            box.label(
                text=f"Search score: {mapr.filters.SEARCH_ASSET_SCORE.get(self.asset.id_, 'n/a')}"
            )
            box.label(text=f"Search matter (DEBUG)")
            col = box.column(align=True)
            for token, weight in self.asset.search_matter.items():
                col.label(text=f"{token}: {weight}")

    def execute(self, context: bpy.types.Context):
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.asset = asset_registry.instance.master_asset_provider.get_asset(self.asset_id)
        return context.window_manager.invoke_popup(self)


MODULE_CLASSES.append(MAPR_ShowAssetDetail)


def draw_asset_buttons_row(
    context: bpy.types.Context,
    layout: bpy.types.UILayout,
    asset: mapr.asset.Asset,
    preview_scale: float,
) -> None:
    # The columns scale based on the content, we need to trim the text so the width of assets
    # resizes correctly.
    asset_title = asset.title
    # 3.0 is a constant that represents scale -> text width transformation
    expected_chars = int(preview_scale * 3.0)
    if (len(asset.title) + 3) > expected_chars:
        asset_title = asset.title[:expected_chars] + "..."

    row = layout.row(align=True)
    row.operator(
        spawn.MAPR_BrowserSpawnAsset.bl_idname,
        text=asset_title,
        icon=utils.get_icon_of_asset_data_type(asset.type_),
    ).asset_id = str(asset.id_)

    use_separator = False
    if "Drawable" in asset.tags or asset.id_ in DRAWABLE_GEONODES_ASSET_IDS:
        row.operator(
            spawn.MAPR_BrowserDrawGeometryNodesAsset.bl_idname, text="", icon='GREASEPENCIL'
        ).asset_id = str(asset.id_)
        use_separator = True

    if (
        asset.type_ == mapr.asset_data.AssetDataType.blender_model
        and spawn.MAPR_BrowserSpawnModelIntoParticleSystem.poll(context)
    ):
        row.operator(
            spawn.MAPR_BrowserSpawnModelIntoParticleSystem.bl_idname, text="", icon='PARTICLES'
        ).asset_id = str(asset.id_)
        use_separator = True

    if use_separator:
        row.separator()

    prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
    if prefs.debug and dev.IS_DEV:
        row.separator()
        row.operator(
            dev.MAPR_BrowserOpenAssetSourceBlend.bl_idname, text="", icon='HOME'
        ).asset_id = str(asset.id_)

    row.operator(MAPR_ShowAssetDetail.bl_idname, text="", icon='VIEWZOOM').asset_id = str(asset.id_)
    if prefs.debug:
        row = layout.row()
        row.enabled = False
        row.label(text=f"Search score: {mapr.filters.SEARCH_ASSET_SCORE.get(asset.id_, 'n/a')}")


def draw_asset_previews(
    context: bpy.types.Context,
    layout: bpy.types.UILayout,
    mapr_prefs: preferences.browser_preferences.BrowserPreferences,
) -> None:
    pm = previews.preview_manager
    assets = filters.asset_repository.current_assets
    if len(asset_registry.instance.get_registered_packs()) == 0:
        col = layout.column()
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(text="You do not have any Asset Packs installed.")

        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(text="Click the button bellow to install Asset Packs in engon preferences.")

        col.separator()
        row = col.row()
        row.scale_y = 1.2
        row.alignment = 'CENTER'
        row.operator(MAPR_BrowserOpenAssetPacksPreferences.bl_idname, icon='SETTINGS')
        return

    elif len(assets) == 0:
        col = layout.column()
        col.separator()
        row = col.row()
        row.alignment = 'CENTER'
        row.label(text="Nothing was found. Try different search parameters.")

        col.separator()
        row = col.row()
        row.scale_y = 1.2
        row.alignment = 'CENTER'
        if filters.asset_repository.current_category_id != mapr.category.DEFAULT_ROOT_CATEGORY.id_:
            row.operator(
                categories.MAPR_BrowserEnterCategory.bl_idname,
                text="Search All Categories",
                icon='LOOP_BACK',
            ).category_id = mapr.category.DEFAULT_ROOT_CATEGORY.id_
        row.operator(
            filters.MAPR_BrowserResetFilter.bl_idname, text="Reset All Filters", icon='PANEL_CLOSE'
        ).reset_all = True
        return

    grid_flow = layout.grid_flow(
        row_major=True,
        align=False,
        # columns = 0 calculates the number of columns automatically
        columns=0,
    )
    for asset in assets:
        entry = grid_flow.box().column(align=True)
        # Convert percentages to Blender icon scale, 0% = 5.0, 100% = 12.5
        preview_scale = mapr_prefs.preview_scale_percentage / 100 * 7.5 + 5
        entry.template_icon(pm.get_icon_id(asset.id_), scale=preview_scale)
        draw_asset_buttons_row(context, entry, asset, preview_scale)


def is_known_browser(window: bpy.types.Window) -> bool:
    """Returns true if the given 'window' is a known browser window (It was opened by us)"""
    return bool(window.screen.get(IS_KNOWN_BROWSER, False))


def prefs_content_draw(self, context: bpy.types.Context) -> None:
    what_is_new_prefs = preferences.prefs_utils.get_preferences(context).what_is_new_preferences
    layout = self.layout
    if what_is_new_prefs.display_what_is_new:
        what_is_new.draw_what_is_new_browser_prompt(context, layout)

    if filters.asset_repository.is_loading:
        row = layout.row()
        row.alignment = 'CENTER'
        row.label(text="Loading...")
        return
    prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
    draw_asset_previews(context, layout, prefs)


def prefs_navbar_draw(self, context: bpy.types.Context) -> None:
    layout = self.layout
    prefs = preferences.prefs_utils.get_preferences(context).browser_preferences

    row = layout.row(align=True)
    row.label(
        text="engon browser",
        icon_value=polib.ui_bpy.icon_manager.get_polygoniq_addon_icon_id("engon"),
    )

    sub = row.row()
    sub.alert = True
    sub.operator(MAPR_BrowserClose.bl_idname, text="", icon='PANEL_CLOSE')

    if prefs.use_pills_nav:
        categories.draw_category_pills_header(context, layout, context.region.width)
    else:
        categories.draw_tree_category_navigation(context, layout)

    layout.separator()
    row = layout.row(align=True)
    row.operator(spawn.MAPR_BrowserSpawnAllDisplayed.bl_idname, icon='IMGDISPLAY')
    layout.separator()
    filters.draw(context, layout)


def prefs_header_draw(self, context: bpy.types.Context) -> None:
    layout: bpy.types.UILayout = self.layout
    prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
    layout.scale_x, layout.scale_y = 1, 1
    # draw EDITOR_TYPE selector
    layout.row().template_header()

    mapr_filters = filters.get_filters(context)
    row = layout.row()

    sub = row.row(align=True)
    mapr_filters.search.draw(context, sub)

    sub = row.row(align=True)
    mapr_filters.asset_types.draw(context, sub)
    if not MAPR_BrowserOpen.is_browser_override_correct:
        sub = row.row(align=True)
        sub.operator(MAPR_EnsureCorrectActivePrefSection.bl_idname, icon='SHADERFX')

    row.separator_spacer()
    sub = row.row()
    sub.enabled = False
    current_assets_count = len(filters.asset_repository.current_assets)
    sub.label(text=f"Browsing {current_assets_count} asset" + "s" * (current_assets_count != 1))

    row.separator_spacer()
    sub = row.row(align=True)
    sub.popover(panel=spawn.SpawnOptionsPopoverPanel.bl_idname, text="", icon='OPTIONS')
    sub.prop(mapr_filters, "sort_mode", text="", icon='SORTALPHA', icon_only=True)
    sub.prop(prefs, "preview_scale_percentage", slider=True, text="")
    sub.popover(
        panel=MAPR_BrowserPreferencesPopoverPanel.bl_idname,
        text="",
        icon='MODIFIER',
    )


def _override_proxy(self, context: bpy.types.Context, override: typing.Callable[..., None]) -> None:
    """Proxy to the override function so we can control whether we draw the browser."""
    panel_name_type = type(self).__name__
    compatible_sections = {'ADDONS', 'KEYMAP', 'THEMES'}
    # If user changed the active section in preferences, the browser will appear incorrect
    # if not in compatible section.
    MAPR_BrowserOpen.is_browser_override_correct = (
        context.preferences.active_section in compatible_sections
    )
    if not is_known_browser(context.window):
        # If the browser is not known, we draw the original panel
        return MAPR_BrowserOpen.USERPREF_prev_draw[panel_name_type](self, context)
    return override(self, context)


def _prefs_navbar_draw_override(self, context: bpy.types.Context) -> None:
    _override_proxy(self, context, prefs_navbar_draw)


def _prefs_header_draw_override(self, context: bpy.types.Context) -> None:
    _override_proxy(self, context, prefs_header_draw)


def _prefs_content_draw_override(self, context: bpy.types.Context) -> None:
    _override_proxy(self, context, prefs_content_draw)


@polib.log_helpers_bpy.logged_operator
class MAPR_EnsureCorrectActivePrefSection(bpy.types.Operator):
    bl_idname = "engon.ensure_correct_active_perf_section"
    bl_description = (
        "After opening preferences and changing the section, the engon browser might "
        "look unusual. This fixes the issue by changing to the 'ADDONS' section"
    )
    bl_label = "Fix engon Browser Layout"

    def execute(self, context: bpy.types.Context):
        context.preferences.active_section = 'ADDONS'
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_EnsureCorrectActivePrefSection)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserOpen(bpy.types.Operator):
    bl_idname = "engon.browser_open"
    bl_description = "Opens engon asset browser in a new window"
    bl_label = "Open engon Asset Browser"

    # We store previous draw functions as class properties to be returned in
    # MAPR_ReturnPreferences
    USERPREF_prev_draw: typing.Dict[str, typing.Callable[..., None]] = {}
    prev_area_ui_types: typing.Dict[bpy.types.Area, str] = {}
    is_browser_override_correct: bpy.props.BoolProperty(
        options={'HIDDEN'},
        description="When user changes the active section in preferences to an incompatible one, "
        "the engon browser might appear incorrect and this property will be set to false",
        default=True,
    )

    def execute(self, context: bpy.types.Context):
        area = context.area
        existing_windows = [
            w for w in context.window_manager.windows if w.screen.get(IS_KNOWN_BROWSER_POPUP, False)
        ]
        # If any windows are already open, close them and reopen one window again so it is
        # focused.
        for window in existing_windows:
            with context.temp_override(window=window):
                bpy.ops.wm.window_close()

        bpy.ops.wm.window_new()
        window: bpy.types.Window = context.window_manager.windows[-1]
        window.screen[IS_KNOWN_BROWSER_POPUP] = True
        area = window.screen.areas[0]

        self.open_browser(context, window, area)
        return {'FINISHED'}

    @classmethod
    def hijack_preferences(cls, context: bpy.types.Context) -> None:
        context.preferences.active_section = 'ADDONS'
        # We hijack the draw functions of preferences, to override it with our own.
        for userpref_type_name in filter(lambda t: t.startswith("USERPREF_"), dir(bpy.types)):
            # Save previous overrides if any, so we can return them, save only if we did not hijack yet
            if userpref_type_name in cls.USERPREF_prev_draw:
                continue
            userpref_type = getattr(bpy.types, userpref_type_name)
            if not hasattr(userpref_type, "draw"):
                continue
            cls.USERPREF_prev_draw[userpref_type_name] = userpref_type.draw
            _draw_funcs = getattr(userpref_type.draw, "_draw_funcs", None)
            if userpref_type == bpy.types.USERPREF_PT_navigation_bar:
                userpref_type.draw = _prefs_navbar_draw_override
            elif userpref_type == bpy.types.USERPREF_HT_header:
                userpref_type.draw = _prefs_header_draw_override
            else:
                userpref_type.draw = _prefs_content_draw_override

            # Since Blender 4.2 there can be multiple draw functions per panel, this needs to be
            # retrieved and stored in our override draw function too, so other methods dependent
            # on the _draw_funcs variable work correctly. (Like 'is_extended').
            if _draw_funcs is not None:
                userpref_type.draw._draw_funcs = _draw_funcs

        utils.tag_prefs_redraw(context)

    @classmethod
    def open_browser(
        cls, context: bpy.types.Context, window: bpy.types.Window, area: bpy.types.Area
    ) -> None:
        cls.prev_area_ui_types[area] = area.ui_type
        window.screen[IS_KNOWN_BROWSER] = True
        area.ui_type = 'PREFERENCES'
        preferences.prefs_utils.get_preferences(context).browser_preferences.prefs_hijacked = True
        # If the asset repository doesn't contain any view (it wasn't queried previously) we
        # query and reconstruct the filters manually within the root category.
        if filters.asset_repository.last_view is None:
            filters.get_filters(context).query_and_reconstruct(
                mapr.category.DEFAULT_ROOT_CATEGORY.id_
            )

        cls.hijack_preferences(context)


MODULE_CLASSES.append(MAPR_BrowserOpen)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserChooseArea(bpy.types.Operator):
    # Operator based on Set Origin operator in ScreenCastKeys from nutti,
    # available at https://github.com/nutti/Screencast-Keys/
    bl_idname = "engon.browser_choose_area"
    bl_description = "Click on a selected area to open engon asset browser there"
    bl_label = "Choose Browser Area"

    handlers: typing.Dict[typing.Tuple[bpy.types.Space, str], typing.Callable] = {}
    is_running = False

    def draw_callback(self, context: bpy.types.Context):
        region = context.region
        if region is not None and region == self.region:
            original_blend = gpu.state.blend_get()
            gpu.state.blend_set('ALPHA')
            polib.render_bpy.rectangle((0, 0), (region.width, region.height), (1, 1, 1, 0.3))
            gpu.state.blend_set(original_blend)

    def add_draw_handlers(self, context: bpy.types.Context):
        """Registers draw handlers for all areas in current screen

        This enables drawing in all sub-windows of active screen
        """
        for area in context.screen.areas:
            space_type = self.space_types.get(area.type, None)
            if space_type is None:
                continue

            for region in area.regions:
                if region.type == "" or region.type != 'WINDOW':
                    continue
                key = (space_type, region.type)
                if key not in MAPR_BrowserChooseArea.handlers:
                    handle = space_type.draw_handler_add(
                        self.draw_callback, (context,), region.type, 'POST_PIXEL'
                    )
                    MAPR_BrowserChooseArea.handlers[key] = handle

    def draw_handler_remove_all(self):
        for (space_type, region_type), handle in MAPR_BrowserChooseArea.handlers.items():
            space_type.draw_handler_remove(handle, region_type)
        MAPR_BrowserChooseArea.handlers.clear()

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        self.area, self.region = polib.ui_bpy.get_mouseovered_region(context, event)
        if self.area is not None:
            self.area.tag_redraw()

        if self.area_prev is not None:
            self.area_prev.tag_redraw()

        self.area_prev = self.area
        if event.type == 'LEFTMOUSE' and self.area is not None:
            # we pass context.window as you can't select area outside of window where this operator originated
            MAPR_BrowserOpen.open_browser(context, context.window, self.area)
            MAPR_BrowserChooseArea.is_running = False
            self.draw_handler_remove_all()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            MAPR_BrowserChooseArea.is_running = False
            self.draw_handler_remove_all()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.area = None
        self.region = None
        self.area_prev = None
        MAPR_BrowserChooseArea.is_running = True
        self.space_types = polib.ui_bpy.get_all_space_types()
        self.add_draw_handlers(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


MODULE_CLASSES.append(MAPR_BrowserChooseArea)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserClose(bpy.types.Operator):
    bl_idname = "engon.browser_close"
    bl_description = "Switches back from polygoniq browser to the original editor type"
    bl_label = "Close Browser"

    @staticmethod
    def return_preferences(context: bpy.types.Context, store_state_to_prefs: bool = True) -> None:
        # We use the previously stored draw functions from MAPR_OpenBrowser. There can be other
        # addons overriding the functionality, so we return what was in the preferences before.
        for userpref_type_str, prev_draw in MAPR_BrowserOpen.USERPREF_prev_draw.items():
            if not hasattr(bpy.types, userpref_type_str):
                # Some classes with hijacked draw functions might not be available
                # from the types module at some points
                # Currently this problem happens only when Blender closes
                # and the preferences were not returned prior to closing.
                continue
            type_ = getattr(bpy.types, userpref_type_str)
            type_.draw = prev_draw
        MAPR_BrowserOpen.USERPREF_prev_draw.clear()

        # Return all areas that still exist and were open at runtime to previous state
        all_areas = {a for window in context.window_manager.windows for a in window.screen.areas}
        for area, prev_ui_type in MAPR_BrowserOpen.prev_area_ui_types.items():
            if area in all_areas:
                area.ui_type = prev_ui_type
        MAPR_BrowserOpen.prev_area_ui_types.clear()

        if store_state_to_prefs:
            preferences.prefs_utils.get_preferences(context).browser_preferences.prefs_hijacked = (
                False
            )
        utils.tag_prefs_redraw(context)

    @staticmethod
    def abandon_window(window: bpy.types.Window) -> None:
        for area, prev_ui_type in MAPR_BrowserOpen.prev_area_ui_types.items():
            if area in list(window.screen.areas):
                area.ui_type = prev_ui_type

        del window.screen[IS_KNOWN_BROWSER]
        if window.screen.get(IS_KNOWN_BROWSER_POPUP) is not None:
            del window.screen[IS_KNOWN_BROWSER_POPUP]

    def execute(self, context: bpy.types.Context):
        MAPR_BrowserClose.return_preferences(context)
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserClose)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserToggleArea(bpy.types.Operator):
    bl_idname = "engon.browser_toggle_area"
    bl_description = (
        "Toggles area under mouse to engon browser and back. If the previous area "
        "contained preferences, this does nothing"
    )
    bl_label = "Toggle engon Browser"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(
            text="Returning to preferences will close the browser in all other areas of this window."
        )
        col.label(text="Do you want to continue?")

    def execute(self, context: bpy.types.Context):
        area = context.area
        # Force open the header region in case it was closed previously
        area.spaces.active.show_region_header = True
        prev_ui_type = MAPR_BrowserOpen.prev_area_ui_types.get(area, None)
        # Area is not stored in MAPR_BrowserOpen, thus it is not opened yet
        if prev_ui_type is None:
            MAPR_BrowserOpen.open_browser(context, context.window, context.area)
        else:
            area.ui_type = prev_ui_type
            del MAPR_BrowserOpen.prev_area_ui_types[area]
            # We only abandon window, if the hijacked area was preferences before. This happens
            # only after user confirms the message presented in 'draw'.
            if prev_ui_type == 'PREFERENCES':
                MAPR_BrowserClose.abandon_window(context.window)

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if context.area is None:
            return {'CANCELLED'}

        # When the area under mouse was previously preferences, we invoke a dialog with
        # a message to inform user that this action will return to preferences, but close all
        # browser views in that window.
        prev_ui_type = MAPR_BrowserOpen.prev_area_ui_types.get(context.area, None)
        if prev_ui_type is not None and prev_ui_type == 'PREFERENCES':
            return context.window_manager.invoke_props_dialog(self, width=400)

        return self.execute(context)


MODULE_CLASSES.append(MAPR_BrowserToggleArea)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserOpenAssetPacksPreferences(bpy.types.Operator):
    bl_idname = "engon.browser_open_asset_packs_preferences"
    bl_description = "Opens engon preferences with the Asset Packs section opened"
    bl_label = "Open Preferences"

    def execute(self, context: bpy.types.Context):
        bpy.ops.preferences.addon_show(module=base_package)
        gen_prefs = preferences.prefs_utils.get_preferences(context).general_preferences
        gen_prefs.show_asset_packs = True
        gen_prefs.show_pack_info_paths = False
        gen_prefs.show_keymaps = False
        gen_prefs.show_updater_settings = False
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserOpenAssetPacksPreferences)


def _active_object_changed():
    # We redraw the browser when active object changed, because some of the operators are
    # only display when active object is of a certain type and we need to update the UI.
    utils.tag_prefs_redraw(bpy.context)


def _subscribe_msg_bus():
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, "active"),
        owner=_MSGBUS_OWNER,
        args=(),
        notify=_active_object_changed,
        options={'PERSISTENT'},
    )


@bpy.app.handlers.persistent
def mapr_browser_load_post_handler(_):
    prefs = preferences.prefs_utils.get_preferences(bpy.context).browser_preferences
    # If mapr browser replaced preferences in previous instance, open it again
    if prefs.prefs_hijacked:
        # We need to clear the previously stored area ui types, so we don't refresh
        # anything that doesn't exist anymore.
        MAPR_BrowserOpen.prev_area_ui_types.clear()
        MAPR_BrowserOpen.hijack_preferences(bpy.context)

    # msgbus subscription is cleared on file load, so we need to subscribe again
    _subscribe_msg_bus()


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.app.handlers.load_post.append(mapr_browser_load_post_handler)
    _subscribe_msg_bus()


def unregister():
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    bpy.app.handlers.load_post.remove(mapr_browser_load_post_handler)
    MAPR_BrowserClose.return_preferences(bpy.context, store_state_to_prefs=False)

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
