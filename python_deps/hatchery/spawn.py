# copyright (c) 2018- polygoniq xyz s.r.o.

# This module contains functions that are used to spawn the asset - get the asset into the scene.
#
# The function here can adjust context and are more high level. The 'load' module is more low-level
# and serves only for loading the datablocks.
#
# Each asset type has its function and spawn options. Spawn options define properties that can
# change the behavior of the spawn function.

import bpy
import bmesh
import abc
import dataclasses
import collections
import math
import mathutils
import typing
import logging
import hashlib

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
    def __init__(self, datablocks: set[bpy.types.ID]):
        self.datablocks = datablocks


@dataclasses.dataclass
class ModelSpawnOptions(DatablockSpawnOptions):
    collection_factory_method: typing.Callable[[], bpy.types.Collection | None] | None = None
    # If present the spawned model instancer is selected, other objects are deselected
    select_spawned: bool = False
    location_override: mathutils.Vector | None = None
    rotation_euler_override: mathutils.Euler | None = None


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

    parent_collection = None
    if options.collection_factory_method is not None:
        parent_collection = options.collection_factory_method()

    if parent_collection is None and options.select_spawned:
        raise RuntimeError(
            "Wrong arguments: Cannot select spawned model objects without a parent collection. "
            "The object wouldn't be present in the View Layer!"
        )

    root_collection = load.load_master_collection(path, link=True)
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

    root_empty.empty_display_size = utils.get_empty_display_size(root_empty)

    for col in root_empty.users_collection:
        col.objects.unlink(root_empty)

    if parent_collection is not None:
        parent_collection.objects.link(root_empty)

        # Only change selection if we linked the object, so it is present in view layer and if
        # caller wants to.
        if options.select_spawned:
            for selected_obj in context.selected_objects:
                selected_obj.select_set(False)

            root_empty.select_set(True)

    return ModelSpawnedData(root_collection, root_empty)


@dataclasses.dataclass
class MaterialSpawnOptions(DatablockSpawnOptions):
    collection_factory_method: typing.Callable[[], bpy.types.Collection | None] | None = None
    texture_size: int = 2048
    use_displacement: bool = False
    select_spawned: bool = True
    target_objects: set[bpy.types.Object] = dataclasses.field(default_factory=set)


class MaterialSpawnedData(SpawnedData):
    def __init__(self, material: bpy.types.Material):
        self.material = material
        super().__init__({material})


