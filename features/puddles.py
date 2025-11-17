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
import mathutils
from . import feature_utils
from . import asset_pack_panels
from .. import polib
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[type] = []


def ensure_puddles_nodegroup(context: bpy.types.Context) -> None:
    puddle_nodegroup = bpy.data.node_groups.get(asset_helpers.AQ_PUDDLES_NODEGROUP_NAME, None)
    if puddle_nodegroup is not None:
        return
    material_library_path = asset_helpers.get_asset_pack_library_path(
        "aquatiq", asset_helpers.AQ_MATERIALS_LIBRARY_BLEND
    )

    if material_library_path is None:
        raise RuntimeError("Material library path of aquatiq not found!")

    with bpy.data.libraries.load(material_library_path, link=False) as (data_from, data_to):
        assert (
            asset_helpers.AQ_PUDDLES_NODEGROUP_NAME in data_from.node_groups
        ), f"Nodegroup {asset_helpers.AQ_PUDDLES_NODEGROUP_NAME} not found in {material_library_path}"
        data_to.node_groups = [asset_helpers.AQ_PUDDLES_NODEGROUP_NAME]


def can_material_have_effect(mat: bpy.types.Material) -> tuple[bool, str]:
    """Checks if material can have effects applied, if not it returns False and reason why not
    for user report, otherwise returns True and empty string.
    """

    if mat is None:
        return False, f"No valid active material!"

    if mat.library is not None:
        return False, f"{mat.name} is linked!"

    if mat.node_tree is None:
        return False, f"{mat.name} has no node tree!"

    return True, ""


def get_active_material_output(
    mat: bpy.types.Material,
) -> bpy.types.ShaderNodeOutputMaterial | None:
    material_outputs = polib.node_utils_bpy.find_nodes_by_bl_idname(
        mat.node_tree.nodes, "ShaderNodeOutputMaterial", recursive=False
    )

    for mat_out in material_outputs:
        if mat_out.is_active_output:
            return mat_out
    return None


def get_displacement_node_input(node: bpy.types.Node) -> bpy.types.NodeSocket | None:
    if isinstance(node, bpy.types.ShaderNodeDisplacement):
        return node.inputs["Height"]

    elif isinstance(node, bpy.types.ShaderNodeGroup):
        if node.node_tree is not None:
            if node.node_tree.name == "mq_Displacement":
                return node.inputs["Height Map"]
    return None


def check_puddles_nodegroup_count(
    objects: typing.Iterable[bpy.types.Object], predicate: typing.Callable[[int], bool]
) -> bool:
    for obj in objects:
        if obj.type not in {'MESH', 'CURVE'}:
            continue

        mat = polib.material_utils_bpy.safe_get_active_material(obj)
        if mat is None:
            continue
        can_have_effect, _ = can_material_have_effect(mat)
        if not can_have_effect:
            continue

        puddles_instances = polib.node_utils_bpy.find_nodegroups_by_name(
            mat.node_tree, asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
        )
        if predicate(len(puddles_instances)):
            return True
    return False


