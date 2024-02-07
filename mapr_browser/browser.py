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
import typing
import mapr
import polib
from . import filters
from . import previews
from . import spawn
from . import categories
from . import utils
from . import dev
from .. import preferences
from .. import asset_registry

MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_panel
class MAPR_BrowserPreferencesPopoverPanel(bpy.types.Panel):
    bl_idname = "PREFERENCES_PT_mapr_preferences"
    bl_label = "Preferences"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'HEADER'

    def draw_debug_info(
        self,
        layout: bpy.types.UILayout,
    ) -> None:
        col = layout.column()
        col.operator(dev.MAPR_BrowserDeleteCache.bl_idname)
        col.operator(dev.MAPR_BrowserReconstructFilters.bl_idname)
        col.operator(dev.MAPR_BrowserReloadPreviews.bl_idname)
        col.separator()
        col.label(text="Asset Providers:")
        sub_col = col.column(align=True)
        for provider in asset_registry.instance.master_asset_provider._asset_providers:
            sub_col.label(text=str(provider))

        col.separator()
        col.label(text="Preview Manager:")
        col.label(text=str(previews.manager_instance))

        col.separator()
        col.label(text="Polygoniq Global:")
        col.label(text=str(getattr(bpy, "polygoniq_global", None)))

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        prefs = preferences.get_preferences(context).mapr_preferences
        layout.prop(prefs, "search_history_count")
        layout.prop(prefs, "use_pills_nav")
        layout.prop(prefs, "debug")
        if prefs.debug:
            self.draw_debug_info(layout)


MODULE_CLASSES.append(MAPR_BrowserPreferencesPopoverPanel)


@polib.log_helpers_bpy.logged_operator
class MAPR_ShowAssetDetail(bpy.types.Operator):
    bl_idname = "engon.browser_show_asset_detail"
    bl_label = "Show Asset Detail"

    asset_id: bpy.props.StringProperty(
        name="Asset ID",
        description="ID of asset to spawn into scene",
        options={'HIDDEN'}
    )

    groups_collapse: bpy.props.BoolVectorProperty(
        size=len(mapr.known_metadata.PARAMETER_GROUPING),
        default=[True] * len(mapr.known_metadata.PARAMETER_GROUPING)
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
        for i, (group_name, group_parameters) in enumerate(mapr.known_metadata.PARAMETER_GROUPING.items()):
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
                text=mapr.known_metadata.format_parameter_name(group_name),
                emboss=False,
                icon='RIGHTARROW' if collapse else 'DOWNARROW_HLT'
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
                    text=f"{mapr.known_metadata.format_parameter_name(param_name)}: {value} {param_unit}")

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
        layout.template_icon(previews.manager_instance.get_preview(self.asset.id_), scale=12.0)
        box = layout.box()
        heading = box.row()
        heading.enabled = False
        if len(self.asset.tags) > 0:
            heading.label(text="Tags")
            row = box.row()
            for tag in sorted(self.asset.tags):
                row.label(text=tag)
        else:
            heading.label(text="No tags found")

        self.draw_parameters(layout)

        row = layout.box().row()
        row.enabled = False
        row.label(text=f"Asset ID: {self.asset.id_}")

    def execute(self, context: bpy.types.Context):
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.asset = asset_registry.instance.master_asset_provider.get_asset(self.asset_id)
        return context.window_manager.invoke_popup(self)


MODULE_CLASSES.append(MAPR_ShowAssetDetail)


def draw_asset_previews(
    context: bpy.types.Context,
    layout: bpy.types.UILayout,
    mapr_prefs: preferences.MaprPreferences
) -> None:
    pm = previews.manager_instance
    assets = filters.asset_repository.get_current_assets()
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
        entry.template_icon(
            pm.get_preview(asset.id_),
            scale=preview_scale
        )

        # The columns scale based on the content, we need to trim the text so the width of assets
        # resizes correctly.
        asset_title = asset.title
        # 3.0 is a constant that represents scale -> text width transformation
        expected_chars = int(preview_scale * 3.0)
        if (len(asset.title) + 3) > expected_chars:
            asset_title = asset.title[:expected_chars] + "..."

        row = entry.row(align=True)
        row.operator(
            spawn.MAPR_BrowserSpawnAsset.bl_idname,
            text=asset_title,
            icon=utils.get_icon_of_asset_data_type(asset.type_)
        ).asset_id = str(asset.id_)

        row.operator(
            MAPR_ShowAssetDetail.bl_idname, text="", icon='VIEWZOOM').asset_id = str(asset.id_)


