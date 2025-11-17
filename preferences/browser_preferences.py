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
import logging
from .. import polib
from .. import hatchery
from .. import mapr
from .. import asset_registry
from . import prefs_utils
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: list[typing.Any] = []


@polib.serialization_bpy.serializable_class
@polib.serialization_bpy.preferences_propagate_property_update(
    lambda context: prefs_utils.get_preferences(context).browser_preferences
)
class SpawnOptions(bpy.types.PropertyGroup):
    """Defines options that should be considered when spawning assets."""

    # General
    remove_duplicates: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Remove Duplicates",
            description="Automatically merges duplicate materials, node groups "
            "and images into one when the asset is spawned. Saves memory",
            default=True,
        )
    )
    make_editable: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Make Editable",
            description="Automatically makes the spawned asset editable",
            default=False,
        )
    )

    # Model
    use_collection: polib.serialization_bpy.Serialize(
        bpy.props.EnumProperty(
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
    )

    # Materialiq
    texture_size: polib.serialization_bpy.Serialize(
        bpy.props.EnumProperty(
            items=lambda _, __: asset_helpers.get_materialiq_texture_sizes_enum_items(),
            name="materialiq5 global maximum side size",
            description="Maximum side size of textures spawned with a material",
        )
    )

    use_displacement: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Use Displacement",
            description="Spawn material with enabled displacement",
            default=False,
        )
    )

    # scatter
    display_type: polib.serialization_bpy.Serialize(
        bpy.props.EnumProperty(
            name="Display As", items=prefs_utils.SCATTER_DISPLAY_ENUM_ITEMS, default='TEXTURED'
        )
    )

    display_percentage: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name="Display Percentage",
            description="Percentage of particles that are displayed in viewport",
            subtype='PERCENTAGE',
            default=100,
            min=0,
            max=100,
        )
    )

    link_instance_collection: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            description="If true, this setting links particle system instance collection to scene. "
            "Objects from instance collection are spawned on (0, -10, 0).",
            name="Link Instance Collection To Scene",
            default=True,
        )
    )

    enable_instance_collection: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Enable Instance Collection",
            description="If true, the linked particle system instance collection will be included "
            "in the view layer.",
            default=False,
        )
    )

    include_base_material: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Include Base Material",
            description="If true base material is loaded with the particle system and set "
            "to the target object as active",
            default=True,
        )
    )

    preserve_density: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Preserve Density",
            description="If true automatically recalculates density based on mesh area",
            default=True,
        )
    )

    count: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name="Count",
            description="Amount of particles to spawn if preserve density is off",
            default=1000,
        )
    )

    # geonodes
    link_target_collections: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Link Target Collections to Scene",
            description="If true, this setting links geometry nodes target collections to scene. "
            "Objects from target collections are spawned 10 units below the lowest affected object.",
            default=True,
        )
    )

    enable_target_collections: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Enable Target Collections",
            description="If true, the linked geometry nodes target collections will be included "
            "in the view layer.",
            default=False,
        )
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
            return hatchery.spawn.SceneSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_world:
            return hatchery.spawn.DatablockSpawnOptions()
        elif asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes:
            return hatchery.spawn.GeometryNodesSpawnOptions(
                lambda: self._get_model_parent_collection(asset, context),
                True,
                set(context.selected_objects),
                lambda: self._get_instance_layer_collection_parent(asset, context),
                self.enable_target_collections,
            )
        else:
            raise NotImplementedError(
                f"Spawn options are not supported for type: {asset.type_}, please contact developers!"
            )

    def can_spawn(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> tuple[bool, tuple[str, str] | None]:
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
    ) -> bpy.types.LayerCollection | None:
        collection = None
        if (
            asset.type_ == mapr.asset_data.AssetDataType.blender_particle_system
            and self.link_instance_collection
        ):
            collection = polib.asset_pack_bpy.collection_get(
                context, asset_helpers.PARTICLE_SYSTEMS_COLLECTION
            )
        elif (
            asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes
            and self.link_target_collections
        ):
            collection = polib.asset_pack_bpy.collection_get(
                context, asset_helpers.GEONODES_TARGET_COLLECTION
            )

        if collection is not None:
            return polib.asset_pack_bpy.find_layer_collection(
                context.view_layer.layer_collection, collection
            )
        return None

    def _get_model_parent_collection(
        self, asset: mapr.asset.Asset, context: bpy.types.Context
    ) -> bpy.types.Collection | None:
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


@polib.serialization_bpy.serializable_class
@polib.serialization_bpy.preferences_propagate_property_update(prefs_utils.get_preferences)
class BrowserPreferences(bpy.types.PropertyGroup):
    """Property group containing all the settings and customizable options for user interface"""

    preview_scale_percentage: polib.serialization_bpy.Serialize(
        bpy.props.FloatProperty(
            name="Preview Scale",
            description="Preview scale",
            min=0,
            max=100,
            default=50,
            subtype='PERCENTAGE',
        )
    )
    category_navigation_style: polib.serialization_bpy.Serialize(
        bpy.props.EnumProperty(
            name="Category Navigation Style",
            description="Style of category navigation to use",
            items=(
                ('TREE_NEW', "Tree New", "Both tree and pills style category navigation"),
                ('TREE', "Tree Old", "Tree style category navigation"),
                ('PILLS', "Pills", "Pills style category navigation"),
            ),
        )
    )
    search_history_count: polib.serialization_bpy.Serialize(
        bpy.props.IntProperty(
            name="Search History Count",
            description="Number of search queries that are remembered during one Blender instance run",
            min=0,
            default=20,
        )
    )

    debug: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Enable Debug",
            description="If true then asset browser displays additional debug information",
            default=False,
        )
    )

    def _update_debug_show_hidden_filters(self, context):
        # we can't reference the operator's bl_id directly, as that would cause circular dependency
        if hasattr(bpy.ops, 'engon.dev_browser_reconstruct_filters'):
            bpy.ops.engon.dev_browser_reconstruct_filters()
        else:
            logger.error(
                "Operator engon.dev_browser_reconstruct_filters operator is not available, "
                "Show Hidden Filters will not work properly."
            )

    debug_show_hidden_filters: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(
            name="Show Hidden Filters",
            description="If true then asset browser displays filters for metadata that have `show_filter: False`",
            default=False,
            update=_update_debug_show_hidden_filters,
        )
    )

    spawn_options: polib.serialization_bpy.Serialize(
        bpy.props.PointerProperty(type=SpawnOptions),
    )

    # We store the state whether preferences were open to be able to re-open it on load
    prefs_hijacked: polib.serialization_bpy.Serialize(
        bpy.props.BoolProperty(options={'HIDDEN'}),
    )


MODULE_CLASSES.append(BrowserPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
