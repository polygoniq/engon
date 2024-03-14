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
import glob
import functools
import typing
import logging
from . import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


# ~/polygoniq_asset_packs
DEFAULT_PACK_INSTALL_PATH = os.path.expanduser(os.path.join("~", "polygoniq_asset_packs"))


class PackInfoSearchPathType:
    SINGLE_FILE = "single_file"
    INSTALL_DIRECTORY = "install_directory"
    RECURSIVE_SEARCH = "recursive_search"
    GLOB = "glob"


class PackInfoSearchPath(bpy.types.PropertyGroup):
    bl_idname = "engon.PackInfoSearchPath"

    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=True,
        description="If set to false this path will be entirely skipped"
    )

    path_type: bpy.props.EnumProperty(
        name="Type",
        items=(
            (PackInfoSearchPathType.INSTALL_DIRECTORY, "Install Directory",
             "Path to a directory containing Asset Pack folders. Only direct child folders are checked!", 'ANIM_DATA', 1
             ),
            (PackInfoSearchPathType.RECURSIVE_SEARCH, "Recursive Search",
             "Finds all Asset Packs inside the path's folder hierarchy", 'INFO', 2
             ),
            (PackInfoSearchPathType.SINGLE_FILE, "Single File",
             "Direct path to an Asset Pack's '.pack-info' file", 'DUPLICATE', 3
             ),
            (PackInfoSearchPathType.GLOB, "Glob Expression",
             "Glob for matching '.pack-info' files of Asset Packs. For power users only!", 'TRASH', 4
             ),
        ),
        default=PackInfoSearchPathType.INSTALL_DIRECTORY,
    )

    file_path: bpy.props.StringProperty(
        name="file path",
        subtype="FILE_PATH",
        default=os.path.join(DEFAULT_PACK_INSTALL_PATH, "botaniq", "botaniq_full.pack-info")
    )

    directory_path: bpy.props.StringProperty(
        name="directory path",
        subtype="DIR_PATH",
        default=DEFAULT_PACK_INSTALL_PATH
    )

    glob_expression: bpy.props.StringProperty(
        name="glob expression",
        default=os.path.join(DEFAULT_PACK_INSTALL_PATH, "*", "*.pack-info")
    )

    def as_dict(self) -> typing.Dict[str, str]:
        ret = {}
        ret["enabled"] = self.enabled
        ret["path_type"] = self.path_type
        ret["file_path"] = self.file_path
        ret["directory_path"] = self.directory_path
        ret["glob_expression"] = self.glob_expression

        return ret

    def load_from_dict(self, info_dict: typing.Dict[str, str]) -> None:
        enabled = info_dict.get("enabled", None)
        if enabled is None:
            raise ValueError("Given json dict does not contain a required key 'enabled'!")
        if not isinstance(enabled, bool):
            raise ValueError(
                f"Given json dict contains enabled but its type is '{type(enabled)}' "
                f"instead of the expected 'bool'!")
        self.enabled = enabled

        path_type = info_dict.get("path_type", None)
        if path_type is None:
            raise ValueError("Given json dict does not contain a required key 'path_type'!")
        if not isinstance(path_type, str):
            raise ValueError(
                f"Given json dict contains path_type but its type is '{type(path_type)}' "
                f"instead of the expected 'str'!")
        self.path_type = path_type

        file_path = info_dict.get("file_path", None)
        if file_path is None:
            raise ValueError("Given json dict does not contain a required key 'file_path'!")
        if not isinstance(file_path, str):
            raise ValueError(
                f"Given json dict contains file_path but its type is '{type(file_path)}' "
                f"instead of the expected 'str'!")
        self.file_path = file_path

        directory_path = info_dict.get("directory_path", None)
        if directory_path is None:
            raise ValueError("Given json dict does not contain a required key 'directory_path'!")
        if not isinstance(directory_path, str):
            raise ValueError(
                f"Given json dict contains directory_path but its type is '{type(directory_path)}' "
                f"instead of the expected 'str'!")
        self.directory_path = directory_path

        glob_expression = info_dict.get("glob_expression", None)
        if glob_expression is None:
            raise ValueError("Given json dict does not contain a required key 'glob_expression'!")
        if not isinstance(glob_expression, str):
            raise ValueError(
                f"Given json dict contains glob_expression but its type is '{type(glob_expression)}' "
                f"instead of the expected 'str'!")
        self.glob_expression = glob_expression

    def get_path_or_expression_by_type(self) -> str:
        if self.path_type == PackInfoSearchPathType.SINGLE_FILE:
            return self.file_path
        elif self.path_type == PackInfoSearchPathType.INSTALL_DIRECTORY:
            return self.directory_path
        elif self.path_type == PackInfoSearchPathType.RECURSIVE_SEARCH:
            return self.directory_path
        elif self.path_type == PackInfoSearchPathType.GLOB:
            return self.glob_expression
        else:
            raise ValueError(f"Unknown Pack Info Search Path Type {self.path_type}")

    def get_discovered_asset_packs(self) -> typing.List[asset_registry.AssetPack]:
        if not self.enabled:
            return []
        return PackInfoSearchPath._get_discovered_asset_packs(
            self.path_type, self.file_path, self.directory_path, self.glob_expression)

    @staticmethod
    def clear_discovered_packs_cache():
        PackInfoSearchPath._get_discovered_asset_packs.cache_clear()

    @staticmethod
    def _generate_glob(path_type: str, file_path: str, directory_path: str, glob_expression) -> str:
        if path_type == PackInfoSearchPathType.SINGLE_FILE:
            # the glob is just the file path
            return glob.escape(file_path)
        elif path_type == PackInfoSearchPathType.INSTALL_DIRECTORY:
            return os.path.join(glob.escape(directory_path), "*", "*.pack-info")
        elif path_type == PackInfoSearchPathType.RECURSIVE_SEARCH:
            return os.path.join(glob.escape(directory_path), "**", "*.pack-info")
        elif path_type == PackInfoSearchPathType.GLOB:
            return glob_expression
        else:
            raise ValueError(f"Unknown Pack Info Search Path Type {path_type}")

    @staticmethod
    @functools.lru_cache(maxsize=100)
    def _get_discovered_asset_packs(
        path_type: str,
        file_path: str,
        directory_path: str,
        glob_expression: str
    ) -> typing.List[asset_registry.AssetPack]:
        discovered_packs: typing.List[asset_registry.AssetPack] = []
        generated_glob = PackInfoSearchPath._generate_glob(
            path_type, file_path, directory_path, glob_expression)
        pack_info_files = glob.glob(generated_glob, recursive=True)
        for pack_info_file in pack_info_files:
            try:
                # Try to load an Asset Pack from the file
                loaded_pack = asset_registry.AssetPack.load_from_json(pack_info_file)
            except (NotImplementedError, ValueError):
                # An Asset Pack couldn't be loaded from the file
                continue
            discovered_packs.append(loaded_pack)
        return discovered_packs


