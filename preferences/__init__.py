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

from .. import addon_updater_ops
import bpy
import bpy_extras
import typing
import os
import glob
import json
import functools
import polib
# we don't use this module in this file but we use it elsewhere in engon, we import
# it here to make sure we handle module cache reloads correctly
from . import prefs_utils
from . import general_preferences
from . import mapr_preferences
from . import what_is_new_preferences
from . import aquatiq_preferences
from . import botaniq_preferences
from . import traffiq_preferences
from .. import keymaps
from .. import ui_utils


telemetry = polib.get_telemetry("engon")


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_preferences
@addon_updater_ops.make_annotations
class Preferences(bpy.types.AddonPreferences):
    bl_idname = polib.utils_bpy.get_top_level_package_name(__package__)

    # Addon updater preferences.
    auto_check_update: bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=True
    )

    updater_interval_months: bpy.props.IntProperty(
        name='Months',
        description="Number of months between checking for updates",
        default=0,
        min=0
    )

    updater_interval_days: bpy.props.IntProperty(
        name='Days',
        description="Number of days between checking for updates",
        default=7,
        min=0,
        max=31
    )

    updater_interval_hours: bpy.props.IntProperty(
        name='Hours',
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23
    )

    updater_interval_minutes: bpy.props.IntProperty(
        name='Minutes',
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59
    )

    general_preferences: bpy.props.PointerProperty(
        name="General Preferences",
        description="Preferences related to all asset packs",
        type=general_preferences.GeneralPreferences
    )

    mapr_preferences: bpy.props.PointerProperty(
        name="Browser Preferences",
        description="Preferences related to the mapr asset browser",
        type=mapr_preferences.MaprPreferences
    )

    what_is_new_preferences: bpy.props.PointerProperty(
        name="\"See What's New\" preferences",
        description="Preferences related to the \"See What's New\" button",
        type=what_is_new_preferences.WhatIsNewPreferences
    )

    aquatiq_preferences: bpy.props.PointerProperty(
        name="Aquatiq Preferences",
        description="Preferences related to the aquatiq asset pack",
        type=aquatiq_preferences.AquatiqPreferences
    )

    botaniq_preferences: bpy.props.PointerProperty(
        name="Botaniq Preferences",
        description="Preferences related to the botaniq asset pack",
        type=botaniq_preferences.BotaniqPreferences
    )

    traffiq_preferences: bpy.props.PointerProperty(
        name="Traffiq Preferences",
        description="Preferences related to the traffiq asset pack",
        type=traffiq_preferences.TraffiqPreferences
    )

    first_time_register: bpy.props.BoolProperty(
        description="Gets set to False when engon gets registered for the first time "
        "or when registered after being unregistered",
        default=True
    )

    show_asset_packs: bpy.props.BoolProperty(
        description="Show/Hide Asset Packs",
        default=True
    )

    show_pack_info_paths: bpy.props.BoolProperty(
        name="Show/Hide Pack Info Search Paths",
        default=False
    )

    show_keymaps: bpy.props.BoolProperty(
        description="Show/Hide Keymaps",
        default=False
    )

    show_updater_settings: bpy.props.BoolProperty(
        description="Show/Hide Updater",
        default=False
    )

    save_prefs: bpy.props.BoolProperty(
        name="Auto-Save Preferences",
        description="Automatically saves Preferences after running operators "
        "(e.g. Install Asset Pack) that change engon preferences",
        default=True
    )

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column()

        # Asset Packs section
        box = polib.ui_bpy.collapsible_box(
            col,
            self,
            "show_asset_packs",
            "Asset Packs",
            self.general_preferences.draw_asset_packs,
            docs_module=polib.utils_bpy.get_top_level_package_name(__package__),
            docs_rel_url="getting_started/asset_packs"
        )

        if self.show_asset_packs:
            # Pack Info Search Paths section
            polib.ui_bpy.collapsible_box(
                box,
                self,
                "show_pack_info_paths",
                "Asset Pack Search Paths (For Advanced Users)",
                functools.partial(self.general_preferences.draw_pack_info_search_paths, context),
                docs_module=polib.utils_bpy.get_top_level_package_name(__package__),
                docs_rel_url="advanced_topics/search_paths"
            )

        # Keymaps section
        polib.ui_bpy.collapsible_box(
            col,
            self,
            "show_keymaps",
            "Keymaps",
            functools.partial(keymaps.draw_settings_ui, context)
        )

        # Update Settings section
        polib.ui_bpy.collapsible_box(
            col,
            self,
            "show_updater_settings",
            "Updates",
            functools.partial(addon_updater_ops.update_settings_ui, self, context)
        )

        box = col.box()

        # Misc preferences
        self.draw_save_userpref_prompt(box)
        row = box.row()
        row.prop(self.what_is_new_preferences, "display_what_is_new")

        # Open Log Folder button
        self.layout.operator(PackLogs.bl_idname, icon='EXPERIMENTAL')

        polib.ui_bpy.draw_settings_footer(self.layout)

    def draw_save_userpref_prompt(self, layout: bpy.types.UILayout):
        row = layout.row()
        row.prop(self, "save_prefs")
        row = row.row()
        row.alignment = 'RIGHT'
        op = row.operator(ui_utils.ShowPopup.bl_idname, text="", icon='INFO')
        op.message = "Automatically saves preferences after running operators " \
            "(e.g. Install Asset Pack) that change engon preferences. \n" \
            "If you do not save preferences after running these operators, " \
            "you might lose important engon data, for example, \n" \
            "your installed Asset Packs might not load properly the next time you open Blender."
        op.title = "Auto-Save Preferences"
        op.icon = 'INFO'


MODULE_CLASSES.append(Preferences)


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
    mapr_preferences.register()
    what_is_new_preferences.register()
    aquatiq_preferences.register()
    botaniq_preferences.register()
    traffiq_preferences.register()
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
    traffiq_preferences.unregister()
    botaniq_preferences.unregister()
    aquatiq_preferences.unregister()
    what_is_new_preferences.unregister()
    mapr_preferences.unregister()
    general_preferences.unregister()
