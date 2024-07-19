# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
from . import asset
from . import asset_data
from . import blender_asset_data
from . import file_provider
from . import asset_provider
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")

try:
    import hatchery
except ImportError:
    from blender_addons import hatchery


# We assign those properties to objects that were not in the source .blend file, but are a part
# of the asset - e. g. empty instancing a model, so we assign them the same ids.
# Defined in metadata in asset's .blend file
ASSET_ID_PROP_NAME = "mapr_asset_id"
# Defined in datablocks in asset's .blend file
ASSET_DATA_ID_PROP_NAME = "mapr_asset_data_id"


def mark_datablock_with_ids(
    datablock: bpy.types.ID, asset_id: asset.AssetID, asset_data_id: asset_data.AssetDataID
) -> None:
    datablock[ASSET_ID_PROP_NAME] = asset_id
    datablock[ASSET_DATA_ID_PROP_NAME] = asset_data_id


class AssetSpawner:
    def __init__(
        self,
        asset_provider_: asset_provider.AssetProvider,
        file_provider_: file_provider.FileProvider,
    ):
        self.asset_provider_ = asset_provider_
        self.file_provider_ = file_provider_

    def spawn(
        self,
        context: bpy.types.Context,
        asset_: asset.Asset,
        options: hatchery.spawn.DatablockSpawnOptions,
    ) -> typing.Optional[hatchery.spawn.SpawnedData]:
        """Tries to spawn first asset data, materializes required files and dependencies."""
        for asset_data_ in self.asset_provider_.list_asset_data(asset_.id_):
            path = self._materialize_files(asset_data_)
            spawned_data = asset_data_.spawn(path, context, options)
            for datablock in spawned_data.datablocks:
                mark_datablock_with_ids(datablock, asset_.id_, asset_data_.id_)

            return spawned_data

        return None

    def _materialize_files(self, asset_data_: blender_asset_data.BlenderAssetData) -> str:
        # 1. Materialize dependencies
        for dep_id in asset_data_.dependency_files:
            if dep_id == "<builtin>":
                continue

            self.file_provider_.materialize_file(dep_id)

        # 2. Materialize file
        return self.file_provider_.materialize_file(asset_data_.primary_blend_file)