def prefs_content_draw_override(self, context: bpy.types.Context):
    if filters.asset_repository.is_loading:
        row = self.layout.row()
        row.alignment = 'CENTER'
        row.label(text="Loading...")
        return
    prefs = preferences.get_preferences(context).mapr_preferences
    draw_asset_previews(context, self.layout, prefs)


def prefs_navbar_draw_override(self, context: bpy.types.Context):
    layout = self.layout
    prefs = preferences.get_preferences(context).mapr_preferences

    row = layout.row(align=True)
    row.label(text="engon browser",
              icon_value=polib.ui_bpy.icon_manager.get_polygoniq_addon_icon_id("engon"))

    sub = row.row()
    sub.alert = True
    sub.operator(MAPR_BrowserClose.bl_idname, text="", icon='PANEL_CLOSE')

    if prefs.use_pills_nav:
        categories.draw_category_pills_header(context, layout, context.region.width)
    else:
        categories.draw_tree_category_navigation(context, layout)

    filters.draw(context, layout)


def prefs_header_draw_override(self, context: bpy.types.Context):
    layout: bpy.types.UILayout = self.layout
    prefs = preferences.get_preferences(context).mapr_preferences
    layout.scale_x, layout.scale_y = 1, 1
    # draw EDITOR_TYPE selector
    layout.row().template_header()

    mapr_filters = filters.get_filters(context)
    row = layout.row()

    sub = row.row(align=True)
    mapr_filters.search.draw(context, sub)

    sub = row.row(align=True)
    mapr_filters.asset_types.draw(context, sub)

    row.separator_spacer()
    sub = row.row(align=True)
    sub.popover(panel=spawn.SpawnOptionsPopoverPanel.bl_idname, text="", icon='FILE_TICK')
    sub.prop(mapr_filters, "sort_mode", text="", icon='SORTALPHA', icon_only=True)
    sub.prop(prefs, "preview_scale_percentage", slider=True, text="")
    sub.popover(
        panel=MAPR_BrowserPreferencesPopoverPanel.bl_idname,
        text="",
        icon='MODIFIER',
    )


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserOpen(bpy.types.Operator):
    bl_idname = "engon.browser_open"
    bl_description = "Opens engon asset browser in a new window"
    bl_label = "Open engon Asset Browser"

    # We store previous draw functions as class properties to be returned in
    # MAPR_ReturnPreferences
    addons_prev_draw: typing.Optional[typing.Callable] = None
    header_prev_draw: typing.Optional[typing.Callable] = None
    nav_prev_draw: typing.Optional[typing.Callable] = None
    prev_area_ui_types: typing.Dict[bpy.types.Area, str] = {}

    def execute(self, context: bpy.types.Context):
        area = context.area
        existing_windows = [
            w for w in context.window_manager.windows if w.screen.get("is_polygoniq", False)]
        # If any windows are already open, close them and reopen one window again so it is
        # focused.
        for window in existing_windows:
            with context.temp_override(window=window):
                bpy.ops.wm.window_close()

        bpy.ops.wm.window_new()
        window: bpy.types.Window = context.window_manager.windows[-1]
        window.screen["is_polygoniq"] = True
        area = window.screen.areas[0]

        self.open_browser(context, area)
        return {'FINISHED'}

    @classmethod
    def hijack_preferences(cls, context: bpy.types.Context) -> None:
        context.preferences.active_section = 'ADDONS'
        # Save previous overrides if any, so we can return them, save only if we did not hijack yet
        if cls.addons_prev_draw is None:
            cls.addons_prev_draw = bpy.types.USERPREF_PT_addons.draw
            bpy.types.USERPREF_PT_addons.draw = prefs_content_draw_override

        if cls.nav_prev_draw is None:
            cls.nav_prev_draw = bpy.types.USERPREF_PT_navigation_bar.draw
            bpy.types.USERPREF_PT_navigation_bar.draw = prefs_navbar_draw_override

        if cls.header_prev_draw is None:
            cls.header_prev_draw = bpy.types.USERPREF_HT_header.draw
            bpy.types.USERPREF_HT_header.draw = prefs_header_draw_override

        utils.tag_prefs_redraw(context)

    @classmethod
    def open_browser(cls, context: bpy.types.Context, area: bpy.types.Area) -> None:
        cls.prev_area_ui_types[area] = area.ui_type
        area.ui_type = 'PREFERENCES'
        preferences.get_preferences(context).mapr_preferences.prefs_hijacked = True
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
                        self.draw_callback, (context,), region.type, 'POST_PIXEL')
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
            MAPR_BrowserOpen.open_browser(context, self.area)
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
        if MAPR_BrowserOpen.addons_prev_draw is not None:
            bpy.types.USERPREF_PT_addons.draw = MAPR_BrowserOpen.addons_prev_draw
            MAPR_BrowserOpen.addons_prev_draw = None

        if MAPR_BrowserOpen.nav_prev_draw is not None:
            bpy.types.USERPREF_PT_navigation_bar.draw = MAPR_BrowserOpen.nav_prev_draw
            MAPR_BrowserOpen.nav_prev_draw = None

        if MAPR_BrowserOpen.header_prev_draw is not None:
            bpy.types.USERPREF_HT_header.draw = MAPR_BrowserOpen.header_prev_draw
            MAPR_BrowserOpen.header_prev_draw = None

        # Return all areas that were open at runtime to previous state
        for area, prev_ui_type in MAPR_BrowserOpen.prev_area_ui_types.items():
            area.ui_type = prev_ui_type

        MAPR_BrowserOpen.prev_area_ui_types.clear()

        if store_state_to_prefs:
            preferences.get_preferences(context).mapr_preferences.prefs_hijacked = False
        utils.tag_prefs_redraw(context)

    def execute(self, context: bpy.types.Context):
        MAPR_BrowserClose.return_preferences(context)
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserClose)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserToggleArea(bpy.types.Operator):
    bl_idname = "engon.browser_toggle_area"
    bl_description = "Toggles area under mouse to mapr browser and back. If the previous area " \
        "contained preferences, this does nothing"
    bl_label = "Toggle engon Browser"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Returning to preferences will close the browser in all other areas.")
        col.label(text="Do you want to continue?")

    def execute(self, context: bpy.types.Context):
        area = context.area
        prev_ui_type = MAPR_BrowserOpen.prev_area_ui_types.get(area, None)
        # Area is not stored in MAPR_BrowserOpen, thus it is not opened yet
        if prev_ui_type is None:
            MAPR_BrowserOpen.open_browser(context, context.area)
        else:
            area.ui_type = prev_ui_type
            del MAPR_BrowserOpen.prev_area_ui_types[area]
            # We only return preferences, if the hijacked area was preferences before. This happens
            # only after user confirms the message presented in 'draw'.
            if prev_ui_type == 'PREFERENCES':
                MAPR_BrowserClose.return_preferences(context, store_state_to_prefs=True)

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if context.area is None:
            return {'CANCELLED'}

        # When the area under mouse was previously preferences, we invoke a dialog with
        # a message to inform user that this action will return to preferences, but close all
        # browser views.
        prev_ui_type = MAPR_BrowserOpen.prev_area_ui_types.get(context.area, None)
        if prev_ui_type is not None and prev_ui_type == 'PREFERENCES':
            return context.window_manager.invoke_props_dialog(self, width=350)

        return self.execute(context)


