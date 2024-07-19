# copyright (c) 2018- polygoniq xyz s.r.o.

# This module contains functions that are used to spawn the asset - get the asset into the scene.
#
# The function here can adjust context and are more high level. The 'load' module is more low-level
# and serves only for loading the datablocks.
#
# Each asset type has its function and spawn options. Spawn options define properties that can
# change the behavior of the spawn function.

import bpy
import abc
import dataclasses
import mathutils
import typing
import logging

from . import utils
from . import load
from . import textures
from . import displacement

logger = logging.getLogger(f"polygoniq.{__name__}")


@dataclasses.dataclass
class DatablockSpawnOptions:
    """Base for all spawn options

    Currently this is empty, but can store option relevant to all asset types.
    """

    pass


class SpawnedData(abc.ABC):
    def __init__(self, datablocks: typing.Set[bpy.types.ID]):
        self.datablocks = datablocks


@dataclasses.dataclass
class ModelSpawnOptions(DatablockSpawnOptions):
    parent_collection: typing.Optional[bpy.types.Collection] = None
    # If present the spawned model instancer is selected, other objects are deselected
    select_spawned: bool = False
    location_override: typing.Optional[mathutils.Vector] = None
    rotation_euler_override: typing.Optional[mathutils.Euler] = None


class ModelSpawnedData(SpawnedData):
    def __init__(self, collection: bpy.types.Collection, instancer: bpy.types.Object):
        self.collection = collection
        self.instancer = instancer
        super().__init__({collection, instancer})


def spawn_model(
    path: str, context: bpy.types.Context, options: ModelSpawnOptions
) -> ModelSpawnedData:
    """Loads model from given 'path' and instances it on empty on cursor position.

    This assumes the path contains 'master' collection - check load.load_master_collection.
    Further spawn behavior like parent collection can be tweaked in ModelSpawnOptions.

    Returns the empty that instances the model 'master' collection.
    """

    if options.parent_collection is None and options.select_spawned:
        raise RuntimeError(
            "Wrong arguments: Cannot select spawned model objects without a parent collection. "
            "The object wouldn't be present in the View Layer!"
        )

    root_collection = load.load_master_collection(path)
    root_empty = bpy.data.objects.new(root_collection.name, None)
    root_empty.instance_type = 'COLLECTION'
    root_empty.instance_collection = root_collection
    root_empty.location = context.scene.cursor.location
    if options.location_override is not None:
        root_empty.location = options.location_override

    if options.rotation_euler_override is not None:
        root_empty.rotation_euler = options.rotation_euler_override

    # Copy all children properties from the instanced objects to the instancer object
    for obj in root_empty.instance_collection.all_objects:
        if obj.library is None:
            continue

        utils.copy_custom_props(obj, root_empty)

    for col in root_empty.users_collection:
        col.objects.unlink(root_empty)

    if options.parent_collection is not None:
        options.parent_collection.objects.link(root_empty)

        # Only change selection if we linked the object, so it is present in view layer and if
        # caller wants to.
        if options.select_spawned:
            for selected_obj in context.selected_objects:
                selected_obj.select_set(False)

            root_empty.select_set(True)

    return ModelSpawnedData(root_collection, root_empty)


@dataclasses.dataclass
class MaterialSpawnOptions(DatablockSpawnOptions):
    texture_size: int = 2048
    use_displacement: bool = False
    target_objects: typing.Set[bpy.types.Object] = dataclasses.field(default_factory=set)


class MaterialSpawnedData(SpawnedData):
    def __init__(self, material: bpy.types.Material):
        self.material = material
        super().__init__({material})


def spawn_material(
    path: str, context: bpy.types.Context, options: MaterialSpawnOptions
) -> MaterialSpawnedData:
    """Loads material from 'path' and adds it to all selected objects containing material slots.

    (materialiq materials only)
    Automatically changes texture sizes and links / unlinks displacement based on spawning options.

    Returns the spawned material.
    """
    material = load.load_material(path)
    for obj in options.target_objects:
        if not utils.can_have_materials_assigned(obj):
            continue
        if len(obj.material_slots) < 1:
            obj.data.materials.append(material)
        else:
            obj.material_slots[obj.active_material_index].material = material

    textures.change_texture_sizes(options.texture_size, textures.get_used_textures(material))

    if displacement.can_link_displacement(material):
        if options.use_displacement:
            displacement.link_displacement(material)
        else:
            displacement.unlink_displacement(material)

    return MaterialSpawnedData(material)


@dataclasses.dataclass
class ParticleSystemSpawnOptions(DatablockSpawnOptions):
    display_type: str = 'TEXTURED'
    display_percentage: float = 100.0
    instance_collection_parent: typing.Optional[bpy.types.Collection] = None
    include_base_material: bool = True
    max_particle_count: int = 10000
    # count is used when preserve_density is False
    count: int = 1000
    preserve_density: bool = True
    target_objects: typing.Set[bpy.types.Object] = dataclasses.field(default_factory=set)


