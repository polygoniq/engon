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
import bpy_extras
import typing
import os
import glob
import json
import logging
from .. import polib
from . import prefs_utils
from .. import asset_pack_installer
from .. import pack_info_search_paths
from .. import asset_registry
from .. import blend_maintenance
from .. import __package__ as base_package

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


class ScatterProperties(bpy.types.PropertyGroup):
    max_particle_count: bpy.props.IntProperty(
        name="Maximum Particles",
        description="Maximum particle threshold for density recalculation",
        default=100000,
    )

    # Used to change visibility of instance collection in active particle system
    active_display_type: bpy.props.EnumProperty(
        name="Display As",
        items=prefs_utils.SCATTER_DISPLAY_ENUM_ITEMS,
        default='TEXTURED',
        update=lambda self, context: self.active_display_type_updated(context),
    )

    # Change Visibility operator global properties
    display_type: bpy.props.EnumProperty(
        name="Display As", items=prefs_utils.SCATTER_DISPLAY_ENUM_ITEMS, default='TEXTURED'
    )

    display_percentage: bpy.props.IntProperty(
        name="Display Percentage",
        description="Percentage of particles that are displayed in viewport",
        subtype='PERCENTAGE',
        default=100,
        min=0,
        max=100,
    )

    def active_display_type_updated(self, context: bpy.types.Context) -> None:
        collection = context.object.particle_systems.active.settings.instance_collection
        assert collection is not None
        for obj in collection.all_objects:
            obj.display_type = self.active_display_type


MODULE_CLASSES.append(ScatterProperties)


class ClickerProperties(bpy.types.PropertyGroup):
    random_rotation_z: bpy.props.FloatProperty(
        name="Random Rotation Z",
        description="Maximum additional random rotation around Z axis",
        default=0.0,
        min=0,
        max=1,
        subtype='FACTOR',
    )
    random_tilt: bpy.props.FloatProperty(
        name="Random Tilt",
        description="Maximum additional random tilt the clicked asset in XY axis",
        default=0.0,
        min=0,
        max=1,
        subtype='FACTOR',
    )
    random_scale: bpy.props.FloatProperty(
        name="Random Scale",
        description="Maximum additional random scale of the clicked asset",
        min=0.0,
        default=0.0,
    )
    align_to_surface: bpy.props.BoolProperty(
        name="Align to Surface",
        description="If enabled, clicked assets will be aligned to the surface normal",
        default=False,
    )
    origin_to_bottom: bpy.props.BoolProperty(
        name="Align Origin to Bottom",
        description=(
            "If enabled, clicked assets origins will be aligned to the bottom of the asset's"
            "bounding box. This option makes the object data unique per instanced object"
        ),
        default=True,
    )


MODULE_CLASSES.append(ClickerProperties)