@polib.log_helpers_bpy.logged_operator
class AddPuddles(bpy.types.Operator):
    bl_idname = "engon.aquatiq_add_puddles"
    bl_label = "Add Puddles"
    bl_description = "Add puddles on active materials of selected objects"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return check_puddles_nodegroup_count(context.selected_objects, lambda x: x == 0)

    def execute(self, context: bpy.types.Context):
        try:
            ensure_puddles_nodegroup(context)
        except Exception as e:
            logger.exception("Uncaught exception when loading puddles node group!")
            self.report({'ERROR'}, f"Failed to load the puddles node group!")
            return {'FINISHED'}

        for obj in context.selected_objects:
            if obj.type not in {'MESH', 'CURVE'}:
                continue

            mat = obj.active_material

            can_have_effect, report = can_material_have_effect(mat)
            if not can_have_effect:
                self.report({'WARNING'}, f"{obj.name} - {report}")
                continue

            material_output = get_active_material_output(mat)
            if material_output is None:
                self.report({'WARNING'}, f"{mat.name} has no active Material Output!")
                continue

            surface_input = material_output.inputs.get("Surface")
            if not surface_input.is_linked:
                self.report({'WARNING'}, f"Material Output in '{mat.name}' has no Surface input!")
                continue

            nodes = mat.node_tree.nodes
            # Use existing nodegroup if possible, otherwise create new
            puddles_instances = polib.node_utils_bpy.find_nodegroups_by_name(
                mat.node_tree, asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
            )
            if len(puddles_instances) > 0:
                puddles_instance = puddles_instances.pop()
            else:
                puddles_instance = nodes.new('ShaderNodeGroup')
                puddles_instance.node_tree = bpy.data.node_groups.get(
                    asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
                )

            puddles_instance.location = material_output.location - mathutils.Vector((200.0, 0))
            puddles_instance.name = asset_helpers.AQ_PUDDLES_NODEGROUP_NAME

            links = mat.node_tree.links
            # If the instance node was already there but has no shader input for some reason,
            # don't connect its output to its input creating circular dependency
            if surface_input.links[0].from_node != puddles_instance:
                links.new(surface_input.links[0].from_socket, puddles_instance.inputs["Shader"])
            links.new(puddles_instance.outputs["Shader"], surface_input)

            mat_displacement_input = material_output.inputs.get("Displacement")
            if mat_displacement_input.is_linked:
                mat_displacement_input_node = mat_displacement_input.links[0].from_node
                height_input = get_displacement_node_input(mat_displacement_input_node)

                if height_input is not None and height_input.is_linked:
                    links.new(height_input.links[0].from_socket, puddles_instance.inputs["Height"])
                    links.new(puddles_instance.outputs["Height"], height_input)
                    puddles_instance.location = (
                        mat_displacement_input_node.location - mathutils.Vector((200.0, 0))
                    )
                    puddles_instance.inputs["Use Height"].default_value = 1.0

            mask = obj.data.vertex_colors.get(asset_helpers.AQ_MASK_NAME, None)
            if mask is None:
                mask = obj.data.vertex_colors.new(name=asset_helpers.AQ_MASK_NAME)

            logger.info(
                f"Added effect {asset_helpers.AQ_PUDDLES_NODEGROUP_NAME} from material {mat.name}"
            )

        return {'FINISHED'}


MODULE_CLASSES.append(AddPuddles)


@polib.log_helpers_bpy.logged_operator
class RemovePuddles(bpy.types.Operator):
    bl_idname = "engon.aquatiq_remove_puddles"
    bl_label = "Remove Puddles"
    bl_description = "Remove puddles from active materials of selected objects"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return check_puddles_nodegroup_count(context.selected_objects, lambda x: x > 0)

    def execute(self, context: bpy.types.Context):
        for obj in context.selected_objects:
            if obj.type not in {'MESH', 'CURVE'}:
                continue

            mat = obj.active_material

            can_have_effect, report = can_material_have_effect(mat)
            if not can_have_effect:
                self.report({'WARNING'}, f"{obj.name} - {report}")
                continue

            puddles_nodes = polib.node_utils_bpy.find_nodegroups_by_name(
                mat.node_tree, asset_helpers.AQ_PUDDLES_NODEGROUP_NAME
            )
            if len(puddles_nodes) == 0:
                continue

            puddles_instance = puddles_nodes.pop()

            links = mat.node_tree.links

            shader_input = puddles_instance.inputs["Shader"]
            shader_output = puddles_instance.outputs["Shader"]

            if shader_input.is_linked and shader_output.is_linked:
                links.new(shader_input.links[0].from_socket, shader_output.links[0].to_socket)

            height_input = puddles_instance.inputs["Height"]
            height_output = puddles_instance.outputs["Height"]

            if height_input.is_linked and height_output.is_linked:
                links.new(height_input.links[0].from_socket, height_output.links[0].to_socket)

            mat.node_tree.nodes.remove(puddles_instance)
            logger.info(
                f"Removed effect {asset_helpers.AQ_PUDDLES_NODEGROUP_NAME} from material {mat.name}"
            )
        return {'FINISHED'}


MODULE_CLASSES.append(RemovePuddles)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class PuddlesPanel(feature_utils.EngonFeaturePanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_puddles"
    bl_parent_id = asset_pack_panels.AquatiqPanel.bl_idname
    bl_label = "Puddles"
    bl_options = {'DEFAULT_CLOSED'}

    feature_name = "puddles"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.AQ_PUDDLES_NODEGROUP_NAME,
        filter_=lambda x: not polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Water Color",
            "Noise Scale",
        ),
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return super().poll(context) and context.mode != 'PAINT_VERTEX'

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='MATFLUID')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout

        layout.operator(AddPuddles.bl_idname, icon='ADD')
        layout.operator(RemovePuddles.bl_idname, icon='PANEL_CLOSE')

        if context.active_object is not None and check_puddles_nodegroup_count(
            [context.active_object], lambda x: x != 0
        ):
            col = layout.column(align=True)
            PuddlesPanel.template.draw_from_material(context.active_object.active_material, col)


MODULE_CLASSES.append(PuddlesPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
