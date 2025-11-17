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
import dataclasses
import os
import urllib.request
import urllib.error
import json
import threading
import functools
from . import polib
from . import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


WORK_FOLDER = os.path.join(
    polib.utils_bpy.get_user_data_resource_path("engon"), "available_asset_packs"
)
INDEX_FILENAME = "index.json"
INDEX_LOCAL_FILE_PATH = os.path.join(WORK_FOLDER, INDEX_FILENAME)
INDEX_REMOTE_URL = f"https://docs.polygoniq.com/api/v1/available_asset_packs/{INDEX_FILENAME}"


pack_thumbnail_icon_manager = polib.preview_manager_bpy.OnlinePreviewManager(
    os.path.join(WORK_FOLDER, "previews"), timeout=5.0
)
available_pack_refresh_lock = threading.Lock()


@dataclasses.dataclass
class AssetPackMarket:
    name: str
    url: str

    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> "AssetPackMarket":
        name = data.get("name", None)
        if name is None:
            raise ValueError("Asset pack market URL must have a 'name' field.")
        url = data.get("url", None)
        if url is None:
            raise ValueError("Asset pack market URL must have a 'url' field.")

        return cls(
            name=name,
            url=url,
        )

    def get_icon_id(self) -> int:
        return polib.ui_bpy.icon_manager.get_icon_id(f"logo_{self.name.lower()}")


@dataclasses.dataclass
class AvailableAssetPackMetadata:
    # id_ is a full name without a variant
    id_: str
    name: str
    version: tuple[int, int, int]
    vendor: str
    description: str
    icon_url: str | None
    # List of full_names of possible variants e. g. botaniq_full, botaniq_lite, ...
    variants: list[str]
    markets: list[AssetPackMarket]
    tags: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> "AvailableAssetPackMetadata":
        id_ = data.get("id", None)
        if id_ is None:
            raise ValueError("Asset pack metadata must have an 'id' field.")
        name = data.get("name", None)
        if name is None:
            raise ValueError("Asset pack metadata must have a 'name' field.")
        version = data.get("version", None)
        if version is None:
            raise ValueError("Asset pack metadata must have a 'version' field.")
        vendor = data.get("vendor", None)
        if vendor is None:
            raise ValueError("Asset pack metadata must have a 'vendor' field.")

        tags = []
        for tag in data.get("tags", []):
            # Skipping non string tag is not reason to raise an error, just ignore it
            if not isinstance(tag, str):
                continue

            tags.append(tag)

        markets = []
        for market_data in data.get("markets", []):
            if not isinstance(market_data, dict):
                raise ValueError("Asset pack market data must be a dictionary.")
            markets.append(AssetPackMarket.from_dict(market_data))

        return cls(
            id_=id_,
            name=name,
            version=tuple(version) if isinstance(version, list) else version,
            vendor=vendor,
            description=data.get("description", ""),
            icon_url=data.get("icon_url", None),
            variants=data.get("variants", []),
            markets=markets,
            tags=tags,
        )


AVAILABLE_ASSET_PACKS: list[AvailableAssetPackMetadata] = []


def _materialize_asset_packs_index(
    timeout: float | None = None,
) -> list[AvailableAssetPackMetadata]:
    """Returns a list of available asset packs, downloading the index file if necessary."""
    if not bpy.app.online_access:
        return []
    ret = []
    update_needed = False
    if not os.path.exists(INDEX_LOCAL_FILE_PATH):
        logger.info(
            f"Local index file {INDEX_LOCAL_FILE_PATH} does not exist, downloading from {INDEX_REMOTE_URL}."
        )
        update_needed = True
    else:
        local_mtime = polib.utils_bpy.get_local_file_last_modified_utc(INDEX_LOCAL_FILE_PATH)
        remote_mtime = polib.utils_bpy.get_remote_file_last_modified_utc(
            INDEX_REMOTE_URL, timeout=timeout
        )
        if remote_mtime is None:
            return []
        if remote_mtime > local_mtime:
            logger.info(
                f"Remote index '{INDEX_REMOTE_URL}' is newer than local file '{INDEX_LOCAL_FILE_PATH}', "
                "downloading new version."
            )
            update_needed = True

    raw_data = None
    if update_needed:
        if not os.path.exists(WORK_FOLDER):
            os.makedirs(WORK_FOLDER, exist_ok=True)
        try:
            with urllib.request.urlopen(INDEX_REMOTE_URL, timeout=timeout) as response:
                raw_data = response.read()
                with open(INDEX_LOCAL_FILE_PATH, "wb") as f:
                    f.write(raw_data)
                indexed_asset_packs = json.loads(raw_data)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            logger.warning(f"Failed to download '{INDEX_REMOTE_URL}'. Reason: {e}")
            return []

    try:
        if raw_data is None:
            with open(INDEX_LOCAL_FILE_PATH) as f:
                indexed_asset_packs = json.load(f)
        else:
            indexed_asset_packs = json.loads(raw_data)
    except json.JSONDecodeError as e:
        logger.exception("Downloaded index file has invalid JSON format")
        return []

    for asset_pack in indexed_asset_packs:
        if not isinstance(asset_pack, dict):
            logger.error("Asset pack metadata must be a dictionary")
            continue
        try:
            metadata = AvailableAssetPackMetadata.from_dict(asset_pack)
            ret.append(metadata)
        except ValueError as e:
            logger.exception(f"Invalid asset pack metadata: {e}")

    return ret


