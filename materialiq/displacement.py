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
import hatchery
from .. import asset_helpers
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


DRAW_MODIFIER_PROPS: typing.Dict[str, typing.List[str]] = {
    "mq_Remesh": ["octree_depth", "scale"],
    "mq_Subdivision": ["levels", "render_levels"],
    "mq_Displacement": ["strength", "mid_level"],
    "mq_Subdivision_Adaptive": []
}

# Shader displacement strength and modifier strength do not map 1:1, this is approximation to get
# similar results
SHADER_TO_MODIFIER_DISPLACEMENT_STRENGTH_RATIO = 1 / 10


def add_subdiv_modifier(obj: bpy.types.Object, use_adaptive: bool) -> None:
    if use_adaptive:
        mod_name = "mq_Subdivision_Adaptive"
    else:
        mod_name = "mq_Subdivision"

    if not mod_name in obj.modifiers:
        mod = obj.modifiers.new(mod_name, 'SUBSURF')
        mod.subdivision_type = 'SIMPLE'
        if use_adaptive:
            obj.cycles.use_adaptive_subdivision = True


def add_remesh_modifier(obj: bpy.types.Object) -> None:
    if obj.modifiers.get("mq_Remesh"):
        return

    mod = obj.modifiers.new("mq_Remesh", 'REMESH')
    mod.octree_depth = 6
    mod.mode = 'SMOOTH'
    mod.use_remove_disconnected = False


def add_disp_modifier(obj: bpy.types.Object, height_map: bpy.types.Image, height_multiplier: float) -> None:
    if not obj.modifiers.get("mq_Displacement"):
        obj.modifiers.new("mq_Displacement", 'DISPLACE')

    mod = obj.modifiers["mq_Displacement"]

    if height_map.name not in bpy.data.textures:
        disp_texture = bpy.data.textures.new(height_map.name, 'IMAGE')
        disp_texture.image = height_map

    mod.texture = bpy.data.textures[height_map.name]
    mod.texture_coords = 'UV'
    mod.strength = height_multiplier * SHADER_TO_MODIFIER_DISPLACEMENT_STRENGTH_RATIO


def is_scene_setup_adaptive_subdiv(context: bpy.types.Context) -> bool:
    return context.scene.cycles.feature_set == 'EXPERIMENTAL' and \
        context.scene.render.engine == 'CYCLES'


def set_scene_adaptive_subdiv(context: bpy.types.Context) -> None:
    context.scene.cycles.feature_set = 'EXPERIMENTAL'
    context.scene.render.engine = 'CYCLES'


class DisplaceObjectCandidate:
    """Object that has active material containing image node with height map texture
    in it's shader node tree (or node tree of any nested nodegroup).
    """

    def __init__(
        self,
        obj: bpy.types.Object,
        mat: bpy.types.Material,
        height_map: bpy.types.Image,
        height_multiplier: float
    ):
        self.obj = obj
        self.mat = mat
        self.height_map = height_map
        self.height_multiplier = height_multiplier


def get_displacement_object_candidates(objects: typing.List[bpy.types.Object]) -> typing.Iterator[DisplaceObjectCandidate]:
    for obj in objects:
        mat = obj.active_material
        if mat is None:
            continue

        # there are two scenarios either the material is not built and we look for inner node in
        # CustomNodeGroup or we look for image node
        height_image_nodes = polib.node_utils_bpy.find_nodes_in_tree(
            mat.node_tree, lambda x: x.bl_idname in {
                'ShaderNodeTexImage', 'ImageVariableNode'} and x.name.startswith("mq_Height_")
        )

        height_image = None
        for node in height_image_nodes:
            if node.bl_idname == 'ImageVariableNode':
                image = node.node_tree.nodes["Inner Node"].image
                if image is None:
                    continue
                height_image = image
                break
            elif node.bl_idname == 'ShaderNodeTexImage':
                if node.image is None:
                    continue
                height_image = node.image
                break

        if height_image is not None:
            displacement_nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(
                mat.node_tree, "mq_Displacement")
            assert len(
                displacement_nodegroups) == 1, f"'mq_Displacement' nodegroup not found in '{mat.name}'"
            displacement_nodegroup = displacement_nodegroups.pop()
            height_multiplier_socket = polib.node_utils_bpy.get_node_input_socket(
                displacement_nodegroup, "Height Multiplier")
            assert height_multiplier_socket is not None, f"'Height Multiplier' input not found " \
                f"in '{displacement_nodegroup.name}' in '{mat.name}'"
            height_multiplier = height_multiplier_socket.default_value

            yield DisplaceObjectCandidate(obj, mat, height_image, height_multiplier)


