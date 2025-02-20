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
from .. import polib


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class ShowPopup(bpy.types.Operator):
    bl_idname = "engon.show_popup"
    bl_label = "Show Popup"
    bl_description = "Shows further info in a popup window"
    bl_options = {'REGISTER'}

    message: bpy.props.StringProperty(default="No message", options={'HIDDEN'})

    title: bpy.props.StringProperty(default="No title", options={'HIDDEN'})

    icon: bpy.props.StringProperty(default='INFO', options={'HIDDEN'})

    def execute(self, context):
        polib.ui_bpy.show_message_box(self.message, self.title, self.icon)
        return {'FINISHED'}


MODULE_CLASSES.append(ShowPopup)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
