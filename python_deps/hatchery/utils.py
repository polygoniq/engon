# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import bmesh
import rna_prop_ui


def copy_custom_prop(src: bpy.types.ID, dst: bpy.types.ID, prop_name: str) -> None:
    """Copies custom property 'prop_name' from 'src' to 'dst' while preserving its settings"""
    # In order to copy the property with its configuration (min, max, subtype, etc)
    # we need to use following code. Code is taken from the "Copy Attributes" addon that's
    # shipped within Blender.

    # Create the property.
    dst[prop_name] = src[prop_name]
    # Copy the settings of the property.
    try:
        dst_prop_manager = dst.id_properties_ui(prop_name)
    except TypeError:
        # Python values like lists or dictionaries don't have any settings to copy.
        # They just consist of a value and nothing else.
        # Note: This also skips copying the properties that cannot be edited by
        # id_properties_ui
        return

    src_prop_manager = src.id_properties_ui(prop_name)
    assert src_prop_manager, f"Property '{prop_name}' not found in {src}"

    dst_prop_manager.update_from(src_prop_manager)

    # Copy the Library Overridable flag, which is stored elsewhere, sometimes it's not possible
    # to copy the library override
    try:
        prop_rna_path = f'["{prop_name}"]'
        is_lib_overridable = src.is_property_overridable_library(prop_rna_path)
        dst.property_overridable_library_set(prop_rna_path, is_lib_overridable)
    except:
        pass


def copy_custom_props(
    src: bpy.types.ID, dst: bpy.types.ID, only_existing: bool = False, recursive: bool = False
) -> None:
    """Copies all custom properties from 'src' to 'dst'

    If 'only_existing' is True, then properties that don't exist on
    the 'dst' object are not created, only values of existing properties are
    updated.

    If 'recursive' is provided the property is copied to all children of 'dst' object
    """
    if recursive:
        for child in dst.children:
            copy_custom_props(src, child, only_existing, recursive)

    for prop_name in src.keys():
        if only_existing and prop_name not in dst:
            continue

        copy_custom_prop(src, dst, prop_name)


def ensure_particle_naming_consistency(
    modifier: bpy.types.ParticleSystemModifier, particle_system: bpy.types.ParticleSystem
) -> None:
    """
    Particle data gets duplicated and has the object duplicate suffix on copy, but modifiers and particle system names do not.
    This function ensures the same naming on the whole particle system -> modifier, data, particle system, instance_collection

    Using the name from instance collection is currently the best approach. Creating modifier creates particle data automatically,
    but we don't want to use those, we use the ones loaded from our blends (this gives them .001). Instance collections have the most
    correct duplicate suffix because we have almost full control over them (at least when we are creating them).
    """
    if modifier is None or particle_system is None:
        raise RuntimeError(
            "Cannot ensure naming consistency if modifier or particle_system is None!"
        )

    ps_settings = particle_system.settings
    if ps_settings is None or ps_settings.instance_collection is None:
        raise RuntimeError(
            f"Cannot ensure naming consistency if particle_system ({particle_system.name}) has no settings or no instance_collection!"
        )

    modifier.name = particle_system.name = ps_settings.name = ps_settings.instance_collection.name


def get_area_based_particle_count(
    obj: bpy.types.Object, density: float, max_particle_count: int, include_weights: bool = False
) -> typing.Tuple[int, int]:
    mesh_area = calculate_mesh_area(obj, include_weights)
    particle_count = int(mesh_area * density)
    if particle_count > max_particle_count:
        return max_particle_count, particle_count - max_particle_count
    return particle_count, 0


def calculate_mesh_area(obj: bpy.types.Object, include_weight: bool = False) -> float:
    mesh = obj.data
    try:
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh)
        else:
            bm = bmesh.new()
            bm.from_mesh(mesh)

        bm.transform(obj.matrix_world)
        if include_weight:
            vg = obj.vertex_groups.active
            mesh_area = 0
            for face in bm.faces:
                f_area = face.calc_area()
                weighted_verts = 0
                weight = 0
                for v in face.verts:
                    # heavy approach, but we don't know whether i vertex is in the group :(
                    try:
                        weight += vg.weight(v.index)
                        weighted_verts += 1
                    except:
                        pass
                if weighted_verts > 0:
                    mesh_area += (weight / weighted_verts) * f_area
        else:
            mesh_area = sum(f.calc_area() for f in bm.faces)

    finally:
        bm.free()

    return mesh_area


def can_have_materials_assigned(obj: bpy.types.Object) -> bool:
    """Checks whether given object can have materials assigned

    We check for multiple things: type of the object and the availability of material_slots.
    """

    # In theory checking the availability of material_slots is not necessary, all these
    # object types should have it. We check for it to avoid exceptions and errors in our code.
    return obj.type in {
        'MESH',
        'CURVE',
        'SURFACE',
        'META',
        'FONT',
        'GPENCIL',
        'VOLUME',
    } and hasattr(obj, "material_slots")
