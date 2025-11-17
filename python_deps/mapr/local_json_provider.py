#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import os
import json
import collections
from . import category
from . import asset
from . import asset_data
from . import blender_asset_data
from . import file_provider
from . import asset_provider
from . import country_locations
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


class LocalJSONProvider(file_provider.FileProvider, asset_provider.AssetProvider):
    def __init__(
        self,
        index_file_path: str,
        file_id_folder_path: str,
        file_id_prefix: str,
        index_json_override: dict | None = None,
    ):
        """Dual purpose asset and file provider, index is loaded from JSON, all files from disk

        index_file_path: path to the file containing MAPR index JSON
        file_id_folder_path: path to where files are provided from, all file IDs are relative to it
                             when file_id_prefix is removed from the ID
        file_id_prefix: all files provided with this providers have to have an ID starting with
                        this prefix
        index_json_override: optional dictionary to override the index JSON with, useful for testing
        """

        self.index_file_path = index_file_path
        self.file_id_folder_path = file_id_folder_path
        self.file_id_prefix = file_id_prefix

        self.index_json_override = index_json_override

        # maps category ID to IDs of its child categories
        self.child_categories: collections.defaultdict[
            category.CategoryID, list[category.CategoryID]
        ] = collections.defaultdict(list)
        # maps category ID to IDs of its child assets
        self.child_assets: collections.defaultdict[category.CategoryID, list[asset.AssetID]] = (
            collections.defaultdict(list)
        )

        # maps asset ID to IDs of categories it is in (including parents recursively)
        self.asset_categories: collections.defaultdict[asset.AssetID, set[category.CategoryID]] = (
            collections.defaultdict(set)
        )

        # maps category ID to its metadata
        self.categories: dict[category.CategoryID, category.Category] = {}
        # maps asset ID to its metadata
        self.assets: dict[asset.AssetID, asset.Asset] = {}
        # maps asset data ID to its data
        self.asset_data: dict[asset_data.AssetDataID, asset_data.AssetData] = {}
        # maps datablock basename to its FileID
        self.basenames_to_file_ids: dict[str, file_provider.FileID] = {}

        self.load_index()

    def materialize_file(self, file_id: file_provider.FileID) -> str | None:
        if not file_id.startswith(f"{self.file_id_prefix}:"):
            return None

        relative_path = file_id[len(self.file_id_prefix) + 1 :]
        full_path = os.path.abspath(os.path.join(self.file_id_folder_path, relative_path))
        if os.path.isfile(full_path):
            return full_path

        logger.warning(
            f"Asked to materialize {file_id}, the prefix matches but the file at the inferred "
            f"full path: {full_path} does not exist."
        )
        return None

    def get_file_id_from_basename(self, basename: str) -> file_provider.FileID | None:
        file_id: file_provider.FileID | None = None

        # Our texture compression pipeline may have switched from jpg to png or vice versa.
        if basename.endswith((".jpg", ".png")):
            name_without_ext, _ = os.path.splitext(basename)
            file_id = self.basenames_to_file_ids.get(name_without_ext + ".jpg", None)
            if file_id is not None:
                return file_id
            else:
                return self.basenames_to_file_ids.get(name_without_ext + ".png", None)

        return self.basenames_to_file_ids.get(basename, None)

    def load_index(self):
        index_json = {}
        if self.index_json_override is None:
            with open(self.index_file_path) as f:
                index_json = json.load(f)
        else:
            index_json = self.index_json_override

        # TODO: sanity check the input json?
        # TODO: convert from dict mapping str->list to str->set?
        self.child_categories = index_json.get("child_categories", {})
        self.child_assets = index_json.get("child_assets", {})
        self.child_asset_data = index_json.get("child_asset_data", {})

        for category_part, category_metadata_json in index_json.get(
            "category_metadata", {}
        ).items():
            self.categories[category_part] = category.Category(
                id_=category_part,
                title=category_metadata_json.get("title", "unknown"),
                preview_file=category_metadata_json.get("preview_file", None),
            )

        asset_to_category_id: dict[str, str] = {}
        for child_category_id, asset_ids in self.child_assets.items():
            for asset_id in asset_ids:
                asset_to_category_id[asset_id] = child_category_id

        self.asset_categories = self.map_assets_to_categories()
        for asset_id, asset_metadata_json in index_json.get("asset_metadata", {}).items():
            # Update vector parameters with color parameters for older asset packs
            # compatibility (prior to engon 1.2.0). Color parameters were defined solely prior to
            # the introduction of vector parameters.
            vector_parameters = asset_metadata_json.get("vector_parameters", {})
            vector_parameters.update(asset_metadata_json.get("color_parameters", {}))

            foreign_search_matter: dict[str, float] = {}
            foreign_search_matter.update(
                {
                    self.categories[category_id].title: category.TITLE_SEARCH_WEIGHT
                    for category_id in self.asset_categories.get(asset_id, set())
                }
            )

            # Convert country of origin to location parameters to make the country of origin
            # compatible with the search map feature. This is relevant for asset packs with
            # implied geographical data, such as "country_of_origin" in traffiq and interniq.
            text_parameters = asset_metadata_json.get("text_parameters", {})
            location_parameters = asset_metadata_json.get("location_parameters", {})
            if (
                "country_of_origin" in text_parameters
                and "location_of_origin" not in location_parameters
            ):
                location = country_locations.COUNTRY_COORDINATES.get(
                    text_parameters["country_of_origin"], None
                )
                if location is None:
                    logger.info(
                        f"Country of origin '{text_parameters['country_of_origin']}' in asset "
                        f"'{asset_id}' not found in known country locations. "
                        f"This asset will be updated in newer version of the asset pack."
                    )
                else:
                    location_parameters.update({"location_of_origin": location})
                    asset_metadata_json.update({"location_parameters": location_parameters})

            asset_metadata = asset.Asset(
                id_=asset_id,
                title=asset_metadata_json.get("title", "unknown"),
                type_=asset_data.AssetDataType[asset_metadata_json.get("type", "unknown")],
                preview_file=asset_metadata_json.get("preview_file", ""),
                tags=asset_metadata_json.get("tags", []),
                numeric_parameters=asset_metadata_json.get("numeric_parameters", {}),
                vector_parameters=vector_parameters,
                text_parameters=asset_metadata_json.get("text_parameters", {}),
                location_parameters=asset_metadata_json.get("location_parameters", {}),
                foreign_search_matter=foreign_search_matter,
            )
            # clear search matter cache since we updated search matter
            # we instantiated the class right here so this will do nothing but we include it for
            # people who will copy code from here
            asset_metadata.clear_search_matter_cache()
            self.assets[asset_id] = asset_metadata

        for asset_data_id, asset_data_json in index_json.get("asset_data", {}).items():
            asset_data_class: type[blender_asset_data.BlenderAssetData] | None = None
            asset_data_type = asset_data_json.get("type")
            if asset_data_type == "blender_model":
                asset_data_class = blender_asset_data.BlenderModelAssetData
            elif asset_data_type == "blender_material":
                asset_data_class = blender_asset_data.BlenderMaterialAssetData
            elif asset_data_type == "blender_world":
                asset_data_class = blender_asset_data.BlenderWorldAssetData
            elif asset_data_type == "blender_scene":
                asset_data_class = blender_asset_data.BlenderSceneAssetData
            elif asset_data_type == "blender_particle_system":
                asset_data_class = blender_asset_data.BlenderParticleSystemAssetData
            elif asset_data_type == "blender_geometry_nodes":
                asset_data_class = blender_asset_data.BlenderGeometryNodesAssetData
            else:
                raise NotImplementedError()

            assert asset_data_class is not None
            asset_data_instance = asset_data_class(
                id_=asset_data_id,
                primary_blend_file=asset_data_json.get("primary_blend_file", ""),
                dependency_files=asset_data_json.get("dependency_files", []),
            )
            self.record_file_id(asset_data_instance.primary_blend_file)
            for dependency_file in asset_data_instance.dependency_files:
                self.record_file_id(dependency_file)
                # TODO: attempt to find the textures with other resolutions is temporary fix
                # for https://git.polygoniq.com/c/polygoniq/-/issues/5094
                # and https://git.polygoniq.com/c/polygoniq/-/issues/5163
                # The code should be reverted to the original state after the issue is fixed
                if (
                    self.file_id_prefix == "/materialiq"
                    and asset_data_type == "blender_material"
                    and dependency_file.endswith(("_2048.jpg", "_2048.png"))
                ):
                    # Try to find other resolutions of the texture
                    for resolution in ["1024", "4096", "8192"]:
                        mod_dependency_file = dependency_file.replace("_2048.", f"_{resolution}.")
                        relative_path = mod_dependency_file[len(self.file_id_prefix) + 1 :]
                        full_path = os.path.abspath(
                            os.path.join(self.file_id_folder_path, relative_path)
                        )
                        if os.path.isfile(full_path):
                            self.record_file_id(mod_dependency_file)

            self.asset_data[asset_data_id] = asset_data_instance

    def list_child_category_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[category.CategoryID]:
        yield from self.child_categories.get(parent_id, [])

    def list_child_asset_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[asset.AssetID]:
        yield from self.child_assets.get(parent_id, [])

    def list_asset_data_ids(
        self, asset_id: asset.AssetID
    ) -> typing.Iterable[asset_data.AssetDataID]:
        yield from self.child_asset_data.get(asset_id, [])

    def get_category(self, category_id: category.CategoryID) -> category.Category | None:
        return self.categories.get(category_id, None)

    def get_asset(self, asset_id: asset.AssetID) -> asset.Asset | None:
        return self.assets.get(asset_id, None)

    def get_asset_data(self, asset_data_id: asset_data.AssetDataID) -> asset_data.AssetData | None:
        return self.asset_data.get(asset_data_id, None)

    def map_assets_to_categories(
        self,
    ) -> collections.defaultdict[asset.AssetID, set[category.CategoryID]]:
        """Returns a mapping of asset ID to category IDs it is in, including parent categories.

        Constructed based on 'child_asset_data' and 'child_categories' mappings. These
        should be populated prior to calling this method.
        """
        # Reverse mapping of child to parent categories
        category_parent_mapping: dict[category.CategoryID, category.CategoryID] = {}
        for parent, children in self.child_categories.items():
            category_parent_mapping.update({child: parent for child in children})

        # Find all parent categories recursively
        def find_parents(category_id, all_parents):
            if category_id in category_parent_mapping:
                parent = category_parent_mapping[category_id]
                all_parents.add(parent)
                find_parents(parent, all_parents)

        asset_to_categories: collections.defaultdict[asset.AssetID, set[category.CategoryID]] = (
            collections.defaultdict(set)
        )
        for category_id, asset_ids in self.child_assets.items():
            for asset_id in asset_ids:
                asset_to_categories[asset_id].add(category_id)
                find_parents(category_id, asset_to_categories[asset_id])

        return asset_to_categories

    def record_file_id(self, file_id: file_provider.FileID) -> None:
        relative_path = file_id[len(self.file_id_prefix) + 1 :]
        basename = os.path.basename(relative_path)
        prev_record = self.basenames_to_file_ids.get(basename, None)
        if prev_record is not None and prev_record != file_id:
            logger.warning(
                f"Basename {basename} previously mapped to {prev_record}, overwriting with {file_id}!"
            )
        self.basenames_to_file_ids[basename] = file_id
