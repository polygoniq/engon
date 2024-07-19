#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

# Minimal library that contains code for spawning Blender assets. We try to keep this library
# as minimal as possible, because every change in this module triggers huge rebuilds
# (mostly rendering previews). We want this library to be only external dependency of
# render_previews, so don't ever import polib here!


if "bounding_box" not in locals():
    from . import bounding_box
    from . import displacement
    from . import load
    from . import spawn
    from . import textures
    from . import utils
else:
    import importlib

    bounding_box = importlib.reload(bounding_box)
    displacement = importlib.reload(displacement)
    load = importlib.reload(load)
    spawn = importlib.reload(spawn)
    textures = importlib.reload(textures)
    utils = importlib.reload(utils)


# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "hatchery",
    "description": "",
}


def register():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


def unregister():  # stub just to avoid an AttributeError when using blender_vscode extension
    pass


__all__ = [
    "bounding_box",
    "displacement",
    "load",
    "spawn",
    "textures",
    "utils",
]
