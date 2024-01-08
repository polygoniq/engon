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
import bpy.utils.previews
import os
import logging
import typing
import mapr
import threading
from .. import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")

# TODO: Unify with IconManager, only instance one class on the call sites


class PreviewManager:
    def __init__(self):
        # The bpy.utils.previews provides most of caching functionality that we need
        self.preview_collection = bpy.utils.previews.new()
        self.lock = threading.Lock()

    def __del__(self):
        self.preview_collection.clear()

    def load_preview(self, full_path: str, id_: str) -> None:
        """Loads previews from 'full_path' and saves on key 'id_'

        Assumes 'full_path' is already existing file in the filesystem.
        """

        with self.lock:
            if id_ in self.preview_collection:
                return

            assert os.path.isfile(full_path)
            try:
                self.preview_collection.load(id_, full_path, 'IMAGE', True)
            except KeyError as e:
                logger.exception(f"Preview {id_} already loaded!")

    def get_preview(self, id_: str) -> int:
        """Return icon_id for preview with id 'id_'

        Returns questionmark icon id if 'id_' is not found.
        """
        if id_ in self.preview_collection:
            return self.preview_collection[id_].icon_id

        # Unknown preview ID
        return 1

    def clear_ids(self, ids: typing.Set[str]) -> None:
        """Clears all previews (if present) based on the id in 'ids'"""
        for id_ in ids:
            if id_ in self.preview_collection:
                del self.preview_collection[id_]

    def clear(self):
        self.preview_collection.clear()

    def __contains__(self, id_: str) -> bool:
        return id_ in self.preview_collection

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: Loaded {len(self.preview_collection)} previews."


manager_instance = PreviewManager()


def ensure_loaded_previews(assets: typing.Iterable[mapr.asset.Asset]) -> None:
    """Ensures previews are loaded for assets listed on the current page"""
    master_file_provider = asset_registry.instance.master_file_provider
    loaded_previews = 0
    for asset in assets:
        file_id = asset.preview_file
        if file_id is None:
            logger.error(f"file_id is None for '{asset.title}'")
            continue

        # Don't materialize and reload the file if the preview file is already present in the
        # preview manager.
        if asset.id_ in manager_instance:
            continue

        full_path = master_file_provider.materialize_file(file_id)
        if full_path is None:
            logger.error(f"Couldn't materialize preview for '{asset.title}' with '{file_id}'")
            continue

        manager_instance.load_preview(full_path, asset.id_)
        loaded_previews += 1

    logger.debug(f"Loaded previews: {loaded_previews}")


# Clear the preview collection when the AssetRegistry refreshes, we can no longer be sure
# whether the previews are right, or not
if manager_instance.clear not in asset_registry.instance.on_refresh:
    asset_registry.instance.on_refresh.append(manager_instance.clear)
