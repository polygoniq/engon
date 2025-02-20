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

    enable_instance_collection: bpy.props.BoolProperty(
        name="Enable Instance Collection",
        description="If true, the linked particle system instance collection will be included "
        "in the view layer.",
        default=False,
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
            return hatchery.spawn.ModelSpawnOptions(
                lambda: self._get_model_parent_collection(asset, context), True
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            # Outside of EDIT mode we only use selected objects
            # In EDIT mode we use all objects in edit mode
            target_objects = (
                {obj for obj in context.scene.objects if obj.mode == 'EDIT'}
                if context.mode == 'EDIT_MESH'
                else set(context.selected_objects)
            )
            return hatchery.spawn.MaterialSpawnOptions(
                lambda: self._get_model_parent_collection(asset, context),
                int(self.texture_size),
                self.use_displacement,
                True,
                target_objects,
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            target_objects = {obj for obj in context.selected_objects if obj.type == 'MESH'}
            return hatchery.spawn.ParticleSystemSpawnOptions(
                lambda: self._get_model_parent_collection(asset, context),
                self.display_type,
                self.display_percentage,
                self._get_instance_layer_collection_parent(asset, context),
                self.enable_instance_collection,
                self.include_base_material,
                # Purposefully use max_particle_count from scatter, as this property has a global
                # meaning.
                prefs_utils.get_preferences(
                    context
                ).general_preferences.scatter_props.max_particle_count,
                self.count,
                self.preserve_density,
                True,
                target_objects,
            )
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return hatchery.spawn.GeometryNodesSpawnOptions(
                lambda: self._get_model_parent_collection(asset, context),
                True,
                set(context.selected_objects),
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
            if self.make_editable and context.mode != 'OBJECT':
                return False, (
                    f"Cannot spawn with make editable in '{context.mode}' mode.",
                    "Please switch to Object Mode.",
                )
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_scene:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_material:
            return True, None
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return True, None
        else:
            raise NotImplementedError(
                f"Invalid type given to can_spawn: {asset.type_}, please contact developers!"
            )

    def _get_instance_layer_collection_parent(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> typing.Optional[bpy.types.LayerCollection]:
        if self.link_instance_collection:
            collection = polib.asset_pack_bpy.collection_get(
                context, asset_helpers.PARTICLE_SYSTEMS_COLLECTION
            )
            return polib.asset_pack_bpy.find_layer_collection(
                context.view_layer.layer_collection, collection
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
