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
import os
import typing
import collections
import json
import zipfile
import logging
import mapr
import polib
import functools
logger = logging.getLogger(f"polygoniq.{__name__}")


class AssetPack:
    @staticmethod
    def from_json_dict(pack_info_path: str, json_dict: typing.Dict[typing.Any, typing.Any], fake_pack: bool = False) -> 'AssetPack':
        """Parses pack info from 'json_dict' and constructs AssetPack from it.

        fake_pack: True if pack is constructed without unzipping all its files on disc, AssetPack
        constructed like this is not meant to be installed. Fake pack might not have all fields
        fully initialized as not all source files are available. We use it e.g. when installing new
        pack to engon, fake AssetPack is constructed just from .pack_info file to show some
        statistics to users.
        """
        # TODO: more safety in the parser
        full_name = json_dict.get("full_name", None)
        if full_name is None:
            raise ValueError("Given json dict does not contain a required key 'full_name'!")
        if not isinstance(full_name, str):
            raise ValueError(
                f"Given json dict contains full_name but its type is '{type(full_name)}' "
                f"instead of the expected 'str'!")
        version = json_dict.get("version", None)
        if version is None:
            raise ValueError("Given json dict does not contain a required key 'version'!")
        if not isinstance(version, list):
            raise ValueError(
                f"Given json dict contains version but its type is '{type(version)}' "
                f"instead of the expected 'list'!")
        vendor = json_dict.get("vendor", None)
        if vendor is None:
            raise ValueError("Given json dict does not contain a required key 'vendor'!")
        if not isinstance(vendor, str):
            raise ValueError(
                f"Given json dict contains vendor but its type is '{type(vendor)}' "
                f"instead of the expected 'str'!")
        engon_features = json_dict.get("engon_features", [])
        pack_info_path = os.path.realpath(os.path.abspath(pack_info_path))
        pack_info_parent_path = os.path.dirname(pack_info_path)
        install_path = os.path.realpath(os.path.abspath(pack_info_parent_path))
        # we don't do any absolutization or anything else because these should all be relative
        # to install path
        index_paths = json_dict.get("index_paths", [])
        if not isinstance(index_paths, list):
            raise ValueError(
                f"Given json dict contains index_paths but its type is '{type(index_paths)}' "
                f"instead of the expected 'list'!")
        file_id_prefix = json_dict.get("file_id_prefix", None)
        if file_id_prefix is None:
            raise ValueError("Given json dict does not contain a required key 'file_id_prefix'!")
        if not isinstance(file_id_prefix, str):
            raise ValueError(
                f"Given json dict contains file_id_prefix but its type is '{type(file_id_prefix)}' "
                f"instead of the expected 'str'!")
        pack_icon = json_dict.get("pack_icon", None)
        if not (pack_icon is None or isinstance(pack_icon, str)):
            raise ValueError(
                f"Given json dict contains pack_icon but its type is '{type(pack_icon)}' "
                f"instead of the expected 'None' or 'str'!")
        vendor_icon = json_dict.get("vendor_icon", None)
        if not (vendor_icon is None or isinstance(vendor_icon, str)):
            raise ValueError(
                f"Given json dict contains vendor_icon but its type is '{type(vendor_icon)}' "
                f"instead of the expected 'None' or 'str'!")

        # Don't load icons if we're constructing fake pack without all source data
        if fake_pack:
            pack_icon = None
            vendor_icon = None

        return AssetPack(
            full_name,
            typing.cast(typing.Tuple[int, int, int], tuple(version)),
            vendor,
            engon_features,
            install_path,
            pack_info_path,
            index_paths,
            file_id_prefix,
            pack_icon,
            vendor_icon
        )

    @staticmethod
    def load_from_json(pack_info_path: str) -> 'AssetPack':
        with open(pack_info_path) as f:
            json_dict = json.load(f)
            return AssetPack.from_json_dict(pack_info_path, json_dict)

    @staticmethod
    def load_from_paq_file(paq_file: zipfile.ZipFile, pack_info_path: str) -> 'AssetPack':
        with paq_file.open(pack_info_path) as f:
            json_dict = json.load(f)
            output = AssetPack.from_json_dict(pack_info_path, json_dict, fake_pack=True)
            return output

    def __init__(
        self,
        full_name: str,
        version: typing.Tuple[int, int, int],
        vendor: str,
        engon_features: typing.List[str],
        install_path: str,
        pack_info_path: str,
        index_paths: typing.List[str],
        file_id_prefix: str,
        pack_icon_path: typing.Optional[str],
        vendor_icon_path: typing.Optional[str]
    ):
        # Each asset pack has a unique full name, we guarantee at most one asset pack registered
        # with that name. If there are multiple versions available the user should register the
        # newest one.
        self.full_name = full_name
        # Semantic version of the asset pack
        self.version = version
        # Who is the author of the asset pack
        self.vendor = vendor
        # Which engon set of features should be enable when this asset pack is present. For
        # example the core botaniq assets open the botaniq features - scatter, wind animation, etc.
        # The same features are also opened by the Evermotion asset packs.
        # TODO: For now we support only one engon_feature but this is an artificial limitation of
        #       the API.
        if len(engon_features) > 1:
            raise NotImplementedError(
                "For now we only support one engon_feature per asset pack!")
        if len(engon_features) == 0:
            raise NotImplementedError("At least one engon feature required in each asset pack!")
        self.engon_feature = engon_features[0]
        self.install_path = install_path
        self.pack_info_path = pack_info_path
        self.index_paths = index_paths
        self.file_id_prefix = file_id_prefix

        # Initialize PreviewManager for icons
        self.pack_icon: typing.Optional[str] = None
        self.vendor_icon: typing.Optional[str] = None
        valid_icon_paths: typing.List[str] = []

        for icon_path, icon_prop_name in zip((pack_icon_path, vendor_icon_path), ("pack_icon", "vendor_icon")):
            if icon_path is not None:
                setattr(self, icon_prop_name, os.path.splitext(os.path.basename(icon_path))[0])
                icon_fullpath = os.path.join(install_path, icon_path)
                if not os.path.isfile(icon_fullpath):
                    raise RuntimeError(
                        f"Asset pack icon '{icon_path}' not found on path '{icon_fullpath}'!")
                valid_icon_paths.append(icon_fullpath)

        self.icon_manager = polib.preview_manager_bpy.PreviewManager()
        for path in valid_icon_paths:
            self.icon_manager.add_preview_path(path)

        # we remember which providers we registered to MAPR to be able to unregister them
        self.asset_providers: typing.List[mapr.asset_provider.AssetProvider] = []
        self.asset_multiplexer: typing.Optional[mapr.asset_provider.AssetProviderMultiplexer] = None
        self.file_providers: typing.List[mapr.asset_provider.FileProvider] = []

        # we remember which blender asset library entry we added
        self.blender_asset_library_entry: typing.Optional[bpy.types.UserAssetLibrary] = None

    def check_pack_validity(self) -> None:
        """Checks whether the provided Asset Pack is valid, throwing Exceptions if not"""

        # Install path is a valid filesystem path where all .blends, textures and other files are
        # located. This is what Find Missing Files operator will use to locate files.
        if not os.path.isabs(self.install_path):
            raise ValueError(
                f"Given install_path {self.install_path} is not an absolute path!")
        if not os.path.isdir(self.install_path):
            raise ValueError(
                f"Given install_path {self.install_path} is not a valid directory!")

        # Paths to MAPR index JSONs, this will be used by browser to browse this asset pack.
        # These paths should be relative to self.install_path
        for index_path in self.index_paths:
            if os.path.isabs(index_path):
                raise ValueError(
                    f"One of the index paths {index_path} is not a path relative to the "
                    f"install_path {self.install_path}. Please don't use absolute index paths for "
                    f"AssetPacks!")

    def get_filepath_from_basename(self, basename: str) -> typing.Optional[str]:
        for provider in self.file_providers:
            file_id = provider.get_file_id_from_basename(basename)
            if file_id is None:
                continue
            filepath = provider.materialize_file(file_id)
            if filepath is not None:
                return filepath
        return None

    def get_version_str(self) -> str:
        return ".".join(map(str, self.version))

    def get_pack_icon_id(self) -> typing.Optional[int]:
        return None if self.pack_icon is None else self.icon_manager.get_icon_id(self.pack_icon)

    def get_vendor_icon_id(self) -> typing.Optional[int]:
        return None if self.vendor_icon is None else self.icon_manager.get_icon_id(self.vendor_icon)

    @functools.cached_property
    def main_category_id(
        self,
    ) -> typing.Optional[mapr.category.CategoryID]:
        if self.asset_multiplexer is None:
            return None

        main_category_id = self.asset_multiplexer.get_root_category_id()

        all_child_of_root_asset_pack_categories: typing.Set[mapr.category.Category] = set()
        for category in self.asset_multiplexer.list_child_category_ids(main_category_id):
            all_child_of_root_asset_pack_categories.add(category)

        if len(all_child_of_root_asset_pack_categories) == 1:
            main_category_id = all_child_of_root_asset_pack_categories.pop()
        else:
            logger.error(f"We expect the pack {self.full_name} to have 1 child-of-root category, "
                         f"but {len(all_child_of_root_asset_pack_categories)} were found. "
                         f"Defaulting to root category '{main_category_id}'.")

        return main_category_id

    def _register_in_mapr(
        self,
        master_asset_provider: mapr.asset_provider.AssetProviderMultiplexer,
        master_file_provider: mapr.file_provider.FileProviderMultiplexer
    ) -> None:
        assert len(self.asset_providers) == 0
        assert len(self.file_providers) == 0

        asset_multiplexer = mapr.asset_provider.AssetProviderMultiplexer()
        file_multiplexer = mapr.file_provider.FileProviderMultiplexer()
        success = False
        for index_path in self.index_paths:
            if not os.path.isabs(index_path):
                index_path = os.path.realpath(
                    os.path.abspath(os.path.join(self.install_path, index_path)))

            if not os.path.isfile(index_path):
                logger.error(f"Index path is not a valid file {index_path}, skipping...")
                continue

            provider = mapr.local_json_provider.LocalJSONProvider(
                index_path,
                self.install_path,
                self.file_id_prefix
            )
            asset_multiplexer.add_asset_provider(provider)
            file_multiplexer.add_file_provider(provider)
            success = True

        if success:
            master_asset_provider.add_asset_provider(asset_multiplexer)
            master_file_provider.add_file_provider(file_multiplexer)
            self.asset_providers.append(asset_multiplexer)
            self.asset_multiplexer = asset_multiplexer
            self.file_providers.append(file_multiplexer)

    def _unregister_from_mapr(
        self,
        master_asset_provider: mapr.asset_provider.AssetProviderMultiplexer,
        master_file_provider: mapr.file_provider.FileProviderMultiplexer
    ) -> None:
        for asset_provider in self.asset_providers:
            master_asset_provider.remove_asset_provider(asset_provider)
        self.asset_providers.clear()
        self.asset_multiplexer = None

        for file_provider in self.file_providers:
            master_file_provider.remove_file_provider(file_provider)
        self.file_providers.clear()

    def _register_blender_asset_library(self) -> None:
        assert self.blender_asset_library_entry is None

        preferences = bpy.context.preferences
        if hasattr(preferences.filepaths, "asset_libraries"):
            # We need to handle the case where this path has already been registered, we don't want
            # a double registration
            for asset_library in preferences.filepaths.asset_libraries:
                abs_library_path = os.path.realpath(os.path.abspath(bpy.path.abspath(
                    asset_library.path)))
                # If the same path or ancestor is already registered, we won't register again
                try:
                    if os.path.commonpath([abs_library_path, self.install_path]) == abs_library_path:
                        break
                except ValueError:
                    # commonpath raises ValueError if the two paths have a different drive
                    pass
            else:
                bpy.ops.preferences.asset_library_add()
                self.blender_asset_library_entry = preferences.filepaths.asset_libraries[-1]
                self.blender_asset_library_entry.name = f"{self.full_name} (engon)"
                self.blender_asset_library_entry.path = self.install_path

    def _unregister_blender_asset_library(self) -> None:
        if self.blender_asset_library_entry is not None:
            preferences = bpy.context.preferences
            index = preferences.filepaths.asset_libraries.find(
                self.blender_asset_library_entry.name)
            if index < 0:
                logger.warning(
                    f"Wanted to unregister {self.full_name} from Blender asset libraries but the "
                    f"library entry is not present!"
                )
            else:
                bpy.ops.preferences.asset_library_remove(index=index)

            self.blender_asset_library_entry = None