class GeneralPreferences(bpy.types.PropertyGroup):
    pack_info_search_paths: bpy.props.CollectionProperty(
        name="Pack Info Search Paths", type=pack_info_search_paths.PackInfoSearchPath
    )
    pack_info_search_path_index: bpy.props.IntProperty(
        name="Pack Info Search Path Index",
        default=0,
    )

    scatter_props: bpy.props.PointerProperty(type=ScatterProperties, name="Scatter Properties")
    clicker_props: bpy.props.PointerProperty(type=ClickerProperties, name="Clicker Properties")

    def get_pack_info_paths(self) -> typing.Iterable[str]:
        environment_globs = os.environ.get("ENGON_ADDITIONAL_PACK_INFO_GLOBS", None)
        if environment_globs is not None:
            for glob_ in environment_globs.split(";"):
                pack_info_files = glob.glob(glob_, recursive=True)
                for pack_info_file in pack_info_files:
                    yield os.path.realpath(os.path.abspath(pack_info_file))

        for search_path in self.pack_info_search_paths:
            for pack in search_path.get_discovered_asset_packs():
                yield pack.pack_info_path

    def refresh_packs(self, save_prefs: bool = False) -> None:
        pack_info_search_paths.PackInfoSearchPath.clear_discovered_packs_cache()
        pack_info_paths = self.get_pack_info_paths()
        asset_registry.instance.refresh_packs_from_pack_info_paths(pack_info_paths)

        # we don't use the prop itself, because sometimes we don't need to save preferences
        if save_prefs:
            bpy.ops.wm.save_userpref()

    def pack_info_search_path_list_ensure_valid_index(self) -> None:
        min_index = 0
        max_index = len(self.pack_info_search_paths) - 1

        index = self.pack_info_search_path_index
        if index < min_index:
            self.pack_info_search_path_index = min_index
        elif index > max_index:
            self.pack_info_search_path_index = max_index

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
        path_type: pack_info_search_paths.PackInfoSearchPathType = pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE,
    ) -> None:
        """Removes all copies of the pack-info search path from the Collection.

        Does not reload Asset Packs.
        """
        filtered_out = [
            p.as_dict()
            for p in self.pack_info_search_paths
            if not (
                p.path_type == path_type
                and p.get_path_or_expression_by_type() == path_or_expression
            )
        ]

        self.pack_info_search_paths.clear()
        for sp in filtered_out:
            self.pack_info_search_paths.add().load_from_dict(sp)
        gen_prefs = prefs_utils.get_preferences(context).general_preferences
        gen_prefs.pack_info_search_path_list_ensure_valid_index()

    def get_search_paths_as_dict(self) -> typing.Dict:
        ret = []
        for search_path in self.pack_info_search_paths:
            ret.append(search_path.as_dict())

        return {"asset_pack_search_paths": ret}

    def add_search_paths_from_dict(
        self, info_dict: typing.Dict[str, typing.List[typing.Dict[str, str]]]
    ) -> None:
        search_paths_list = info_dict.get("asset_pack_search_paths", None)
        if search_paths_list is None:
            raise ValueError(
                "Given json dict does not contain a required key 'asset_pack_search_paths'!"
            )
        if not isinstance(search_paths_list, list):
            raise ValueError(
                f"Given json dict contains asset_pack_search_paths but its type is '{type(search_paths_list)}' "
                f"instead of the expected 'list'!"
            )

        for search_path_props in search_paths_list:
            search_path: pack_info_search_paths.PackInfoSearchPath = (
                self.pack_info_search_paths.add()
            )
            search_path.load_from_dict(search_path_props)

    def draw_asset_packs(self, layout: bpy.types.UILayout) -> None:
        row = layout.row()
        row.alignment = 'LEFT'
        row.scale_y = 1.2
        op = row.operator(InstallAssetPack.bl_idname, text="Install Asset Pack", icon='NEWFOLDER')
        row.operator(PackInfoSearchPathList_RefreshPacks.bl_idname, icon='FILE_REFRESH', text="")
        try:
            engon_version = polib.utils_bpy.get_addon_mod_info(base_package)["version"]
        except (ValueError, KeyError):
            # This shouldn't happen at all, because we are in the same __package__ that we are
            # searching for the version, but just to be sure and to always display asset pack
            # preferences, we catch this.
            engon_version = None

        for pack in asset_registry.instance.get_registered_packs():
            subbox: bpy.types.UILayout = layout.box()

            # Left row for Asset Pack name
            row = subbox.row()
            row.scale_y = row.scale_x = 1.2
            row.label(
                text=f"{pack.full_name}",
                **polib.ui_bpy.get_asset_pack_icon_parameters(
                    pack.get_pack_icon_id(), 'ASSET_MANAGER'
                ),
            )

            # Right row for Update and Uninstall buttons
            row = row.row(align=True)
            row.alignment = 'RIGHT'
            op = row.operator(UpdateAssetPack.bl_idname, text="", icon='FILE_PARENT')
            op.current_filepath = pack.install_path

            op = row.operator(UninstallAssetPack.bl_idname, text="", icon='TRASH')
            op.current_filepath = pack.install_path

            split = subbox.split(factor=0.20)
            label_col = split.column(align=True)
            label_col.enabled = False
            value_col = split.column(align=True)
            value_col.enabled = False

            label_col.label(text=f"Version:")
            value_col.label(text=f"{pack.get_version_str()}")
            label_col.label(text=f"Vendor:")
            sub_row = value_col.row(align=True)
            sub_row.alignment = 'LEFT'
            vendor_icon_id = pack.get_vendor_icon_id()
            if vendor_icon_id is not None:
                sub_row.label(icon_value=vendor_icon_id)
            sub_row.label(text=pack.vendor)
            label_col.label(text=f"Installation path:")
            value_col.label(text=f"{pack.install_path}")

            if engon_version is not None and engon_version < pack.min_engon_version:
                col = subbox.column(align=True)
                col.label(
                    text=f"engon {'.'.join(map(str, pack.min_engon_version))} or newer is recommended for this Asset Pack!",
                    icon='ERROR',
                )
                col.label(
                    text="Some features might not work correctly, please update engon in the "
                    "'Updates' section.",
                )

    def get_all_discovered_asset_packs(self) -> typing.Iterable[asset_registry.AssetPack]:
        """Returns discovered asset packs from all search paths."""
        for search_path in self.pack_info_search_paths:
            yield from search_path.get_discovered_asset_packs()

    def draw_pack_info_search_paths(
        self, context: bpy.types.Context, layout: bpy.types.UILayout
    ) -> None:
        gen_prefs = prefs_utils.get_preferences(context).general_preferences
        gen_prefs.pack_info_search_path_list_ensure_valid_index()

        discovered_asset_packs = self.get_all_discovered_asset_packs()
        registered_asset_packs = asset_registry.instance.get_registered_packs()
        discovered_but_unregistered_packs = set(discovered_asset_packs) - set(
            registered_asset_packs
        )

        discovered_but_unregistered_packs_count = len(discovered_but_unregistered_packs)

        row = layout.row()
        col = row.column(align=True)
        col.operator(PackInfoSearchPathList_OT_AddItem.bl_idname, text="", icon='ADD')
        col.operator(PackInfoSearchPathList_OT_DeleteItem.bl_idname, text="", icon='REMOVE')
        sub = col.row()
        sub.alert = discovered_but_unregistered_packs_count > 0
        sub.operator(PackInfoSearchPathList_RefreshPacks.bl_idname, text="", icon='FILE_REFRESH')
        col.separator()
        col.operator(
            PackInfoSearchPathList_OT_MoveItem.bl_idname, text="", icon='TRIA_UP'
        ).direction = "UP"
        col.operator(
            PackInfoSearchPathList_OT_MoveItem.bl_idname, text="", icon='TRIA_DOWN'
        ).direction = "DOWN"
        col.separator(factor=2)
        col.operator(PackInfoSearchPathList_RemoveAll.bl_idname, text="", icon='TRASH')

        col = row.column(align=True)
        col.template_list(
            "MY_UL_PackInfoSearchPathList",
            "PackInfoSearchPath",
            self,
            "pack_info_search_paths",
            self,
            "pack_info_search_path_index",
        )

        row = col.row(align=True)
        row.operator(PackInfoSearchPathList_Import.bl_idname, icon='IMPORT')
        row.operator(PackInfoSearchPathList_Export.bl_idname, icon='EXPORT')

        if discovered_but_unregistered_packs_count > 0:
            row = layout.row()
            row.alert = True
            row.label(
                text=f"Refresh Asset Packs to register {discovered_but_unregistered_packs_count} "
                f"newly discovered pack{'' if discovered_but_unregistered_packs_count == 1 else 's'}!",
                icon='FILE_REFRESH',
            )