class ParticlesSpawnedData(SpawnedData):
    def __init__(
        self,
        particles: typing.Iterable[bpy.types.ParticleSettings],
        material: typing.Optional[bpy.types.Material] = None,
    ):
        self.particles = particles
        self.material = material
        datablocks = set(particles)
        if material is not None:
            datablocks.add(material)
        super().__init__(datablocks)


def spawn_particles(
    path: str, context: bpy.types.Context, options: ParticleSystemSpawnOptions
) -> ParticlesSpawnedData:
    """Loads all particle systems from a given path and puts them on objects based on options.

    Returns list of particle settings that were loaded.
    """
    all_particle_settings = load.load_particles(path)

    # Get lowest z location from target objects and calculate total mesh are of all target objects
    # so the instanced objects locations and particle counts are adjusted properly.
    lowest_obj_z = 0.0
    total_mesh_area = 0.0
    for target_obj in options.target_objects:
        lowest_obj_z = min(target_obj.location.z, lowest_obj_z)
        total_mesh_area += utils.calculate_mesh_area(target_obj)

    for particle_settings in all_particle_settings:
        particle_settings.display_percentage = options.display_percentage
        for obj in particle_settings.instance_collection.all_objects:
            # We spawn all objects 10units below the lowest location of target objects
            obj.location.z = lowest_obj_z - 10.0
            obj.display_type = options.display_type

        if options.instance_collection_parent is not None:
            options.instance_collection_parent.children.link(particle_settings.instance_collection)

        if options.preserve_density:
            new_count = int(total_mesh_area * particle_settings.pps_density)
            if new_count > options.max_particle_count:
                logger.warning(
                    f"Particle count exceeded maximum by: {int(new_count - options.max_particle_count)}"
                )
                new_count = options.max_particle_count
        else:
            new_count = options.count
        particle_settings.count = new_count

        for target_obj in options.target_objects:
            # Create modifiers and adjust particle system settings based on spawn options
            mod: bpy.types.ParticleSystemModifier = target_obj.modifiers.new(
                particle_settings.name, type='PARTICLE_SYSTEM'
            )
            mod.particle_system.settings = particle_settings
            utils.ensure_particle_naming_consistency(mod, mod.particle_system)

    spawned_material_data = None
    if options.include_base_material:
        spawned_material_data = spawn_material(
            path, context, MaterialSpawnOptions(target_objects=options.target_objects)
        )

    return ParticlesSpawnedData(
        all_particle_settings,
        spawned_material_data.material if spawned_material_data is not None else None,
    )


class WorldSpawnedData(SpawnedData):
    def __init__(self, world: bpy.types.World):
        self.world = world
        super().__init__({world})


def spawn_world(
    path: str, context: bpy.types.Context, options: DatablockSpawnOptions
) -> WorldSpawnedData:
    """Loads world from 'path' and replaces current scene world with it, returns the loaded world."""
    world = load.load_world(path)
    context.scene.world = world
    return WorldSpawnedData(world)


class SceneSpawnedData(SpawnedData):
    def __init__(self, scene: bpy.types.Scene):
        self.scene = scene
        super().__init__({scene})


def spawn_scene(
    path: str, context: bpy.types.Context, options: DatablockSpawnOptions
) -> SceneSpawnedData:
    """Loads scene from 'path' and replaces current scene with it, returns the loaded scene."""
    scene = load.load_scene(path)
    context.window.scene = scene
    return SceneSpawnedData(scene)


@dataclasses.dataclass
class GeometryNodesSpawnOptions(DatablockSpawnOptions):
    parent_collection: typing.Optional[bpy.types.Collection] = None


class GeometryNodesSpawnedData(SpawnedData):
    def __init__(
        self, container_obj: bpy.types.Object, modifiers: typing.Iterable[bpy.types.Modifier]
    ):
        self.container_obj = container_obj
        self.modifiers = modifiers
        super().__init__({container_obj} | {m.node_group for m in modifiers})


def spawn_geometry_nodes(
    path: str, context: bpy.types.Context, options: GeometryNodesSpawnOptions
) -> GeometryNodesSpawnedData:
    """Loads object with the same name as basename of 'path' and adds it to the scene collection"""
    # Currently default behavior is to append the object containing the geometry nodes.
    # TODO: In future we want to load either node group into node tree, apply onto active
    # object and choose whether to start draw, or edit mode.
    obj = load.load_master_object(path)
    if options.parent_collection is not None:
        options.parent_collection.objects.link(obj)

    # Due to a bug in Blender while converting boolean inputs we reassign the modifier node
    # group when spawning. The bug happens when object with modifiers is appended from a blend
    # file, where the modifier node group is linked from a different file. First append is
    # correct, but any subsequently appended object with the same modifier triggers the:
    # 'Property type does not match input socket (NAME)' error and can make some setups not work
    # Issue link: https://projects.blender.org/blender/blender/issues/110825
    for mod in obj.modifiers:
        if mod.type == 'NODES':
            mod.node_group = mod.node_group

    return GeometryNodesSpawnedData(obj, {m for m in obj.modifiers if m.type == 'NODES'})
