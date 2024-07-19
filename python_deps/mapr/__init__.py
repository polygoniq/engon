#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


if "asset_data" not in locals():
    from . import asset_data
    from . import asset_provider
    from . import asset
    from . import blender_asset_data
    from . import blender_asset_spawner
    from . import category
    from . import filters
    from . import file_provider
    from . import known_metadata
    from . import local_json_provider
    from . import parameter_meta
    from . import query
else:
    import importlib

    asset_data = importlib.reload(asset_data)
    asset_provider = importlib.reload(asset_provider)
    asset = importlib.reload(asset)
    blender_asset_data = importlib.reload(blender_asset_data)
    blender_asset_spawner = importlib.reload(blender_asset_spawner)
    category = importlib.reload(category)
    filters = importlib.reload(filters)
    file_provider = importlib.reload(file_provider)
    known_metadata = importlib.reload(known_metadata)
    local_json_provider = importlib.reload(local_json_provider)
    parameter_meta = importlib.reload(parameter_meta)
    query = importlib.reload(query)

# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "mapr",
    "description": "",
}


def register():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


def unregister():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


__all__ = [
    "asset_data",
    "asset_provider",
    "asset",
    "blender_asset_data",
    "blender_asset_spawner",
    "category",
    "filters",
    "file_provider",
    "known_metadata",
    "local_json_provider",
    "parameter_meta",
    "query",
]