MODULE_CLASSES.append(GeneralPreferences)


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
        prefs = prefs_utils.get_preferences(context)
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
        prefs = prefs_utils.get_preferences(context)
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
        prefs = prefs_utils.get_preferences(context)
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
    def poll(cls, context: bpy.types.Context) -> bool:
        prefs = prefs_utils.get_preferences(context)
        return len(prefs.general_preferences.pack_info_search_paths) > 0

    def execute(self, context: bpy.types.Context):
        prefs = prefs_utils.get_preferences(context)
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

        prefs.general_preferences.pack_info_search_path_list_ensure_valid_index()
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
        ),
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        prefs = prefs_utils.get_preferences(context)
        return len(prefs.general_preferences.pack_info_search_paths) > 1

    def execute(self, context: bpy.types.Context):
        prefs = prefs_utils.get_preferences(context)
        the_list = prefs.general_preferences.pack_info_search_paths
        index = prefs.general_preferences.pack_info_search_path_index
        neighbor = index + (-1 if self.direction == 'UP' else 1)
        the_list.move(neighbor, index)
        prefs.general_preferences.pack_info_search_path_index = neighbor
        prefs.general_preferences.pack_info_search_path_list_ensure_valid_index()
        return {'FINISHED'}


MODULE_CLASSES.append(PackInfoSearchPathList_OT_MoveItem)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_RemoveAll(bpy.types.Operator):
    bl_idname = "engon.pack_info_search_path_list_remove_all"
    bl_label = "Remove All Search Paths"
    bl_description = "Remove all Search Paths from the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        prefs = prefs_utils.get_preferences(context)
        prefs.general_preferences.pack_info_search_paths.clear()
        prefs.general_preferences.pack_info_search_path_list_ensure_valid_index()

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_confirm(self, event)


