# copyright (c) 2018- polygoniq xyz s.r.o.

from . import migrator
from . import asset_changes


def register():
    migrator.register()


def unregister():
    migrator.unregister()
