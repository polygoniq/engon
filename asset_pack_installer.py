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
import zipfile
import glob
from . import polib
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
    ABORTED = "Aborted"
    FINISHED = "Finished"
    NOT_READY = "Not Ready"
    EXIT = "Exit"
    # This status serves for our custom cancel button in versions before 4.1.0
    # TODO: Remove this status when we drop support for Blender versions before 4.1.0
    CANCELED = "Canceled"


INSTALLER_OPERATION_DESCRIPTIONS: typing.Dict[InstallerStatus, str] = {
    InstallerStatus.READY: "Ready to start _ACTION_.",
    InstallerStatus.NOT_FOUND: "No Asset Pack was found.",
    InstallerStatus.CANCELED: "_ACTION_ was canceled.",
    InstallerStatus.ABORTED: "_ACTION_ was unsuccessful.",
    InstallerStatus.FINISHED: "_ACTION_ was successful.",
    InstallerStatus.NOT_READY: "_ACTION_ is not ready to proceed. Resolve the issue(s) below.",
    InstallerStatus.EXIT: "Exited _ACTION_.",
}


class AssetPackInstaller:
    def __init__(self):
        self._operation: InstallerOperation = InstallerOperation.INSTALL
        self._status: InstallerStatus = InstallerStatus.NOT_READY
        self._warning_messages: typing.List[str] = []
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

        # Flags for switching to another update from installation
        self._update_available: bool = False
        self._try_updating: bool = False

        # Flags for for re-installing already installed Asset Pack - if asset pack is found
        # in install directory but it's not registered in engon. It could differ from the installed
        # version, so we have to replace all contents
        self._reinstall_available: bool = False
        self._try_reinstalling: bool = False

        # Flags for re-registering already installed Asset Pack - if asset pack is being installed
        # from the same pack-info file already present in the install directory
        self._reregister_available: bool = False
        self._try_reregistering: bool = False

    @property
    def status(self) -> InstallerStatus:
        return self._status

    # Use this method to change the status
    # The only place where not to use this is inside _clear_installer
    @status.setter
    def status(self, new_status: InstallerStatus) -> None:
        self._status = new_status
        logger.info(f"Status: {self.get_installer_status_description()}")

    @property
    def warning_messages(self) -> typing.Iterable[str]:
        return (message for message in self._warning_messages)

    @property
    def error_messages(self) -> typing.Iterable[str]:
        return (message for message in self._error_messages)

    @property
    def warning_messages_present(self) -> bool:
        return len(self._warning_messages) > 0

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
    def try_updating(self) -> bool:
        return self._try_updating

    @try_updating.setter
    def try_updating(self, value: bool) -> None:
        self._try_updating = value
        self._validate_install_path()

    @property
    def is_reinstall_available(self) -> bool:
        return self._reinstall_available

    @property
    def try_reinstalling(self) -> bool:
        return self._try_reinstalling

    @try_reinstalling.setter
    def try_reinstalling(self, value: bool) -> None:
        self._try_reinstalling = value
        self._validate_install_path()

    @property
    def is_reregister_available(self) -> bool:
        return self._reregister_available

    @property
    def try_reregistering(self) -> bool:
        return self._try_reregistering

    @try_reregistering.setter
    def try_reregistering(self, value: bool) -> None:
        self._try_reregistering = value
        self._validate_install_path()

    @property
    def status_description(self) -> str:
        # Return the status description containing the current operation name
        description = INSTALLER_OPERATION_DESCRIPTIONS.get(self.status, None)
        if description is None:
            raise AttributeError("Provided Status does not have a description!")
        return description.replace("_ACTION_", self._operation.value)

    @property
    def is_ready(self) -> bool:
        return self._status == InstallerStatus.READY

    @property
    def can_installer_proceed(self) -> bool:
        return self._status == InstallerStatus.READY or self._status == InstallerStatus.NOT_READY

    @property
    def install_path(self) -> str:
        return self._install_path

    @install_path.setter
    def install_path(self, new_install_path: str) -> None:
        """Sets the install/uninstall path, checks for errors and warnings and updates the status.

        Always set the install/uninstall path using this method.
        """
        logger.info(f"Changing Install Path to: '{new_install_path}'")
        self._install_path = new_install_path
        self._validate_install_path()

    def _validate_install_path(self) -> None:
        """Checks the current install path for errors and warnings and updates the status."""
        self._warning_messages.clear()
        self._update_available = False
        self._reinstall_available = False
        self._reregister_available = False
        free_space = 0
        closest_existing_directory: typing.Optional[str] = (
            polib.utils_bpy.get_first_existing_ancestor_directory(
                self._install_path, whitelist={DEFAULT_PACK_INSTALL_PATH}
            )
        )
        if closest_existing_directory is not None:
            free_space = shutil.disk_usage(closest_existing_directory).free
        self._free_space = free_space

        # We don't need this during uninstallation
        if (
            self._operation == InstallerOperation.INSTALL
            or self._operation == InstallerOperation.UPDATE
        ):

            if closest_existing_directory is None:
                self.record_warning_message("Install Path is not valid!")
            elif free_space < self._pack_size:
                self.record_warning_message("Not enough Disk Space!")

        # We only need this during installation
        if self._operation == InstallerOperation.INSTALL:
            assert self._loaded_asset_pack is not None
            pack_destination = os.path.join(self._install_path, self.pack_root_directory)
            already_exists = os.path.exists(pack_destination)
            already_installed_pack = asset_registry.instance.get_pack_by_full_name(self.full_name)
            if already_installed_pack is not None:
                if self._loaded_asset_pack.version > already_installed_pack.version:
                    self._update_available = True
                    self._uninstall_pack_info_path = already_installed_pack.pack_info_path
                    if not self._try_updating:
                        self.record_warning_message(
                            "A lower version of this Asset Pack is already installed. Try updating it."
                        )
                elif already_installed_pack.version > self._loaded_asset_pack.version:
                    # This cannot be resolved
                    self.record_error_message(
                        "Higher version of this Asset Pack is already installed."
                    )
                else:
                    # This cannot be resolved
                    self.record_error_message("This Asset Pack is already installed.")
            elif already_exists and self._operation == InstallerOperation.INSTALL:
                # The pack might be loaded from an extracted pack within the install directory
                if os.path.abspath(
                    os.path.join(pack_destination, self.pack_info_basename)
                ) == os.path.abspath(self._pack_info_path):
                    self._reregister_available = True
                    if not self._try_reregistering:
                        self.record_warning_message(
                            "Install Path already contains an unregistered copy of this Asset Pack. Try re-registering it."
                        )
                else:
                    # The pack is not loaded from an extracted pack within the install directory
                    # We need full re-installation
                    self._reinstall_available = True
                    if not self._try_reinstalling:
                        self.record_warning_message(
                            "Install Path already contains the same version of this Asset Pack. Try re-installing it."
                        )

            # Disable 'try_operation' if the operation is not available
            if not self._update_available:
                self._try_updating = False
            if not self._reinstall_available:
                self._try_reinstalling = False
            if not self._reregister_available:
                self._try_reregistering = False

        if self.error_messages_present:
            self.abort_operation()
        elif self.warning_messages_present:
            self.status = InstallerStatus.NOT_READY
        else:
            # Everything succeeded, we are ready to proceed with the operation
            self.status = InstallerStatus.READY
        return

    def abort_operation(self) -> None:
        self.status = InstallerStatus.ABORTED
        for message in self._warning_messages:
            self.record_error_message(message)
        self._warning_messages.clear()

    def cancel_installer_operation(self) -> None:
        self._warning_messages.clear()
        self._error_messages.clear()
        self.status = InstallerStatus.CANCELED

    def exit_installer_operation(self) -> None:
        self._warning_messages.clear()
        self._error_messages.clear()
        self.status = InstallerStatus.EXIT

    def get_installer_status_description(self) -> str:
        """Return the status description containing the current operation name."""

        return self._status.value.replace("_ACTION_", self._operation.value)

    def record_warning_message(self, warning_message: str) -> None:
        """Record issues that are not critical to the operation.

        Resolving them should let the operation proceed.
        """

        self._warning_messages.append(warning_message)
        logger.warning(warning_message)

    def record_error_message(self, error_message: str) -> None:
        """Record issues that are critical to the operation.

        These cannot be resolved and the operation should be aborted.
        """

        self._error_messages.append(error_message)
        logger.error(error_message)

    def load_installation(self, filepath: str) -> None:
        self._load_installer(InstallerOperation.INSTALL, filepath)

    def load_uninstallation(self, filepath: str) -> None:
        self._load_installer(InstallerOperation.UNINSTALL, filepath)

    def load_update(self, filepath: str, update_filepath: str) -> None:
        self._load_installer(InstallerOperation.UPDATE, filepath, update_file_path=update_filepath)

    def get_paq_file_sources(self, file_path: str) -> typing.Optional[typing.List[str]]:
        """Returns all file sources needed to open a paq archive, or None if encountering an error.

        The input can either be:
        'paq' - indicating one file archive - we return the filepath
        'paq.001' - indicating multipart archive - we return all parts of the multipart archive in a ordered list
        anything else - we return an empty list - this is for cases when the pack is being installed
        from an extracted folder, so we can still continue to look for a .pack-info file in it

        NOTE: Other parts of archive aren't considered as a valid input as we allow selecting only the
        first part ('paq.001') of the multipart archive in the blender file browser.
        """

        if file_path.endswith(".paq"):
            logger.info(f"Loading from a single source file. Found source file: '{file_path}'")
            return [file_path]

        if file_path.endswith(".paq.001"):
            file_sources: typing.List[str] = []
            no_suffix = file_path[:-4]
            # find all paq.xxx files
            file_sources.extend(glob.glob(f"{no_suffix}.[0-9][0-9][1-9]"))
            file_sources.sort()
            assert no_suffix not in file_sources
            logger.info(f"Loading from multiple source parts. Found source files: {file_sources}")
            for i, paq_part in enumerate(file_sources):
                # index 0 should contain paq.001, index 1 should contain paq.002, ...
                expected_file_path = f"{no_suffix}.{(i + 1):03}"
                if paq_part != expected_file_path:
                    self.record_error_message(
                        f"Couldn't find all parts of '.paq' file. Part '{os.path.basename(expected_file_path)}' "
                        f"is missing!"
                    )
                    self.abort_operation()
                    return None
            return file_sources

        return []

    def _get_asset_pack_and_size_from_filepath(
        self, file_path: str
    ) -> typing.Tuple[typing.Optional[asset_registry.AssetPack], int, str]:
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
                        pack_info_files = [
                            name for name in archive.namelist() if name.endswith(".pack-info")
                        ]
                        if not self._check_only_one_info_file(pack_info_files):
                            return NO_RESULT
                        assert len(pack_info_files) == 1
                        pack_info_file = pack_info_files[0]
                        pack_size = sum(file_info.file_size for file_info in archive.filelist)
                        asset_pack = asset_registry.AssetPack.load_from_paq_file(
                            archive, pack_info_file
                        )
            else:
                pack_info_files = self._get_pack_info_files_from_ancestor_directory(pack_filepath)
                if not self._check_only_one_info_file(pack_info_files):
                    return NO_RESULT
                assert len(pack_info_files) == 1
                pack_info_file = pack_info_files[0]
                root_directory = os.path.dirname(pack_info_file)
                pack_size = sum(f.stat().st_size for f in pathlib.Path(root_directory).rglob('*'))
                asset_pack = asset_registry.AssetPack.load_from_json(pack_info_file)
                # We might need to update the filepath because we found the pack-info file in an
                # ancestor directory.
                pack_filepath = root_directory

        except zipfile.BadZipFile as e:
            self.record_error_message(".paq file is corrupted.")
        except (ValueError, PermissionError, OSError) as e:
            self.record_error_message(str(e))

        if asset_pack is None or self.error_messages_present:
            self.abort_operation()
            return NO_RESULT

        return asset_pack, pack_size, pack_filepath

    def _check_only_one_info_file(self, pack_info_files: typing.List[str]) -> bool:
        pack_info_files_count = len(pack_info_files)
        if pack_info_files_count != 1:
            self.status = InstallerStatus.NOT_FOUND
            if pack_info_files_count > 1:
                self.record_error_message("Selected folder contains more than one .pack-info file.")
            else:
                self.record_error_message("No .pack-info file was found.")
            return False
        return True

    def _clear_installer(self) -> None:
        self._operation = InstallerOperation.INSTALL
        self._status = InstallerStatus.NOT_READY
        self._warning_messages.clear()
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
        self._try_updating = False
        self._reinstall_available = False
        self._try_reinstalling = False
        self._reregister_available = False
        self._try_reregistering = False

    def _load_installer(
        self,
        operation: InstallerOperation,
        file_path: str,
        update_file_path: typing.Optional[str] = None,
    ) -> None:
        self._clear_installer()
        self._operation = operation

        pack: typing.Optional[asset_registry.AssetPack] = None
        pack_size: int = 0
        update_pack: typing.Optional[asset_registry.AssetPack] = None
        update_pack_size: int = 0
        uninstall_pack: typing.Optional[asset_registry.AssetPack] = None

        logger.info(f"Loading Asset Pack from '{file_path}'")
        pack, pack_size, file_path = self._get_asset_pack_and_size_from_filepath(file_path)

        # No info means something went wrong with loading the Asset Pack
        if pack is None:
            return

        if self._operation == InstallerOperation.UPDATE:
            assert update_file_path is not None
            logger.info(f"Loading Update Asset Pack from '{file_path}'")
            update_pack, update_pack_size, update_file_path = (
                self._get_asset_pack_and_size_from_filepath(update_file_path)
            )

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
            self.abort_operation()
            return

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
            self.install_path = self.uninstall_path
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
        """Successful update returns a tuple of the old and new .pack-info path of the updated Asset Pack."""

        old_pack_info_path = self.execute_uninstallation()
        new_pack_info_path = self.execute_installation()

        if old_pack_info_path is not None and new_pack_info_path is not None:
            return (old_pack_info_path, new_pack_info_path)
        return None

    def execute_installation(self) -> typing.Optional[str]:
        """Successful installation returns the .pack-info path of the installed Asset Pack."""

        def install_from_paq_file(
            path_or_reader: str | polib.split_file_reader.SplitFileReader,
        ) -> None:
            with zipfile.ZipFile(path_or_reader, "r") as archive:
                logger.info(f"Extracting to '{self._install_path}'")
                archive.extractall(path=self._install_path)
                self.status = InstallerStatus.FINISHED

        if self._status != InstallerStatus.READY:
            self.abort_operation()
            return None

        try:
            if self._try_reregistering:
                logger.info(f"Re-register enabled. No installation needed.")
                self.status = InstallerStatus.FINISHED
                return os.path.join(
                    self._install_path, self.pack_root_directory, self.pack_info_basename
                )

            logger.info(f"Executing installation to '{self._install_path}'")
            destination = os.path.join(self.install_path, self.pack_root_directory)
            if os.path.exists(destination):
                if self.try_reinstalling:
                    logger.info(f"Re-install enabled. Deleting '{destination}'")
                    shutil.rmtree(destination)
                else:
                    self.record_error_message("Install Path already contains this Asset Pack.")
                    self.abort_operation()
                    return None

            paq_sources = self.get_paq_file_sources(self.pack_filepath)
            if len(paq_sources) == 1:
                install_from_paq_file(paq_sources[0])
            elif len(paq_sources) > 1:
                # Only use the reader for multi-part paq files
                # Using it on single-part files adds a lot of unnecessary overhead
                with polib.split_file_reader.SplitFileReader(paq_sources) as reader:
                    install_from_paq_file(reader)
            elif os.path.isdir(self.pack_filepath):
                logger.info(f"Copying to '{self._install_path}'")
                shutil.copytree(self.pack_filepath, destination)
                self.status = InstallerStatus.FINISHED
            else:
                self.record_error_message("Path does not point to a Folder or a PAQ file")
                self.abort_operation()

            if self._status == InstallerStatus.FINISHED:
                return os.path.join(
                    self._install_path, self.pack_root_directory, self.pack_info_basename
                )

        except (
            zipfile.BadZipFile,
            shutil.Error,
            PermissionError,
            ValueError,
            RuntimeError,
            OSError,
        ) as e:
            self.record_error_message(str(e))
            self.abort_operation()

        return None

    def execute_uninstallation(self) -> typing.Optional[str]:
        """Successful uninstallation returns the .pack-info path of the uninstalled Asset Pack."""

        if self._status != InstallerStatus.READY:
            self.abort_operation()
            return None
        # Checks for not allowing deletion of internal Asset Packs
        if "G:/Shared drives/Builds" in polib.utils_bpy.normalize_path(
            self.uninstall_path
        ) or "execroot/_main" in polib.utils_bpy.normalize_path(
            os.path.realpath(self.uninstall_path)
        ):
            self.record_error_message("Cannot uninstall internal polygoniq Asset Pack!")
            self.abort_operation()
            return None

        logger.info(f"Deleting '{self.uninstall_path}'")
        try:
            if not os.path.isdir(self.uninstall_path):
                self.record_error_message("Path does not point to a Folder.")
                self.abort_operation()
                return None
            shutil.rmtree(self.uninstall_path)
            if self._operation == InstallerOperation.UPDATE:
                self.status = InstallerStatus.READY
            else:
                self.status = InstallerStatus.FINISHED
            return self.uninstall_pack_info_path

        except (shutil.Error, PermissionError, OSError) as e:
            self.record_error_message(str(e))
            self.abort_operation()

        return None

    def _get_direct_child_pack_info_files(self, parent_dir: str) -> typing.List[str]:
        if not os.path.exists(parent_dir):
            return []
        elif os.path.isfile(parent_dir):
            parent_dir = os.path.dirname(parent_dir)
        return [
            os.path.join(parent_dir, name)
            for name in os.listdir(parent_dir)
            if name.endswith(".pack-info")
        ]

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
    """Mixin for providing methods for Asset Pack Installation related operator dialogs.

    This class is used by Instal/Uninstall/Update Asset Pack operators in preferences.
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
        name="Cancel Installer Operation", default=False, update=_update_cancel_installer_operation
    )

    # Used during Installation and Update
    # Should contain the path without the Asset Pack's root folder
    install_path: bpy.props.StringProperty(
        name="Install Path",
        description="Select Asset Pack Install Path",
        set=_set_install_path,
        get=_get_install_path,
    )

    # Used for passing to operators when offering to switch operation
    filepath: bpy.props.StringProperty(options={'HIDDEN'})

    close: bpy.props.BoolProperty(options={'HIDDEN'})

    def draw_status_and_messages(self, layout: bpy.types.UILayout) -> None:
        description = instance.status_description
        layout.box().label(text=description, icon='INFO')

        for warning_message in instance.warning_messages:
            box = layout.box()
            box.alert = True
            box.label(text=warning_message, icon='ERROR')

        for error_message in instance.error_messages:
            box = layout.box()
            box.alert = True
            box.label(text=error_message, icon='CANCEL')

    def draw_pack_info(
        self, layout: bpy.types.UILayout, header: str = "", show_install_path=False
    ) -> None:
        col = layout.column(align=True)

        if header != "":
            col.box().label(text=header, icon='INFO')

        row = col.box().row(align=True)
        label_col = row.column(align=True)
        label_col.alignment = 'LEFT'
        row.separator(factor=2.0)
        value_col = row.column(align=True)
        value_col.alignment = 'LEFT'

        label_col.label(text="Name:")
        value_col.label(text=instance.full_name)
        label_col.label(text="Version:")
        value_col.label(text=instance.version)
        label_col.label(text="Vendor:")
        value_col.label(text=instance.vendor)
        if show_install_path:
            label_col.label(text="Install Path:")
            value_col.label(text=instance.install_path)

    def draw_installer_info(self, layout: bpy.types.UILayout) -> None:
        row = layout.row(align=True)
        label_col = row.column(align=True)
        label_col.alignment = 'LEFT'
        row.separator(factor=2.0)
        value_col = row.column(align=True)
        value_col.alignment = 'LEFT'

        label_col.label(text=f"Pack Folder Name:")
        value_col.label(text=instance.pack_root_directory)
        if instance._operation == InstallerOperation.UNINSTALL:
            label_col.label(text=f"Estimated Freed Disk Space:")
            value_col.label(text=instance.pack_size)
        else:
            if instance._operation == InstallerOperation.UPDATE:
                label_col.label(text=f"Estimated Extra Space Required:")
                value_col.label(text=instance.pack_size)
            else:
                label_col.label(text=f"Estimated Pack Size:")
                value_col.label(text=instance.pack_size)
            label_col.label(text=f"Free Disk Space:")
            value_col.label(text=instance.free_space)

    def check_should_dialog_close(self) -> bool:
        return not instance.can_installer_proceed

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        polib.ui_bpy.center_mouse(context)
        # When the dialog is supposed to close, we don't want to show the OK and Cancel buttons
        if self.check_should_dialog_close():
            return context.window_manager.invoke_popup(self, width=550)
        return context.window_manager.invoke_props_dialog(self, width=550)

    # Since Blender 4.1.0 there is a cancel button in the dialog window
    # This method is called when the cancel button is clicked
    # This method is also called when user clicks outside of the operator dialog window
    def cancel(self, context: bpy.types.Context):
        instance.exit_installer_operation()
