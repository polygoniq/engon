# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import os
import typing


def try_get_linked_datablock(
    datablock_collection: bpy.types.bpy_prop_collection, datablock_name: str, blend_path: str
) -> typing.Optional[bpy.types.ID]:
    """Returns datablock 'datablock_name' linked from 'blend_path' or None if datablock wasn't linked yet.

    Tries to find library corresponding to 'blend_path' and then checks if there's the datablock
    'datablock_name' linked from this library.
    """
    # Filenames longer than 63 characters are cropped in Blender
    expected_lib_name = os.path.basename(blend_path)[:63]
    # This is not 100% reliable, there can be multiple libraries with the same name, so we also
    # check if library.filepath is the same as the blend_path later.
    library = bpy.data.libraries.get(expected_lib_name, None)
    if library is None:
        return None

    lib_path = bpy.path.abspath(library.filepath)
    blend_path = os.path.abspath(blend_path)
    try:
        if os.path.samefile(lib_path, blend_path):
            return datablock_collection.get((datablock_name, library.filepath), None)
    except OSError:
        pass
    return None


def load_master_collection(blend_path: str, link: bool = True) -> bpy.types.Collection:
    """Links master collection from 'blend_path' and returns it.

    Master collection is the collection with the same name as basename of the 'blend_path'
    """
    asset_name, _ = os.path.splitext(os.path.basename(blend_path))
    if link:
        # Check if collection is already linked. Linking already linked collection doesn't do
        # anything wrong, Blender recognizes that the same collection is already linked. However it
        # prints warning: "WARN (blo.readfile): ...\readfile.c:4543 link_named_part: Append: ID 'ASSET_NAME' is already linked"
        # which looks unprofessional.
        linked_collection = try_get_linked_datablock(bpy.data.collections, asset_name, blend_path)
        if linked_collection is not None:
            return linked_collection

    with bpy.data.libraries.load(blend_path, link=link) as (data_from, data_to):
        # The root collection of the asset should have the same name as the asset name
        assert asset_name in data_from.collections
        data_to.collections = [asset_name]

    return data_to.collections[0]


def load_material(blend_path: str) -> bpy.types.Material:
    """Appends material 'blend_path' to current file and returns it.

    This allows loading materials from .blend file that are linked. The assumption here is
    that the .blend has to contain a mesh with the same name as the material - this loads the
    mesh and gets access to its material which is then returned.
    """
    asset_name, _ = os.path.splitext(os.path.basename(blend_path))
    # We use two approaches to load material:
    # 1. Material is present in the blend_path -> load first one
    # 2. Material is not available in data_from -> Material can be linked in the source file so it
    #    isn't available through the load API. We take the first mesh in the data and load the
    #    material from there.
    #
    # We use those two approaches because the materials can be linked from the library in the
    # material sources directly if artists want to use the materials in assets too (simplifies
    # linking and changes a lot).
    using_transfer_mesh = False
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        if len(data_from.materials) > 0:
            assert len(data_from.materials) > 0
            data_to.materials = [data_from.materials[0]]
        else:
            if asset_name in data_from.meshes:
                data_to.meshes = [asset_name]
                using_transfer_mesh = True

    if using_transfer_mesh:
        transfer_mesh: bpy.types.Mesh = data_to.meshes[0]
        assert len(transfer_mesh.materials) > 0
        material = transfer_mesh.materials[0].make_local()
        bpy.data.meshes.remove(transfer_mesh)
    else:
        material = data_to.materials[0]

    return material


def load_particles(blend_path: str) -> typing.List[bpy.types.ParticleSettings]:
    """Loads are particle system from 'blend_path' and returns them."""
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.particles = data_from.particles

    assert len(data_to.particles) > 0
    return data_to.particles


def load_world(blend_path: str) -> bpy.types.World:
    """Loads first world from 'blend_path' and returns it."""
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        assert len(data_from.worlds) > 0
        data_to.worlds = [data_from.worlds[0]]

    world = data_to.worlds[0]
    return world


def load_scene(blend_path: str) -> bpy.types.Scene:
    """Loads first scene from 'blend_path' and returns it."""
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        assert len(data_from.scenes) > 0
        data_to.scenes = [data_from.scenes[0]]

    return data_to.scenes[0]


def load_master_object(blend_path: str) -> bpy.types.Object:
    """Loads object with the same name as basename of the given .blend path"""
    asset_name, _ = os.path.splitext(os.path.basename(blend_path))
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        assert len(data_from.objects) > 0
        data_to.objects = [asset_name]

    return data_to.objects[0]