MODULE_CLASSES.append(MAPR_BrowserToggleArea)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserOpenAssetPacksPreferences(bpy.types.Operator):
    bl_idname = "engon.browser_open_asset_packs_preferences"
    bl_description = "Opens engon preferences with the Asset Packs section opened"
    bl_label = "Open Preferences"

    def execute(self, context: bpy.types.Context):
        top_package = __package__.split(".", 1)[0]
        assert top_package != "", \
            f"Top package of hierarchy `{__package__}` cannot be an empty string!"
        MAPR_BrowserClose.return_preferences(context)
        bpy.ops.preferences.addon_show(module=top_package)
        gen_prefs = preferences.get_preferences(context).general_preferences
        gen_prefs.show_asset_packs = True
        gen_prefs.show_pack_info_paths = False
        gen_prefs.show_keymaps = False
        gen_prefs.show_updater_settings = False
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserOpenAssetPacksPreferences)


@bpy.app.handlers.persistent
def mapr_browser_load_post_handler(_):
    prefs = preferences.get_preferences(bpy.context).mapr_preferences
    # If mapr browser replaced preferences in previous instance, open it again
    if prefs.prefs_hijacked:
        # We need to clear the previously stored area ui types, so we don't refresh
        # anything that doesn't exist anymore.
        MAPR_BrowserOpen.prev_area_ui_types.clear()
        MAPR_BrowserOpen.hijack_preferences(bpy.context)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.app.handlers.load_post.append(mapr_browser_load_post_handler)


def unregister():
    bpy.app.handlers.load_post.remove(mapr_browser_load_post_handler)
    MAPR_BrowserClose.return_preferences(bpy.context, store_state_to_prefs=False)

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
