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
import math
import mathutils
import logging
from .. import polib
from .. import hatchery
from .. import mapr
from .. import asset_registry
from . import prefs_utils
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


class SpawnOptions(bpy.types.PropertyGroup):
    """Defines options that should be considered when spawning assets."""

    # General
    remove_duplicates: bpy.props.BoolProperty(
        name="Remove Duplicates",
        description="Automatically merges duplicate materials, node groups "
        "and images into one when the asset is spawned. Saves memory",
        default=True,
    )
    make_editable: bpy.props.BoolProperty(
        name="Make Editable",
        description="Automatically makes the spawned asset editable",
        default=False,
    )

    # Model
    use_collection: bpy.props.EnumProperty(
        name="Target Collection",
        description="Collection to spawn the model into",
        items=(
            (
                'PACK',
                "Asset Pack Collection",
                "Spawn model into collection named as the asset pack - 'botaniq, traffiq, ...'",
            ),
            ('ACTIVE', "Active Collection", "Spawn model into the active collection"),
            (
                'PARTICLE_SYSTEM',
                "Particle System Collection",
                "Spawn model into active particle system collection",
            ),
        ),
    )

    # Materialiq
    texture_size: bpy.props.EnumProperty(
        items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
        name="materialiq5 global maximum side size",
        description="Maximum side size of textures spawned with a material",
    )

    use_displacement: bpy.props.BoolProperty(
        name="Use Displacement",
        description="Spawn material with enabled displacement",
        default=False,
    )

    # scatter
    display_type: bpy.props.EnumProperty(
        name="Display As", items=prefs_utils.SCATTER_DISPLAY_ENUM_ITEMS, default='TEXTURED'
    )

    display_percentage: bpy.props.IntProperty(
        name="Display Percentage",
        description="Percentage of particles that are displayed in viewport",
        subtype='PERCENTAGE',
        default=100,
        min=0,
        max=100,
    )

    link_instance_collection: bpy.props.BoolProperty(
        description="If true, this setting links particle system instance collection to scene. "
        "Objects from instance collection are spawned on (0, -10, 0).",
        name="Link Instance Collection To Scene",
        default=True,
    )

    include_base_material: bpy.props.BoolProperty(
        name="Include Base Material",
        description="If true base material is loaded with the particle system and set "
        "to the target object as active",
        default=True,
    )

    preserve_density: bpy.props.BoolProperty(
        name="Preserve Density",
        description="If true automatically recalculates density based on mesh area",
        default=True,
    )

    count: bpy.props.IntProperty(
        name="Count",
        description="Amount of particles to spawn if preserve density is off",
        default=1000,
    )

    def get_spawn_options(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> hatchery.spawn.DatablockSpawnOptions:
        """Returns spawn options for given asset based on its type"""
        if asset.type_ == mapr.asset_data.AssetDataType.blender_model:
            cursor_loc = mathutils.Vector(context.scene.cursor.location)
            particle_spawn_location = cursor_loc - mathutils.Vector((0, 0, 10))
            particle_spawn_rotation = mathutils.Euler((0, math.radians(90), 0), 'XYZ')
            return hatchery.spawn.ModelSpawnOptions(
                self._get_model_parent_collection(asset, context),
                True,
                # Spawn the asset on Z - 10 in particle systems
                particle_spawn_location if self.use_collection == 'PARTICLE_SYSTEM' else None,
                # Rotate the spawned asset 90 around Y to make it straight in particle systems
                # that use Rotation around Z Axis - which are most of our particle systems.
                particle_spawn_rotation if self.use_collection == 'PARTICLE_SYSTEM' else None,
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            return hatchery.spawn.MaterialSpawnOptions(
                int(self.texture_size), self.use_displacement, set(context.selected_objects)
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            return hatchery.spawn.ParticleSystemSpawnOptions(
                self.display_type,
                self.display_percentage,
                self._get_instance_collection_parent(asset, context),
                self.include_base_material,
                # Purposefully use max_particle_count from scatter, as this property has a global
                # meaning.
                prefs_utils.get_preferences(
                    context
                ).general_preferences.scatter_props.max_particle_count,
                self.count,
                self.preserve_density,
                {context.active_object},
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return hatchery.spawn.GeometryNodesSpawnOptions(
                self._get_model_parent_collection(asset, context)
            )
        else:
            raise NotImplementedError(
                f"Spawn options are not supported for type: {asset.type_}, please contact developers!"
            )

    def can_spawn(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> typing.Tuple[bool, typing.Optional[typing.Tuple[str, str]]]:
        """Checks whether the given asset can spawn in given Blender context.

        Returns boolean value and a tuple of strings (Error, Hint To User)
        """
        if asset.type_ == mapr.asset_data.AssetDataType.blender_model:
            if self.use_collection == 'PARTICLE_SYSTEM':
                if context.active_object is None:
                    return False, (
                        "Can't spawn model into particle system - No active object!",
                        "Select active object with particle system.",
                    )
                if context.active_object.particle_systems.active is None:
                    return False, (
                        "Can't spawn model into particle system - No particle system found!",
                        "Select object with at least one particle system.",
                    )
                instance_collection = (
                    context.active_object.particle_systems.active.settings.instance_collection
                )
                if instance_collection is None:
                    return False, (
                        "Can't spawn model into particle system - Missing instance collection!",
                        "Select particle system and assign instance collection to it.",
                    )
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            if context.active_object is None:
                return False, (
                    "Can't spawn particle system - No active object!",
                    "Select a mesh object.",
                )
            else:
                if context.active_object.type != 'MESH':
                    return False, (
                        "Current object doesn't support particle systems!",
                        "Select a mesh object.",
                    )
                return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            if self.use_collection == 'PARTICLE_SYSTEM':
                return False, (
                    "Can't spawn geometry nodes into particle system collection!",
                    "Try spawning model asset.",
                )
            return True, None
        else:
            raise NotImplementedError(
                f"Invalid type given to can_spawn: {asset.type_}, please contact developers!"
            )

    def _get_instance_collection_parent(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> typing.Optional[bpy.types.Collection]:
        if self.link_instance_collection:
            return polib.asset_pack_bpy.collection_get(
                context, asset_helpers.PARTICLE_SYSTEMS_COLLECTION
            )

        return None

    def _get_model_parent_collection(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> typing.Optional[bpy.types.Collection]:
        if self.use_collection == 'ACTIVE':
            return context.collection
        elif self.use_collection == 'PACK':
            asset_pack = asset_registry.instance.get_asset_pack_of_asset(asset.id_)
            collection = polib.asset_pack_bpy.collection_get(
                context, asset_pack.short_name if asset_pack is not None else "unknown"
            )
            return collection

        elif self.use_collection == 'PARTICLE_SYSTEM':
            if context.active_object is None:
                logger.error(
                    "Tried to to spawn object into particle system collection, but no object is active!"
                )
                return None

            ps = context.active_object.particle_systems.active
            if ps is None:
                logger.error(f"No active particle system found!")
                return None

            coll = ps.settings.instance_collection
            if coll is not None:
                return coll
            else:
                logger.error(f"No particle system instance collection found!")
                return None
        else:
            raise ValueError(f"Unknown value of 'use_collection': {self.use_collection}")


MODULE_CLASSES.append(SpawnOptions)


class BrowserPreferences(bpy.types.PropertyGroup):
    """Property group containing all the settings and customizable options for user interface"""

    preview_scale_percentage: bpy.props.FloatProperty(
        name="Preview Scale",
        description="Preview scale",
        min=0,
        max=100,
        default=50,
        subtype='PERCENTAGE',
    )
    use_pills_nav: bpy.props.BoolProperty(
        name="Tree / Pills Category Navigation",
        description="If toggled, then pills navigation will be drawn, tree navigation otherwise",
        default=False,
    )
    search_history_count: bpy.props.IntProperty(
        name="Search History Count",
        description="Number of search queries that are remembered during one Blender instance run",
        min=0,
        default=20,
    )
    debug: bpy.props.BoolProperty(
        name="Enable Debug",
        description="If true then asset browser displays addition debug information",
        default=False,
    )

    spawn_options: bpy.props.PointerProperty(type=SpawnOptions)

    # We store the state whether preferences were open to be able to re-open it on load
    prefs_hijacked: bpy.props.BoolProperty(options={'HIDDEN'})


MODULE_CLASSES.append(BrowserPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