def _refresh_available_asset_packs() -> None:
    """Populates the AVAILABLE_ASSET_PACKS list based on the remote index.json content.

    Downloads and assigns the pack preview to 'pack_thumbnail_icon_manager'.
    Clears AVAILABLE_ASSET_PACKS access methods caches.
    """
    if not bpy.app.online_access:
        return
    # Avoid multiple asset registry refreshes manipulating the same list
    with available_pack_refresh_lock:
        AVAILABLE_ASSET_PACKS.clear()
        for available_pack_metadata in _materialize_asset_packs_index():
            if available_pack_metadata.icon_url is not None:
                pack_thumbnail_icon_manager.request_preview_url(
                    available_pack_metadata.icon_url,
                    id_override=pack_thumbnail_icon_manager.preview_id_from_url(
                        available_pack_metadata.icon_url
                    ),
                )
            AVAILABLE_ASSET_PACKS.append(available_pack_metadata)

    # Clear the cache once all new packs are updated.
    get_available_pack_from_full_name.cache_clear()


@functools.lru_cache
def get_available_pack_from_full_name(
    full_name: str,
) -> AvailableAssetPackMetadata | None:
    """Returns available asset pack if it contains variant matching 'full_name'.

    NOTE: This doesn't fetch data, data has to be firstly updated by one of the refresh methods.
    Returns None if the pack is not found.
    """
    for pack_metadata in AVAILABLE_ASSET_PACKS:
        for variant in pack_metadata.variants:
            if full_name == variant:
                # If the variant matches the full name, we can return the version
                return pack_metadata
    return None


def get_not_installed_available_asset_packs() -> list[AvailableAssetPackMetadata]:
    """Returns a list of asset packs that are not installed, but available for download.

    NOTE: This doesn't fetch data, data has to be firstly updated by one of the refresh methods.
    """
    registered_packs_full_names = asset_registry.instance.get_registered_packs_full_names()
    not_yet_installed_packs = []
    for pack_metadata in AVAILABLE_ASSET_PACKS:
        if f"{pack_metadata.id_}_dev" in registered_packs_full_names:
            # Skip dev packs, they are only internally renamed
            continue

        if any(variant in registered_packs_full_names for variant in pack_metadata.variants):
            continue

        # If the pack is not registered, yield it
        not_yet_installed_packs.append(pack_metadata)

    return not_yet_installed_packs


def refresh_available_asset_packs_background() -> None:
    """Refreshes the available asset packs in the background.

    Populates the AVAILABLE_ASSET_PACKS list based on the remote index.json content in a background
    thread.
    """
    threading.Thread(
        target=_refresh_available_asset_packs,
    ).start()


@polib.log_helpers_bpy.logged_operator
class ShowAvailablePackInfo(bpy.types.Operator):
    bl_idname = "engon.show_asset_pack_info"
    bl_label = "Show Available Asset Pack Info"
    bl_description = "Shows additional information about the available asset pack"
    bl_options = {'REGISTER'}

    pack_id: bpy.props.StringProperty(name="Pack ID", default="")

    @staticmethod
    def draw_asset_pack_info(
        popup_menu: bpy.types.UIPopupMenu,
        pack_metadata: AvailableAssetPackMetadata,
    ) -> None:
        col = popup_menu.layout.column()
        col.label(text=f"Version: {'.'.join(map(str, pack_metadata.version))}")
        col.label(text=f"Vendor: {pack_metadata.vendor}")
        col.separator()
        polib.ui_bpy.draw_message_in_lines(
            col,
            pack_metadata.description,
            max_chars=100,
        )

        if len(pack_metadata.markets) > 0:
            col.separator()
            col.label(text="Available from:")
            for market in pack_metadata.markets:
                row = col.row()
                row.scale_y = 1.2
                row.operator(
                    "wm.url_open", text=market.name.capitalize(), icon_value=market.get_icon_id()
                ).url = market.url

        if len(pack_metadata.tags) > 0:
            col.separator()
            row = col.row(align=True)
            row.alignment = 'LEFT'
            for tag in pack_metadata.tags:
                row.label(text=tag.capitalize())

    def execute(self, context: bpy.types.Context):
        available_pack_metadata = next(
            filter(lambda pack: pack.id_ == self.pack_id, AVAILABLE_ASSET_PACKS), None
        )
        if available_pack_metadata is None:
            self.report({'ERROR'}, f"Asset pack metadata for '{self.pack_id}' not found.")
            return {'CANCELLED'}

        context.window_manager.popup_menu(
            lambda popup_menu, _: ShowAvailablePackInfo.draw_asset_pack_info(
                popup_menu, available_pack_metadata
            ),
            title=available_pack_metadata.name,
            icon='PRESET',
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ShowAvailablePackInfo)


def draw_available_asset_packs(
    context: bpy.types.Context, layout: bpy.types.UILayout, icon_scale: float = 6.0
) -> None:
    grid_flow = layout.grid_flow(
        row_major=True,
        align=False,
        # columns = 0 calculates the number of columns automatically
        columns=0,
    )
    for pack_metadata in get_not_installed_available_asset_packs():
        col = grid_flow.column(align=True)
        box = col.box()
        box.template_icon(
            (
                pack_thumbnail_icon_manager.get_icon_id(
                    pack_thumbnail_icon_manager.preview_id_from_url(pack_metadata.icon_url)
                )
                if pack_metadata.icon_url is not None
                else 1
            ),
            scale=icon_scale,
        )
        row = col.row(align=True)
        row.scale_y = 1.2
        row.operator(
            ShowAvailablePackInfo.bl_idname,
            text=pack_metadata.name,
            icon='URL',
        ).pack_id = pack_metadata.id_


def register() -> None:
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    if not bpy.app.background:
        asset_registry.instance.on_refresh.append(refresh_available_asset_packs_background)


def unregister() -> None:
    if not bpy.app.background:
        asset_registry.instance.on_refresh.remove(refresh_available_asset_packs_background)

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
