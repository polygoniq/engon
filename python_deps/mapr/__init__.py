#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import logging

logger = logging.getLogger(f"polygoniq.{__name__}")

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


# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "mapr",
    "description": "",
}


def register():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


def unregister():  # mostly stub just to avoid an AttributeError when using blender_vscode extension
    import sys

    # Remove all nested modules from module cache, more reliable than importlib.reload(..)
    # Idea by BD3D / Jacques Lucke
    for module_name in list(sys.modules.keys()):
        if module_name.startswith(__package__):
            del sys.modules[module_name]


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
