# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import logging
from .. import polib
from . import filters
from .. import asset_registry
from .. import preferences

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


def get_updated_asset_packs(context: bpy.types.Context) -> typing.Set[asset_registry.AssetPack]:
    what_is_new_pref = preferences.prefs_utils.get_preferences(context).what_is_new_preferences
    never_seen_packs = set()
    for pack in asset_registry.instance.get_registered_packs():
        seen_pack = what_is_new_pref.latest_seen_asset_packs.get(pack.full_name)
        if seen_pack is not None and tuple(seen_pack.version) < pack.version:
            never_seen_packs.add(pack)

    return never_seen_packs


def _draw_what_is_new_browser_operators(
    layout: bpy.types.UILayout, updated_packs: typing.Set[asset_registry.AssetPack]
) -> None:
    for asset_pack in updated_packs:
        category = asset_registry.instance.master_asset_provider.get_category_safe(
            asset_pack.main_category_id
        )
        search_op = layout.operator(
            MAPR_BrowserDisplayNewAssets.bl_idname,
            text=category.title,
            **polib.ui_bpy.get_asset_pack_icon_parameters(
                asset_pack.get_pack_icon_id(), 'ASSET_MANAGER'
            ),
        )
        search_op.category_id = category.id_
        search_op.pack_name = asset_pack.full_name


def draw_what_is_new_browser_prompt(context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
    updated_packs = get_updated_asset_packs(context)
    if len(updated_packs) == 0:
        return

    row = layout.row(align=True)
    row.alignment = 'CENTER'

    if len(updated_packs) < 4:
        row.label(text="See What's New!", icon='OUTLINER_OB_LIGHT')
        row = layout.row(align=True)
        row.scale_y = 2.0
        row.alignment = 'CENTER'
        _draw_what_is_new_browser_operators(row, updated_packs)
    else:
        row = row.row(align=True)
        row.scale_y = 2.0
        row.popover(
            MAPR_BrowserWhatIsNewPopoverPanel.bl_idname,
            icon='OUTLINER_OB_LIGHT',
            text="See What's New!",
        )

    row.separator()
    row.operator(MAPR_BrowserDismissNewAssets.bl_idname, text="", icon='X')

    layout.separator()


def _ensure_asset_pack_known(
    what_is_new_pref: preferences.what_is_new_preferences.WhatIsNewPreferences,
    pack_full_name: str,
    pack_version: typing.Tuple[int, int, int],
) -> None:
    # If an asset pack is not present seen_packs, it means that it's a completely new pack.
    # We don't want to display the 'what is new' filter for such asset pack,
    # as user is likely to go explore on their own anyway.
    seen_pack = what_is_new_pref.latest_seen_asset_packs.get(pack_full_name)
    if seen_pack is None:
        what_is_new_pref.see_asset_pack(pack_full_name, pack_version)


def ensure_all_registered_asset_packs_known() -> None:
    context = bpy.context
    prefs = preferences.prefs_utils.get_preferences(context)
    for pack in asset_registry.instance.get_registered_packs():
        logger.debug(f"First time seeing {pack.full_name}, marking version as seen.")
        _ensure_asset_pack_known(prefs.what_is_new_preferences, pack.full_name, pack.version)
    if prefs.save_prefs:
        bpy.ops.wm.save_userpref()


@polib.log_helpers_bpy.logged_panel
class MAPR_BrowserWhatIsNewPopoverPanel(bpy.types.Panel):
    bl_idname = "PREFERENCES_PT_what_is_new_popover_panel"
    bl_label = "See What's New"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'HEADER'

    def draw(self, context: bpy.types.Context) -> None:
        _draw_what_is_new_browser_operators(self.layout, get_updated_asset_packs(context))


MODULE_CLASSES.append(MAPR_BrowserWhatIsNewPopoverPanel)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserDisplayNewAssets(bpy.types.Operator):
    bl_idname = "engon.browser_display_new_assets"
    bl_label = "Display New Assets"
    bl_description = (
        "Resets all filters in engon "
        "and searches for assets that were added since the seen asset pack version"
    )

    pack_name: bpy.props.StringProperty(
        name="Asset Pack Name", description="Full name of the asset pack to search from"
    )
    category_id: bpy.props.StringProperty(
        name="Category ID", description="Category ID belonging to the asset pack to search from"
    )

    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context)
        what_is_new_pref = prefs.what_is_new_preferences
        seen_pack = what_is_new_pref.latest_seen_asset_packs.get(self.pack_name)
        assert seen_pack is not None
        old_major, old_minor, old_patch = seen_pack.version
        filters.MAPR_BrowserResetFilter.reset_all_filters(context)
        dyn_filters = filters.get_filters(context)

        asset_pack = asset_registry.instance.get_pack_by_full_name(self.pack_name)
        assert asset_pack is not None
        filter_ = dyn_filters.get_param_filter("vec:introduced_in")
        if filter_ is None:
            logger.error(
                f"No mandatory 'vec:introduced_in' parameter in asset pack {self.pack_name}"
            )
            return {'CANCELLED'}
        newest_version = asset_pack.version
        filter_.range_start = (old_major, old_minor, old_patch + 1)
        filter_.range_end = newest_version
        dyn_filters.query_and_reconstruct(self.category_id)

        what_is_new_pref.see_asset_pack(self.pack_name, newest_version)
        if prefs.save_prefs:
            bpy.ops.wm.save_userpref()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserDisplayNewAssets)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserDismissNewAssets(bpy.types.Operator):
    bl_idname = "engon.browser_dismiss_new"
    bl_label = "Dismiss New Assets"
    bl_description = "Marks all installed asset pack versions as seen"

    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context)
        what_is_new_pref = prefs.what_is_new_preferences
        for pack in asset_registry.instance.get_registered_packs():
            what_is_new_pref.see_asset_pack(pack.full_name, pack.version)
        if prefs.save_prefs:
            bpy.ops.wm.save_userpref()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserDismissNewAssets)


def register() -> None:
    asset_registry.instance.on_refresh.append(ensure_all_registered_asset_packs_known)
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    asset_registry.instance.on_refresh.remove(ensure_all_registered_asset_packs_known)
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
