#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.


import bpy
import re
import os
import typing
from . import utils_bpy

import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


def polygoniq_duplicate_data_filter(
    data: bpy.types.ID, data_filepaths: typing.Optional[typing.Set[str]] = None
) -> bool:
    """Filters polygoniq duplicate data based on addon prefix and duplicate suffix.

    If 'data_filepaths' argument is provided, images with path common to paths provided are also
    considered duplicates.
    """
    if not utils_bpy.contains_object_duplicate_suffix(data.name):
        return False

    if data_filepaths is None:
        data_filepaths = set()

    KNOWN_PREFIXES = ("aq_", "bq_", "mq_", "tq_", "iq_", "eq_", "st_", "am154_", "am176_")

    orig_name = utils_bpy.remove_object_duplicate_suffix(data.name)
    if isinstance(data, bpy.types.NodeTree):
        return orig_name.startswith(KNOWN_PREFIXES)

    if isinstance(data, bpy.types.Material):
        return orig_name.startswith(KNOWN_PREFIXES)

    if isinstance(data, bpy.types.Image):
        img_path = os.path.abspath(bpy.path.abspath(data.filepath, library=data.library))
        for path in data_filepaths:
            try:
                if os.path.commonpath([img_path, path]) == path:
                    return True
            except ValueError:
                continue

    return False


DuplicateFilter = typing.Callable[[bpy.types.ID, typing.Optional[typing.Set[str]]], bool]


def _is_duplicate_filtered(
    data: bpy.types.ID,
    filters: typing.Iterable[DuplicateFilter],
    install_paths: typing.Optional[typing.Set[str]] = None,
) -> bool:
    filtered = False
    for filter_ in filters:
        if not filter_(data, install_paths):
            filtered = True
            break

    return filtered


def remove_duplicate_datablocks(
    datablocks: bpy.types.bpy_prop_collection,
    filters: typing.Optional[typing.Iterable[DuplicateFilter]] = None,
    install_paths: typing.Optional[typing.Set[str]] = None,
) -> typing.List[str]:
    to_remove = []

    for datablock in datablocks:
        if filters is not None and _is_duplicate_filtered(datablock, filters, install_paths):
            continue

        # ok, so it's a duplicate, let's figure out the "proper" datablock
        orig_datablock_name = utils_bpy.remove_object_duplicate_suffix(datablock.name)
        if orig_datablock_name in datablocks:
            orig_node_group = datablocks[orig_datablock_name]
            datablock.user_remap(orig_node_group)
            if datablock.users == 0:
                to_remove.append(datablock)
        else:
            # the original datablock is gone, we should rename this one
            datablock.name = orig_datablock_name
    ret = []
    for datablock in to_remove:
        ret.append(datablock.name)
        datablocks.remove(datablock)
    return ret