def spawn_material(
    path: str, context: bpy.types.Context, options: MaterialSpawnOptions
) -> MaterialSpawnedData:
    """Loads material from 'path' and adds it to all target objects or to their selected faces if edit mode is toggled on

    (materialiq materials only)
    Automatically changes texture sizes and links / unlinks displacement based on spawning options.

    Returns the spawned material.
    """

    material = load.load_material(path)
    # Copy the set of targets to avoid modifying the original
    target_objects = set(options.target_objects)

    # If no object is selected we will spawn a sphere and assign material to it
    if context.mode != 'EDIT_MESH' and len(target_objects) == 0:
        prev_active = context.active_object
        bpy.ops.mesh.primitive_uv_sphere_add()
        bpy.ops.object.shade_smooth()
        # The spawned sphere is the active object
        assert context.active_object is not None
        obj = context.active_object
        obj.name = material.name
        obj.data.name = material.name
        obj.location = context.scene.cursor.location
        context.collection.objects.unlink(obj)
        if options.collection_factory_method is not None:
            parent_collection = options.collection_factory_method()
            if parent_collection is not None:
                parent_collection.objects.link(obj)

                if options.select_spawned:
                    for selected_obj in context.selected_objects:
                        selected_obj.select_set(False)
                    obj.select_set(True)

        target_objects.add(obj)
        context.view_layer.objects.active = prev_active

    for obj in target_objects:
        if not utils.can_have_materials_assigned(obj):
            continue
        if context.mode == 'EDIT_MESH':
            # In EDIT mode we only assign material to selected faces of the edited objects
            if obj.mode != 'EDIT':
                continue
            # Convert to BMesh to force update of selected faces
            bm = bmesh.from_edit_mesh(obj.data)
            selected_faces = [face for face in bm.faces if face.select]
            if not any(selected_faces):
                continue
            with context.temp_override(active_object=obj, selected_objects=[obj], object=obj):
                for index, material_slot in enumerate(obj.material_slots):
                    # If a material slot with the same material is already present, assign the selected
                    # faces to it. The already assigned material might have been tweaked by the user
                    # but we don't want to override it.
                    orig_mapr_index = material_slot.material.get("mapr_asset_id", "")
                    if orig_mapr_index != "" and orig_mapr_index == material.get(
                        "mapr_asset_id", ""
                    ):
                        obj.active_material_index = index
                        # Add the currently selected faces to the already assigned material
                        bpy.ops.object.material_slot_select()
                        bpy.ops.object.material_slot_assign()
                        # Revert face selection as user had it before
                        for face in bm.faces:
                            face.select_set(face in selected_faces)
                        bmesh.update_edit_mesh(obj.data)
                        break
                else:
                    # The first material slot added to an object will automatically contain all faces
                    # Unless there are more material slots, assigning a smaller subset of faces to it
                    # will not work as expected
                    bpy.ops.object.material_slot_add()
                    bpy.ops.object.material_slot_assign()
                    obj.material_slots[obj.active_material_index].material = material

        elif len(obj.material_slots) == 0:
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
    collection_factory_method: typing.Callable[[], bpy.types.Collection | None] | None = None
    display_type: str = 'TEXTURED'
    display_percentage: float = 100.0
    instance_layer_collection_parent: bpy.types.LayerCollection | None = None
    # 'enable_instance_collection' is only used when 'instance_layer_collection_parent' is not None
    enable_instance_collection: bool = False
    include_base_material: bool = True
    max_particle_count: int = 10000
    # count is used when preserve_density is False
    count: int = 1000
    preserve_density: bool = True
    select_spawned: bool = True
    target_objects: set[bpy.types.Object] = dataclasses.field(default_factory=set)


class ParticlesSpawnedData(SpawnedData):
    def __init__(
        self,
        particles: typing.Iterable[bpy.types.ParticleSettings],
        material: bpy.types.Material | None = None,
    ):
        self.particles = particles
        self.material = material
        datablocks = set(particles)
        if material is not None:
            datablocks.add(material)
        super().__init__(datablocks)


def get_expected_particle_system_settings_seed(
    particle_settings: bpy.types.ParticleSettings,
) -> int:
    """Returns a unique but consistent seed for the particle system based on its name."""
    return int(hashlib.md5(particle_settings.name.encode()).hexdigest(), 16) % (2**31)