@polib.log_helpers_bpy.logged_operator
class AddDisplacement(bpy.types.Operator):
    bl_idname = "engon.materialiq_add_displacement"
    bl_label = "Add Displacement"
    bl_description = "Adds displacement to selected materialiq materials"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return next(get_displacement_object_candidates(context.selected_objects), None) is not None

    displacement_object_candidates: typing.List[DisplaceObjectCandidate] = []

    add_subdiv_mod: bpy.props.BoolProperty(
        name="Subdivision Surface Modifier",
        default=False,
        description="Add Subdiv Modifier to modifier stack"
    )

    add_remesh_mod: bpy.props.BoolProperty(
        name="Remesh Modifier (requires Object/World Mapping)",
        default=False,
        description="Add Remesh Modifier to modifier stack"
    )

    add_disp_mod: bpy.props.BoolProperty(
        name="Displacement Modifier (requires UV Mapping)",
        default=False,
        description="Add Displacement Modifier to modifier stack"
    )

    set_scene_adaptive_subdiv: bpy.props.BoolProperty(
        name="Adaptive Subdivision (Set to Cycles and Experimental)",
        default=True,
        description="Will set render engine to Cycles and feature set to Experimental"
    )

    affected_objects: bpy.props.StringProperty(
        name="Displacement Objects and Materials",
        default="",
        description="Dictionary of Objects and their Materials that will have displacement applied"
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        if len(self.displacement_object_candidates) == 0:
            layout.label(
                text="No material with displacement support found in active materials", icon='ERROR')
            return

        layout.prop(self, "add_subdiv_mod")
        layout.prop(self, "add_remesh_mod")
        layout.prop(self, "add_disp_mod")
        layout.prop(self, "set_scene_adaptive_subdiv")
        layout.label(text="Affected Objects : Materials")
        col = layout.column(align=True)
        for dc in self.displacement_object_candidates:
            col.label(text=f"{dc.obj.name} : {dc.mat.name}")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.displacement_object_candidates = list(get_displacement_object_candidates(
            context.selected_objects))
        return context.window_manager.invoke_props_dialog(self, width=600)

    def execute(self, context: bpy.types.Context):
        for displacement_candidate in self.displacement_object_candidates:
            hatchery.displacement.link_displacement(displacement_candidate.mat)
            if self.add_subdiv_mod:
                add_subdiv_modifier(displacement_candidate.obj, use_adaptive=False)
            if self.add_remesh_mod:
                add_remesh_modifier(displacement_candidate.obj)
            if self.add_disp_mod:
                add_disp_modifier(displacement_candidate.obj, displacement_candidate.height_map,
                                  displacement_candidate.height_multiplier)
            if self.set_scene_adaptive_subdiv:
                add_subdiv_modifier(displacement_candidate.obj, use_adaptive=True)
                set_scene_adaptive_subdiv(context)

        logger.info(
            f"Added displacement to these objects and their materials: "
            f"{dict({dc.obj.name: dc.mat.name for dc in self.displacement_object_candidates})}"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(AddDisplacement)


@polib.log_helpers_bpy.logged_operator
class RemoveDisplacement(bpy.types.Operator):
    bl_idname = "engon.materialiq_remove_displacement"
    bl_label = "Remove Displacement"
    bl_description = "Removes displacement from selected materialiq materials"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return next(get_displacement_object_candidates(context.selected_objects), None) is not None

    def execute(self, context: bpy.types.Context):
        displacement_candidates = list(get_displacement_object_candidates(context.selected_objects))
        for displacement_candidate in displacement_candidates:
            hatchery.displacement.unlink_displacement(displacement_candidate.mat)

            for mod in displacement_candidate.obj.modifiers:
                if any(mod.name.startswith(x) for x in DRAW_MODIFIER_PROPS):
                    displacement_candidate.obj.modifiers.remove(mod)

        logger.info(
            f"Removed displacement from these objects and their materials: "
            f"{dict({dc.obj.name: dc.mat.name for dc in displacement_candidates})}"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(RemoveDisplacement)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
