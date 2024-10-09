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
import typing
import logging

from .. import polib
from .. import mapr
from .. import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")

preview_manager = polib.preview_manager_bpy.PreviewManager(blocking_load=False)


def asset_registry_changed(
    asset_pack: asset_registry.AssetPack, change: asset_registry.AssetPackChange
) -> None:
    previews_id_to_full_path: typing.Dict[str, str] = {}
    asset_provider = asset_pack.asset_multiplexer
    file_provider = asset_pack.file_multiplexer
    for asset in asset_provider.list_assets(
        mapr.category.DEFAULT_ROOT_CATEGORY.id_, recursive=True
    ):
        full_path = file_provider.materialize_file(asset.preview_file)
        if full_path:
            previews_id_to_full_path[asset.id_] = full_path

    if change == asset_registry.AssetPackChange.REGISTERED:
        logger.debug(
            f"Adding {len(previews_id_to_full_path)} preview paths for {asset_pack.full_name}..."
        )
        for id_, full_path in previews_id_to_full_path.items():
            preview_manager.add_preview_path(full_path, id_override=id_)

    elif change == asset_registry.AssetPackChange.UNREGISTERED:
        logger.debug(
            f"Removing {len(previews_id_to_full_path)} preview paths for {asset_pack.full_name}..."
        )
        preview_manager.clear(previews_id_to_full_path.keys())

    else:
        raise ValueError(f"Unknown asset pack change: {change}")


if asset_registry_changed not in asset_registry.instance.on_changed:
    asset_registry.instance.on_changed.append(asset_registry_changed)