MODULE_CLASSES.append(PackInfoSearchPathList_RemoveAll)


@polib.log_helpers_bpy.logged_operator
class PackInfoSearchPathList_RefreshPacks(bpy.types.Operator):
    bl_idname = "engon.pack_info_search_path_refresh_packs"
    bl_label = "Refresh Asset Packs"
    bl_description = (
        "Search through all search paths, find .pack-info files "
        + "and register them. Saves Preferences"
    )
    bl_options = {'REGISTER'}

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = prefs_utils.get_preferences(context)
        gen_prefs = prefs.general_preferences
        gen_prefs.refresh_packs(save_prefs=prefs.save_prefs)
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
    filter_glob: bpy.props.StringProperty(default="*.paq;*.paq.001;*.pack-info", options={'HIDDEN'})

    # Intentional shadowing of the filepath prop from the ImportHelper
    # This allows us to force this prop to use 'SKIP_SAVE' option, so we can use the operator without the file selection window
    # NOTE: Do not change the default value or this will not work
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            # Invoke the file selection window
            return super().invoke(context, event)
        return self.execute(context)

    def execute(self, context: bpy.types.Context):
        # Special condition for preventing Drag & Drop triggering unwanted failed installation dialogs
        # This is a workaround as the FileHandler is not able to accept '.paq.001' files, so we allow '.001' files there
        if (
            bpy.app.version >= (4, 1, 0)
            and self.filepath.endswith(".001")
            and not self.filepath.endswith(".paq.001")
        ):
            logger.error(f"Unsupported file '{self.filepath}'")
            return {'CANCELLED'}
        installer = asset_pack_installer.instance
        installer.load_installation(self.filepath)
        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT', filepath=self.filepath)

        return {'FINISHED'}


MODULE_CLASSES.append(InstallAssetPack)

