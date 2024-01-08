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

import typing
import bpy
import logging
import polib
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


def can_change_lights_status(obj: bpy.types.Object) -> bool:
    return polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS in obj


def get_lights_status_value(lights_container: bpy.types.Object) -> float:
    return lights_container[polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS]


def set_lights_status_value(lights_container: bpy.types.Object, value: float) -> None:
    lights_container[polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS] = value


main_lights_status = (
    (0, "off"),
    (0.25, "park"),
    (0.50, "low-beam"),
    (0.75, "high-beam")
)


def get_main_lights_status_text(value: float) -> str:
    ret = "unknown"
    for min_value, status in main_lights_status:
        if value < min_value:
            return ret
        ret = status

    return ret


def find_unique_lights_containers(objects: typing.Iterable[bpy.types.Object]) -> typing.Set[bpy.types.Object]:
    ret = set()
    for obj in objects:
        light_obj = polib.asset_pack_bpy.find_traffiq_lights_container(obj)
        if light_obj is None:
            continue
        if light_obj in ret:
            continue

        ret.add(light_obj)

    return ret
