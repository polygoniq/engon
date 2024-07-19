# copyright (c) 2018- polygoniq xyz s.r.o.

import os
import zipfile
import bpy
import typing
import addon_utils


def get_addon_version_in_blender(full_name: str) -> typing.Optional[typing.Iterable[int]]:
    """Retrieves the version of given addon by full name

    The given name of the addon is the actual full / implementation name.
    For example "botaniq_lite" or "traffiq_starter".
    """

    for module in addon_utils.modules():
        name = getattr(module, "__name__")
        if name is None or name != full_name:
            continue
        enabled, _ = addon_utils.check(name)
        if not enabled:
            continue

        bl_info = getattr(module, "bl_info", None)
        if bl_info is None:
            continue
        version = bl_info.get("version")
        return version

    return None


def install_addon_zip(zip_file_path: str, module_name: str) -> None:
    """From zip file in 'zip_file_path' installs module named 'module_name'"""
    if not zipfile.is_zipfile(zip_file_path):
        raise RuntimeError(f"{zip_file_path} is not a valid ZIP file!")

    path_addons = bpy.utils.user_resource('SCRIPTS', path="addons", create=True)

    os.makedirs(path_addons, exist_ok=True)
    file_to_extract = zipfile.ZipFile(zip_file_path, 'r')

    def module_filesystem_remove(path_base: str, module_name: str) -> None:
        # ported from bl_operators/userpref.py
        module_name = os.path.splitext(module_name)[0]
        for f in os.listdir(path_base):
            f_base = os.path.splitext(f)[0]
            if f_base == module_name:
                f_full = os.path.join(path_base, f)

                if os.path.isdir(f_full):
                    os.rmdir(f_full)
                else:
                    os.remove(f_full)

    # remove existing addon files
    for f in file_to_extract.namelist():
        module_filesystem_remove(path_addons, f)

    file_to_extract.extractall(path_addons)

    def refresh_and_enable(module_name: str):
        addon_utils.modules_refresh()
        bpy.ops.preferences.addon_enable(module=module_name)

    # we do the actual update in the blender event loop to avoid crashes in case
    # grumpy_cat is updating itself
    bpy.app.timers.register(
        lambda: refresh_and_enable(module_name), first_interval=0, persistent=True
    )


def uninstall_addon_module_name(module_name: str) -> None:
    bpy.ops.preferences.addon_disable(module=module_name)
    bpy.ops.preferences.addon_remove(module=module_name)