# Drag & Drop support is only available in Blender 4.1+
if bpy.app.version >= (4, 1, 0):

    class InstallAssetPackDragAndDropHandler(bpy.types.FileHandler):
        bl_idname = "ENGON_FH_install_asset_pack_drag_and_drop"
        bl_label = "Drag & Drop Install Asset Pack"
        bl_import_operator = InstallAssetPack.bl_idname
        # .paq.001 is not supported so we allow .001 and check the "real" extension in the install operator
        bl_file_extensions = ".paq;.pack-info;.001"

        @classmethod
        def poll_drop(cls, context: bpy.types.Context) -> bool:
            return True

    MODULE_CLASSES.append(InstallAssetPackDragAndDropHandler)


@polib.log_helpers_bpy.logged_operator
class AssetPackInstallationDialog(
    bpy.types.Operator, asset_pack_installer.AssetPackInstallerDialogMixin
):
    bl_idname = "engon.asset_pack_install_dialog"
    bl_label = "Install Asset Pack"
    bl_description = "Asset Pack Installation Dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    try_updating: bpy.props.BoolProperty(
        get=lambda self: asset_pack_installer.instance.try_updating,
        set=lambda self, value: setattr(asset_pack_installer.instance, "try_updating", value),
        description="If checked, proceeding with the installation will start an UPDATE dialog for this Asset Pack",
    )

    try_reregistering: bpy.props.BoolProperty(
        get=lambda self: asset_pack_installer.instance.try_reregistering,
        set=lambda self, value: setattr(asset_pack_installer.instance, "try_reregistering", value),
        description="If checked, proceeding with the installation will RE-REGISTER this Asset Pack",
    )

    try_reinstalling: bpy.props.BoolProperty(
        get=lambda self: asset_pack_installer.instance.try_reinstalling,
        set=lambda self, value: setattr(asset_pack_installer.instance, "try_reinstalling", value),
        description="If checked, proceeding with the installation will REMOVE the already present Asset Pack. "
        "This new Asset Pack will be installed in its place.",
    )

    def draw(self, context: bpy.types.Context) -> None:
        installer = asset_pack_installer.instance
        layout: bpy.types.UILayout = self.layout

        if self.check_should_dialog_close():
            if not self.close:
                self.close = True
            if not self.canceled:
                layout.label(text=self.__class__.bl_label)
            self.draw_status_and_messages(layout)
            return

        self.draw_pack_info(layout, header="This Asset Pack will be installed:")

        box = layout.box()
        if not installer.is_update_available:
            col = box.column(align=True)
            col.label(text="Select an installation directory")
            split = col.split(factor=0.05, align=True)
            split.operator(
                SelectAssetPackInstallPath.bl_idname, text="", icon='FILE_FOLDER'
            ).filepath = os.path.expanduser("~" + os.sep)
            split.prop(self, "install_path", text="")

        self.draw_installer_info(box)
        col = box.column()
        self.draw_status_and_messages(col)
        if installer.is_update_available:
            row = col.box().row(align=True)
            row.prop(self, "try_updating", text="")
            row.label(text="Update Pack")
        elif installer.is_reregister_available:
            row = col.box().row(align=True)
            row.prop(self, "try_reregistering", text="")
            row.label(text="Re-register Pack")
        elif installer.is_reinstall_available:
            row = col.box().row(align=True)
            row.prop(self, "try_reinstalling", text="")
            row.label(text="Re-install Pack")

        col = layout.box().column(align=True)
        if not installer.is_ready:
            col.label(text="Clicking 'OK' will ABORT the installation.")
        elif self.try_updating:
            col.label(text="Clicking 'OK' will start an UPDATE dialog for this Asset Pack.")
        elif self.try_reregistering:
            col.label(text="Clicking 'OK' will RE-REGISTER the already present Asset Pack.")
        elif self.try_reinstalling:
            col.label(text="Clicking 'OK' will REMOVE the already present Asset Pack.")
            col.label(
                text="It will COPY all contents of this Asset Pack into the installation directory."
            )
        else:
            col.label(
                text="Clicking 'OK' will COPY all contents of this Asset Pack into the installation directory."
            )

        # We show custom cancel button only in versions before 4.1.0
        # From that version all operators have cancel button natively
        if bpy.app.version < (4, 1, 0):
            layout.prop(self, "canceled", toggle=True, text="Cancel Installation", icon='CANCEL')

    @staticmethod
    def _install_pack(
        context: bpy.types.Context, installer: asset_pack_installer.AssetPackInstaller
    ) -> None:
        prefs = prefs_utils.get_preferences(context)
        gen_prefs = prefs.general_preferences

        pack_info_path_to_add: typing.Optional[str] = installer.execute_installation()
        if pack_info_path_to_add is not None and not installer.check_asset_pack_already_installed():
            gen_prefs.add_new_pack_info_search_path(
                file_path=pack_info_path_to_add,
                path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE,
            )
            asset_registry.instance.register_pack_from_pack_info_path(
                pack_info_path_to_add, refresh_registry=False
            )
            gen_prefs.refresh_packs(save_prefs=prefs.save_prefs)
            blend_maintenance.migrator.find_missing_files()

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        if self.try_updating:
            installer.load_update(installer.uninstall_path, self.filepath)
            bpy.ops.engon.asset_pack_update_dialog('INVOKE_DEFAULT')
            return {'FINISHED'}

        AssetPackInstallationDialog._install_pack(context, installer)

        bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackInstallationDialog)


