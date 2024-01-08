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

from . import addon_updater_ops
import bpy
import bpy_extras
import typing
import os
import glob
import json
import logging
import enum
import polib
import hatchery
import mapr
from . import asset_pack_installer
from . import pack_info_search_paths
from . import asset_registry
from . import asset_helpers
from . import keymaps
from . import ui_utils
logger = logging.getLogger(f"polygoniq.{__name__}")


telemetry = polib.get_telemetry("engon")


MODULE_CLASSES: typing.List[typing.Any] = []


# Create alias to the custom property names, it makes code shorter and more readable
CustomPropertyNames = polib.asset_pack_bpy.CustomPropertyNames


DISPLAY_ENUM_ITEMS = (
    ('BOUNDS', "Bounds", "Bounds, Display the bounds of the object"),
    ('WIRE', "Wire", "Wire, Display the object as a wireframe"),
    ('SOLID', "Solid",
        "Solid, Display the object as a solid (if solid drawing is enabled in the viewport)"),
    ('TEXTURED', "Textured",
        "Textured, Display the object with textures (if textures are enabled in the viewport)"),
)


BUMPS_MODIFIER_NAME = "tq_bumps_displacement"
BUMPS_MODIFIERS_CONTAINER_NAME = "tq_Bump_Modifiers_Container"


class ScatterProperties(bpy.types.PropertyGroup):
    max_particle_count: bpy.props.IntProperty(
        name="Maximum Particles",
        description="Maximum particle threshold for density recalculation",
        default=100000
    )

    # Used to change visibility of instance collection in active particle system
    active_display_type: bpy.props.EnumProperty(
        name="Display As",
        items=DISPLAY_ENUM_ITEMS,
        default='TEXTURED',
        update=lambda self, context: self.active_display_type_updated(context)
    )

    # Change Visibility operator global properties
    display_type: bpy.props.EnumProperty(
        name="Display As",
        items=DISPLAY_ENUM_ITEMS,
        default='TEXTURED'
    )

    display_percentage: bpy.props.IntProperty(
        name="Display Percentage",
        description="Percentage of particles that are displayed in viewport",
        subtype='PERCENTAGE',
        default=100,
        min=0,
        max=100,
    )

    def active_display_type_updated(self, context: bpy.types.Context):
        collection = context.object.particle_systems.active.settings.instance_collection
        for obj in collection.all_objects:
            obj.display_type = self.active_display_type


MODULE_CLASSES.append(ScatterProperties)


