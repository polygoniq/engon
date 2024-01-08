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
import mapr

# Estimate of PX width (without scale) of a letter in Blender
# If we are able to count exact letter width, then we know more precisely when to wrap
EST_LETTER_WIDTH_PX = 10


def get_icon_of_asset_data_type(type_: mapr.asset_data.AssetDataType) -> str:
    return {
        mapr.asset_data.AssetDataType.unknown: 'QUESTION',
        mapr.asset_data.AssetDataType.blender_model: 'OBJECT_DATA',
        mapr.asset_data.AssetDataType.blender_material: 'MATERIAL',
        mapr.asset_data.AssetDataType.blender_particle_system: 'PARTICLES',
        mapr.asset_data.AssetDataType.blender_scene: 'SCENE_DATA',
        mapr.asset_data.AssetDataType.blender_world: 'WORLD',
        mapr.asset_data.AssetDataType.blender_geometry_nodes: 'GEOMETRY_NODES'
    }.get(type_, 'QUESTION')


def tag_prefs_redraw(context: bpy.types.Context) -> None:
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PREFERENCES':
                area.tag_redraw()
