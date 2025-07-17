# copyright (c) 2018- polygoniq xyz s.r.o.

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

from . import browser
from . import categories
from . import dev
from . import filters
from . import previews
from . import spawn
from . import state
from . import what_is_new
from . import tiled_map


def register():
    state.register()
    filters.register()
    categories.register()
    dev.register()
    spawn.register()
    browser.register()
    what_is_new.register()
    tiled_map.register()


def unregister():
    tiled_map.unregister()
    what_is_new.unregister()
    browser.unregister()
    spawn.unregister()
    dev.unregister()
    categories.unregister()
    filters.unregister()
    state.unregister()

    # Delete the preview_manager to close the preview collection and allow previews to free
    del previews.preview_manager