@polib.log_helpers_bpy.logged_operator
class UninstallAssetPack(bpy.types.Operator):
    bl_idname = "engon.uninstall_asset_pack"
    bl_label = "Uninstall Asset Pack"
    bl_description = (
        "Uninstalls selected asset pack, selected asset pack will be also removed from the disc"
    )
    bl_options = {'REGISTER'}

    current_filepath: bpy.props.StringProperty(default="")

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        installer.load_uninstallation(self.current_filepath)
        bpy.ops.engon.asset_pack_uninstall_dialog('INVOKE_DEFAULT')

        return {'FINISHED'}


MODULE_CLASSES.append(UninstallAssetPack)


@polib.log_helpers_bpy.logged_operator
class AssetPackUninstallationDialog(
    bpy.types.Operator, asset_pack_installer.AssetPackInstallerDialogMixin
):
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
            if not self.canceled:
                layout.label(text=self.__class__.bl_label)
            self.draw_status_and_messages(layout)
            return

        self.draw_pack_info(
            layout, header="This Asset Pack will be uninstalled:", show_install_path=True
        )

        box = layout.box()
        self.draw_installer_info(box)
        col = box.column()
        self.draw_status_and_messages(col)

        box = layout.box()
        if not installer.is_ready:
            box.label(text="Clicking 'OK' will ABORT the uninstallation.")
        else:
            box.label(
                text="Clicking 'OK' will REMOVE all contents of this Asset Pack from the installation directory."
            )

        # We show custom cancel button only in versions before 4.1.0
        # From that version all operators have cancel button natively
        if bpy.app.version < (4, 1, 0):
            layout.prop(self, "canceled", toggle=True, text="Cancel Uninstallation", icon='CANCEL')

    @staticmethod
    def _uninstall_pack(
        context: bpy.types.Context, installer: asset_pack_installer.AssetPackInstaller
    ):
        prefs = prefs_utils.get_preferences(context)
        gen_prefs = prefs.general_preferences

        pack_info_path_to_remove = installer.execute_uninstallation()
        if pack_info_path_to_remove is not None:
            gen_prefs.remove_all_copies_of_pack_info_search_path(
                context,
                pack_info_path_to_remove,
                path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE,
            )
            asset_registry.instance.unregister_pack_from_pack_info_path(
                pack_info_path_to_remove, refresh_registry=False
            )
            gen_prefs.refresh_packs(save_prefs=prefs.save_prefs)

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        AssetPackUninstallationDialog._uninstall_pack(context, installer)

        bpy.ops.engon.asset_pack_uninstall_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackUninstallationDialog)


