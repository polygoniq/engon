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
from .. import __package__ as base_package

if typing.TYPE_CHECKING:
    # TYPE_CHECKING is always False at runtime, so this block will never be executed
    # This import is used only for type hinting
    from .. import preferences


SCATTER_DISPLAY_ENUM_ITEMS = (
    ('BOUNDS', "Bounds", "Bounds, Display the bounds of the object"),
    ('WIRE', "Wire", "Wire, Display the object as a wireframe"),
    (
        'SOLID',
        "Solid",
        "Solid, Display the object as a solid (if solid drawing is enabled in the viewport)",
    ),
    (
        'TEXTURED',
        "Textured",
        "Textured, Display the object with textures (if textures are enabled in the viewport)",
    ),
)


def get_preferences(context: bpy.types.Context) -> 'preferences.Preferences':
    return context.preferences.addons[base_package].preferences
