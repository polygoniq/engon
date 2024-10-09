#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

# Minimal library that contains code for spawning Blender assets. We try to keep this library
# as minimal as possible, because every change in this module triggers huge rebuilds
# (mostly rendering previews). We want this library to be only external dependency of
# render_previews, so don't ever import polib here!

from . import bounding_box
from . import displacement
from . import load
from . import spawn
from . import textures
from . import utils


# fake bl_info so that this gets picked up by vscode blender integration
bl_info = {
    "name": "hatchery",
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
    "bounding_box",
    "displacement",
    "load",
    "spawn",
    "textures",
    "utils",
]
