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
import typing
import os
import pathlib
import shutil
import enum
import logging
import polib
import zipfile
import glob
from . import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")


# ~/polygoniq_asset_packs
DEFAULT_PACK_INSTALL_PATH = os.path.expanduser(os.path.join("~", "polygoniq_asset_packs"))


class InstallerOperation(enum.Enum):
    INSTALL = "Installation"
    UNINSTALL = "Uninstallation"
    UPDATE = "Update"


class InstallerStatus(enum.Enum):
    READY = "Ready"
    NOT_FOUND = "Not Found"
    CANCELED = "Canceled"
    ABORTED = "Aborted"
    FINISHED = "Finished"
    NOT_READY = "Not Ready"


INSTALLER_OPERATION_DESCRIPTIONS: typing.Dict[InstallerStatus, str] = {
    InstallerStatus.READY: "Ready to start _ACTION_.",
    InstallerStatus.NOT_FOUND: "No Asset Pack was found.",
    InstallerStatus.CANCELED: "_ACTION_ was canceled.",
    InstallerStatus.ABORTED: "_ACTION_ was unsuccessful.",
    InstallerStatus.FINISHED: "_ACTION_ was successful.",
    InstallerStatus.NOT_READY: "_ACTION_ is not ready to proceed."
}


class AssetPackInstaller:
    def __init__(self):
        self._operation: InstallerOperation = InstallerOperation.INSTALL
        self._status: InstallerStatus = InstallerStatus.NOT_READY
        self._error_messages: typing.List[str] = []

        # Asset Pack Metadata
        self.full_name: str = ""
        self.version: str = ""
        self.vendor: str = ""

        # Filepath from which the Asset Pack was loaded
        # Used only during installation from PAQ file
        self.pack_filepath: str = ""

        # Path to the pack-info file
        self._pack_info_path: str = ""

        # .pack-info path of the Asset Pack to be uninstall
        self._uninstall_pack_info_path: str = ""

        # Pack size in bytes
        self._pack_size: int = 0

        # Free disk space in bytes
        self._free_space: int = 0

        # Used during Installation and Update
        # Should contain the path without the Asset Pack's root folder
        self._install_path: str = DEFAULT_PACK_INSTALL_PATH

        # Asset Pack to be used during installation
        # Used mainly for comparing if it is already installed or if it is a different version
        self._loaded_asset_pack: typing.Optional['asset_registry.AssetPack'] = None

        # Flag for switching to another update from installation
        self._update_available: bool = False

    @property
    def error_messages(self) -> typing.Iterable[str]:
        return (message for message in self._error_messages)

    @property
    def error_messages_present(self) -> bool:
        return len(self._error_messages) > 0

    # Basename of the root directory
    @property
    def pack_root_directory(self) -> str:
        return os.path.basename(os.path.dirname(self._pack_info_path))

    # Path to the pack-info file
    @property
    def pack_info_path(self) -> str:
        return self._pack_info_path

    # Basename of the pack-info file
    @property
    def pack_info_basename(self) -> str:
        return os.path.basename(self._pack_info_path)

    @property
    def uninstall_pack_info_path(self) -> str:
        return self._uninstall_pack_info_path

    # Used during Uninstallation and Update
    # Should contain the path including the Asset Pack's root folder
    @property
    def uninstall_path(self) -> str:
        return os.path.dirname(self._uninstall_pack_info_path)

    @property
    def pack_size(self) -> str:
        return polib.utils_bpy.convert_size(self._pack_size)

    @property
    def free_space(self) -> str:
        return polib.utils_bpy.convert_size(self._free_space)

    @property
    def is_update_available(self) -> bool:
        return self._update_available

    @property
    def status_description(self) -> str:
        # Return the status description containing the current operation name
        description = INSTALLER_OPERATION_DESCRIPTIONS.get(self._status, None)
        if description is None:
            raise AttributeError("Provided Status does not have a description!")
        return description.replace("_ACTION_", self._operation.value)

    @property
    def ready(self) -> bool:
        return self._status == InstallerStatus.READY

    @property
    def can_installer_proceed(self) -> bool:
        return self._status == InstallerStatus.READY or \
            self._status == InstallerStatus.NOT_READY

    @property
    def install_path(self) -> str:
        return self._install_path

    @install_path.setter
    def install_path(self, new_install_path: str) -> None:
        self._install_path = new_install_path
        self._error_messages.clear()
        self._update_available = False
        free_space = 0
        closest_existing_directory: typing.Optional[str] = polib.utils_bpy.get_first_existing_ancestor_directory(
            new_install_path, whitelist={DEFAULT_PACK_INSTALL_PATH})
        if closest_existing_directory is not None:
            free_space = shutil.disk_usage(closest_existing_directory).free
        self._free_space = free_space

        # We don't need this during uninstallation
        if self._operation == InstallerOperation.INSTALL or \
                self._operation == InstallerOperation.UPDATE:

            if closest_existing_directory is None:
                self.record_error_message("Install Path is not valid!")
            elif free_space < self._pack_size:
                self.record_error_message("Not enough Disk Space!")

        # We only need this during installation
        if self._operation == InstallerOperation.INSTALL:
            assert self._loaded_asset_pack is not None
            pack_destination = os.path.join(self._install_path, self.pack_root_directory)
            already_exists = os.path.exists(pack_destination)
            already_installed_pack = asset_registry.instance.get_pack_by_full_name(self.full_name)
            if already_installed_pack is not None:
                self._uninstall_pack_info_path = already_installed_pack.pack_info_path
                if self._loaded_asset_pack.version > already_installed_pack.version:
                    self.record_error_message(
                        "A lower version of this Asset Pack is already installed. Try updating it.")
                    self._update_available = True
                elif already_installed_pack.version > self._loaded_asset_pack.version:
                    self.record_error_message(
                        "Higher version of this Asset Pack is already installed.")
                else:
                    self.record_error_message(
                        "This Asset Pack is already installed.")
            elif already_exists and self._operation == InstallerOperation.INSTALL:
                self.record_error_message(
                    "Install Path already contains an unregistered version of this Asset Pack.")

        if not self.error_messages_present:
            # Everything succeeded, we are ready to proceed with the operation
            self._status = InstallerStatus.READY
        else:
            self._status = InstallerStatus.NOT_READY
        return

    def abort_operation(self) -> None:
        self._status = InstallerStatus.ABORTED

    def cancel_installer_operation(self) -> None:
        self._error_messages.clear()
        self._status = InstallerStatus.CANCELED

    def get_installer_status_description(self) -> str:
        # Return the status description containing the current operation name
        return self._status.value.replace("_ACTION_", self._operation.value)

    def log_status_and_error_messages(self):
        description = self.get_installer_status_description()
        logger.info(description)

        for error_message in instance.error_messages:
            logger.error(error_message)

    def record_error_message(self, error_message: str) -> None:
        self._error_messages.append(error_message)

    def load_installation(self, filepath: str) -> None:
        self._load_installer(InstallerOperation.INSTALL, filepath)

    def load_uninstallation(self, filepath: str) -> None:
        self._load_installer(InstallerOperation.UNINSTALL, filepath)

    def load_update(self, filepath: str, update_filepath: str) -> None:
        self._load_installer(InstallerOperation.UPDATE, filepath, update_file_path=update_filepath)

    def get_paq_file_sources(self, file_path: str) -> typing.Optional[typing.List[str]]:
        """Returns all file sources needed to open a paq archive, or None if encountering an error

        The input can either be:
        'paq' - indicating one file archive - we return the filepath
        'paq.001' - indicating multipart archive - we return all parts of the multipart archive in a ordered list
        anything else - we return an empty list - this is for cases when the pack is being installed
        from an extracted folder, so we can still continue to look for a .pack-info file in it

        NOTE: Other parts of archive aren't considered as a valid input as we allow selecting only the
        first part ('paq.001') of the multipart archive in the blender file browser.
        """

        if file_path.endswith(".paq"):
            return [file_path]

        if file_path.endswith(".paq.001"):
            file_sources: typing.List[str] = []
            no_suffix = file_path[:-4]
            # find all paq.xxx files
            file_sources.extend(glob.glob(f"{no_suffix}.[0-9][0-9][1-9]"))
            file_sources.sort()
            assert no_suffix not in file_sources
            for i, paq_part in enumerate(file_sources):
                # index 0 should contain paq.001, index 1 should contain paq.002, ...
                expected_file_path = f"{no_suffix}.{(i + 1):03}"
                if paq_part != expected_file_path:
                    self.record_error_message(
                        f"Couldn't find all parts of '.paq' file. Part '{os.path.basename(expected_file_path)}'"
                        f"is missing!")
                    self._status = InstallerStatus.ABORTED
                    return None
            return file_sources

        return []

    def _get_asset_pack_and_size_from_filepath(self, file_path: str) -> typing.Tuple[typing.Optional[asset_registry.AssetPack], int, str]:
        """Recursively searches for an Asset Pack from a provided path.

        After successfully finding an Asset Pack, this method returns a tuple
        of the Asset Pack, it's size and the real path it was loaded from.
        """

        asset_pack: typing.Optional[asset_registry.AssetPack] = None
        pack_info_files: typing.List[str] = []
        pack_filepath = file_path
        pack_size = 0
        NO_RESULT = None, 0, ""

        paq_sources = self.get_paq_file_sources(pack_filepath)
        if paq_sources is None:
            return NO_RESULT
        try:
            if len(paq_sources) > 0:
                # Using the reader for single-part paq files here is OK
                # There seems to be minimal overhead
                with polib.split_file_reader.SplitFileReader(paq_sources) as reader:
                    with zipfile.ZipFile(reader, "r") as archive:
                        pack_info_files = [name for name in archive.namelist()
                                           if name.endswith(".pack-info")]
                        if not self._check_only_one_info_file(pack_info_files):
                            return NO_RESULT
                        assert len(pack_info_files) == 1
                        pack_info_file = pack_info_files[0]
                        pack_size = sum(file_info.file_size for file_info in archive.filelist)
                        asset_pack = asset_registry.AssetPack.load_from_paq_file(
                            archive, pack_info_file)
            else:
                pack_info_files = self._get_pack_info_files_from_ancestor_directory(pack_filepath)
                if not self._check_only_one_info_file(pack_info_files):
                    return NO_RESULT
                assert len(pack_info_files) == 1
                pack_info_file = pack_info_files[0]
                root_directory = os.path.dirname(pack_info_file)
                pack_size = sum(f.stat().st_size for f in pathlib.Path(
                    root_directory).rglob('*'))
                asset_pack = asset_registry.AssetPack.load_from_json(pack_info_file)
                # We might need to update the filepath because we found the pack-info file in an
                # ancestor directory.
                pack_filepath = root_directory

        except zipfile.BadZipFile as e:
            self.record_error_message(".paq file is corrupted.")
        except (ValueError, PermissionError, OSError) as e:
            self.record_error_message(str(e))

        if asset_pack is None or self.error_messages_present:
            self._status = InstallerStatus.ABORTED
            return NO_RESULT

        return asset_pack, pack_size, pack_filepath

    def _check_only_one_info_file(self, pack_info_files: typing.List[str]) -> bool:
        pack_info_files_count = len(pack_info_files)
        if pack_info_files_count != 1:
            self._status = InstallerStatus.NOT_FOUND
            if pack_info_files_count > 1:
                self.record_error_message("Selected folder contains more than one .pack-info file.")
            else:
                self.record_error_message("No .pack-info file was found.")
            return False
        return True

    def _clear_installer(self) -> None:
        self._operation = InstallerOperation.INSTALL
        self._status = InstallerStatus.NOT_READY
        self._error_messages.clear()
        self.full_name = ""
        self.version = ""
        self.vendor = ""
        self.pack_filepath = ""
        self._pack_info_path = ""
        self._uninstall_pack_info_path = ""
        self._pack_size = 0
        self._free_space = 0
        self._install_path = DEFAULT_PACK_INSTALL_PATH
        self._loaded_asset_pack = None
        self._update_available = False

    def _load_installer(
        self,
        operation: InstallerOperation,
        file_path: str,
        update_file_path: typing.Optional[str] = None
    ) -> None:
        self._clear_installer()
        self._operation = operation

        pack: typing.Optional[asset_registry.AssetPack] = None
        pack_size: int = 0
        update_pack: typing.Optional[asset_registry.AssetPack] = None
        update_pack_size: int = 0
        uninstall_pack: typing.Optional[asset_registry.AssetPack] = None

        pack, pack_size, file_path = self._get_asset_pack_and_size_from_filepath(file_path)

        # No info means something went wrong with loading the Asset Pack
        if pack is None:
            return

        if self._operation == InstallerOperation.UPDATE:
            assert update_file_path is not None
            update_pack, update_pack_size, update_file_path = self._get_asset_pack_and_size_from_filepath(
                update_file_path)

            # No info means something went wrong with loading the Asset Pack
            if update_pack is None:
                return

            if update_pack.pack_info_path == pack.pack_info_path:
                self.record_error_message("You cannot select the same Asset Pack!")
            if update_pack.full_name != pack.full_name:
                self.record_error_message("The selected Asset Pack differs in name.")
            if update_pack.vendor != pack.vendor:
                self.record_error_message("The selected Asset Pack is not of from the same vendor.")
            elif update_pack.version <= pack.version:
                self.record_error_message("The selected Asset Pack is not of higher version.")

            # Count how much more space the update needs
            update_pack_size -= pack_size
            if update_pack_size < 0:
                update_pack_size = 0
            pack_size = update_pack_size
            # Assign Update Pack as the regular, but keep the former for later
            pack, uninstall_pack = update_pack, pack
            file_path = update_file_path

        if self.error_messages_present:
            self._status = InstallerStatus.ABORTED
            return

        # Everything succeeded, we are ready to proceed with the operation
        self._status = InstallerStatus.READY

        self.full_name = pack.full_name
        self.version = pack.get_version_str()
        self.vendor = pack.vendor
        self.pack_filepath = file_path
        self._pack_info_path = pack.pack_info_path
        self._pack_size = pack_size

        # This needs to be set last
        # The install path update method uses the other properties for more checks
        if self._operation == InstallerOperation.INSTALL:
            self._loaded_asset_pack = pack
            self.install_path = DEFAULT_PACK_INSTALL_PATH
        if self._operation == InstallerOperation.UNINSTALL:
            self._uninstall_pack_info_path = pack.pack_info_path
            # This is only for printing in the dialog window
            # We do not need to recalculate anything
            self._install_path = self.uninstall_path
        elif self._operation == InstallerOperation.UPDATE and uninstall_pack is not None:
            # Show version update
            self.version = uninstall_pack.get_version_str() + " -> " + pack.get_version_str()
            # We want to install into the same install path
            # The new root folder might have a different name
            self._uninstall_pack_info_path = uninstall_pack.pack_info_path
            self.install_path = os.path.dirname(self.uninstall_path)

    def check_asset_pack_already_installed(self) -> bool:
        return asset_registry.instance.get_pack_by_full_name(self.full_name) is not None

    def execute_update(self) -> typing.Optional[typing.Tuple[str, str]]:
        """Successful update returns a tuple of the old and new .pack-info path of the updated Asset Pack"""

        old_pack_info_path = self.execute_uninstallation()
        new_pack_info_path = self.execute_installation()

        if old_pack_info_path is not None and new_pack_info_path is not None:
            return (old_pack_info_path, new_pack_info_path)
        return None

    def execute_installation(self) -> typing.Optional[str]:
        """Successful installation returns the .pack-info path of the installed Asset Pack"""

        def install_from_paq_file(path_or_reader: str | polib.split_file_reader.SplitFileReader) -> None:
            with zipfile.ZipFile(path_or_reader, "r") as archive:
                archive.extractall(path=self._install_path)
                self._status = InstallerStatus.FINISHED

        if self._status != InstallerStatus.READY:
            self._status = InstallerStatus.ABORTED
            return None

        try:
            paq_sources = self.get_paq_file_sources(self.pack_filepath)
            if len(paq_sources) == 1:
                install_from_paq_file(paq_sources[0])
            elif len(paq_sources) > 1:
                # Only use the reader for multi-part paq files
                # Using it on single-part files adds a lot of unnecessary overhead
                with polib.split_file_reader.SplitFileReader(paq_sources) as reader:
                    install_from_paq_file(reader)
            elif os.path.isdir(self.pack_filepath):
                destination = os.path.join(self.install_path, self.pack_root_directory)
                shutil.copytree(self.pack_filepath, destination)
                self._status = InstallerStatus.FINISHED
            else:
                self._status = InstallerStatus.ABORTED
                self.record_error_message("Path does not point to a Folder or a PAQ file")

            if self._status == InstallerStatus.FINISHED:
                return os.path.join(self._install_path, self.pack_root_directory, self.pack_info_basename)

        except (zipfile.BadZipFile, shutil.Error, PermissionError, ValueError, RuntimeError, OSError) as e:
            self._status = InstallerStatus.ABORTED
            self.record_error_message(str(e))

        return None

    def execute_uninstallation(self) -> typing.Optional[str]:
        """Successful uninstallation returns the .pack-info path of the uninstalled Asset Pack"""

        if self._status != InstallerStatus.READY:
            self._status = InstallerStatus.ABORTED
            return None
        # Checks for not allowing deletion of internal Asset Packs
        if "G:/Shared drives/Builds" in polib.utils_bpy.normalize_path(self.uninstall_path) or \
            "execroot/pq" in polib.utils_bpy.normalize_path(
                os.path.realpath(self.uninstall_path)):
            self.record_error_message("Cannot uninstall internal polygoniq Asset Pack!")
            self._status = InstallerStatus.ABORTED
            return None
        try:
            if not os.path.isdir(self.uninstall_path):
                self._status = InstallerStatus.ABORTED
                self.record_error_message("Path does not point to a Folder.")
                return None
            shutil.rmtree(self.uninstall_path)
            if self._operation == InstallerOperation.UPDATE:
                self._status = InstallerStatus.READY
            else:
                self._status = InstallerStatus.FINISHED
            return self.uninstall_pack_info_path

        except (shutil.Error, PermissionError, OSError) as e:
            self._status = InstallerStatus.ABORTED
            self.record_error_message(str(e))

        return None

    def _get_direct_child_pack_info_files(self, parent_dir: str) -> typing.List[str]:
        if not os.path.exists(parent_dir):
            return []
        elif os.path.isfile(parent_dir):
            parent_dir = os.path.dirname(parent_dir)
        return [os.path.join(parent_dir, name) for name in os.listdir(parent_dir) if name.endswith(".pack-info")]

    def _get_pack_info_files_from_ancestor_directory(self, current_dir: str) -> typing.List[str]:
        if not os.path.exists(current_dir):
            return []
        pack_info_files: typing.List[str] = self._get_direct_child_pack_info_files(current_dir)
        while current_dir != os.path.dirname(current_dir) and len(pack_info_files) == 0:
            current_dir = os.path.dirname(current_dir)
            pack_info_files = self._get_direct_child_pack_info_files(current_dir)
        return pack_info_files


