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
import logging
from .. import mapr
from .. import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[typing.Any] = []


class BrowserAssetState(bpy.types.PropertyGroup):
    """Stores state of the browser per individual asset. The 'name' is the 'asset_id' key.

    With the 'asset_id' used as 'name' one can use .get on the collection property to find the
    state associatively.
    """

    name: bpy.props.StringProperty(
        name="Asset ID",
        description="Asset ID of the asset this state belongs to",
    )
    selected: bpy.props.BoolProperty(
        name="Selected",
        description="If true then the asset is selected in the browser",
    )


MODULE_CLASSES.append(BrowserAssetState)


class BrowserState(bpy.types.PropertyGroup):
    """Encapsulates runtime state of the browser like selected assets."""

    assets_state: bpy.props.CollectionProperty(type=BrowserAssetState)
    active_asset_id: bpy.props.StringProperty(
        name="Active Asset ID",
        description="ID of the currently active (last selected asset) asset in the browser",
    )

    def is_asset_selected(self, asset_id: mapr.asset.AssetID) -> bool:
        asset_state = self.assets_state.get(asset_id, None)
        if asset_state is None:
            return False

        return asset_state.selected

    def is_at_least_one_asset_selected(self) -> bool:
        return next(self.selected_asset_ids, None) is not None

    def is_at_least_one_asset_of_type_selected(
        self, asset_type: mapr.asset_data.AssetDataType
    ) -> bool:
        return next(filter(lambda x: x.type_ == asset_type, self.selected_assets), None) is not None

    def select_asset(self, asset_id: mapr.asset.AssetID, selected: bool) -> None:
        """Select or deselect an asset by its ID.

        This also sets the active asset ID to the given asset ID.
        """
        state = self._ensure_asset_state(asset_id)
        state.selected = selected
        self.active_asset_id = asset_id

    def select_asset_range(
        self,
        asset_ids: typing.Iterable[mapr.asset.AssetID],
        selected: bool,
    ) -> None:
        """Select or deselect a range of assets by their IDs.

        Note that this does not change the active asset ID.
        """
        for asset_id in asset_ids:
            state = self._ensure_asset_state(asset_id)
            state.selected = selected

    def reset_active_asset(self) -> None:
        self.active_asset_id = ""

    @property
    def selected_asset_ids(self) -> typing.Iterable[mapr.asset.AssetID]:
        return (asset_state.name for asset_state in self.assets_state if asset_state.selected)

    @property
    def selected_assets(self) -> typing.Iterable[mapr.asset.Asset]:
        asset_provider = asset_registry.instance.master_asset_provider
        for asset_id in self.selected_asset_ids:
            asset = asset_provider.get_asset(asset_id)
            if asset is not None:
                yield asset

    def _ensure_asset_state(self, asset_id: mapr.asset.AssetID) -> BrowserAssetState:
        existing_state = self.assets_state.get(asset_id, None)
        if existing_state is not None:
            return existing_state

        new_state = self.assets_state.add()
        new_state.name = asset_id
        return new_state


MODULE_CLASSES.append(BrowserState)


def get_browser_state(context: bpy.types.Context) -> BrowserState:
    return context.window_manager.pq_browser_state


def on_asset_pack_changed(
    asset_pack: asset_registry.AssetPack, change: asset_registry.AssetPackChange
) -> None:
    # When pack is unregistered, remove state for all assets that belonged the pack.
    if change == asset_registry.AssetPackChange.UNREGISTERED:
        assets_state = get_browser_state(bpy.context).assets_state
        # Remove all assets from the browser that belong to this asset pack
        for asset in asset_registry.instance.master_asset_provider.list_assets(
            asset_pack.main_category_id, True
        ):
            idx = assets_state.find(asset.id_)
            if idx != -1:
                assets_state.remove(idx)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.pq_browser_state = bpy.props.PointerProperty(type=BrowserState)

    asset_registry.instance.on_changed.append(on_asset_pack_changed)


def unregister():
    if on_asset_pack_changed in asset_registry.instance.on_changed:
        asset_registry.instance.on_changed.remove(on_asset_pack_changed)

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.WindowManager.pq_browser_state
