# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import logging
from . import polib
from . import mapr
from . import hatchery
from . import asset_registry
from . import preferences

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []

# The 'make_selection_linked' implementation is here because we need to access the 'asset_registry'
# instance. The 'make_selection_editable' is in the 'polib.asset_pack_bpy' module, where it can
# be used without dependency on the 'mapr' module.
# If we ever need 'make_selection_linked' in other places, let's move it to 'polib' and add the
# dependency to 'mapr'.


def make_selection_linked(
    context: bpy.types.Context,
    asset_provider: mapr.asset_provider.AssetProvider,
    file_provider: mapr.file_provider.FileProvider,
) -> typing.List[bpy.types.Object]:
    previous_active_obj_name = context.active_object.name if context.active_object else None
    converted_objects = []

    spawner = mapr.blender_asset_spawner.AssetSpawner(asset_provider, file_provider)

    for obj in polib.asset_pack_bpy.find_root_objects(context.selected_objects):
        if obj.instance_type == 'COLLECTION':
            continue

        id_from_object = obj.get(mapr.blender_asset_spawner.ASSET_ID_PROP_NAME, None)
        if id_from_object is None:
            # Object can have missing id if it comes from pre-engon asset pack
            logger.error(f"Object '{obj.name}' has no asset id, cannot convert to linked.")
            continue

        asset = asset_provider.get_asset(id_from_object)
        if asset is None:
            # This can happen if the asset id of the object present in scene is not known
            # to engon - e.g. if corresponding asset pack is not loaded.
            logger.error(
                f"Asset with id '{id_from_object}' not found in any installed or registered "
                "Asset Pack, cannot convert to linked."
            )
            continue

        if asset.type_ != mapr.asset_data.AssetDataType.blender_model:
            continue

        old_model_matrix = obj.matrix_world.copy()
        old_collections = list(obj.users_collection)
        old_color = tuple(obj.color)
        old_parent = obj.parent

        # This way old object names won't interfere with the new ones
        hierarchy_objects = polib.asset_pack_bpy.get_hierarchy(obj)
        for hierarchy_obj in hierarchy_objects:
            hierarchy_obj.name = polib.utils_bpy.generate_unique_name(
                f"del_{hierarchy_obj.name}", bpy.data.objects
            )

        # Spawn the asset if its mapr id is found
        spawned_data = spawner.spawn(
            context,
            asset,
            hatchery.spawn.ModelSpawnOptions(collection_factory_method=None, select_spawned=False),
        )
        if spawned_data is None:
            logger.error(f"Failed to spawn asset {asset.id_}")
            continue

        assert isinstance(spawned_data, hatchery.spawn.ModelSpawnedData)

        instance_root = spawned_data.instancer
        instance_root.matrix_world = old_model_matrix
        instance_root.parent = old_parent
        instance_root.color = old_color

        for coll in old_collections:
            if instance_root.name not in coll.objects:
                coll.objects.link(instance_root)

        converted_objects.append(instance_root)

        bpy.data.batch_remove(hierarchy_objects)

    # Force Blender to evaluate view_layer data after programmatically removing/linking objects.
    # https://docs.blender.org/api/current/info_gotcha.html#no-updates-after-setting-values
    context.view_layer.update()

    # Select root instances of the newly created objects, user had to have them selected before,
    # otherwise they wouldn't be converted at all.
    for obj in converted_objects:
        obj.select_set(True)

    if (
        previous_active_obj_name is not None
        and previous_active_obj_name in context.view_layer.objects
    ):
        context.view_layer.objects.active = bpy.data.objects[previous_active_obj_name]

    return converted_objects


@polib.log_helpers_bpy.logged_operator
class MakeSelectionEditable(bpy.types.Operator):
    bl_idname = "engon.make_selection_editable"
    bl_label = "Convert to Editable"
    bl_description = "Converts Collections into Mesh Data with Editable Materials"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        selected_objects_and_parents_names = polib.asset_pack_bpy.make_selection_editable(
            context, True, keep_selection=True, keep_active=True
        )
        pack_paths = asset_registry.instance.get_packs_paths()

        logger.info(f"Resulting objects and parents: {selected_objects_and_parents_names}")

        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        if prefs.spawn_options.remove_duplicates:
            filters = [polib.remove_duplicates_bpy.polygoniq_duplicate_data_filter]
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.materials, filters, pack_paths
            )
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.images, filters, pack_paths
            )
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.node_groups, filters, pack_paths
            )

        return {'FINISHED'}


MODULE_CLASSES.append(MakeSelectionEditable)


@polib.log_helpers_bpy.logged_operator
class MakeSelectionLinked(bpy.types.Operator):
    bl_idname = "engon.make_selection_linked"
    bl_label = "Convert to Linked"
    bl_description = (
        "Converts selected objects to their linked variants from "
        "engon asset packs. WARNING: This operation removes "
        "all local changes. Doesn't work on particle systems, "
        "only polygoniq assets are supported by this operator"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.mode == 'OBJECT'
            and next(
                polib.asset_pack_bpy.get_polygoniq_objects(
                    context.selected_objects, include_linked=False
                ),
                None,
            )
            is not None
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        converted_objects = make_selection_linked(
            context,
            asset_registry.instance.master_asset_provider,
            asset_registry.instance.master_file_provider,
        )

        self.report({'INFO'}, f"Converted {len(converted_objects)} object(s) to linked")

        return {'FINISHED'}


MODULE_CLASSES.append(MakeSelectionLinked)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