class GeneralPreferences(bpy.types.PropertyGroup):
    pack_info_search_paths: bpy.props.CollectionProperty(
        name="Pack Info Search Paths",
        type=pack_info_search_paths.PackInfoSearchPath
    )
    pack_info_search_path_index: bpy.props.IntProperty(
        name="Pack Info Search Path Index",
        default=0,
    )

    remove_duplicates: bpy.props.BoolProperty(
        name="Remove Duplicates",
        description="Automatically merges duplicate materials, node groups "
        "and images into one. Saves memory",
        default=True,
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

    scatter_props: bpy.props.PointerProperty(
        type=ScatterProperties,
        name="Scatter Properties"
    )

    @staticmethod
    def get_main_material_library(addon_name: str, library_blend: str) -> typing.Optional[str]:
        # We need to specify the library blend as well, because some asset packs (i.e. evermotion)
        # share the same engon features but have their own material library.
        for addon in asset_registry.instance.get_packs_by_engon_feature(addon_name):
            # TODO: The material library should be present in the root folder, we should unify this
            for blend_folder_candidate in ["blends", "blends/models"]:
                material_library_path_candidate = \
                    os.path.join(addon.install_path, blend_folder_candidate, library_blend)
                if os.path.isfile(material_library_path_candidate):
                    return material_library_path_candidate
        return None

    def add_new_pack_info_search_path(
        self,
        path_type: typing.Optional[pack_info_search_paths.PackInfoSearchPathType] = None,
        file_path: typing.Optional[str] = None,
        directory_path: typing.Optional[str] = None,
        glob_expression: typing.Optional[str] = None,
    ) -> None:
        """Adds a new pack-info search path to the Collection.

        Does not reload Asset Packs.
        """
        search_path: pack_info_search_paths.PackInfoSearchPath = self.pack_info_search_paths.add()
        if path_type is not None:
            search_path.path_type = path_type
        if file_path is not None:
            search_path.file_path = file_path
        if directory_path is not None:
            search_path.directory_path = directory_path
        if glob_expression is not None:
            search_path.glob_expression = glob_expression

    def remove_all_copies_of_pack_info_search_path(
        self,
        context: bpy.types.Context,
        path_or_expression: str,
        path_type: pack_info_search_paths.PackInfoSearchPathType = pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE
    ) -> None:
        """Removes all copies of the pack-info search path from the Collection.

        Does not reload Asset Packs.
        """
        filtered_out = [p for p in self.pack_info_search_paths
                        if not (p.path_type == path_type and
                                p.get_path_or_expression_by_type() == path_or_expression)]
        self.pack_info_search_paths.clear()
        for sp in filtered_out:
            self.add_new_pack_info_search_path(path_type=sp.path_type, file_path=sp.file_path,
                                               directory_path=sp.directory_path, glob_expression=sp.glob_expression)
        pack_info_search_path_list_ensure_valid_index(context)

    def get_search_paths_as_dict(self) -> typing.Dict:
        ret = []
        for search_path in self.pack_info_search_paths:
            ret.append(search_path.as_dict())

        return {"asset_pack_search_paths": ret}

    def add_search_paths_from_dict(
            self,
            info_dict: typing.Dict[str, typing.List[typing.Dict[str, str]]]
    ) -> None:
        search_paths_list = info_dict.get("asset_pack_search_paths", None)
        if search_paths_list is None:
            raise ValueError(
                "Given json dict does not contain a required key 'asset_pack_search_paths'!")
        if not isinstance(search_paths_list, list):
            raise ValueError(
                f"Given json dict contains asset_pack_search_paths but its type is '{type(search_paths_list)}' "
                f"instead of the expected 'list'!")

        for search_path_props in search_paths_list:
            search_path: pack_info_search_paths.PackInfoSearchPath = self.pack_info_search_paths.add()
            search_path.load_from_dict(search_path_props)

    def draw_pack_info_search_paths(self, context: bpy.types.Context, layout: bpy.types.UILayout):
        box = layout.box()
        row = box.row()
        row.prop(self, "show_pack_info_paths",
                 icon='DISCLOSURE_TRI_DOWN' if self.show_pack_info_paths else 'DISCLOSURE_TRI_RIGHT',
                 text="",
                 emboss=False,)
        row.label(text="Asset Pack Search Paths (For Advanced Users)")

        pack_info_search_path_list_ensure_valid_index(context)

        if not self.show_pack_info_paths:
            return

        row = box.row()
        col = row.column(align=True)
        col.operator(PackInfoSearchPathList_OT_AddItem.bl_idname,
                     text="", icon='ADD')
        col.operator(PackInfoSearchPathList_OT_DeleteItem.bl_idname,
                     text="", icon='REMOVE')
        col.operator(PackInfoSearchPathList_RefreshPacks.bl_idname,
                     text="", icon='FILE_REFRESH')
        col.separator()
        col.operator(PackInfoSearchPathList_OT_MoveItem.bl_idname,
                     text="", icon='TRIA_UP').direction = "UP"
        col.operator(PackInfoSearchPathList_OT_MoveItem.bl_idname,
                     text="", icon='TRIA_DOWN').direction = "DOWN"
        col.separator(factor=2)
        col.operator(PackInfoSearchPathList_RemoveAll.bl_idname,
                     text="", icon='LIBRARY_DATA_BROKEN')

        col = row.column(align=True)
        col.template_list(
            "MY_UL_PackInfoSearchPathList",
            "PackInfoSearchPath",
            self,
            "pack_info_search_paths",
            self,
            "pack_info_search_path_index"
        )

        row = col.row(align=True)
        row.operator(PackInfoSearchPathList_Import.bl_idname, icon='IMPORT')
        row.operator(PackInfoSearchPathList_Export.bl_idname, icon='EXPORT')

        row = layout.row()


MODULE_CLASSES.append(GeneralPreferences)


def pack_info_search_path_list_ensure_valid_index(context: bpy.types.Context) -> None:
    prefs = get_preferences(context)
    min_index = 0
    max_index = len(prefs.general_preferences.pack_info_search_paths) - 1

    index = prefs.general_preferences.pack_info_search_path_index
    if index < min_index:
        prefs.general_preferences.pack_info_search_path_index = min_index
    elif index > max_index:
        prefs.general_preferences.pack_info_search_path_index = max_index


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_Export(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "engon.pack_info_search_path_list_export"
    bl_label = "Export"
    bl_description = "Exports Search Paths in JSON format"
    bl_options = {'REGISTER', 'UNDO'}

    # ExportHelper mixin class uses this
    filename_ext = ".json"

    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        search_paths_dict = prefs.general_preferences.get_search_paths_as_dict()
        data_out = json.dumps(search_paths_dict, indent=4)
        with open(self.filepath, "w") as outf:
            outf.write(data_out)

        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_Export)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_Import(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "engon.pack_info_search_path_list_import"
    bl_label = "Import"
    bl_description = "Imports Search Paths in JSON format"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        with open(self.filepath) as f:
            data_in = json.load(f)
            prefs.general_preferences.add_search_paths_from_dict(data_in)

        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_Import)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_OT_AddItem(bpy.types.Operator):
    """Add a new pack-info search path"""

    bl_idname = "engon.pack_info_search_path_list_add_item"
    bl_label = "Add an item"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        prefs.general_preferences.add_new_pack_info_search_path()

        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_OT_AddItem)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_OT_DeleteItem(bpy.types.Operator):
    """Delete the selected pack-info search path from the list"""

    bl_idname = "engon.pack_info_search_path_list_delete_item"
    bl_label = "Delete an item"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        prefs = get_preferences(context)
        return len(prefs.general_preferences.pack_info_search_paths) > 0

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        the_list = prefs.general_preferences.pack_info_search_paths
        index = prefs.general_preferences.pack_info_search_path_index
        if index > 0:
            prefs.general_preferences.pack_info_search_path_index -= 1
            the_list.remove(index)
            # current index remains unchanged, we switch to the search path
            # just above the one we are deleting
        else:
            # switch to search path just below the one we are deleting
            prefs.general_preferences.pack_info_search_path_index += 1
            # remove the first search path
            the_list.remove(index)
            # this means all the indices have to be adjusted by -1
            prefs.general_preferences.pack_info_search_path_index -= 1

        pack_info_search_path_list_ensure_valid_index(context)
        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_OT_DeleteItem)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_OT_MoveItem(bpy.types.Operator):
    bl_idname = "engon.pack_info_search_path_list_move_item"
    bl_label = "Move pack-info search path in the list"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="direction",
        items=(
            ('UP', "Up", "Move currently active PackInfoSearchPath one step higher in the list"),
            ('DOWN', "Down", "Move currently active PackInfoSearchPath one step lower in the list"),
        )
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        prefs = get_preferences(context)
        return len(prefs.general_preferences.pack_info_search_paths) > 1

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        the_list = prefs.general_preferences.pack_info_search_paths
        index = prefs.general_preferences.pack_info_search_path_index
        neighbor = index + (-1 if self.direction == 'UP' else 1)
        the_list.move(neighbor, index)
        prefs.general_preferences.pack_info_search_path_index = neighbor
        pack_info_search_path_list_ensure_valid_index(context)
        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_OT_MoveItem)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_RemoveAll(bpy.types.Operator):
    bl_idname = "engon.pack_info_search_path_list_remove_all"
    bl_label = "Remove All"
    bl_description = "Remove all Search Paths from the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        prefs.general_preferences.pack_info_search_paths.clear()
        pack_info_search_path_list_ensure_valid_index(context)

        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_RemoveAll)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_RefreshPacks(bpy.types.Operator):
    bl_idname = "engon.pack_info_search_path_refresh_packs"
    bl_label = "Refresh Asset Packs"
    bl_description = "Search through all search paths, find .pack-info files " + \
        "and register them. Saves Preferences"
    bl_options = {'REGISTER'}

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        prefs.refresh_packs(save_prefs=prefs.save_prefs)
        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_RefreshPacks)


