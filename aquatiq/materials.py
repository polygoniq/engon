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
import logging
import polib
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


class MaterialWarning:
    VOLUME = "Object has to have volume for this material to work correctly."
    SHORELINE = "Material is from the complex shoreline scene, open it to see how it works with\n" \
        "other materials to create the best result."


MATERIAL_WARNING_MAP = {
    "aq_Water_Ocean": {MaterialWarning.SHORELINE, MaterialWarning.VOLUME},
    "aq_Water_Shoreline": {MaterialWarning.SHORELINE},
    "aq_Water_SwimmingPool": {MaterialWarning.VOLUME},
    "aq_Water_Lake": {MaterialWarning.VOLUME},
    "aq_Water_Pond": {MaterialWarning.VOLUME},
}


def get_material_warnings_obj_based(
    obj: bpy.types.Object,
    material_name: str
) -> typing.Set[str]:

    warnings = MATERIAL_WARNING_MAP.get(material_name, None)
    if warnings is None:
        return set()

    # Create copy of the original set so the original isn't modified
    warnings = set(warnings)
    if not polib.linalg_bpy.is_obj_flat(obj):
        warnings -= {MaterialWarning.VOLUME}

    return warnings


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
