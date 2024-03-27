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

import polib
import mapr
from .. import asset_registry

preview_manager = polib.preview_manager_bpy.PreviewManager()


def update_all_known_asset_preview_paths() -> None:
    """Populates the 'manager_instance' with paths that lead to individual previews.

    Asset ID is used as an ID for the preview.
    """
    preview_manager.clear()
    asset_provider = asset_registry.instance.master_asset_provider
    file_provider = asset_registry.instance.master_file_provider
    for asset in asset_provider.list_assets(mapr.category.DEFAULT_ROOT_CATEGORY.id_, recursive=True):
        full_path = file_provider.materialize_file(asset.preview_file)
        if full_path:
            preview_manager.add_preview_path(full_path, id_override=asset.id_)


# Clear the preview collection when the AssetRegistry refreshes, we can no longer be sure
# whether the previews are right, or not
if update_all_known_asset_preview_paths not in asset_registry.instance.on_refresh:
    asset_registry.instance.on_refresh.append(update_all_known_asset_preview_paths)