@polib.log_helpers_bpy.logged_operator
class InstallAssetPack(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "engon.install_asset_pack"
    bl_label = "Select File"
    bl_description = "Install Asset Pack from a paq file or an extracted Asset Pack folder. The Asset Pack will be registered automatically"
    bl_options = {'REGISTER'}

    # These are the primary file types the user should select
    # All other file types work as well, but are not visible by default
    filter_glob: bpy.props.StringProperty(
        default="*.paq;*.paq.001;*.pack-info",
        options={'HIDDEN'})

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        installer.load_installation(self.filepath)
        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT', filepath=self.filepath)

        return {'FINISHED'}


MODULE_CLASSES.append(InstallAssetPack)


@polib.log_helpers_bpy.logged_operator
class AssetPackInstallationDialog(bpy.types.Operator, asset_pack_installer.AssetPackInstallerDialogMixin):
    bl_idname = "engon.asset_pack_install_dialog"
    bl_label = "Install Asset Pack"
    bl_description = "Asset Pack Installation Dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    try_updating: bpy.props.BoolProperty()

    def draw(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        layout: bpy.types.UILayout = self.layout

        if self.check_should_dialog_close():
            if not self.close:
                self.close = True
            self.draw_status_and_error_messages(layout)
            return

        self.draw_pack_info(layout, header="This Asset Pack will be installed:")

        box = layout.box()
        col = box.column(align=True)
        col.label(text="Select an installation directory")
        split = col.split(factor=0.05, align=True)
        split.operator(
            SelectAssetPackInstallPath.bl_idname, text="", icon='FILE_FOLDER').filepath = os.path.expanduser("~" + os.sep)
        split.prop(self, "install_path", text="")

        col = box.column(align=True)
        col.label(text=f"Pack Folder Name: {installer.pack_root_directory}")
        col.label(text=f"Estimated Pack Size: {installer.pack_size}")
        col.label(text=f"Free Disk Space: {installer.free_space}")
        col = box.column()
        self.draw_status_and_error_messages(col)
        if installer.is_update_available:
            col.box().prop(self, "try_updating", text="Try Updating")

        box = layout.box()
        box.label(text=f"Clicking 'OK' will COPY all contents of this Asset Pack "
                  f"into the installation directory.")

        layout.prop(self, "canceled", toggle=True, text="Cancel Installation", icon='CANCEL')

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        gen_prefs: GeneralPreferences = prefs.general_preferences
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        if self.try_updating:
            bpy.ops.engon.update_asset_pack_internal(
                current_filepath=installer.uninstall_path, update_filepath=self.filepath)
            return {'FINISHED'}

        pack_info_path_to_add: typing.Optional[str] = installer.execute_installation()
        if pack_info_path_to_add is not None and \
                not installer.check_asset_pack_already_installed():
            gen_prefs.add_new_pack_info_search_path(file_path=pack_info_path_to_add,
                                                    path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE)
            prefs.refresh_packs(save_prefs=prefs.save_prefs)

        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackInstallationDialog)


@polib.log_helpers_bpy.logged_operator
class UninstallAssetPack(bpy.types.Operator):
    bl_idname = "engon.uninstall_asset_pack"
    bl_label = "Uninstall Asset Pack"
    bl_description = "Uninstalls selected asset pack, selected asset pack will be also removed from the disc"
    bl_options = {'REGISTER'}

    current_filepath: bpy.props.StringProperty(default="")

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        installer.load_uninstallation(self.current_filepath)
        bpy.ops.engon.asset_pack_uninstall_dialog('INVOKE_DEFAULT')

        return {'FINISHED'}


MODULE_CLASSES.append(UninstallAssetPack)


@polib.log_helpers_bpy.logged_operator
class AssetPackUninstallationDialog(bpy.types.Operator, asset_pack_installer.AssetPackInstallerDialogMixin):
    bl_idname = "engon.asset_pack_uninstall_dialog"
    bl_label = "Uninstall Asset Pack"
    bl_description = "Asset Pack Uninstallation Dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    def draw(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        layout: bpy.types.UILayout = self.layout

        if self.check_should_dialog_close():
            if not self.close:
                self.close = True
            self.draw_status_and_error_messages(layout)
            return

        self.draw_pack_info(
            layout, header="This Asset Pack will be uninstalled:", show_install_path=True)

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"Pack Folder Name: {installer.pack_root_directory}")
        col.label(text=f"Estimated Freed Disk Space: {installer.pack_size}")
        col = box.column()
        self.draw_status_and_error_messages(col)

        box = layout.box()
        box.label(text=f"Clicking 'OK' will REMOVE all contents of this Asset Pack "
                  f"from the installation directory.")

        layout.prop(self, "canceled", toggle=True, text="Cancel Uninstallation", icon='CANCEL')

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        gen_prefs: GeneralPreferences = prefs.general_preferences
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        pack_info_path_to_remove = installer.execute_uninstallation()
        if pack_info_path_to_remove is not None:
            gen_prefs.remove_all_copies_of_pack_info_search_path(context, pack_info_path_to_remove,
                                                                 path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE)
            prefs.refresh_packs(save_prefs=prefs.save_prefs)

        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackUninstallationDialog)


@polib.log_helpers_bpy.logged_operator
class UpdateAssetPackInternal(bpy.types.Operator):
    bl_idname = "engon.update_asset_pack_internal"
    bl_label = "Select File"
    bl_description = "Update Asset Pack"
    bl_options = {'REGISTER'}

    current_filepath: bpy.props.StringProperty(
        options={'HIDDEN'}
    )

    update_filepath: bpy.props.StringProperty(
        options={'HIDDEN'}
    )

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        installer.load_update(self.current_filepath, self.update_filepath)
        bpy.ops.engon.asset_pack_update_dialog('INVOKE_DEFAULT')

        return {'FINISHED'}


MODULE_CLASSES.append(UpdateAssetPackInternal)


