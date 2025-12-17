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

import functools
import typing
import bpy
import bisect
import enum
import os
import glob
import collections
import random
import logging
from . import polib
from . import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")


PARTICLE_SYSTEMS_COLLECTION = "engon_particle_systems"
GEONODES_TARGET_COLLECTION = "engon_geometry_nodes"
ANIMATION_EMPTIES_COLL_NAME = "animation_empties"


# aquatiq constants
AQ_MASK_NAME = "aq_mask"
AQ_PUDDLES_NODEGROUP_NAME = "aq_Puddles"
# Node groups where 'aq_mask' alpha affects something in the shader
AQ_MASKABLE_NODE_GROUP_NAMES = {"aq_Fountain", AQ_PUDDLES_NODEGROUP_NAME}
AQ_RIVER_GENERATOR_NODE_GROUP_NAME = "aq_Generator_River"
AQ_RAIN_GENERATOR_NODE_GROUP_NAME = "aq_Rain-Generator_Rain"
AQ_MATERIALS_LIBRARY_BLEND = "aq_Library_Materials.blend"

# botaniq constants
BOTANIQ_ALL_SEASONS_RAW = "spring-summer-autumn-winter"
BQ_COLLECTION_NAME = "botaniq"
BQ_VINE_GENERATOR_NODE_GROUP_NAME = "bq_Vine_Generator"
BQ_CURVES_SCATTER_NODE_GROUP_NAME = "bq_Curve_Scatter"
BQ_ANIM_LIBRARY_BLEND = "bq_Library_Animation_Data.blend"

# traffiq constants
TQ_MODIFIER_LIBRARY_BLEND = "tq_Library_Modifiers.blend"
TQ_EMERGENCY_LIGHTS_NODE_GROUP_NAME = "tq_Emergency_Lights"
TQ_LICENSE_PLATE_NODE_GROUP_NAME_PREFIX = "tq_License-Plate_"
# Mimics the distribution of car colors in the real world
TQ_COLOR_DISTRIBUTION = (
    (0.0, (0.004, 0.004, 0.004)),  # 0E0E0E
    (0.018, (0.063, 0.063, 0.063)),  # 474747
    (0.031, (0.558, 0.558, 0.558)),  # C5C5C5
    (0.041, (0.216, 0.004, 0.175)),  # 800E74
    (0.043, (0.012, 0.001, 0.028)),  # 1D042F
    (0.045, (0.295, 0.185, 0.0)),  # 947700
    (0.053, (0.271, 0.22, 0.126441)),  # 8E8164
    (0.060, (0.04, 0.099, 0.006)),  # 385913
    (0.070, (0.006, 0.026, 0.002)),  # 132D07
    (0.074, (0.106, 0.192, 0.009)),  # 5C7918
    (0.078, (0.014, 0.183, 0.152)),  # 1F766D
    (0.081, (0.043, 0.017, 0.003)),  # 3B2309
    (0.101, (0.096, 0.0, 0.002)),  # 570006
    (0.173, (0.333, 0.07, 0.0)),  # 9C4B00
    (0.178, (0.282, 0.0, 0.0)),  # 910000
    (0.2, (0.002, 0.011, 0.042)),  # 071B3A
    (0.278, (0.006, 0.054, 0.264)),  # 11428C
    (0.3, (0.187, 0.187, 0.187)),  # 787878
    (0.45, (0.037, 0.037, 0.037)),  # 363636
    (0.6, (0.558, 0.558, 0.558)),  # C5C5C5
    (0.8, (0.004, 0.004, 0.004)),  # 0E0E0E
)

# aesthetiq constants
SQ_PICTORAL_MATERIALS_LIBRARY_BLEND = "sq_Library_Pictoral-Materials.blend"
SQ_PICTORIAL_MATERIAL_PREFIX = "sq_Pictoral_"  # todo: fix typo in "Pictoral" in material names
SQ_FRAME_GENERATOR_LIBRARY_BLEND = "sq_Library_Frame-Generator-Geonodes.blend"
SQ_FRAME_GENERATOR_MODIFIER = "sq_Frame-Generator"
SQ_FRAME_GENERATOR_OBJECT = "sq_Frame-generator"

PARTICLE_SYSTEM_PREFIX = f"engon_{polib.asset_pack.PARTICLE_SYSTEM_TOKEN}_"


# Inputs for the aquatiq puddle nodes
class PuddleNodeInputs:
    PUDDLE_FACTOR = "Puddle Factor"
    PUDDLE_SCALE = "Puddle Scale"
    ANIMATION_SPEED = "Animation Speed"
    NOISE_STRENGTH = "Noise Strength"
    ANGLE_THRESHOLD = "Angle Threshold"


