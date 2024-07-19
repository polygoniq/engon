# copyright (c) 2018- polygoniq xyz s.r.o.
# This module contains the materialiq displacement functionality.

# Some of the code is repeated and could be reused from 'polib/node_utils_bpy', but that would mean
# we have to split the semantically correct module into two modules in 'polib' and in 'hatchery'
# as we don't want to import polib here.


import bpy
import typing


def _get_top_level_material_outputs(
    node_tree: bpy.types.NodeTree,
) -> typing.Set[bpy.types.ShaderNodeOutputMaterial]:
    ret = set()
    for node in node_tree.nodes:
        if isinstance(node, bpy.types.ShaderNodeOutputMaterial):
            ret.add(node)

    return ret


def _get_displacement_nodegroups(
    node_tree: bpy.types.NodeTree,
) -> typing.Set[bpy.types.ShaderNodeGroup]:
    ret = set()
    for node in node_tree.nodes:
        if not hasattr(node, "node_tree"):
            continue

        if node.node_tree.name.startswith("mq_Displacement"):
            ret.add(node)
        else:
            ret.update(_get_displacement_nodegroups(node.node_tree))

    return ret


def unlink_displacement(material: bpy.types.Material) -> None:
    if material.node_tree is None:
        # it's not using nodes or the node_tree is invalid
        return

    material_output_nodes = _get_top_level_material_outputs(material.node_tree)

    for material_output_node in material_output_nodes:
        # Find links connected to the material output node "Displacement" socket and unlink them
        for link in material.node_tree.links:
            if link.to_node != material_output_node:
                continue
            if link.to_socket.name != "Displacement":
                continue

            material.node_tree.links.remove(link)
            break


def can_link_displacement(material: bpy.types.Material) -> bool:
    if material.node_tree is None:
        return False

    displacement_nodegroups = _get_displacement_nodegroups(material.node_tree)

    return len(displacement_nodegroups) == 1


def link_displacement(material: bpy.types.Material) -> None:
    if material.node_tree is None:
        # it's not using nodes or the node_tree is invalid
        return

    displacement_nodegroups = _get_displacement_nodegroups(material.node_tree)
    if len(displacement_nodegroups) != 1:
        raise RuntimeError(
            f"Tried to link materialiq displacement in {material.name} which does not have the "
            f"mq_Displacement node or there are multiple such nodes."
        )

    displacement_nodegroup = displacement_nodegroups.pop()

    material_output_nodes = _get_top_level_material_outputs(material.node_tree)

    for material_output_node in material_output_nodes:
        material.node_tree.links.new(
            displacement_nodegroup.outputs["Displacement"],
            material_output_node.inputs["Displacement"],
        )
