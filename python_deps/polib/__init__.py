#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import sys
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")

from . import asset_pack

# polib is used outside of Blender as well, we have to support
# a usecase where bpy is not available and can't be imported
try:
    import bpy
    from . import asset_pack_bpy
    from . import color_utils_bpy
    from . import custom_props_bpy
    from . import geonodes_mod_utils_bpy
    from . import linalg_bpy
    from . import log_helpers_bpy
    from . import material_utils_bpy
    from . import node_utils_bpy
    from . import preview_manager_bpy
    from . import remove_duplicates_bpy
    from . import render_bpy
    from . import rigs_shared_bpy
    from . import snap_to_ground_bpy
    from . import spline_utils_bpy
    from . import split_file_reader
    from . import telemetry_module_bpy as telemetry_native_module
    from . import ui_bpy
    from . import utils_bpy
    from . import serialization_bpy

    def init_polygoniq_global():
        global telemetry_module_bpy

        if not hasattr(bpy, "polygoniq_global"):
            bpy.polygoniq_global = {"telemetry": {}, "telemetry_module_bpy": {}}  # deprecated!

        if "telemetry_module_bpy" not in bpy.polygoniq_global:
            bpy.polygoniq_global["telemetry_module_bpy"] = {}

        # another polygoniq addon might have already initialized telemetry!
        # we want to use just one instance unless it's a different API version
        if telemetry_native_module.API_VERSION in bpy.polygoniq_global["telemetry_module_bpy"]:
            telemetry_module_bpy = bpy.polygoniq_global["telemetry_module_bpy"][
                telemetry_native_module.API_VERSION
            ]
        else:
            telemetry_module_bpy = telemetry_native_module
            bpy.polygoniq_global["telemetry_module_bpy"][
                telemetry_native_module.API_VERSION
            ] = telemetry_module_bpy
            telemetry_module_bpy.bootstrap_telemetry()

    init_polygoniq_global()

    def get_telemetry(product: str):
        return telemetry_module_bpy.get_telemetry(product)

except ImportError as e:
    if e.name != "bpy":
        raise

    logger.info(
        f"polib has been initialized without bpy, all polib modules that use bpy are imported as dummies only."
    )

    import types

    asset_pack_bpy = types.ModuleType("asset_pack_bpy")
    custom_props_bpy = types.ModuleType("custom_props_bpy")
    color_utils_bpy = types.ModuleType("color_utils_bpy")
    geonodes_mod_utils_bpy = types.ModuleType("geonodes_mod_utils_bpy")
    linalg_bpy = types.ModuleType("linalg_bpy")
    log_helpers_bpy = types.ModuleType("log_helpers_bpy")
    material_utils_bpy = types.ModuleType("material_utils_bpy")
    node_utils_bpy = types.ModuleType("node_utils_bpy")
    preview_manager_bpy = types.ModuleType("preview_manager_bpy")
    remove_duplicates_bpy = types.ModuleType("remove_duplicates_bpy")
    render_bpy = types.ModuleType("render_bpy")
    rigs_shared_bpy = types.ModuleType("rigs_shared_bpy")
    snap_to_ground_bpy = types.ModuleType("snap_to_ground_bpy")
    spline_utils_bpy = types.ModuleType("spline_utils_bpy")
    split_file_reader = types.ModuleType("split_file_reader")
    telemetry_native_module = types.ModuleType("telemetry_native_module")
    ui_bpy = types.ModuleType("ui_bpy")
    utils_bpy = types.ModuleType("utils_bpy")
    serialization_bpy = types.ModuleType("serialization_bpy")


# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "polib",
    "description": "",
}


def register():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


def unregister():  # mostly stub just to avoid an AttributeError when using blender_vscode extension
    # Remove all nested modules from module cache, more reliable than importlib.reload(..)
    # Idea by BD3D / Jacques Lucke
    for module_name in list(sys.modules.keys()):
        if module_name.startswith(__package__):
            del sys.modules[module_name]


__all__ = [
    "asset_pack_bpy",
    "asset_pack",
    "color_utils_bpy",
    "custom_props_bpy",
    "geonodes_mod_utils_bpy",
    "get_telemetry",
    "linalg_bpy",
    "log_helpers_bpy",
    "material_utils_bpy",
    "node_utils_bpy",
    "preview_manager_bpy",
    "remove_duplicates_bpy",
    "render_bpy",
    "rigs_shared_bpy",
    "snap_to_ground_bpy",
    "spline_utils_bpy",
    "split_file_reader",
    # telemetry_module_bpy intentionally missing, you should interact with it via get_telemetry
    "ui_bpy",
    "utils_bpy",
    "serialization_bpy",
]
