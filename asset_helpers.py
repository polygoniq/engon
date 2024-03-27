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

import typing
import bpy
import enum
import os
import glob
import collections
import logging
import polib
from . import asset_registry
logger = logging.getLogger(__name__)


PARTICLE_SYSTEMS_COLLECTION = "engon_particle_systems"
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
BQ_ANIM_LIBRARY_BLEND = "bq_Library_Animation_Data.blend"

# traffiq constants
TQ_MODIFIER_LIBRARY_BLEND = "tq_Library_Modifiers.blend"


PARTICLE_SYSTEM_PREFIX = f"engon_{polib.asset_pack_bpy.PARTICLE_SYSTEM_TOKEN}_"


# Inputs for the aquatiq puddle nodes
class PuddleNodeInputs:
    PUDDLE_FACTOR = "Puddle Factor"
    PUDDLE_SCALE = "Puddle Scale"
    ANIMATION_SPEED = "Animation Speed"
    NOISE_STRENGTH = "Noise Strength"
    ANGLE_THRESHOLD = "Angle Threshold"


def is_asset_with_engon_feature(obj: bpy.types.Object, feature: str, include_editable: bool = True, include_linked: bool = True) -> bool:
    engon_feature_packs = asset_registry.instance.get_packs_by_engon_feature(feature)
    polygoniq_addon = obj.get("polygoniq_addon", None)
    if polygoniq_addon is None or polygoniq_addon not in (x.file_id_prefix.strip("/") for x in engon_feature_packs):
        return False
    return polib.asset_pack_bpy.is_polygoniq_object(obj, lambda x: x == polygoniq_addon, include_editable, include_linked)


def is_object_from_seasons(obj: bpy.types.Object, seasons: typing.Set[str]) -> bool:
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
    return any(node.type == 'GROUP' and node.node_tree.name.startswith("mq_")
               for node in material.node_tree.nodes)


def get_materialiq_texture_sizes_enum_items():
    """Returns enum items for materialiq texture sizes based on what is present in asset registry

    Always returns 1024, as it is the base texture size present in all materialiq variants.
    """
    texture_sizes = {1024}
    mq_variant_size_map = {
        "lite": 2048,
        "full": 4096,
        "ultra": 8192,
        "dev": 8192
    }
    registered_packs = asset_registry.instance.get_packs_by_engon_feature("materialiq")
    for pack in registered_packs:
        _, pack_variant = pack.full_name.split("_", 1)
        for i, variant in enumerate(mq_variant_size_map):
            # If we find variant that matches, we include all previous texture sizes,
            # as the variant includes them too.
            if variant == pack_variant:
                texture_sizes.update(list(mq_variant_size_map.values())[:i + 1])
                break

    return [
        (str(size), str(size), f"materialiq texture size: {size}") for size in texture_sizes]


def get_asset_pack_library_path(engon_feature: str, library_blend_name: str) -> typing.Optional[str]:
    for pack in asset_registry.instance.get_packs_by_engon_feature(engon_feature):
        for lib in glob.iglob(os.path.join(pack.install_path, "blends", "**", library_blend_name), recursive=True):
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


class ObjectSource(enum.Enum):
    editable = 0,
    instanced = 1,
    particles = 2,


ObjectSourceMap = typing.Mapping[str, typing.List[
    typing.Tuple[ObjectSource, typing.Union[bpy.types.Object, bpy.types.ParticleSystem]]]]


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
        if obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION' \
           and obj.instance_collection is not None:
            for o in obj.instance_collection.all_objects:
                m[o.name].append((ObjectSource.instanced, obj))

        elif obj.type == 'MESH':
            for ps in obj.particle_systems:
                if ps.settings.instance_collection is not None:
                    for o in ps.settings.instance_collection.all_objects:
                        m[o.name].append((ObjectSource.particles, ps))

            m[obj.name].append((ObjectSource.editable, obj))
    return m


def get_animation_empties_collection(context: bpy.types.Context) -> bpy.types.Collection:
    """Returns collection for animation empty objects, creates the collection if no exists.

    This creates 'botaniq/animation_empties' collection hierarchy. If the 'botaniq' collection
    isn't present it is created as well.
    """
    bq_collection = polib.asset_pack_bpy.collection_get(context, BQ_COLLECTION_NAME)
    return polib.asset_pack_bpy.collection_get(context, ANIMATION_EMPTIES_COLL_NAME, bq_collection)


def gather_instanced_objects(
    objects: typing.Iterable[bpy.types.Object]
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
            if polib.asset_pack_bpy.is_pps(mod.particle_system.name) \
               and instance_collection is not None:
                yield from instance_collection.all_objects