def has_active_particle_system(obj: bpy.types.Object) -> bool:
    active_particle_system = obj.particle_systems.active
    if active_particle_system is None:
        return False

    return True


def has_active_object_with_particle_system(context: bpy.types.Context) -> bool:
    """Returns true if context is in object mode and has active object with active particle system

    This is mainly used for the poll methods of particle system operators that work
    on active object with particle system.
    """
    if context.mode != 'OBJECT':
        return False

    if context.active_object is None:
        return False

    return has_active_particle_system(context.active_object)


def is_obj_with_engon_feature(
    obj: bpy.types.Object, feature: str, include_editable: bool = True, include_linked: bool = True
) -> bool:
    if not polib.asset_pack_bpy.is_polygoniq_object(
        obj, include_editable=include_editable, include_linked=include_linked
    ):
        return False

    mapr_asset_id = obj.get("mapr_asset_id", None)
    if mapr_asset_id is None:
        # The asset might be ours but if it doesn't have a MAPR ID we can't figure out which asset
        # pack it's from.
        return False

    asset_pack = asset_registry.instance.get_asset_pack_of_asset(mapr_asset_id)
    if asset_pack is None:
        # The asset has a mapr ID but we can't find an enabled asset pack that has it
        # this is unusual and most probably somebody spawned an asset from an asset pack, then
        # disabled or uninstalled the pack. Either way we can't figure out which engon feature it
        # has if it's not present.
        return False

    return feature in asset_pack.engon_features


def is_object_from_seasons(obj: bpy.types.Object, seasons: set[str]) -> bool:
    pure_name = polib.utils_bpy.remove_object_duplicate_suffix(obj.name)
    name_split = pure_name.rsplit("_", 3)
    if len(name_split) != 4:
        return False

    # TODO: We could limit to 3 splits but this would be an unused assumption, the code would still
    #       work with "summer-summer-summer-summer-summer"
    found_seasons = set(name_split[3].split("-"))
    return len(found_seasons.intersection(seasons)) > 0


def is_materialiq_material(material: bpy.types.Material) -> bool:
    if material.node_tree is None:
        return False
    return any(
        node.type == 'GROUP' and node.node_tree.name.startswith("mq_")
        for node in material.node_tree.nodes
    )


@functools.cache
def get_materialiq_texture_sizes_enum_items(
    filter_by_registered_packs: bool = True,
) -> list[tuple[str, str, str]]:
    """Returns enum items for materialiq texture sizes.

    If `filter_by_registered_packs` is True, only sizes available for the registered packs are returned.
    Always returns 1024, as it is the base texture size present in all materialiq variants.
    """
    if filter_by_registered_packs:
        texture_sizes = {1024}
        mq_variant_size_map = {"lite": 2048, "full": 4096, "ultra": 8192, "dev": 8192}
        registered_packs = asset_registry.instance.get_packs_by_engon_feature("materialiq")
        for pack in registered_packs:
            _, pack_variant = pack.full_name.split("_", 1)
            for i, variant in enumerate(mq_variant_size_map):
                # If we find variant that matches, we include all previous texture sizes,
                # as the variant includes them too.
                if variant == pack_variant:
                    texture_sizes.update(list(mq_variant_size_map.values())[: i + 1])
                    break
    else:
        texture_sizes = {1024, 2048, 4096, 8192}

    return [(str(size), str(size), f"materialiq texture size: {size}") for size in texture_sizes]


def get_asset_pack_library_path(engon_feature: str, library_blend_name: str) -> str | None:
    for pack in asset_registry.instance.get_packs_by_engon_feature(engon_feature):
        for lib in glob.iglob(
            os.path.join(pack.install_path, "blends", "**", library_blend_name), recursive=True
        ):
            return lib
    return None


def exclude_variant_from_asset_name(asset_name: str) -> str:
    """Given a full asset name of a plain asset (not particle system!) this function will generate
    a key of the asset that contains all parts of the asset name except the variant. This is useful
    mainly in the randomize variant operator.
    """

    split_res = asset_name.split("_")
    # asset name consists of 5 parts
    # particle systems are not supported by this function
    if len(split_res) == 5:
        prefix, category, name, variant, seasons = split_res
    else:
        return "invalid"

    return "_".join([category, name, seasons])


class ObjectSource(enum.StrEnum):
    EDITABLE = "EDITABLE"
    INSTANCED = "INSTANCED"
    PARTICLES = "PARTICLES"