@polib.log_helpers_bpy.logged_operator
class UpdateAssetPack(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "engon.update_asset_pack"
    bl_label = "Update Asset Pack"
    bl_description = "Updates asset pack with the new version selected via file browser"
    bl_options = {'REGISTER'}

    # These are the primary file types the user should select
    # All other file types work as well, but are not visible by default
    filter_glob: bpy.props.StringProperty(default="*.paq;*.paq.001;*.pack-info", options={'HIDDEN'})

    # Intentional shadowing of the filepath prop from the ImportHelper
    # This allows us to force this prop to use 'SKIP_SAVE' option, so we can use the operator without the file selection window
    # NOTE: Do not change the default value or this will not work
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})

    current_filepath: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            # Invoke the file selection window
            return super().invoke(context, event)
        return self.execute(context)

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

    def draw(self, context: bpy.types.Context) -> None:
        installer = asset_pack_installer.instance
        layout: bpy.types.UILayout = self.layout

        if self.check_should_dialog_close():
            if not self.close:
                self.close = True
            if not self.canceled:
                layout.label(text=self.__class__.bl_label)
            self.draw_status_and_messages(layout)
            return

        self.draw_pack_info(layout, header="This Asset Pack will be updated:")

        box = layout.box()
        self.draw_installer_info(box)
        col = box.column()
        self.draw_status_and_messages(col)

        col = layout.box().column(align=True)
        if not installer.is_ready:
            col.label(text="Clicking 'OK' will ABORT the update.")
        else:
            col.label(
                text="Clicking 'OK' will REMOVE the old version of the Asset Pack from the installation directory."
            )
            col.label(text="It will be REPLACED with the new version.")

        # We show custom cancel button only in versions before 4.1.0
        # From that version all operators have cancel button natively
        if bpy.app.version < (4, 1, 0):
            layout.prop(self, "canceled", toggle=True, text="Cancel Update", icon='CANCEL')

    @staticmethod
    def _update_pack(
        context: bpy.types.Context, installer: asset_pack_installer.AssetPackInstaller
    ) -> None:
        prefs = prefs_utils.get_preferences(context)
        gen_prefs = prefs.general_preferences

        update_paths = installer.execute_update()
        if update_paths is not None:
            pack_info_path_to_remove, pack_info_path_to_add = update_paths
            gen_prefs.remove_all_copies_of_pack_info_search_path(
                context,
                pack_info_path_to_remove,
                path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE,
            )
            asset_registry.instance.unregister_pack_from_pack_info_path(
                pack_info_path_to_remove, refresh_registry=False
            )
            gen_prefs.add_new_pack_info_search_path(
                file_path=pack_info_path_to_add,
                path_type=pack_info_search_paths.PackInfoSearchPathType.SINGLE_FILE,
            )
            asset_registry.instance.register_pack_from_pack_info_path(
                pack_info_path_to_add, refresh_registry=False
            )
            gen_prefs.refresh_packs(save_prefs=prefs.save_prefs)
            blend_maintenance.migrator.find_missing_files()

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance

        if self.close:
            return {'FINISHED'}

        AssetPackUpdateDialog._update_pack(context, installer)

        bpy.ops.engon.asset_pack_update_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


MODULE_CLASSES.append(AssetPackUpdateDialog)


@polib.log_helpers_bpy.logged_operator
class SelectAssetPackInstallPath(bpy.types.Operator, polib.ui_bpy.SelectFolderPathMixin):
    bl_idname = "engon.select_asset_pack_install_path"
    bl_description = "Select a Custom Install Path for the Asset Pack"

    def execute(self, context: bpy.types.Context):
        installer = asset_pack_installer.instance
        if os.path.exists(self.filepath):
            installer.install_path = os.path.dirname(self.filepath)

        return bpy.ops.engon.asset_pack_install_dialog('INVOKE_DEFAULT')


MODULE_CLASSES.append(SelectAssetPackInstallPath)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