@polib.log_helpers_bpy.logged_operator
class UpdateAssetPack(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "engon.update_asset_pack"
    bl_label = "Update Asset Pack"
    bl_description = "Updates asset pack with the new version selected via file browser"
    bl_options = {'REGISTER'}

    # These are the primary file types the user should select
    # All other file types work as well, but are not visible by default
    filter_glob: bpy.props.StringProperty(
        default="*.paq;*.paq.001;*.pack-info",
        options={'HIDDEN'})

    current_filepath: bpy.props.StringProperty(
        options={'HIDDEN'}
    )

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        installer.load_update(self.current_filepath, self.filepath)
        bpy.ops.engon.asset_pack_update_dialog('INVOKE_DEFAULT')

        return {'FINISHED'}


MODULE_CLASSES.append(UpdateAssetPack)


@polib.log_helpers_bpy.logged_operator
class AssetPackUpdateDialog(bpy.types.Operator, asset_pack_installer.AssetPackInstallerDialogMixin):
    bl_idname = "engon.asset_pack_update_dialog"
    bl_label = "Update Asset Pack"
    bl_description = "Asset Pack Update Dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    def draw(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        layout: bpy.types.UILayout = self.layout

        if self.check_should_dialog_close():
            if not self.close:
                self.close = True
            self.draw_status_and_error_messages(layout)
            return

        self.draw_pack_info(
            layout, header="This Asset Pack will be updated:")

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"Pack Folder Name: {installer.pack_root_directory}")
        col.label(text=f"Estimated Extra Space Required: {installer.pack_size}")
        col.label(text=f"Free Disk Space: {installer.free_space}")
        col = box.column()
        self.draw_status_and_error_messages(col)

        col = layout.box().column(align=True)
        col.label(text=f"Clicking 'OK' will REMOVE all contents of the old version of the Asset Pack "
                  f"from the installation directory.")
        col.label(text=f"It will be REPLACED with the new version.")

        layout.prop(self, "canceled", toggle=True, text="Cancel Update", icon='CANCEL')

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = get_preferences(context)
        gen_prefs: GeneralPreferences = prefs.general_preferences
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        update_paths = installer.execute_update()
        if update_paths is not None:
            pack_info_path_to_remove, pack_info_path_to_add = update_paths
            gen_prefs.remove_all_copies_of_pack_info_search_path(context, pack_info_path_to_remove,
                                                                 path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE)
            # Asset Packs need to be refreshed after removing
            # In case the paths are same, the asset_registry wouldn't load the new Asset Pack
            # No need to save prefs here
            prefs.refresh_packs()
            gen_prefs.add_new_pack_info_search_path(file_path=pack_info_path_to_add,
                                                    path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE)
            prefs.refresh_packs(save_prefs=prefs.save_prefs)

        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackUpdateDialog)


