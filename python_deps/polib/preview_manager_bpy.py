# copyright (c) 2018- polygoniq xyz s.r.o.


import bpy
import bpy.utils.previews
import os
import urllib.request
import urllib.error
import logging
import typing

from . import utils_bpy

logger = logging.getLogger(f"polygoniq.{__name__}")


class PreviewManager:
    """Loads previews from provided paths on demand based on basenames or custom ids.

    'blocking_load' forces the preview to load the image data immediately when requested."""

    def __init__(self, blocking_load: bool = True) -> None:
        self.preview_collection = bpy.utils.previews.new()
        self.id_path_map: typing.Dict[str, str] = {}
        self.allowed_extensions = {".png", ".jpg"}
        self.blocking_load = blocking_load

    def add_preview_path(self, path: str, id_override: typing.Optional[str] = None) -> None:
        """Adds 'path' as a possible place from where preview can be loaded if requested.

        By default the ID of the preview is the basename of the file without extension. If 'path'
        is a single file, then 'id_override' can be used to override the default behavior.

        If 'path' is a directory, then all files with allowed extension are considered.

        The preview is then loaded on demand when requested by its ID using 'get_icon_id'.
        """
        self._update_path_map_entry(path, id_override)

    def get_icon_id(self, id_: str) -> int:
        """Return icon_id for preview with id 'id_'

        Returns question mark icon id if 'id_' is not found.
        """
        if id_ in self.preview_collection:
            return self.preview_collection[id_].icon_id
        else:
            path = self.id_path_map.get(id_, None)
            if path is None:
                return 1

            # There might be paths, that weren't removed from the map, but the file was already
            # deleted on the filesystem. In that case (else branch) we remove the id_ from
            # the path map.
            if os.path.isfile(path):
                logger.debug(f"Preview: {id_} loaded on demand {id_}")
                self._load_preview(path, id_)
                assert id_ in self.preview_collection
                return self.preview_collection[id_].icon_id
            else:
                del self.id_path_map[id_]

        # Unknown preview ID
        return 1

    def get_polygoniq_addon_icon_id(self, addon_name: str) -> int:
        return self.get_icon_id(f"logo_{addon_name}")

    def get_engon_feature_icon_id(self, feature_name: str) -> int:
        return self.get_icon_id(f"logo_{feature_name}_features")

    def clear(self, ids: typing.Optional[typing.Set[str]] = None) -> None:
        """Clears the whole preview collection or only 'ids' if provided.

        This doesn't clear the paths where previews can be found. If there is some invalid path,
        it is cleared when the preview should be loaded, but it wasn't be found.
        """
        if ids is None:
            self.preview_collection.clear()
        else:
            for id_ in ids:
                if id_ in self.preview_collection:
                    del self.preview_collection[id_]

    def _update_path_map_entry(self, path: str, id_override: typing.Optional[str] = None) -> None:
        if os.path.isdir(path):
            if id_override is not None:
                raise RuntimeError("id_override is not allowed for directories!")

            for file in os.listdir(path):
                filename, ext = os.path.splitext(file)
                basename = os.path.basename(filename)
                if ext.lower() in self.allowed_extensions:
                    self.id_path_map[basename] = os.path.join(path, file)
                    if basename in self.preview_collection:
                        del self.preview_collection[basename]

        elif os.path.isfile(path):
            filename, ext = os.path.splitext(path)
            basename = os.path.basename(filename)
            key = id_override if id_override is not None else basename
            if ext.lower() in self.allowed_extensions:
                self.id_path_map[key] = path
                if key in self.preview_collection:
                    del self.preview_collection[key]

    def _load_preview(self, full_path: str, id_: str) -> None:
        """Loads previews from 'full_path' and saves on key 'id_'

        Assumes 'full_path' is already existing file in the filesystem.
        """

        if id_ in self.preview_collection:
            return

        assert os.path.isfile(full_path)
        try:
            self.preview_collection.load(id_, full_path, 'IMAGE', True)
            if self.blocking_load:
                # Accessing this property getter triggers bpy kernel to ensure the preview
                self.preview_collection[id_].icon_size[:]
        except KeyError as e:
            logger.exception(f"Preview {id_} already loaded!")

    def __del__(self):
        self.preview_collection.close()

    def __contains__(self, id_: str) -> bool:
        return id_ in self.preview_collection

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: Loaded {len(self.preview_collection)} previews."


class OnlinePreviewManager(PreviewManager):
    """Preview manager with extra functionality for loading previews from online sources."""

    def __init__(
        self,
        downloads_folder_path: str,
        blocking_load: bool = True,
        timeout: typing.Optional[float] = None,
    ) -> None:
        super().__init__(blocking_load)
        self.downloads_folder_path = downloads_folder_path
        self.timeout = timeout

    def preview_id_from_url(self, url: str) -> str:
        """Infers ID of a preview loaded from URL."""
        return os.path.basename(url)

    def request_preview_url(
        self,
        url: str,
        id_override: typing.Optional[str] = None,
    ) -> None:
        """Downloads image from 'url' so it can be loaded locally."""
        basename = os.path.basename(url)
        full_path = os.path.join(self.downloads_folder_path, basename)

        needs_download = False
        if not os.path.isfile(full_path):
            logger.debug(f"Preview file '{full_path}' does not exist, downloading from '{url}'.")
            needs_download = True
        else:
            local_mtime = utils_bpy.get_local_file_last_modified_utc(full_path)
            remote_mtime = utils_bpy.get_remote_file_last_modified_utc(url, timeout=self.timeout)
            if remote_mtime is not None and remote_mtime > local_mtime:
                logger.debug(
                    f"Remote preview file '{url}' is newer than local file '{full_path}', downloading new version."
                )
                needs_download = True

        if needs_download:
            os.makedirs(self.downloads_folder_path, exist_ok=True)
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    with open(full_path, 'wb') as out_file:
                        out_file.write(response.read())

            except urllib.error.HTTPError as e:
                logger.error(f"HTTP error while downloading preview from {url}: {e}")
            except urllib.error.URLError as e:
                logger.error(f"URL error while downloading preview from {url}: {e}")
        else:
            logger.debug(f"Preview file '{full_path}' already exists, and is up-to-date.")

        self._update_path_map_entry(full_path, id_override)