MODULE_CLASSES.append(PackInfoSearchPath)


class ShowDiscoveredPacks(bpy.types.Operator):
    bl_idname = "engon.show_discovered_packs"
    bl_label = "Show Discovered Packs"
    bl_description = "Show Asset Packs Discovered in this Search Path"

    pack_info_search_path: bpy.props.PointerProperty(type=PackInfoSearchPath)

    def execute(self, context: bpy.types.Context):
        discovered_packs = self.pack_info_search_path.get_discovered_asset_packs()

        def _draw_discovered_packs(menu: bpy.types.UIPopupMenu, context: bpy.types.Context) -> None:
            if len(discovered_packs) == 0:
                return
            layout: bpy.types.UILayout = menu.layout
            col = layout.column(align=True)
            for index, pack in enumerate(discovered_packs):
                if index != 0:
                    col.label(text=20 * "-")
                col.label(text=f"Full Name: {pack.full_name}")
                col.label(text=f"Version: {pack.get_version_str()}")
                col.label(text=f"Vendor: {pack.vendor}")
                col.label(text=f"pack-info Path: {pack.pack_info_path}")

        if len(discovered_packs) == 0:
            context.window_manager.popup_menu(
                _draw_discovered_packs, title="No Asset Packs Found in the Search Path!", icon='INFO')
        else:
            context.window_manager.popup_menu(
                _draw_discovered_packs, title="Discovered Asset Packs", icon='INFO')
        return {'FINISHED'}


MODULE_CLASSES.append(ShowDiscoveredPacks)


class MY_UL_PackInfoSearchPathList(bpy.types.UIList):
    """UI list for managing pack-info search paths"""

    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout, data,
                  item: PackInfoSearchPath, icon, active_data, active_propname, index):

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            split = layout.split(factor=0.35, align=True)
            row = split.row(align=True)
            row.prop(item, "enabled", text="")
            row.prop(item, "path_type", text="")
            split = split.split(factor=0.75, align=True)
            if item.path_type == PackInfoSearchPathType.SINGLE_FILE:
                split.prop(item, "file_path", text="")
            elif item.path_type in {PackInfoSearchPathType.INSTALL_DIRECTORY, PackInfoSearchPathType.RECURSIVE_SEARCH}:
                split.prop(item, "directory_path", text="")
            elif item.path_type == PackInfoSearchPathType.GLOB:
                split.prop(item, "glob_expression", text="")
            else:
                raise ValueError(f"Unknown Pack Info Search Path Type {self.path_type}")
            row = split.row(align=True)
            if not item.enabled:
                return
            discovered_packs_count = len(item.get_discovered_asset_packs())
            label_text = "Pack"
            if discovered_packs_count != 1:
                label_text += "s"
            row.label(text=f"{str(discovered_packs_count)} {label_text}")
            op = row.operator(
                ShowDiscoveredPacks.bl_idname, icon='PRESET', text="")
            # We cannot assign the whole item into pack_info_search_path
            # because PointerProperty inside an Operator is read-only
            # We have to assign each property manually
            op.pack_info_search_path.enabled = item.enabled
            op.pack_info_search_path.path_type = item.path_type
            op.pack_info_search_path.file_path = item.file_path
            op.pack_info_search_path.directory_path = item.directory_path
            op.pack_info_search_path.glob_expression = item.glob_expression

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="")


MODULE_CLASSES.append(MY_UL_PackInfoSearchPathList)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