@polib.log_helpers_bpy.logged_operator
class SelectAssetPackInstallPath(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "engon.select_asset_pack_install_path"
    bl_label = "Select Path"
    bl_description = "Select a Custom Install Path for the Asset Pack"
    bl_options = {'REGISTER', 'INTERNAL'}

    # Empty filer_glob to show folders only
    filter_glob: bpy.props.StringProperty(
        default="",
        options={'HIDDEN'})

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        if os.path.exists(self.filepath):
            installer.install_path = os.path.dirname(self.filepath)

        return bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')


MODULE_CLASSES.append(SelectAssetPackInstallPath)


class SpawnOptions(bpy.types.PropertyGroup):
    """Defines options that should be considered when spawning assets."""
    # General
    remove_duplicates: bpy.props.BoolProperty(
        name="Remove Duplicates",
        description="Automatically merges duplicate materials, node groups "
        "and images into one when the asset is spawned. Saves memory",
        default=True,
    )
    make_editable: bpy.props.BoolProperty(
        name="Make Editable",
        description="Automatically makes the spawned asset editable",
        default=False
    )

    # Model
    use_collection: bpy.props.EnumProperty(
        name="Target Collection",
        description="Collection to spawn the model into",
        items=(
            ('PACK', "Asset Pack Collection",
             "Spawn model into collection named as the asset pack - 'botaniq, traffiq, ...'"),
            ('ACTIVE', "Active Collection", "Spawn model into the active collection"),
            ('PARTICLE_SYSTEM', "Particle System Collection",
             "Spawn model into active particle system collection")
        ),
    )

    # Materialiq
    texture_size: bpy.props.EnumProperty(
        items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
        name="materialiq5 global maximum side size",
        description="Maximum side size of textures spawned with a material",
    )

    use_displacement: bpy.props.BoolProperty(
        name="Use Displacement",
        description="Spawn material with enabled displacement",
        default=False,
    )

    # scatter
    display_type: bpy.props.EnumProperty(
        name="Display As",
        items=DISPLAY_ENUM_ITEMS,
        default='TEXTURED'
    )

    display_percentage: bpy.props.IntProperty(
        name="Display Percentage",
        description="Percentage of particles that are displayed in viewport",
        subtype='PERCENTAGE',
        default=100,
        min=0,
        max=100,
    )

    link_instance_collection: bpy.props.BoolProperty(
        description="If true, this setting links particle system instance collection to scene. "
        "Objects from instance collection are spawned on (0, -10, 0).",
        name="Link Instance Collection To Scene",
        default=True
    )

    include_base_material: bpy.props.BoolProperty(
        name="Include Base Material",
        description="If true base material is loaded with the particle system and set "
        "to the target object as active",
        default=True
    )

    preserve_density: bpy.props.BoolProperty(
        name="Preserve Density",
        description="If true automatically recalculates density based on mesh area",
        default=True
    )

    count: bpy.props.IntProperty(
        name="Count",
        description="Amount of particles to spawn if preserve density is off",
        default=1000,
    )

    def get_spawn_options(
        self,
        asset: mapr.asset.Asset,
        context: bpy.types.Context
    ) -> hatchery.spawn.DatablockSpawnOptions:
        """Returns spawn options for given asset based on its type"""
        if asset.type_ == mapr.asset_data.AssetDataType.blender_model:
            return hatchery.spawn.ModelSpawnOptions(
                self._get_model_parent_collection(asset, context), True)
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            return hatchery.spawn.MaterialSpawnOptions(
                int(self.texture_size),
                self.use_displacement,
                context.selected_objects
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            return hatchery.spawn.ParticleSystemSpawnOptions(
                self.display_type,
                self.display_percentage,
                self._get_instance_collection_parent(asset, context),
                self.include_base_material,
                # Purposefully use max_particle_count from scatter, as this property has a global
                # meaning.
                get_preferences(context).general_preferences.scatter_props.max_particle_count,
                self.count,
                self.preserve_density,
                {context.active_object}
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return hatchery.spawn.DatablockSpawnOptions()
        else:
            raise NotImplementedError(
                f"Spawn options are not supported for type: {asset.type_}, please contact developers!")

    def can_spawn(
        self,
        asset: mapr.asset.Asset,
        context: bpy.types.Context
    ) -> typing.Tuple[bool, typing.Optional[typing.Tuple[str, str]]]:
        """Checks whether the given asset can spawn in given Blender context.

        Returns boolean value and a tuple of strings (Error, Hint To User)
        """
        if asset.type_ == mapr.asset_data.AssetDataType.blender_model:
            if self.use_collection == 'PARTICLE_SYSTEM':
                if context.active_object is None:
                    return False, (
                        "Can't spawn model into particle system - No active object!",
                        "Select active object with particle system."
                    )
                if context.active_object.particle_systems.active is None:
                    return False, (
                        "Can't spawn model into particle system - No particle system found!",
                        "Select object with at least one particle system."
                    )
                instance_collection = context.active_object.particle_systems.active.settings.instance_collection
                if instance_collection is None:
                    return False, (
                        "Can't spawn model into particle system - Missing instance collection!",
                        "Select particle system and assign instance collection to it."
                    )
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            material_assignable_objects = [
                hatchery.utils.can_have_materials_assigned(o) for o in context.selected_objects]

            # Check whether there is any selected object that has assignable material
            if len(material_assignable_objects) == 0:
                return False, (
                    "Can't spawn material - No valid selected objects!",
                    "Select objects that can have material assigned."
                )
            else:
                return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            if context.active_object is None:
                return False, (
                    "Can't spawn particle system - No active object!",
                    "Select a mesh object."
                )
            else:
                if context.active_object.type != 'MESH':
                    return False, (
                        "Current object doesn't support particle systems!",
                        "Select a mesh object."
                    )
                return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return True, None
        else:
            raise NotImplementedError(
                f"Invalid type given to can_spawn: {asset.type_}, please contact developers!")

    def _get_instance_collection_parent(
        self,
        asset: mapr.asset.Asset,
        context: bpy.types.Context
    ) -> typing.Optional[bpy.types.Collection]:
        if self.link_instance_collection:
            return polib.asset_pack_bpy.collection_get(
                context, asset_helpers.PARTICLE_SYSTEMS_COLLECTION)

        return None

    def _get_model_parent_collection(
        self,
        asset: mapr.asset.Asset,
        context: bpy.types.Context
    ) -> bpy.types.Collection:
        if self.use_collection == 'ACTIVE':
            return context.collection
        elif self.use_collection == 'PACK':
            collection = polib.asset_pack_bpy.collection_get(context, asset.text_parameters.get(
                "polygoniq_addon", "unknown"))
            return collection

        elif self.use_collection == 'PARTICLE_SYSTEM':
            if context.active_object is None:
                logger.error(
                    "Tried to to spawn object into particle system collection, but no object is active!")
                return None

            ps = context.active_object.particle_systems.active
            if ps is None:
                logger.error(f"No active particle system found!")
                return None

            coll = ps.settings.instance_collection
            if coll is not None:
                return coll
            else:
                logger.error(f"No particle system instance collection found!")
                return None
        else:
            raise ValueError(f"Unknown value of 'use_collection': {self.use_collection}")


MODULE_CLASSES.append(SpawnOptions)


class MaprPreferences(bpy.types.PropertyGroup):
    """Property group containing all the settings and customizable options for user interface"""
    preview_scale_percentage: bpy.props.FloatProperty(
        name="Preview Scale",
        description="Preview scale",
        min=0,
        max=100,
        default=50,
        subtype='PERCENTAGE'
    )
    use_pills_nav: bpy.props.BoolProperty(
        name="Tree / Pills Category Navigation",
        description="If toggled, then pills navigation will be drawn, tree navigation otherwise",
        default=False
    )
    search_history_count: bpy.props.IntProperty(
        name="Search History Count",
        description="Number of search queries that are remembered during one Blender instance run",
        min=0,
        default=20
    )
    debug: bpy.props.BoolProperty(
        name="Enable Debug",
        description="If true then asset browser displays addition debug information",
        default=False,
    )

    spawn_options: bpy.props.PointerProperty(type=SpawnOptions)

    # We store the state whether preferences were open to be able to re-open it on load
    prefs_hijacked: bpy.props.BoolProperty(options={'HIDDEN'})


MODULE_CLASSES.append(MaprPreferences)


class PuddleProperties(bpy.types.PropertyGroup):
    puddle_factor: bpy.props.FloatProperty(
        name=asset_helpers.PuddleNodeInputs.PUDDLE_FACTOR,
        get=lambda _: PuddleProperties.get_active_object_puddle_input_value(
            asset_helpers.PuddleNodeInputs.PUDDLE_FACTOR),
        set=lambda _, value: PuddleProperties.set_selection_puddle_inputs(
            asset_helpers.PuddleNodeInputs.PUDDLE_FACTOR, value),
        soft_min=0.0,
        soft_max=1.0,
        precision=3
    )

    puddle_scale: bpy.props.FloatProperty(
        name=asset_helpers.PuddleNodeInputs.PUDDLE_SCALE,
        get=lambda _: PuddleProperties.get_active_object_puddle_input_value(
            asset_helpers.PuddleNodeInputs.PUDDLE_SCALE),
        set=lambda _, value: PuddleProperties.set_selection_puddle_inputs(
            asset_helpers.PuddleNodeInputs.PUDDLE_SCALE, value),
        soft_min=0.0,
        soft_max=1000.0,
        precision=3
    )

    animation_speed: bpy.props.FloatProperty(
        name=asset_helpers.PuddleNodeInputs.ANIMATION_SPEED,
        get=lambda _: PuddleProperties.get_active_object_puddle_input_value(
            asset_helpers.PuddleNodeInputs.ANIMATION_SPEED),
        set=lambda _, value: PuddleProperties.set_selection_puddle_inputs(
            asset_helpers.PuddleNodeInputs.ANIMATION_SPEED, value),
        soft_min=0.0,
        soft_max=1000.0,
        precision=3
    )

    noise_strength: bpy.props.FloatProperty(
        name=asset_helpers.PuddleNodeInputs.NOISE_STRENGTH,
        get=lambda _: PuddleProperties.get_active_object_puddle_input_value(
            asset_helpers.PuddleNodeInputs.NOISE_STRENGTH),
        set=lambda _, value: PuddleProperties.set_selection_puddle_inputs(
            asset_helpers.PuddleNodeInputs.NOISE_STRENGTH, value),
        soft_min=0.0,
        soft_max=1.0,
        precision=3
    )

    angle_threshold: bpy.props.FloatProperty(
        name=asset_helpers.PuddleNodeInputs.ANGLE_THRESHOLD,
        get=lambda _: PuddleProperties.get_active_object_puddle_input_value(
            asset_helpers.PuddleNodeInputs.ANGLE_THRESHOLD),
        set=lambda _, value: PuddleProperties.set_selection_puddle_inputs(
            asset_helpers.PuddleNodeInputs.ANGLE_THRESHOLD, value),
        soft_min=0.0,
        soft_max=90.0,
        precision=3
    )

    @staticmethod
    def get_active_object_puddle_input_value(input_name: str) -> float:
        if bpy.context.active_object is None:
            return 0.0

        mat = bpy.context.active_object.active_material
        if mat is None:
            return 0.0

        puddles_name = asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
        puddle_nodes = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, puddles_name)
        if len(puddle_nodes) == 0:
            return 0.0
        puddle_node = puddle_nodes.pop()
        return puddle_node.inputs[input_name].default_value

    @staticmethod
    def set_selection_puddle_inputs(input_name: str, value: float) -> None:
        for obj in bpy.context.selected_objects:
            if obj is None:
                continue

            mat = obj.active_material
            if mat is None:
                continue

            puddles_name = asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
            puddle_nodes = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, puddles_name)
            for puddle_node in puddle_nodes:
                puddle_node.inputs[input_name].default_value = value


MODULE_CLASSES.append(PuddleProperties)


class AquatiqPreferences(bpy.types.PropertyGroup):
    draw_mask_factor: bpy.props.FloatProperty(
        name="Mask Factor",
        description="Value of 1 means visible, value of 0 means hidden",
        update=lambda self, context: self.update_mask_factor(context),
        soft_max=1.0,
        soft_min=0.0
    )

    def update_mask_factor(self, context: bpy.types.Context):
        context.tool_settings.vertex_paint.brush.color = [self.draw_mask_factor] * 3

    puddle_properties: bpy.props.PointerProperty(
        type=PuddleProperties
    )


MODULE_CLASSES.append(AquatiqPreferences)


class WindPreset(enum.Enum):
    BREEZE = "Breeze"
    WIND = "Wind"
    STORM = "Storm"
    UNKNOWN = "Unknown"


class AnimationType(enum.Enum):
    WIND_BEST_FIT = "Wind-Best-Fit"
    WIND_TREE = "Wind-Tree"
    WIND_PALM = "Wind-Palm"
    WIND_LOW_VEGETATION = "Wind-Low-Vegetation"
    WIND_LOW_VEGETATION_PLANTS = "Wind-Low-Vegetation-Plants"
    WIND_SIMPLE = "Wind-Simple"
    UNKNOWN = "Unknown"


class WindStyle(enum.Enum):
    LOOP = "Loop"
    PROCEDURAL = "Procedural"
    UNKNOWN = "Unknown"


class WindAnimationProperties(bpy.types.PropertyGroup):
    auto_make_instance: bpy.props.BoolProperty(
        name="Automatic Make Instance",
        description="Automatically make instance out of object when spawning animation. "
        "Better performance, but assets share data, customization per instance",
        default=False
    )

    animation_type: bpy.props.EnumProperty(
        name="Wind animation type",
        description="Select one of predefined animations types."
        "This changes the animation and animation modifier stack",
        items=(
            (AnimationType.WIND_BEST_FIT.value, AnimationType.WIND_BEST_FIT.value,
             "Different animation types based on the selection", 'SHADERFX', 0),
            (AnimationType.WIND_TREE.value, AnimationType.WIND_TREE.value,
             "Animation mostly suited for tree assets", 'BLANK1', 1),
            (AnimationType.WIND_PALM.value, AnimationType.WIND_PALM.value,
             "Animation mostly suited for palm assets", 'BLANK1', 2),
            (AnimationType.WIND_LOW_VEGETATION.value, AnimationType.WIND_LOW_VEGETATION.value,
             "Animation mostly suited for low vegetation assets", 'BLANK1', 3),
            (AnimationType.WIND_LOW_VEGETATION_PLANTS.value, AnimationType.WIND_LOW_VEGETATION_PLANTS.value,
             "Animation mostly suited for low vegetation plant assets", 'BLANK1', 4),
            (AnimationType.WIND_SIMPLE.value, AnimationType.WIND_SIMPLE.value,
             "Simple animation, works only on assets with Leaf_ or Grass_ materials", 'BLANK1', 5)
        )
    )

    preset: bpy.props.EnumProperty(
        name="Wind animation preset",
        description="Select one of predefined animations presets."
        "This changes detail of animation and animation modifier stack",
        items=(
            (WindPreset.BREEZE.value, WindPreset.BREEZE.value, "Light breeze wind", 'BOIDS', 0),
            (WindPreset.WIND.value, WindPreset.WIND.value, "Moderate wind", 'CURVES_DATA', 1),
            (WindPreset.STORM.value, WindPreset.STORM.value, "Strong storm wind", 'MOD_NOISE', 2)
        )
    )

    strength: bpy.props.FloatProperty(
        name="Wind strength",
        description="Strength of the wind applied on the trees",
        default=0.25,
        min=0.0,
        soft_max=1.0,
    )

    looping: bpy.props.IntProperty(
        name="Loop time",
        description="At how many frames should the animation repeat. Minimal value to ensure good "
        "animation appearance is 80",
        default=120,
        min=80,
    )

    bake_folder: bpy.props.StringProperty(
        name="Bake Folder",
        description="Folder where baked .abc animations are saved",
        default=os.path.realpath(os.path.expanduser("~/botaniq_animations/")),
        subtype='DIR_PATH'
    )

    # Used to choose target of most wind animation operators but not all.
    # It's not used in operators where it doesn't make sense,
    # e.g. Add Animation works on selected objects.
    operator_target: bpy.props.EnumProperty(
        name="Target",
        description="Choose to what objects the operator should apply",
        items=[
            ('SELECTED', "Selected Objects", "All selected objects"),
            ('SCENE', "Scene Objects", "All objects in current scene"),
            ('ALL', "All Objects", "All objects in the .blend file"),
        ],
        default='SCENE',
    )


MODULE_CLASSES.append(WindAnimationProperties)


class BotaniqPreferences(bpy.types.PropertyGroup):
    float_min: bpy.props.FloatProperty(
        name="Min Value",
        description="Miniumum float value",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1
    )

    float_max: bpy.props.FloatProperty(
        name="Max Value",
        description="Maximum float value",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1
    )

    brightness: bpy.props.FloatProperty(
        name="Brightness",
        description="Adjust assets brightness",
        default=1.0,
        min=0.0,
        max=10.0,
        soft_max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            CustomPropertyNames.BQ_BRIGHTNESS,
            self.brightness
        ),
    )

    hue_per_branch: bpy.props.FloatProperty(
        name="Hue Per Branch",
        description="Randomize hue per branch",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            CustomPropertyNames.BQ_RANDOM_PER_BRANCH,
            self.hue_per_branch
        ),
    )

    hue_per_leaf: bpy.props.FloatProperty(
        name="Hue Per Leaf",
        description="Randomize hue per leaf",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            CustomPropertyNames.BQ_RANDOM_PER_LEAF,
            self.hue_per_leaf
        ),
    )

    season_offset: bpy.props.FloatProperty(
        name="Season Offset",
        description="Change season of asset",
        default=1.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            self.get_adjustment_affected_objects(context),
            CustomPropertyNames.BQ_SEASON_OFFSET,
            self.season_offset
        ),
    )

    wind_anim_properties: bpy.props.PointerProperty(
        name="Animation Properties",
        description="Wind animation related property group",
        type=WindAnimationProperties
    )

    def get_adjustment_affected_objects(self, context: bpy.types.Context):
        extended_objects = set(context.selected_objects)
        if context.active_object is not None:
            extended_objects.add(context.active_object)

        return set(extended_objects).union(
            asset_helpers.gather_instanced_objects(extended_objects))

    @property
    def animation_data_path(self) -> typing.Optional[str]:
        # TODO: This is absolutely terrible and we need to replace it later, we assume one animation
        #       data library existing and that being used for everything. In the future each asset
        #       pack should be able to have its own
        for pack in asset_registry.instance.get_packs_by_engon_feature("botaniq"):
            library_path_candidate = \
                os.path.join(
                    pack.install_path,
                    "blends",
                    "models",
                    "bq_Library_Animation_Data.blend"
                )
            if os.path.isfile(library_path_candidate):
                return library_path_candidate
        return None


