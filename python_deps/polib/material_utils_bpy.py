# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import numpy
import typing
from . import node_utils_bpy


def safe_get_active_material(
    obj: typing.Optional[bpy.types.Object],
) -> typing.Optional[bpy.types.Material]:
    """Returns active material of object. Returns None if object is None"""
    if obj is None:
        return None

    return obj.active_material


def is_material_slot_used_on_geometry(
    obj: bpy.types.Object,
    material_index: int,
    used_indices: typing.Optional[typing.FrozenSet[int]] = None,
) -> bool:
    """Returns whether a material slot on given index contains a material that is used
    by a given Object's geometry.

    Pass used_indices if this function is used in a loop for performance reasons.
    """
    try:
        slot = obj.material_slots[material_index]
    except IndexError:
        raise Exception(f"Invalid material index {material_index} on {obj}")

    if slot.material is None:
        return False

    if used_indices is None:
        used_indices = get_material_slots_used_by_mesh(obj)
        used_indices |= get_material_slots_used_by_spline(obj)
        used_indices |= get_material_slots_used_by_text(obj)

    return material_index in used_indices


def is_material_used_on_geonodes(
    obj: bpy.types.Object,
    material_index: int,
    geonode_materials: typing.Optional[typing.FrozenSet[bpy.types.Material]] = None,
) -> bool:
    """Returns whether a material slot on given index contains a material that is used
    by a given Object's geometry nodes modifiers.

    Pass geonode_materials if this function is used in a loop for performance reasons.
    """
    try:
        slot = obj.material_slots[material_index]
    except IndexError:
        raise Exception(f"Invalid material index {material_index} on {obj}")

    if slot.material is None:
        return False

    if geonode_materials is None:
        geonode_materials = get_materials_used_by_geonodes(obj)

    obj_mat_name = slot.material.name
    geonode_mats_names = [material.name for material in geonode_materials]
    return obj_mat_name in geonode_mats_names


def get_material_slots_used_by_mesh(obj: bpy.types.Object) -> typing.FrozenSet[int]:
    """Return a FrozenSet[material_index] used by a given Object's mesh"""
    if not hasattr(obj.data, "polygons"):
        return frozenset()

    material_indices = numpy.zeros(len(obj.data.polygons), dtype=numpy.int32)
    obj.data.polygons.foreach_get('material_index', material_indices)
    unique_indices = numpy.unique(material_indices)
    return frozenset(unique_indices)


def get_material_slots_used_by_spline(obj: bpy.types.Object) -> typing.FrozenSet[int]:
    """Return a FrozenSet[material_index] used by a given Object's splines"""
    if not hasattr(obj.data, "splines"):
        return frozenset()

    seen_indices = set()
    for spline in obj.data.splines:
        seen_indices.add(spline.material_index)

    return frozenset(seen_indices)


def get_material_slots_used_by_text(obj: bpy.types.Object) -> typing.FrozenSet[int]:
    """Return a FrozenSet[material_index] used by a given Object's texts"""
    if not hasattr(obj.data, "body_format"):
        return frozenset()

    seen_indices = set()
    for character in obj.data.body_format:
        seen_indices.add(character.material_index)

    return frozenset(seen_indices)


def get_materials_used_by_geonodes(obj: bpy.types.Object) -> typing.FrozenSet[bpy.types.Material]:
    """Returns a FrozenSet[Material] used by a given Object's geometry nodes modifiers."""

    used_materials = set()
    for mod in obj.modifiers:
        if mod.type != 'NODES':
            continue

        if mod.node_group is None:
            continue

        # Scan modifier inputs
        for input_ in node_utils_bpy.get_node_tree_inputs_map(mod.node_group).values():
            if node_utils_bpy.get_socket_type(input_) == 'NodeSocketMaterial':
                mat = mod[input_.identifier]
                if mat is not None:
                    used_materials.add(mat)

        for node in node_utils_bpy.find_nodes_in_tree(mod.node_group):
            for node_input in filter(lambda i: i.type == 'MATERIAL', node.inputs):
                if node_input.default_value is not None:
                    used_materials.add(node_input.default_value)
            if hasattr(node, 'material'):
                if node.material is not None:
                    used_materials.add(node.material)

    return frozenset(used_materials)