instance: AssetPackInstaller = AssetPackInstaller()


class AssetPackInstallerDialogMixin:
    """Mixin for providing methods for Asset Pack Installation related operator dialogs

    This class is used by Instal/Uninstall/Update Asset Pack operators in preferences
    """

    def _update_cancel_installer_operation(self, _) -> None:
        if self.canceled:
            instance.cancel_installer_operation()

    def _set_install_path(self, install_path: str) -> None:
        instance.install_path = install_path

    def _get_install_path(self) -> str:
        return instance.install_path

    # Setting to True changes status to 'CANCELED'
    canceled: bpy.props.BoolProperty(
        name="Cancel Installer Operation",
        default=False,
        update=_update_cancel_installer_operation
    )

    # Used during Installation and Update
    # Should contain the path without the Asset Pack's root folder
    install_path: bpy.props.StringProperty(
        name="Install Path",
        description="Select Asset Pack Install Path",
        set=_set_install_path,
        get=_get_install_path
    )

    # Used for passing to operators when offering to switch operation
    filepath: bpy.props.StringProperty(
        options={'HIDDEN'}
    )

    close: bpy.props.BoolProperty(
        options={'HIDDEN'}
    )

    def draw_status_and_error_messages(self, layout: bpy.types.UILayout) -> None:
        prev_alert = layout.alert
        description = instance.status_description
        layout.box().label(text=description, icon='INFO')

        for error_message in instance.error_messages:
            layout.alert = True
            layout.box().label(text=error_message, icon='ERROR')
            layout.alert = prev_alert

    def draw_pack_info(
        self,
        layout: bpy.types.UILayout,
        header: str = "",
        show_install_path=False
    ) -> None:
        col = layout.column(align=True)

        if header != "":
            col.box().label(text=header, icon='INFO')

        col = col.box().column(align=True)
        col.label(text=f"Name: {instance.full_name}")
        col.label(text=f"Version: {instance.version}")
        col.label(text=f"Vendor: {instance.vendor}")
        if show_install_path:
            col.label(text=f"Install Path: {instance.install_path}")

    def check_should_dialog_close(self) -> bool:
        return not instance.can_installer_proceed

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if not instance.can_installer_proceed:
            instance.log_status_and_error_messages()
        polib.ui_bpy.center_mouse(context)
        return context.window_manager.invoke_props_dialog(self, width=550)