MODULE_CLASSES.append(BotaniqPreferences)


class CarPaintProperties(bpy.types.PropertyGroup):
    @staticmethod
    def update_car_paint_color_prop(context, value: typing.Tuple[float, float, float, float]):
        # Don't allow to accidentally set color to random
        if all(v > 0.99 for v in value[:3]):
            value = (0.99, 0.99, 0.99, value[3])

        polib.asset_pack_bpy.update_custom_prop(
            context, context.selected_objects, CustomPropertyNames.TQ_PRIMARY_COLOR, value)

    primary_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        description="Changes primary color of assets",
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        size=4,
        update=lambda self, context: CarPaintProperties.update_car_paint_color_prop(
            context, self.primary_color),
    )
    flakes_amount: bpy.props.FloatProperty(
        name="Flakes Amount",
        description="Changes amount of flakes in the car paint",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            CustomPropertyNames.TQ_FLAKES_AMOUNT,
            self.flakes_amount
        ),
    )
    clearcoat: bpy.props.FloatProperty(
        name="Clearcoat",
        description="Changes clearcoat property of car paint",
        default=0.2,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            CustomPropertyNames.TQ_CLEARCOAT,
            self.clearcoat
        ),
    )


MODULE_CLASSES.append(CarPaintProperties)


class WearProperties(bpy.types.PropertyGroup):
    @staticmethod
    def get_modifier_library_data_path() -> typing.Optional[str]:
        # We don't cache this because in theory the registered packs could change
        for pack in asset_registry.instance.get_packs_by_engon_feature("traffiq"):
            modifier_library_path_candidate = os.path.join(
                pack.install_path, "blends", "models", "Library_Traffiq_Modifiers.blend")
            if os.path.isfile(modifier_library_path_candidate):
                return modifier_library_path_candidate

        return None

    @staticmethod
    def update_bumps_prop(context: bpy.types.Context, value: float):
        prefs = get_preferences(context)
        # Cache objects that support bumps
        bumps_objs = [
            obj for obj in context.selected_objects if CustomPropertyNames.TQ_BUMPS in obj]

        modifier_library_path = None

        # Add bumps modifier that improves bumps effect on editable objects.
        # Bumps work for linked assets but looks better on editable ones with added modifier
        for obj in bumps_objs:
            # Object is not editable mesh
            if obj.data is None or obj.type != "MESH":
                continue
            # If modifier is not assigned to the object, append it from library
            if BUMPS_MODIFIER_NAME not in obj.modifiers:
                if modifier_library_path is None:
                    modifier_library_path = WearProperties.get_modifier_library_data_path()
                polib.asset_pack_bpy.append_modifiers_from_library(
                    BUMPS_MODIFIERS_CONTAINER_NAME, modifier_library_path, [obj])
                logger.info(f"Added bumps modifier on: {obj.name}")

            assert BUMPS_MODIFIER_NAME in obj.modifiers
            obj.modifiers[BUMPS_MODIFIER_NAME].strength = value

        polib.asset_pack_bpy.update_custom_prop(
            context,
            bumps_objs,
            CustomPropertyNames.TQ_BUMPS,
            value
        )

    dirt_wear_strength: bpy.props.FloatProperty(
        name="Dirt",
        description="Makes assets look dirty",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            CustomPropertyNames.TQ_DIRT,
            self.dirt_wear_strength
        ),
    )
    scratches_wear_strength: bpy.props.FloatProperty(
        name="Scratches",
        description="Makes assets look scratched",
        default=0.0,
        min=0.0,
        max=1.0,
        step=0.1,
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            context.selected_objects,
            CustomPropertyNames.TQ_SCRATCHES,
            self.scratches_wear_strength
        ),
    )
    bumps_wear_strength: bpy.props.FloatProperty(
        name="Bumps",
        description="Makes assets look dented, appends displacement modifier for better effect if object is editable",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        step=0.1,
        update=lambda self, context: WearProperties.update_bumps_prop(
            context, self.bumps_wear_strength),
    )


