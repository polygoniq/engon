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
from .. import polib
from .. import hatchery
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class ChangeTextureSizeGlobal(bpy.types.Operator):
    bl_idname = "engon.materialiq_change_texture_size_global"
    bl_label = "Change Texture Size Of All Materials"
    bl_description = "Change global texture size of all materialiq materials"
    bl_options = {'REGISTER', 'UNDO'}

    max_size: bpy.props.EnumProperty(
        items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
        name="Texture maximum side size",
    )

    def execute(self, context: bpy.types.Context):
        hatchery.textures.change_texture_sizes(int(self.max_size))
        self.report({"INFO"}, f"Changed global texture sizes to {self.max_size}")
        return {'FINISHED'}


MODULE_CLASSES.append(ChangeTextureSizeGlobal)


@polib.log_helpers_bpy.logged_operator
class ChangeTextureSizeActiveMaterial(bpy.types.Operator):
    bl_idname = "engon.materialiq_change_texture_size_active_material"
    bl_label = "Change Texture Size Of Active Material"
    bl_description = "Change maximum texture size of active materialiq material"
    bl_options = {'REGISTER', 'UNDO'}

    max_size: bpy.props.EnumProperty(
        items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
        name="Texture maximum side size",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return False

        textures = hatchery.textures.get_used_textures(mat)
        return any(hatchery.textures.is_materialiq_texture(t) for t in textures)

    def execute(self, context: bpy.types.Context):
        textures = hatchery.textures.get_used_textures(context.active_object.active_material)
        hatchery.textures.change_texture_sizes(int(self.max_size), textures)
        self.report(
            {"INFO"},
            f"Changed active material '{context.active_object.active_material.name}' "
            f"texture sizes to {self.max_size}",
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ChangeTextureSizeActiveMaterial)


@polib.log_helpers_bpy.logged_operator
class SyncTextureNodes(bpy.types.Operator):
    bl_idname = "engon.materialiq_sync_texture_nodes"
    bl_label = "Sync Texture Nodes"
    bl_description = (
        "Synchronizes values of all texture nodes inside active material (for the "
        "same image) with values from texture node displayed in Textures Panel. Currently "
        "does not sync sequence properties and colorspace settings"
    )

    node_tree_name: bpy.props.StringProperty(
        name="Node Tree Name", description="Name of node tree containing textures to be synced"
    )

    @staticmethod
    def sync_texture_node_values(
        src: bpy.types.ShaderNodeTexImage, targets: typing.Iterable[bpy.types.ShaderNodeTexImage]
    ) -> None:
        """Sets values of blender defined properties from 'src' node to all nodes in 'targets'

        This currently doesn't sync sequence properties or nested property groups.
        """
        # Find out the set of property names that needs to be synced. This is done by accessing
        # properties defined by 'src' - bpy.types.ShaderNodeTexImage and 'src.bl_rna.base' - base
        # shader node. When we subtract properties defined by the base node from the NodeTexImage
        # node (only writable ones!) we get only the NodeTexImage defined properties
        tex_image_node_all_prop_names = {
            p.identifier for p in src.bl_rna.properties if not p.is_readonly
        }
        base_node_prop_names = set(src.bl_rna.base.bl_rna.properties.keys())
        tex_image_node_prop_names = tex_image_node_all_prop_names - base_node_prop_names
        for prop_name in tex_image_node_prop_names:
            prop_value = getattr(src, prop_name, None)
            if prop_value is None:
                continue

            for target in targets:
                setattr(target, prop_name, prop_value)

    def execute(self, context: bpy.types.Context):
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return {'CANCELLED'}

        node_tree = bpy.data.node_groups.get(self.node_tree_name, None)
        if node_tree is None:
            self.report({'ERROR'}, f"Node tree called '{self.node_tree_name}' doesn't exist")
            return {'CANCELLED'}

        channel_nodes_map = polib.node_utils_bpy.get_channel_nodes_map(node_tree)
        for nodes in channel_nodes_map.values():
            if len(nodes) <= 1:
                continue

            SyncTextureNodes.sync_texture_node_values(nodes[0], nodes[1:])

        return {'FINISHED'}


MODULE_CLASSES.append(SyncTextureNodes)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
