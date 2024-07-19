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


MODULE_CLASSES: typing.List[typing.Any] = []


class AquatiqPreferences(bpy.types.PropertyGroup):
    draw_mask_factor: bpy.props.FloatProperty(
        name="Mask Factor",
        description="Value of 1 means visible, value of 0 means hidden",
        update=lambda self, context: self.update_mask_factor(context),
        soft_max=1.0,
        soft_min=0.0,
    )

    def update_mask_factor(self, context: bpy.types.Context):
        context.tool_settings.vertex_paint.brush.color = [self.draw_mask_factor] * 3


MODULE_CLASSES.append(AquatiqPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