MODULE_CLASSES.append(WearProperties)


class RigProperties(bpy.types.PropertyGroup):
    auto_bake_steering: bpy.props.BoolProperty(
        name="Auto Bake Steering",
        description="If true, follow path operator will automatically try to bake steering",
        default=True
    )
    auto_bake_wheels: bpy.props.BoolProperty(
        name="Auto Bake Wheel Rotation",
        description="If true, follow path operator will automatically try to bake wheel rotation",
        default=True
    )
    auto_reset_transforms: bpy.props.BoolProperty(
        name="Auto Reset Transforms",
        description="If true, follow path operator will automatically reset transforms"
        "of needed objects to give the expected results",
        default=True
    )


MODULE_CLASSES.append(RigProperties)


class LightsProperties(bpy.types.PropertyGroup):
    main_lights_status: bpy.props.EnumProperty(
        name="Main Lights Status",
        items=(
            ("0", "off", "Front and rear lights are off"),
            ("0.25", "park", "Park lights are on"),
            ("0.50", "low-beam", "Low-beam lights are on"),
            ("0.75", "high-beam", "High-beam lights are on"),
        ),
        update=lambda self, context: polib.asset_pack_bpy.update_custom_prop(
            context,
            [polib.asset_pack_bpy.find_traffiq_lights_container(
                o) for o in context.selected_objects],
            CustomPropertyNames.TQ_LIGHTS,
            float(self.main_lights_status)
        ),
    )


MODULE_CLASSES.append(LightsProperties)