def spawn_particles(
    path: str, context: bpy.types.Context, options: ParticleSystemSpawnOptions
) -> ParticlesSpawnedData:
    """Loads all particle systems from a given path and puts them on target objects or on a simple plane.

    Returns list of particle settings that were loaded.
    """
    container_obj, all_particle_settings = load.load_particles(path)
    # Copy the set of targets to avoid modifying the original
    target_objects = set(options.target_objects)
    # In case there are no target objects, we will spawn the particles on the container object
    if len(target_objects) == 0:
        target_objects.add(container_obj)
        container_obj.location = context.scene.cursor.location
        if options.collection_factory_method is not None:
            parent_collection = options.collection_factory_method()
            if parent_collection is not None:
                parent_collection.objects.link(container_obj)
                if options.select_spawned:
                    for selected_obj in context.selected_objects:
                        selected_obj.select_set(False)
                    container_obj.select_set(True)
    else:
        bpy.data.objects.remove(container_obj)

    # Get lowest z location from target objects and calculate total mesh are of all target objects
    # so the instanced objects locations and particle counts are adjusted properly.
    lowest_obj_z = math.inf if len(target_objects) > 0 else context.scene.cursor.location.z
    total_mesh_area = 0.0
    for target_obj in target_objects:
        lowest_obj_z = min(target_obj.location.z, lowest_obj_z)
        total_mesh_area += utils.calculate_mesh_area(target_obj)

    for particle_settings in all_particle_settings:
        particle_settings.display_percentage = options.display_percentage
        for obj in particle_settings.instance_collection.all_objects:
            # We spawn all objects 10 units below the lowest location of target objects
            obj.location.z = lowest_obj_z - 10.0
            obj.display_type = options.display_type

        if options.instance_layer_collection_parent is not None:
            # Link the instance collection to the parent collection
            instance_collection_parent = options.instance_layer_collection_parent.collection
            instance_collection_parent.children.link(particle_settings.instance_collection)
            if not options.enable_instance_collection:
                # Exclude the instance collection from the view layer
                particle_layer_collection = options.instance_layer_collection_parent.children.get(
                    particle_settings.instance_collection.name, None
                )
                if particle_layer_collection is not None:
                    particle_layer_collection.exclude = True

        if options.preserve_density:
            try:
                new_count = int(total_mesh_area * particle_settings.pps_density)
            except ValueError:
                logger.exception(
                    f"Error while calculating particle count with preserve density option. "
                    f"(total_mesh_area: {total_mesh_area}, pps_density: {particle_settings.pps_density}) "
                    f"Setting particle count to default value: {options.count}"
                )
                new_count = options.count
            if new_count > options.max_particle_count:
                logger.warning(
                    f"Particle count exceeded maximum by: {int(new_count - options.max_particle_count)}"
                )
                new_count = options.max_particle_count
        else:
            new_count = options.count
        particle_settings.count = new_count

        for target_obj in target_objects:
            # Create modifiers and adjust particle system settings based on spawn options
            mod: bpy.types.ParticleSystemModifier = target_obj.modifiers.new(
                particle_settings.name, type='PARTICLE_SYSTEM'
            )
            mod.particle_system.settings = particle_settings
            # If seed is 0, particles of all the systems will be spawned over each other
            mod.particle_system.seed = get_expected_particle_system_settings_seed(particle_settings)
            utils.ensure_particle_naming_consistency(mod, mod.particle_system)

    spawned_material_data = None
    if options.include_base_material:
        with context.temp_override(mode='OBJECT'):
            spawned_material_data = spawn_material(
                path, context, MaterialSpawnOptions(target_objects=target_objects)
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


@dataclasses.dataclass
class SceneSpawnOptions(DatablockSpawnOptions):
    activate_spawned: bool = True


class SceneSpawnedData(SpawnedData):
    def __init__(self, scene: bpy.types.Scene):
        self.scene = scene
        super().__init__({scene})


def spawn_scene(
    path: str, context: bpy.types.Context, options: SceneSpawnOptions
) -> SceneSpawnedData:
    """Loads scene from 'path' and replaces current scene with it, returns the loaded scene."""
    scene = load.load_scene(path)
    if options.activate_spawned:
        context.window.scene = scene
    return SceneSpawnedData(scene)


@dataclasses.dataclass
class GeometryNodesSpawnOptions(DatablockSpawnOptions):
    collection_factory_method: typing.Callable[[], bpy.types.Collection | None] | None = None
    select_spawned: bool = True
    target_objects: set[bpy.types.Object] = dataclasses.field(default_factory=set)
    parent_targets_layer_collection_factory_method: typing.Optional[
        typing.Callable[[], bpy.types.LayerCollection | None]
    ] = None
    # 'enable_target_collections' is only used when 'parent_targets_layer_collection_factory_method' is not None
    enable_target_collections: bool = False


class GeometryNodesSpawnedData(SpawnedData):
    def __init__(
        self,
        container_objs_to_mods_map: dict[bpy.types.Object, set[bpy.types.Modifier]],
    ):
        self.container_objs_to_mods_map = container_objs_to_mods_map
        node_groups = set()
        for mods in container_objs_to_mods_map.values():
            for mod in mods:
                assert mod.type == 'NODES'
                node_groups.add(mod.node_group)
        super().__init__(node_groups)


def spawn_geometry_nodes(
    path: str, context: bpy.types.Context, options: GeometryNodesSpawnOptions
) -> GeometryNodesSpawnedData:
    """Loads object with the same name as basename of 'path' and copies its modifiers to suitable target objects.

    If there are no suitable target objects, adds a standalone object with the modifiers into the scene collection.
    """
    cols = set(filter(lambda col: col.library is None, bpy.data.collections))
    container_object = load.load_master_object(path)
    asset_name = container_object.name
    target_collections = set(filter(lambda col: col.library is None, bpy.data.collections)) - cols
    # Due to a bug in Blender while converting boolean inputs we reassign the modifier node
    # group when spawning. The bug happens when object with modifiers is appended from a blend
    # file, where the modifier node group is linked from a different file. First append is
    # correct, but any subsequently appended object with the same modifier triggers the:
    # 'Property type does not match input socket (NAME)' error and can make some setups not work
    # Issue link: https://projects.blender.org/blender/blender/issues/110825
    for mod in container_object.modifiers:
        if mod.type == 'NODES':
            mod.node_group = mod.node_group

    container_objs_to_mods_map: dict[bpy.types.Object, set[bpy.types.Modifier]] = (
        collections.defaultdict(set)
    )
    target_objects = set(options.target_objects)
    curve_targets = [obj for obj in target_objects if obj.type == 'CURVE']
    if container_object.type == 'CURVE' and len(curve_targets) > 0:
        # Let's copy the modifiers one object at a time so we have more control
        for target_obj in curve_targets:
            with context.temp_override(
                active_object=container_object,
                object=container_object,
                selected_objects=[target_obj],
            ):
                prev_mods = set(target_obj.modifiers)
                for mod in container_object.modifiers:
                    if mod.type == 'NODES':
                        bpy.ops.object.modifier_copy_to_selected(modifier=mod.name)
                spawned_mods = set(target_obj.modifiers) - prev_mods
                container_objs_to_mods_map[target_obj].update(spawned_mods)
        bpy.data.objects.remove(container_object)
    else:
        if options.collection_factory_method is not None:
            targets_collection = options.collection_factory_method()
            if targets_collection is not None:
                targets_collection.objects.link(container_object)
                if options.select_spawned:
                    for selected_obj in context.selected_objects:
                        selected_obj.select_set(False)
                    container_object.select_set(True)

        container_object.location = context.scene.cursor.location
        container_objs_to_mods_map[container_object].update(
            mod for mod in container_object.modifiers if mod.type == 'NODES'
        )

    # Get lowest z location from target objects so the objects from target collections are adjusted properly.
    lowest_obj_z = math.inf if len(target_objects) > 0 else context.scene.cursor.location.z
    for target_obj in target_objects:
        lowest_obj_z = min(target_obj.location.z, lowest_obj_z)

    if (
        options.parent_targets_layer_collection_factory_method is not None
        and len(target_collections) > 0
    ):
        parent_targets_layer_collection = options.parent_targets_layer_collection_factory_method()
        if parent_targets_layer_collection is not None:
            targets_collection = bpy.data.collections.new(asset_name)
            parent_targets_layer_collection.collection.children.link(targets_collection)
            targets_layer_collection = parent_targets_layer_collection.children.get(
                targets_collection.name, None
            )
            assert targets_layer_collection is not None

            if not options.enable_target_collections:
                # Exclude the target collections from the view layer
                targets_layer_collection.exclude = True

            for target_col in target_collections:
                for obj in target_col.objects:
                    # We spawn all objects 10 units below the lowest location of target objects
                    obj.location.z = lowest_obj_z - 10.0

                # Link the target collection to the parent collection
                targets_collection.children.link(target_col)

    return GeometryNodesSpawnedData(container_objs_to_mods_map)
