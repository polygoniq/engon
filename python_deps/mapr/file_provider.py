#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import abc
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


# string ID of a file we can "materialize", see FileProvider
FileID = str


class FileProvider(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def materialize_file(self, file_id: FileID) -> str | None:
        """Makes a file represented by the given FileID appear locally on disk

        If the file provider is a streaming provider this function can be blocking and take some
        time before the file is downloaded.

        For example for FileID='botaniq-6.4.4:blends/models/coniferous/Some_Tree_A.blend' this function
        could return 'C:/polygoniq_cache/botaniq-6.4.4/blends/models/coniferous/Some_Tree_A.blend'.

        Relative paths are guaranteed to work for FileIDs after materializing. For example if we
        materialize FileID='botaniq-6.4.4:blends/models/coniferous/Some_Tree_A.blend' and
        FileID='botaniq-6.4.4:blends/models/Library_Botaniq_Materials.blend' the latter's relative path
        from FileIDs is '../Library_Botaniq_Materials.blend', the relative path on local disk will
        be the same. However, this API does not handle dependencies. If you need libraries, textures
        and blends you have to call materialize_file for all the FileIDs.

        Returns: absolute path on disk where the file is available or None if such FileID is not
        known to this FileProvider.
        """
        pass

    @abc.abstractmethod
    def get_file_id_from_basename(self, basename: str) -> FileID | None:
        """Returns a FileID of a file matching the basename if it is known to the file provider."""
        pass


class FileProviderMultiplexer(FileProvider):
    def __init__(self):
        super().__init__()

        # we use list instead of set because we want the file providers to be ordered
        self._file_providers: list[FileProvider] = []

    def add_file_provider(self, file_provider: FileProvider) -> None:
        self._file_providers.append(file_provider)

    def remove_file_provider(self, file_provider: FileProvider) -> None:
        self._file_providers.remove(file_provider)

    def clear_providers(self) -> None:
        self._file_providers.clear()

    def materialize_file(self, file_id: FileID) -> str | None:
        # TODO: Decide whether we go in order or in reverse order. Should providers added later
        # override previous providers?
        for provider in reversed(self._file_providers):
            ret = provider.materialize_file(file_id)
            if ret is not None:
                return ret

        return None

    def get_file_id_from_basename(self, basename: str) -> FileID | None:
        for provider in reversed(self._file_providers):
            ret = provider.get_file_id_from_basename(basename)
            if ret is not None:
                return ret

        return None