class TraffiqPreferences(bpy.types.PropertyGroup):
    car_paint_properties: bpy.props.PointerProperty(
        type=CarPaintProperties
    )

    wear_properties: bpy.props.PointerProperty(
        type=WearProperties
    )

    lights_properties: bpy.props.PointerProperty(
        type=LightsProperties
    )

    rig_properties: bpy.props.PointerProperty(
        type=RigProperties
    )


MODULE_CLASSES.append(TraffiqPreferences)


@polib.log_helpers_bpy.logged_preferences
@addon_updater_ops.make_annotations
class Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

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

    mq_global_texture_size: bpy.props.EnumProperty(
        items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
        name="materialiq global maximum side size",
    )

    general_preferences: bpy.props.PointerProperty(
        name="General Preferences",
        description="Preferences related to all asset packs",
        type=GeneralPreferences
    )

    mapr_preferences: bpy.props.PointerProperty(
        name="Browser Preferences",
        description="Preferences related to the mapr asset browser",
        type=MaprPreferences
    )

    aquatiq_preferences: bpy.props.PointerProperty(
        name="Aquatiq Preferences",
        description="Preferences related to the aquatiq addon",
        type=AquatiqPreferences
    )

    botaniq_preferences: bpy.props.PointerProperty(
        name="Botaniq Preferences",
        description="Preferences related to the botaniq addon",
        type=BotaniqPreferences
    )

    traffiq_preferences: bpy.props.PointerProperty(
        name="Traffiq Preferences",
        description="Preferences related to the traffiq addon",
        type=TraffiqPreferences
    )

    first_time_register: bpy.props.BoolProperty(
        description="Gets set to False when engon gets registered for the first time "
        "or when registered after being unregistered",
        default=True
    )

    save_prefs: bpy.props.BoolProperty(
        name="Auto-Save Preferences",
        description="Automatically saves Preferences after running operators "
        "(e.g. Install Asset Pack) that change engon preferences",
        default=True
    )

    def get_pack_info_paths(self) -> typing.Iterable[str]:
        environment_globs = os.environ.get("ENGON_ADDITIONAL_PACK_INFO_GLOBS", None)
        if environment_globs is not None:
            for glob_ in environment_globs.split(";"):
                pack_info_files = glob.glob(glob_, recursive=True)
                for pack_info_file in pack_info_files:
                    yield os.path.realpath(os.path.abspath(pack_info_file))

        for search_path in self.general_preferences.pack_info_search_paths:
            for pack in search_path.get_discovered_asset_packs():
                yield pack.pack_info_path

    def refresh_packs(self, save_prefs: bool = False) -> None:
        pack_info_search_paths.PackInfoSearchPath.clear_discovered_packs_cache()
        pack_info_paths = self.get_pack_info_paths()
        asset_registry.instance.refresh_packs_from_pack_info_paths(pack_info_paths)

        # we don't use the prop itself, because sometimes we don't need to save preferences
        if save_prefs:
            bpy.ops.wm.save_userpref()

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column()

        # Asset Packs section
        box = col.box()
        row = box.row()
        row.prop(self.general_preferences, "show_asset_packs",
                 icon='DISCLOSURE_TRI_DOWN' if self.general_preferences.show_asset_packs else 'DISCLOSURE_TRI_RIGHT',
                 text="",
                 emboss=False,)
        row.label(text="Asset Packs")
        if self.general_preferences.show_asset_packs:
            row = box.row()
            row.alignment = 'LEFT'
            row.scale_y = 1.2
            op = row.operator(InstallAssetPack.bl_idname,
                              text="Install Asset Pack", icon='NEWFOLDER')
            op.filepath = os.path.expanduser("~" + os.sep)
            row.operator(PackInfoSearchPathList_RefreshPacks.bl_idname,
                         icon='FILE_REFRESH', text="")
            for pack in asset_registry.instance.get_registered_packs():
                subbox: bpy.types.UILayout = box.box()

                # Left row for Asset Pack name
                row = subbox.row()
                row.scale_y = row.scale_x = 1.2
                row.label(
                    text=f"{pack.full_name}",
                    **polib.ui_bpy.get_asset_pack_icon_parameters(pack.get_pack_icon_id(), 'ASSET_MANAGER')
                )

                # Right row for Update and Uninstall buttons
                row = row.row(align=True)
                row.alignment = 'RIGHT'
                op = row.operator(UpdateAssetPack.bl_idname, text="", icon='FILE_PARENT')
                op.current_filepath = pack.install_path
                op.filepath = os.path.expanduser("~" + os.sep)

                op = row.operator(UninstallAssetPack.bl_idname, text="", icon='TRASH')
                op.current_filepath = pack.install_path

                sub_col = subbox.column(align=True)
                sub_col.enabled = False
                sub_col.label(text=f"Version: {pack.get_version_str()}")
                sub_row = sub_col.row(align=True)
                sub_row.alignment = 'LEFT'
                sub_row.label(text=f"Vendor:")
                vendor_icon_id = pack.get_vendor_icon_id()
                if vendor_icon_id is not None:
                    sub_row.label(icon_value=vendor_icon_id)
                sub_row.label(text=pack.vendor)

                sub_col.label(text=f"Installation path: {pack.install_path}")

            self.general_preferences.draw_pack_info_search_paths(context, box)

        # Keymaps section
        box = col.box()
        row = box.row()
        row.prop(self.general_preferences, "show_keymaps",
                 icon='DISCLOSURE_TRI_DOWN' if self.general_preferences.show_keymaps else 'DISCLOSURE_TRI_RIGHT',
                 text="",
                 emboss=False,)
        row.label(text="Keymaps")
        if self.general_preferences.show_keymaps:
            keymaps.draw_settings_ui(context, box)

        # Update Settings section
        box = col.box()
        row = box.row()
        row.prop(self.general_preferences, "show_updater_settings",
                 icon='DISCLOSURE_TRI_DOWN' if self.general_preferences.show_updater_settings else 'DISCLOSURE_TRI_RIGHT',
                 text="",
                 emboss=False,)
        row.label(text="Updater Settings")
        if self.general_preferences.show_updater_settings:
            addon_updater_ops.update_settings_ui(self, context, box)

        # Save Preferences checkbox
        self.draw_save_userpref_prompt(col)

        # Open Log Folder button
        self.layout.operator(PackLogs.bl_idname, icon='EXPERIMENTAL')

        polib.ui_bpy.draw_settings_footer(self.layout)

    def draw_save_userpref_prompt(self, layout: bpy.types.UILayout):
        box = layout.box()
        row = box.row()
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


def get_preferences(context: bpy.types.Context) -> Preferences:
    return context.preferences.addons[__package__].preferences


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