class AssetRegistry:
    """Stores information about all asset packs registered into engon.

    The state of the registry is based on the pack-info packs provided and passed to
    refresh_packs_from_pack_info_paths.
    """

    def __init__(self):
        self._packs_by_full_name: typing.Dict[str, AssetPack] = {}
        self._packs_by_engon_feature: typing.DefaultDict[str, typing.List[AssetPack]] = \
            collections.defaultdict(list)
        self._packs_by_pack_info_path: typing.Dict[str, AssetPack] = {}
        self.master_asset_provider: mapr.asset_provider.AssetProvider = \
            mapr.asset_provider.CachedAssetProviderMultiplexer()
        self.master_file_provider: mapr.file_provider.FileProvider = \
            mapr.file_provider.FileProviderMultiplexer()
        self.on_refresh: typing.List[typing.Callable[[], None]] = []

    def get_pack_by_full_name(self, full_name: str) -> typing.Optional[AssetPack]:
        """Returns registered asset pack based on 'full_name' if present, None otherwise
        """
        return self._packs_by_full_name.get(full_name, None)

    def get_packs_by_engon_feature(self, engon_feature: str) -> typing.List[AssetPack]:
        """Returns registered addons with given 'addon_name'
        """
        return self._packs_by_engon_feature[engon_feature]

    def get_pack_by_pack_info_path(self, pack_info_path: str) -> typing.Optional[AssetPack]:
        """Returns registered asset pack based on 'pack_info_path' if present, None otherwise
        """
        return self._packs_by_pack_info_path.get(pack_info_path, None)

    def get_packs_paths(self) -> typing.Set[str]:
        return {p.install_path for p in self._packs_by_full_name.values()}

    def _register_pack(
        self,
        asset_pack: AssetPack
    ) -> None:
        """Registers an addon into the registry

        If addon information with the same 'full_name' is already present, an exception is raised.
        """

        asset_pack.check_pack_validity()
        previously_registered = self.get_pack_by_full_name(asset_pack.full_name)
        if previously_registered is not None:
            raise RuntimeError(f"Asset pack with name {asset_pack.full_name} already registered!")

        assert asset_pack.full_name not in self._packs_by_full_name
        self._packs_by_full_name[asset_pack.full_name] = asset_pack
        self._packs_by_engon_feature[asset_pack.engon_feature].append(asset_pack)
        assert asset_pack.pack_info_path not in self._packs_by_pack_info_path
        self._packs_by_pack_info_path[asset_pack.pack_info_path] = asset_pack

        asset_pack._register_in_mapr(self.master_asset_provider, self.master_file_provider)
        asset_pack._register_blender_asset_library()

    def _unregister_pack(
        self,
        asset_pack: AssetPack
    ) -> None:
        asset_pack._unregister_blender_asset_library()
        asset_pack._unregister_from_mapr(self.master_asset_provider, self.master_file_provider)

        del self._packs_by_full_name[asset_pack.full_name]
        self._packs_by_engon_feature[asset_pack.engon_feature].remove(asset_pack)
        del self._packs_by_pack_info_path[asset_pack.pack_info_path]

    def get_registered_packs(self) -> typing.Iterable[AssetPack]:
        return self._packs_by_full_name.values()

    def get_install_paths_by_engon_feature(self) -> typing.Dict[str, typing.List[str]]:
        """Returns a dictionary with engon features as keys and list of related packs as values"""
        output_dict: typing.Dict[str, typing.List[str]] = {}
        for feature, asset_packs in self._packs_by_engon_feature.items():
            output_dict[feature] = [pack.install_path for pack in asset_packs]
        return output_dict

    def register_pack_from_pack_info_path(self, pack_info_path: str, refresh_registry: bool = True) -> None:
        asset_pack = AssetPack.load_from_json(pack_info_path)
        logger.info(f"Registering asset pack '{asset_pack.full_name}' from '{pack_info_path}'")
        self._register_pack(asset_pack)
        if refresh_registry:
            self._registry_refreshed()

    def unregister_pack_from_pack_info_path(self, pack_info_path: str, refresh_registry: bool = True) -> None:
        asset_pack = self.get_pack_by_pack_info_path(pack_info_path)
        assert asset_pack is not None
        logger.info(f"Unregistering asset pack '{asset_pack.full_name}' from '{pack_info_path}'")
        self._unregister_pack(asset_pack)
        if refresh_registry:
            self._registry_refreshed()

    def refresh_packs_from_pack_info_paths(self, pack_info_files: typing.Iterable[str]) -> None:
        input_pack_info_files: typing.Set[str] = set(pack_info_files)
        logger.info(
            f"Refreshing registered asset packs from pack-info files: {input_pack_info_files}")

        existing_pack_info_paths = set(self._packs_by_pack_info_path.keys())
        # We assume the pack-info files themselves have not changed
        logger.info(
            f"Keeping {existing_pack_info_paths.intersection(input_pack_info_files)} as they are")
        pack_info_files_to_remove = existing_pack_info_paths - input_pack_info_files
        logger.info(f"Will unregister {pack_info_files_to_remove}")
        for pack_info_file in pack_info_files_to_remove:
            asset_pack = self.get_pack_by_pack_info_path(pack_info_file)
            assert asset_pack is not None
            self._unregister_pack(asset_pack)

        pack_info_files_to_add = input_pack_info_files - existing_pack_info_paths
        logger.info(f"Will newly register {pack_info_files_to_add}")
        for pack_info_file in pack_info_files_to_add:
            assert pack_info_file not in self._packs_by_pack_info_path
            try:
                asset_pack = AssetPack.load_from_json(pack_info_file)
                self._register_pack(asset_pack)
            except:
                logger.exception(
                    f"Tried to newly register '{pack_info_file}' but parsing or registration failed!")

        self._registry_refreshed()

    def _registry_refreshed(self) -> None:
        """Calls all 'on_refresh' callbacks to the registry.

        This should be called whenever the state of the registry changed - whenever other code
        cannot expect that the registry state is the same as before (clean caches, ...).
        """
        for func in self.on_refresh:
            func()


instance = AssetRegistry()


def reload_asset_pack_icons():
    for asset_pack in instance.get_registered_packs():
        asset_pack.icon_manager.clear()


instance.on_refresh.append(reload_asset_pack_icons)
