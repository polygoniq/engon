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
import logging
from . import filters
from . import previews
from . import utils
from .. import mapr
from .. import polib
from .. import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []

# Top secret path to the dev location
EXPECTED_DEV_PATH = os.path.realpath(os.path.expanduser("~/polygoniq/"))
IS_DEV = os.path.exists(os.path.join(EXPECTED_DEV_PATH, ".git"))


class MAPR_BrowserDeleteCache(bpy.types.Operator):
    bl_idname = "engon.dev_browser_delete_cache"
    bl_label = "Delete Cache"

    def execute(self, context: bpy.types.Context):
        filters.asset_repository.clear_cache()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserDeleteCache)


class MAPR_BrowserReconstructFilters(bpy.types.Operator):
    bl_idname = "engon.dev_browser_reconstruct_filters"
    bl_label = "Reconstruct Filters"

    def execute(self, context: bpy.types.Context):
        filters_ = filters.get_filters()
        filters_.clear_and_reconstruct()
        filters_.reenable()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReconstructFilters)


class MAPR_BrowserOpenAssetSourceBlend(bpy.types.Operator):
    bl_idname = "engon.dev_open_asset_source_blend"
    bl_label = "Open Asset Source Blend"
    bl_description = "Tries to figure out the development location of this asset and open it"

    asset_id: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return IS_DEV

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.label(text=f"Asset ID: {self.asset_id}")
        self.layout.label(text=f"Path: {self.asset_path}")

    def execute(self, context: bpy.types.Context):
        if getattr(self, "asset_path", None) is None:
            raise RuntimeError("asset_path is initialized in invoke, use INVOKE_DEFAULT!")

        polib.utils_bpy.fork_running_blender(self.asset_path)
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        assert IS_DEV is True

        self.asset_path = self._get_asset_dev_path()
        if self.asset_path is None:
            self.report({'ERROR'}, f"Development path not found for '{self.asset_id}'")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=800)

    def _get_asset_dev_path(self) -> typing.Optional[str]:
        asset_provider = asset_registry.instance.master_asset_provider
        asset = asset_provider.get_asset(self.asset_id)
        if asset is None:
            self.report({'ERROR'}, f"No asset found for '{self.asset_id}'")
            return None

        first_asset_data: typing.Optional[mapr.asset_data.AssetData] = None
        for asset_data_id in asset_provider.list_asset_data_ids(asset.id_):
            asset_data = asset_provider.get_asset_data(asset_data_id)
            if asset_data is not None:
                first_asset_data = asset_data
                break

        if first_asset_data is None:
            self.report({'ERROR'}, f"No asset data found for '{self.asset_id}'")
            return None

        assert first_asset_data is not None

        file_provider = asset_registry.instance.master_file_provider
        path = file_provider.materialize_file(first_asset_data.primary_blend_file)
        # Construct the pack_name from the primary_blend_file FileID - the pack name is the
        # first token of the FileID before ":" without the leading slash.
        pack_name = first_asset_data.primary_blend_file.split(":", 1)[0].removeprefix("/")
        candidate_path = os.path.join(
            EXPECTED_DEV_PATH,
            "blender_asset_packs",
            pack_name,
            f"{pack_name}_asset_pack",
            path[path.find("blends") :],
        )
        if os.path.isfile(candidate_path):
            return candidate_path

        self.report({'WARNING'}, f"Tried '{candidate_path}', but it doesn't belong to a file :(")
        return None


MODULE_CLASSES.append(MAPR_BrowserOpenAssetSourceBlend)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
