# copyright (c) 2018- polygoniq xyz s.r.o.
# This module contains materialiq texture switching related functions.

import bpy
import os
import typing
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")

TEXTURE_EXTENSIONS = {".png", ".jpg"}


def generate_filepath(texture_path: str, basename: str, max_size: str, ext: str) -> str:
    if basename.startswith("mq_") and basename.split("_")[-1].isdigit():
        name_without_resolution = basename.rsplit("_", 1)[0]

    return os.path.join(texture_path, f"{name_without_resolution}_{max_size}{ext}")


def is_materialiq_texture(image: bpy.types.Image) -> bool:
    basename, _ = os.path.splitext(os.path.basename(image.filepath))
    if basename.startswith("mq_") and basename.split("_")[-1].isdigit():
        return True

    return False


def change_texture_size(max_size: int, image: bpy.types.Image):
    if not is_materialiq_texture(image):
        return

    basename, ext = os.path.splitext(os.path.basename(image.filepath))
    if ext not in TEXTURE_EXTENSIONS:
        return

    logger.debug(f"Changing {image.name} to {max_size}...")

    new_path = None
    found = False
    parent_dir = os.path.dirname(image.filepath)
    for ext in TEXTURE_EXTENSIONS:
        new_path = generate_filepath(parent_dir, basename, str(max_size), ext)
        new_abs_path = bpy.path.abspath(new_path)
        # We getsize() to check that the file is not empty. Because of compress_texture, there could
        # exist different file formats of the same texture, and all except one of them would be empty.
        if os.path.exists(new_abs_path) and os.path.getsize(new_abs_path) > 0:
            found = True
            break

    if not found:
        logger.warning(f"Can't find {image.name} in size {max_size}, skipping...")
        return

    image.filepath = new_path
    image.name = os.path.basename(new_path)


def change_texture_sizes(
    max_size: int, only_textures: typing.Optional[typing.Set[bpy.types.Image]] = None
):
    logger.debug(f"mq: changing textures to {max_size}...")

    if only_textures is not None:
        for image in only_textures:
            change_texture_size(max_size, image)
    else:
        for image in bpy.data.images:
            change_texture_size(max_size, image)


def get_used_textures_in_node(node: bpy.types.Node) -> typing.Set[bpy.types.Image]:
    ret = set()

    if hasattr(node, "node_tree"):
        for child_node in node.node_tree.nodes:
            ret.update(get_used_textures_in_node(child_node))

    if hasattr(node, "image"):
        if node.image:
            ret.add(node.image)

    return ret


def get_used_textures(material: bpy.types.Material) -> typing.Set[bpy.types.Image]:
    if material is None:
        return set()

    if not material.use_nodes:
        logger.warning(
            f"Can't get used textures from material '{material.name}' that is not using "
            f"the node system!"
        )
        return set()

    assert material.node_tree is not None, "use_nodes is True, yet node_tree is None"
    ret = set()
    for node in material.node_tree.nodes:
        ret.update(get_used_textures_in_node(node))

    return ret
