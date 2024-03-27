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

import bpy
import typing
from . import filters
from . import previews


MODULE_CLASSES: typing.List[typing.Any] = []


class MAPR_BrowserDeleteCache(bpy.types.Operator):
    bl_idname = "engon.dev_browser_delete_cache"
    bl_label = "Delete Cache"

    def execute(self, context: bpy.types.Context):
        filters.asset_repository.clear_cache()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserDeleteCache)


class MAPR_BrowserReconstructFilters(bpy.types.Operator):
    bl_idname = "engon.dev_browser_reconstruct_filters"
    bl_label = "Reconstruct Filters"

    def execute(self, context: bpy.types.Context):
        filters.get_filters().clear()
        filters.get_filters().reconstruct()
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReconstructFilters)


class MAPR_BrowserReloadPreviews(bpy.types.Operator):
    bl_idname = "engon.dev_browser_reload_previews"
    bl_label = "Reload Previews (In Current View)"

    def execute(self, context: bpy.types.Context):
        assets = filters.asset_repository.current_assets
        previews.preview_manager.clear(ids={asset.id_ for asset in assets})
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReloadPreviews)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
