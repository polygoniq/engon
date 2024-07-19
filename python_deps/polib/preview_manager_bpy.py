# copyright (c) 2018- polygoniq xyz s.r.o.


import bpy
import bpy.utils.previews
import os
import logging
import typing
import threading

logger = logging.getLogger(f"polygoniq.{__name__}")


class PreviewManager:
    """Loads previews from provided paths on demand based on basenames or custom ids."""

    def __init__(self):
        self.preview_collection = bpy.utils.previews.new()
        self.lock = threading.Lock()
        self.id_path_map: typing.Dict[str, str] = {}
        self.allowed_extensions = {".png", ".jpg"}

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

        with self.lock:
            if id_ in self.preview_collection:
                return

            assert os.path.isfile(full_path)
            try:
                self.preview_collection.load(id_, full_path, 'IMAGE', True)
            except KeyError as e:
                logger.exception(f"Preview {id_} already loaded!")

    def __del__(self):
        self.preview_collection.close()

    def __contains__(self, id_: str) -> bool:
        return id_ in self.preview_collection

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: Loaded {len(self.preview_collection)} previews."
