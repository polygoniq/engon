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

from .. import addon_updater
from .. import addon_updater_ops
import bpy
import typing
import functools

# we don't use this module in this file but we use it elsewhere in engon, we import
# it here to make sure we handle module cache reloads correctly
from . import prefs_utils
from . import general_preferences
from . import browser_preferences
from . import what_is_new_preferences
from .. import available_asset_packs
from .. import keymaps
from .. import utils
from .. import features
from .. import polib
from .. import __package__ as base_package


telemetry = polib.get_telemetry("engon")


MODULE_CLASSES: list[typing.Any] = []
CONFLICTING_ADDONS = polib.utils_bpy.get_conflicting_addons(base_package)


@polib.log_helpers_bpy.logged_operator
class ShowReleaseNotes(bpy.types.Operator):
    bl_idname = "engon.show_release_notes"
    bl_label = "Show Release Notes"
    bl_description = "Show the release notes for the latest version of engon"
    bl_options = {'REGISTER'}

    release_tag: bpy.props.StringProperty(
        name="Release Tag",
        default="",
    )

    update_operator_bl_idname: bpy.props.StringProperty(
        name="Update Operator ID",
        description="The ID of the operator to display as the update button",
        default="",
    )

    def execute(self, context: bpy.types.Context):
        polib.ui_bpy.show_release_notes_popup(
            context, base_package, self.release_tag, self.update_operator_bl_idname
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ShowReleaseNotes)