ObjectSourceMap = typing.Mapping[
    str,
    list[tuple[ObjectSource, bpy.types.Object | bpy.types.ParticleSystem]],
]


def get_obj_source_map(objs: typing.Iterable[bpy.types.Object]) -> ObjectSourceMap:
    """Returns mapping of obj.name to list of its usages. Each usage contains type and object.

    Useful when inferring what is the 'origin object' of different objects in order to reach
    it's properties and for example change them.

    Example:
    Scene contains plane A with particle system 'p' with objects {X, Y, Z}, empty B instancing
    collection containing {U, V, W} and editable object C. For such setup this function returns:
    {
        "X" -> [('PARTICLES', A.particle_systems[p])],
        "Y" -> [('PARTICLES', A.particle_systems[p])],
        "Z" -> [('PARTICLES', A.particle_systems[p])],
        "U" -> [('INSTANCED', B)],
        "V" -> [('INSTANCED', B)],
        "W" -> [('INSTANCED', B)],
        "C" -> [('EDITABLE', C)]
    }

    Note: If you input only X, Y, Z objects then this will yield that those are 'EDITABLE'. In order
    to get result when objects are considered 'PARTICLES' the A object needs to be present in input!
    """
    m = collections.defaultdict(list)
    for obj in objs:
        if (
            obj.type == 'EMPTY'
            and obj.instance_type == 'COLLECTION'
            and obj.instance_collection is not None
        ):
            for o in obj.instance_collection.all_objects:
                m[o.name].append((ObjectSource.INSTANCED, obj))

        elif obj.type == 'MESH':
            for ps in obj.particle_systems:
                if ps.settings.instance_collection is not None:
                    for o in ps.settings.instance_collection.all_objects:
                        m[o.name].append((ObjectSource.PARTICLES, ps))

            m[obj.name].append((ObjectSource.EDITABLE, obj))
    return m


def get_animation_empties_collection(context: bpy.types.Context) -> bpy.types.Collection:
    """Returns collection for animation empty objects, creates the collection if no exists.

    This creates 'botaniq/animation_empties' collection hierarchy. If the 'botaniq' collection
    isn't present it is created as well.
    """
    bq_collection = polib.asset_pack_bpy.collection_get(context, BQ_COLLECTION_NAME)
    return polib.asset_pack_bpy.collection_get(context, ANIMATION_EMPTIES_COLL_NAME, bq_collection)


def gather_instanced_objects(
    objects: typing.Iterable[bpy.types.Object],
) -> typing.Iterator[bpy.types.Object]:
    """Goes through 'objects' and gathers all particle system instanced objects.

    This checks whether any object from 'objects' is a polygoniq particle system and if yes
    it yields objects from particle systems instance collections.
    """
    for obj in objects:
        for mod in obj.modifiers:
            if mod.type != 'PARTICLE_SYSTEM':
                continue

            instance_collection = mod.particle_system.settings.instance_collection
            if (
                polib.asset_pack.is_pps_name(mod.particle_system.name)
                and instance_collection is not None
            ):
                yield from instance_collection.all_objects


def gather_curves_instanced_objects(
    objects: typing.Iterable[bpy.types.Object],
) -> typing.Iterator[bpy.types.Object]:
    """Goes through 'objects' and gathers all objects instanced in curve scatter.

    This checks whether any object from 'objects' is a polygoniq curve scatter and if yes
    it yields objects from curve scatter instance collections.
    """
    for obj in objects:
        for mod in obj.modifiers:
            if mod.type != 'NODES':
                continue

            mod = typing.cast(bpy.types.NodesModifier, mod)

            if mod.node_group is None or not mod.node_group.name.startswith(
                BQ_CURVES_SCATTER_NODE_GROUP_NAME
            ):
                continue

            for group_input in mod.node_group.inputs:
                if group_input.type == 'COLLECTION' and group_input.description.startswith(
                    "bq_Curve_Scatter_Collection"
                ):
                    if mod.get(group_input.identifier) is not None:
                        yield from mod.get(group_input.identifier).all_objects

            instance_collection = mod.node_group.nodes.get("Instance Collection")
            if instance_collection is not None and instance_collection.collection is not None:
                yield from instance_collection.collection.all_objects


def get_car_color() -> tuple[float, float, float]:
    value = random.random()
    idx = bisect.bisect(TQ_COLOR_DISTRIBUTION, value, key=lambda x: x[0]) - 1
    return TQ_COLOR_DISTRIBUTION[idx][1]
