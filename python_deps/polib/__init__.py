#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


if "asset_pack_bpy" not in locals():
    from . import asset_pack
    from . import bl_info_utils

    # polib is used outside of Blender as well, we have to support
    # a usecase where bpy is not available and can't be imported
    try:
        import bpy
        from . import asset_pack_bpy
        from . import color_utils
        from . import geonodes_mod_utils_bpy
        from . import installation_utils_bpy
        from . import linalg_bpy
        from . import log_helpers_bpy
        from . import material_utils_bpy
        from . import module_install_utils_bpy
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

        # singleton instance
        module_provider = module_install_utils_bpy.ModuleProvider()

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
        color_utils = types.ModuleType("color_utils")
        geonodes_mod_utils_bpy = types.ModuleType("geonodes_mod_utils_bpy")
        installation_utils_bpy = types.ModuleType("installation_utils_bpy")
        linalg_bpy = types.ModuleType("linalg_bpy")
        log_helpers_bpy = types.ModuleType("log_helpers_bpy")
        material_utils_bpy = types.ModuleType("material_utils_bpy")
        module_install_utils_bpy = types.ModuleType("module_install_utils_bpy")
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


else:
    import importlib

    try:
        asset_pack = importlib.reload(asset_pack)
        asset_pack_bpy = importlib.reload(asset_pack_bpy)
        color_utils = importlib.reload(color_utils)
        bl_info_utils = importlib.reload(bl_info_utils)
        geonodes_mod_utils_bpy = importlib.reload(geonodes_mod_utils_bpy)
        installation_utils_bpy = importlib.reload(installation_utils_bpy)
        linalg_bpy = importlib.reload(linalg_bpy)
        log_helpers_bpy = importlib.reload(log_helpers_bpy)
        material_utils_bpy = importlib.reload(material_utils_bpy)
        module_install_utils_bpy = importlib.reload(module_install_utils_bpy)
        node_utils_bpy = importlib.reload(node_utils_bpy)
        remove_duplicates_bpy = importlib.reload(remove_duplicates_bpy)
        render_bpy = importlib.reload(render_bpy)
        rigs_shared_bpy = importlib.reload(rigs_shared_bpy)
        snap_to_ground_bpy = importlib.reload(snap_to_ground_bpy)
        spline_utils_bpy = importlib.reload(spline_utils_bpy)
        split_file_reader = importlib.reload(split_file_reader)
        telemetry_native_module = importlib.reload(telemetry_native_module)
        ui_bpy = importlib.reload(ui_bpy)
        utils_bpy = importlib.reload(utils_bpy)
    except ImportError:
        # in case these are fake modules created with types.ModuleType (when bpy is not available)
        pass


# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "polib",
    "description": "",
}


def register():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


def unregister():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


__all__ = [
    "asset_pack_bpy",
    "asset_pack",
    "color_utils",
    "bl_info_utils",
    "geonodes_mod_utils_bpy",
    "get_telemetry",
    "installation_utils_bpy",
    "linalg_bpy",
    "log_helpers_bpy",
    "material_utils_bpy",
    "module_install_utils_bpy",
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
]