@polib.log_helpers_bpy.logged_preferences
@addon_updater_ops.make_annotations
@polib.serialization_bpy.serializable_class
class Preferences(bpy.types.AddonPreferences, polib.serialization_bpy.Savable):
    bl_idname = base_package
    addon_name = base_package.split('.')[-1]  # Use only the last part in case of development
    save_version = 2
    strict_mode = False

    @property
    def config_name(self) -> str:
        return "preferences"

    @property
    def auto_save(self) -> bool:
        return True

    # Addon updater preferences.
    auto_check_update: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Auto-check for Update",
            description="If enabled, auto-check for updates using an interval",
            default=True,
        )
    )

    updater_interval_months: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name='Months',
            description="Number of months between checking for updates",
            default=0,
            min=0,
        )
    )

    updater_interval_days: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name='Days',
            description="Number of days between checking for updates",
            default=7,
            min=0,
            max=31,
        )
    )

    updater_interval_hours: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name='Hours',
            description="Number of hours between checking for updates",
            default=0,
            min=0,
            max=23,
        )
    )

    updater_interval_minutes: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name='Minutes',
            description="Number of minutes between checking for updates",
            default=0,
            min=0,
            max=59,
        )
    )

    general_preferences: polib.serialization_bpy.Serialize(
        bpy.props.PointerProperty(
            name="General Preferences",
            description="Preferences related to all asset packs",
            type=general_preferences.GeneralPreferences,
        )
    )

    browser_preferences: polib.serialization_bpy.Serialize(
        bpy.props.PointerProperty(
            name="Browser Preferences",
            description="Preferences related to the mapr asset browser",
            type=browser_preferences.BrowserPreferences,
        )
    )

    what_is_new_preferences: polib.serialization_bpy.Serialize(
        bpy.props.PointerProperty(
            name="\"See What's New\" preferences",
            description="Preferences related to the \"See What's New\" button",
            type=what_is_new_preferences.WhatIsNewPreferences,
        )
    )

    botaniq_adjustment_preferences: bpy.props.PointerProperty(
        name="Botaniq Adjustment Preferences",
        description="Preferences related to the botaniq adjustment feature",
        type=features.botaniq_adjustments.BotaniqAdjustmentPreferences,
    )

    colorize_preferences: bpy.props.PointerProperty(
        name="Colorize Preferences",
        description="Preferences related to the colorize engon feature",
        type=features.colorize.ColorizePreferences,
    )

    light_adjustments_preferences: bpy.props.PointerProperty(
        name="Light Adjustments Preferences",
        description="Preferences related to the light adjustments engon feature",
        type=features.light_adjustments.LightAdjustmentsPreferences,
    )

    aquatiq_paint_mask_preferences: bpy.props.PointerProperty(
        name="Aquatiq Paint Mask Preferences",
        description="Preferences related to the aquatiq paint mask engon feature",
        type=features.aquatiq_paint_mask.PaintMaskPreferences,
    )

    botaniq_animations_preferences: bpy.props.PointerProperty(
        name="Botaniq Animations Preferences",
        description="Preferences related to the botaniq animations engon feature",
        type=features.botaniq_animations.botaniq_animations.BotaniqAnimationsPreferences,
    )

    traffiq_lights_settings_preferences: bpy.props.PointerProperty(
        name="Traffiq Light Settings Preferences",
        description="Preferences related to the traffiq lights settings engon feature",
        type=features.traffiq_lights_settings.TraffiqLightsSettingsPreferences,
    )

    traffiq_paint_adjustments_preferences: bpy.props.PointerProperty(
        name="Traffiq Paint Adjustments Preferences",
        description="Preferences related to the traffiq paint adjustments engon feature",
        type=features.traffiq_paint_adjustments.TraffiqPaintAdjustmentPreferences,
    )

    traffiq_wear_preferences: bpy.props.PointerProperty(
        name="Traffiq Wear Preferences",
        description="Preferences related to the traffiq wear preferences engon feature",
        type=features.traffiq_wear.TraffiqWearPreferences,
    )

    traffiq_rigs_preferences: bpy.props.PointerProperty(
        name="Traffiq Rigs Preferences",
        description="Preferences related to the traffiq rigs engon feature",
        type=features.traffiq_rigs.TraffiqRigsPreferences,
    )

    pictorial_wear_preferences: bpy.props.PointerProperty(
        name="Pictorial Wear Preferences",
        description="Preferences related to the pictorial wear engon feature",
        type=features.pictorial_wear.PictorialWearPreferences,
    )

    pictorial_adjustments_preferences: bpy.props.PointerProperty(
        name="Pictorial Adjustments Preferences",
        description="Preferences related to the pictorial adjustments engon feature",
        type=features.pictorial_adjustments.PictorialAdjustmentsPreferences,
    )

    sculpture_wear_preferences: bpy.props.PointerProperty(
        name="Sculpture Wear Preferences",
        description="Preferences related to the sculpture wear engon feature",
        type=features.sculpture_wear.SculptureWearPreferences,
    )

    first_time_register: bpy.props.BoolProperty(
        description="Gets set to False when engon gets registered for the first time "
        "or when registered after being unregistered",
        default=True,
    )

    show_asset_packs: bpy.props.BoolProperty(
        description="Show/Hide Installed Asset Packs", default=True
    )

    show_available_packs: bpy.props.BoolProperty(
        description="Show/Hide Available Asset Packs", default=False
    )

    show_pack_info_paths: bpy.props.BoolProperty(
        name="Show/Hide Pack Info Search Paths", default=False
    )

    show_keymaps: bpy.props.BoolProperty(description="Show/Hide Keymaps", default=False)

    show_updater_settings: bpy.props.BoolProperty(description="Show/Hide Updater", default=False)

    def draw(self, context: bpy.types.Context) -> None:
        polib.ui_bpy.draw_conflicting_addons(self.layout, base_package, CONFLICTING_ADDONS)
        col = self.layout.column()

        # Asset Packs section
        box = polib.ui_bpy.collapsible_box(
            col,
            self,
            "show_asset_packs",
            "Asset Packs",
            self.general_preferences.draw_asset_packs,
            docs_module=base_package,
            docs_rel_url="getting_started/asset_packs",
        )

        if self.show_asset_packs:
            # Pack Info Search Paths section
            polib.ui_bpy.collapsible_box(
                box,
                self,
                "show_pack_info_paths",
                "Asset Pack Search Paths (For Advanced Users)",
                functools.partial(self.general_preferences.draw_pack_info_search_paths, context),
                docs_module=base_package,
                docs_rel_url="advanced_topics/search_paths",
            )

        # Available Asset Packs section
        not_installed_available_packs = (
            available_asset_packs.get_not_installed_available_asset_packs()
        )
        if len(not_installed_available_packs) > 0:
            polib.ui_bpy.collapsible_box(
                col,
                self,
                "show_available_packs",
                f"Discover Available Asset Packs ({len(not_installed_available_packs)})",
                functools.partial(
                    available_asset_packs.draw_available_asset_packs,
                    context,
                ),
            )

        # Keymaps section
        polib.ui_bpy.collapsible_box(
            col,
            self,
            "show_keymaps",
            "Keymaps",
            functools.partial(
                polib.keymaps_bpy.draw_settings_ui, context, keymaps.KEYMAP_DEFINITIONS
            ),
        )

        if bpy.app.online_access:
            # Update Settings section
            polib.ui_bpy.collapsible_box(
                col,
                self,
                "show_updater_settings",
                "Updates",
                functools.partial(self.draw_update_settings, context),
            )

        box = col.box()

        # Misc preferences
        row = box.row()
        row.prop(self.what_is_new_preferences, "display_what_is_new")

        polib.serialization_bpy.io_operators_bpy.draw_import_export_savable_panel(
            self.layout,
            "Preferences",
            ExportPreferences.bl_idname,
            ImportPreferences.bl_idname,
            SearchPreferences.bl_idname,
        )

        # Open Log Folder button
        self.layout.operator(PackLogs.bl_idname, icon='EXPERIMENTAL')

        polib.ui_bpy.draw_settings_footer(self.layout)

    def draw_update_settings(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        col = layout.column()
        addon_updater_ops.update_settings_ui(self, context, col)
        split = col.split(factor=0.5)
        left_row = split.row()
        left_row.enabled = bool(addon_updater.Updater.update_ready)
        op = left_row.operator(
            ShowReleaseNotes.bl_idname, text="Latest Release Notes", icon='PRESET_NEW'
        )
        op.release_tag = ""
        op.update_operator_bl_idname = addon_updater_ops.AddonUpdaterUpdateNow.bl_idname
        right_row = split.row()
        # TODO: Broken 4.2
        if addon_updater.Updater.current_version is not None:
            current_release_tag = polib.utils_bpy.get_release_tag_from_version(
                addon_updater.Updater.current_version
            )
            op = right_row.operator(
                ShowReleaseNotes.bl_idname, text="Current Release Notes", icon='PRESET'
            )
            op.release_tag = current_release_tag
            op.update_operator_bl_idname = ""


MODULE_CLASSES.append(Preferences)


def on_preferences_imported(op, context: bpy.types.Context) -> None:
    # We need to refresh assetpacks after any import as they might have changed
    prefs = prefs_utils.get_preferences(context)
    gen_prefs = prefs.general_preferences
    gen_prefs.refresh_packs()


(
    ExportPreferences,
    ImportPreferences,
    FoundPreferencesItem,
    SearchPreferences,
    ImportPreferencesIgnoreVersion,
) = polib.serialization_bpy.io_operators_bpy.savable_operators_factory(
    "engon",
    "preferences",
    lambda self: prefs_utils.get_preferences(bpy.context),  # type: ignore[return-value]
    on_preferences_imported,
)

MODULE_CLASSES.extend(
    [
        ExportPreferences,
        ImportPreferences,
        FoundPreferencesItem,
        SearchPreferences,
        ImportPreferencesIgnoreVersion,
    ]
)


@polib.log_helpers_bpy.logged_operator
class PackLogs(bpy.types.Operator):
    bl_idname = "engon.pack_logs"
    bl_label = "Pack Logs"
    bl_description = "Archives polygoniq logs as zip file and opens its location"
    bl_options = {'REGISTER'}

    def execute(self, context):
        packed_logs_directory_path = polib.log_helpers_bpy.pack_logs(telemetry)
        polib.utils_bpy.xdg_open_file(packed_logs_directory_path)
        return {'FINISHED'}


MODULE_CLASSES.append(PackLogs)


def register():
    general_preferences.register()
    browser_preferences.register()
    what_is_new_preferences.register()
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    polib.serialization_bpy.utils_bpy.post_register_load(
        lambda: prefs_utils.get_preferences(bpy.context)  # type: ignore[return-value]
    )


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
    what_is_new_preferences.unregister()
    browser_preferences.unregister()
    general_preferences.unregister()
