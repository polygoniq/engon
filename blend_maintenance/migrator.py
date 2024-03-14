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
import polib
import hatchery
import mapr
import logging
import itertools
import functools
import os
import re
import collections
from . import asset_changes
from .. import preferences
from .. import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")

MODULE_CLASSES: typing.List[typing.Type] = []


@polib.log_helpers_bpy.logged_operator
class RemoveDuplicates(bpy.types.Operator):
    bl_idname = "engon.remove_duplicates"
    bl_label = "Remove Duplicate Data"
    bl_description = "Merges duplicate materials, node groups and images. Saves memory"
    bl_options = {'REGISTER'}

    def execute(self, context: bpy.types.Context):
        pack_paths = asset_registry.instance.get_packs_paths()
        filters = [polib.remove_duplicates_bpy.polygoniq_duplicate_data_filter]
        removed_material_names = polib.remove_duplicates_bpy.remove_duplicate_datablocks(
            bpy.data.materials, filters, pack_paths)
        logger.info(f"Removed materials: {removed_material_names}")
        removed_images_names = polib.remove_duplicates_bpy.remove_duplicate_datablocks(
            bpy.data.images, filters, pack_paths)
        logger.info(f"Removed images: {removed_images_names}")
        removed_node_names = polib.remove_duplicates_bpy.remove_duplicate_datablocks(
            bpy.data.node_groups, filters, pack_paths)
        logger.info(f"Removed node groups: {removed_node_names}")

        if len(removed_material_names) > 0 or len(removed_images_names) > 0 or len(removed_node_names) > 0:
            self.report(
                {'INFO'},
                f"{len(removed_material_names)} materials, {len(removed_images_names)} images, "
                f"{len(removed_node_names)} nodes have been merged."
            )
        else:
            self.report(
                {'INFO'},
                "No duplicates to merge."
            )

        return {'FINISHED'}


MODULE_CLASSES.append(RemoveDuplicates)


@polib.log_helpers_bpy.logged_operator
class FindMissingFiles(bpy.types.Operator):
    bl_idname = "engon.find_missing_files"
    bl_label = "Find Missing Files"
    bl_description = \
        "Use Blender's Find Missing Files operator with engon's asset pack install paths"
    bl_options = {'REGISTER', 'UNDO'}

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        missing_datablocks: typing.Set[bpy.types.ID] = set()
        datablocks_to_reload: typing.List[bpy.types.ID] = []
        for datablock in itertools.chain(bpy.data.libraries, bpy.data.images):
            if not polib.utils_bpy.isfile_case_sensitive(bpy.path.abspath(datablock.filepath, library=datablock.library)):
                missing_datablocks.add(datablock)

        for pack in asset_registry.instance.get_registered_packs():
            found_datablocks: typing.List[bpy.types.ID] = []
            for datablock in missing_datablocks:
                new_path = pack.get_filepath_from_basename(bpy.path.basename(datablock.filepath))
                if new_path is not None:
                    datablock.filepath = new_path
                    found_datablocks.append(datablock)

            for datablock in found_datablocks:
                missing_datablocks.remove(datablock)
                datablocks_to_reload.append(datablock)

        for datablock in datablocks_to_reload:
            try:
                datablock.reload()
                logger.info(f"Reloaded '{datablock.name}'")
            except ReferenceError:
                logger.error("ReferenceError: Failed to reload some data")

        return {'FINISHED'}


MODULE_CLASSES.append(FindMissingFiles)


@polib.log_helpers_bpy.logged_operator
class MigrateFromMaterialiq4(bpy.types.Operator):
    bl_idname = "engon.materialiq_migrate_from_materialiq4"
    bl_label = "Migrate from materialiq4"
    bl_description = \
        "Finds materialiq4 materials and replaces them with their equivalents from the latest version of materialiq"

    def execute(self, context: bpy.types.Context):
        spawn_options = preferences.get_preferences(context).mapr_preferences.spawn_options
        asset_provider = asset_registry.instance.master_asset_provider
        file_provider = asset_registry.instance.master_file_provider
        spawner = mapr.blender_asset_spawner.AssetSpawner(asset_provider, file_provider)

        for material in list(bpy.data.materials):
            if material.node_tree is None:
                # can't be a materialiq4 material if it's not using nodes
                continue

            mq4_node_tree: typing.Optional[bpy.types.NodeTree] = None
            for node in polib.node_utils_bpy.find_nodes_in_tree(
                material.node_tree,
                lambda x: x.type == 'GROUP'
            ):
                if node.node_tree.name.endswith("_mqn"):
                    mq4_node_tree = node.node_tree
                    break

            mq_material_asset_id = None
            if mq4_node_tree is not None:
                mq_material_asset_id = asset_changes.MQ4_NODE_TREES_TO_MQ.get(mq4_node_tree.name)

            if mq_material_asset_id is None:
                mq4_material_name = polib.utils_bpy.remove_object_duplicate_suffix(material.name)
                mq_material_asset_id = asset_changes.MQ4_NODE_TREES_TO_MQ.get(
                    mq4_material_name)

            if mq_material_asset_id is None:
                if "_mqm" in material.name:
                    logger.error(
                        f"Tried migrating {material.name} from materialiq4, could not find a "
                        f"mapping in the node tree map or the material name map. Skipping!"
                    )
                continue

            asset_ = asset_provider.get_asset(mq_material_asset_id)
            if asset_ is None:
                logger.error(
                    f"Tried migrating {material.name} from materialiq4 to {mq_material_asset_id}, "
                    f"however we were not able to query that asset via MAPR asset_provider."
                )
                continue

            spawned_data: typing.Optional[hatchery.spawn.MaterialSpawnedData] = spawner.spawn(
                context,
                asset_,
                # We use the global spawn options - this will use the user selected texture
                # size and displacement preferences
                hatchery.spawn.MaterialSpawnOptions(
                    int(spawn_options.texture_size),
                    spawn_options.use_displacement,
                    # We don't assign the material directly to any object, we use user_remap
                    # in the next code block.
                    set()
                )
            )

            if spawned_data is not None:
                assert isinstance(spawned_data, hatchery.spawn.MaterialSpawnedData)
                material.user_remap(typing.cast(bpy.types.Material, spawned_data.material))
            else:
                logger.error(
                    f"Tried migrating {material.name} from materialiq4 to {mq_material_asset_id}, "
                    f"however none of the asset data associated spawned a valid bpy.types.Material!"
                )

        return {'FINISHED'}


MODULE_CLASSES.append(MigrateFromMaterialiq4)


# Using unbounded cache, make sure it gets cleared eventually
@functools.cache
def get_blend_datablock_names(blend_filepath: str) -> typing.Dict[str, typing.List[str]]:
    assert polib.utils_bpy.isfile_case_sensitive(bpy.path.abspath(blend_filepath))
    assert os.path.splitext(blend_filepath)[1] == ".blend"

    ret: typing.Dict[str, typing.List[str]] = {}
    with bpy.data.libraries.load(blend_filepath) as (data_from, _):
        for attr in dir(data_from):
            if not attr.startswith("__"):
                ret[attr] = getattr(data_from, attr)

    return ret


@polib.log_helpers_bpy.logged_operator
class MigrateLibraryPaths(bpy.types.Operator):
    bl_idname = "engon.migrate_library_paths"
    bl_label = "Migrate Assets"
    bl_description = (
        "Finds broken links to assets from engon asset packs caused by past refactors and fixes "
        "them. Finds missing custom properties and adds them. And more version migration tasks"
    )

    def log_and_report(self, level: int, message: str) -> None:
        if level == logging.INFO:
            logger.log(level, message)
            self.report({'INFO'}, message)
        elif level == logging.WARNING:
            logger.log(level, message)
            self.report({'WARNING'}, message)
        elif level == logging.ERROR:
            logger.log(level, message)
            self.report({'ERROR'}, message)
        else:
            # logging module defines also NOTSET, DEBUG and CRITICAL but we don't use them here
            raise ValueError(f"Unknown log level {level}")

    def fix_datablock_filepath(
        self,
        datablock: typing.Union[bpy.types.Library, bpy.types.Image],
        filename_migrations: typing.List[typing.List[asset_changes.RegexMapping]],
        pack_subdirectories: typing.Set[str],
    ) -> bool:
        filename_candidate = bpy.path.basename(datablock.filepath)
        for version_migrations in filename_migrations:
            for filename_migration in version_migrations:
                if not re.match(filename_migration.pattern, filename_candidate):
                    continue

                filename_candidate = re.sub(
                    filename_migration.pattern, filename_migration.replacement, filename_candidate)
                # TODO: Possible speed up: if we build a dictionary of all files in asset pack
                # subdirectories (key = filename, value = path), we could then query if
                # filename_candidate exists and then assign its path as library.filepath
                for directory in pack_subdirectories:
                    new_path = os.path.join(directory, filename_candidate)
                    if polib.utils_bpy.isfile_case_sensitive(bpy.path.abspath(new_path)):
                        self.log_and_report(logging.INFO, f"Migrating filepath of "
                                            f"{type(datablock).__name__} '{datablock.name}' from "
                                            f"'{datablock.filepath}' to '{new_path}'")
                        datablock.filepath = new_path
                        return True
        return False

    def fix_blend_file_libraries(
        self,
        asset_pack_migrations: typing.List[asset_changes.AssetPackMigration],
        pack_subdirectories: set[str]
    ) -> typing.List[bpy.types.Library]:
        library_filename_migrations: typing.List[typing.List[asset_changes.RegexMapping]] = []
        for migration in asset_pack_migrations:
            if len(migration.library_changes) > 0:
                library_filename_migrations.append(migration.library_changes)

        fixed_libraries: typing.List[bpy.types.Library] = []
        for library in bpy.data.libraries:
            if polib.utils_bpy.isfile_case_sensitive(bpy.path.abspath(library.filepath)):
                continue
            success = self.fix_datablock_filepath(
                library, library_filename_migrations, pack_subdirectories)
            if success:
                fixed_libraries.append(library)

        # Can't reload in loop because of potential ReferenceError
        for library in fixed_libraries:
            library.reload()

        return fixed_libraries

    def fix_image_filepaths(
        self,
        asset_pack_migrations: typing.List[asset_changes.AssetPackMigration],
        pack_subdirectories: typing.Set[str],
    ) -> typing.List[bpy.types.Image]:
        """Fixes image_datablock.filepath of editable image datablocks."""
        image_filename_migrations: typing.List[typing.List[asset_changes.RegexMapping]] = []
        for migration in asset_pack_migrations:
            if "images" in migration.datablock_changes:
                image_filename_migrations.append(migration.datablock_changes["images"])

        fixed_images: typing.List[bpy.types.Image] = []
        for image in bpy.data.images:
            if image.library is not None:
                # we handle here only datablocks stored in this blend
                continue
            if image.filepath == "":
                # packed image
                continue
            if polib.utils_bpy.isfile_case_sensitive(bpy.path.abspath(image.filepath)):
                continue

            success = self.fix_datablock_filepath(
                image, image_filename_migrations, pack_subdirectories)
            if success:
                fixed_images.append(image)

        return fixed_images

    def fix_one_datablock(
        self,
        datablock: bpy.types.ID,
        datablock_type: str,
        asset_pack_migrations: typing.List[asset_changes.AssetPackMigrations],
    ) -> typing.Optional[bpy.types.ID]:
        for pack_name, version_migrations in asset_pack_migrations:
            name_candidate = datablock.name
            for migration in version_migrations:
                datablock_changes = migration.datablock_changes.get(datablock_type, [])

                for change in datablock_changes:
                    if not re.match(change.pattern, name_candidate):
                        continue

                    name_candidate = re.sub(change.pattern, change.replacement, name_candidate)

                    lib_datablocks = get_blend_datablock_names(datablock.library.filepath)
                    if name_candidate not in lib_datablocks.get(datablock_type, []):
                        # Datablock name_candidate does not exist in library blend
                        continue

                    prop_coll = getattr(bpy.data, datablock_type)
                    # Multiple linked datablocks can have the same name, we want to get the one from
                    # migrated library.
                    new_datablock = prop_coll.get(
                        (name_candidate, datablock.library.filepath), None)
                    if new_datablock is None:
                        with bpy.data.libraries.load(datablock.library.filepath, link=True) as (data_from, data_to):
                            assert name_candidate in getattr(data_from, datablock_type)
                            setattr(data_to, datablock_type, [name_candidate])

                        new_datablock = prop_coll.get(
                            (name_candidate, datablock.library.filepath), None)
                        if new_datablock is None:
                            logger.error(f"Failed to link datablock '{name_candidate}' of type '"
                                         f"'{datablock_type}' from '{datablock.library.filepath}'!")
                            continue

                    datablock.user_remap(new_datablock)
                    self.log_and_report(logging.INFO, f"Remapped datablock '{datablock.name}' of "
                                        f"type '{datablock_type}' to '{name_candidate}' that is "
                                        f"linked from {datablock.library.filepath}")
                    return new_datablock
        self.log_and_report(logging.WARNING,
                            f"Datablock '{datablock.name}' of type '{datablock_type}' "
                            f"wasn't migrated. No suitable migration rule was found!")
        return None

    def fix_datablocks(
        self,
        asset_pack_migrations: typing.List[asset_changes.AssetPackMigrations],
    ) -> typing.List[bpy.types.ID]:
        fixed_datablocks: typing.List[bpy.types.ID] = []
        for datablock, datablock_type in polib.utils_bpy.get_all_datablocks(bpy.data):
            if datablock.library is None:
                # datablock stored in this blend
                continue

            if not os.path.isfile(bpy.path.abspath(datablock.library.filepath)):
                # we can not fix a datablock that is not in a valid library
                continue

            # Verify that the datablock needs relinking
            if bpy.app.version >= (3, 6, 0):
                data_missing = datablock.is_missing
            else:
                lib_datablocks = get_blend_datablock_names(datablock.library.filepath)
                data_missing = datablock.name not in lib_datablocks.get(datablock_type, [])

            if not data_missing:
                continue

            fixed = self.fix_one_datablock(datablock, datablock_type, asset_pack_migrations)
            if fixed is not None:
                fixed_datablocks.append(fixed)

        return fixed_datablocks

    def migrate_instance_collection_custom_props(self) -> None:
        """Ensures that root object of instanced collection contains all current custom props

        We use custom props for various features which wouldn't work if those props are missing.

        Currently, we don't update custom props of local datablocks because it's much harder to get
        new custom props from source blend for them and even if we update custom props, features may
        still not work because datablock is old.
        """
        for root_obj in bpy.data.objects:
            if root_obj.instance_type != 'COLLECTION' or root_obj.instance_collection is None:
                continue

            if "polygoniq_addon" not in root_obj and "mapr_asset_id" not in root_obj:
                # Asset doesn't come from us.
                # We were adding 'polygoniq_addon' to all spawned assets prior to engon 1.0 release.
                # We may stop using it in the future but we plan to use 'mapr_asset_id' in all
                # assets instead.
                continue

            for child_obj in root_obj.instance_collection.all_objects:
                for prop_name in child_obj.keys():
                    # Don't override values of feature-specific custom props, we don't want to
                    # change e.g. saturation of trees when migrating.
                    if prop_name.startswith(("bq_", "tq_")) and prop_name in root_obj:
                        continue
                    hatchery.utils.copy_custom_prop(child_obj, root_obj, prop_name)

    def execute(self, context: bpy.types.Context):
        """Relink broken paths caused by renaming blends in major version bump.

        We have unified addon prefix for all asset packs, meaning we had to rename the blends, and
        corresponding datablocks inside the blends.

        Unfortunately we have no way of knowing if the library path is from specific addon, so we
        need to use less then optimal approach. We first check all the missing libraries,
        if we are able to find existing library with prefixed name, either in the original location or
        in any of the asset pack subdirectories, we know from which addon it comes. Then we know
        how particular linked datablocks changed, so we can infer their new name and reload them.
        """
        try:
            pack_subdirectories_map = collections.defaultdict(set)
            for pack in asset_registry.instance.get_registered_packs():
                pack_name = pack.file_id_prefix.strip("/")

                # Gather all subdirectories of pack
                for root, _, _ in os.walk(pack.install_path):
                    pack_subdirectories_map[pack_name].add(root)

            fixed_libraries: typing.List[bpy.types.Library] = []
            fixed_images: typing.List[bpy.types.Image] = []

            for asset_pack_changes in asset_changes.ASSET_PACK_MIGRATIONS:
                pack_subdirs = pack_subdirectories_map.get(asset_pack_changes.pack_name, set())
                if len(pack_subdirs) == 0:
                    # This asset pack is not installed
                    continue

                fixed_libraries.extend(
                    self.fix_blend_file_libraries(asset_pack_changes.migrations, pack_subdirs))
                fixed_images.extend(
                    self.fix_image_filepaths(asset_pack_changes.migrations, pack_subdirs))

            fixed_datablocks = self.fix_datablocks(asset_changes.ASSET_PACK_MIGRATIONS)
            self.migrate_instance_collection_custom_props()
        finally:
            # Clear cache from this run, no need to use the memory anymore, plus asset packs
            # (and thus their blends) can change before the next run
            get_blend_datablock_names.cache_clear()

        self.log_and_report(logging.INFO,
                            f"Migrator fixed {len(fixed_libraries)} libraries, "
                            f"{len(fixed_images)} local images and "
                            f"{len(fixed_datablocks)} datablocks")
        return {'FINISHED'}


MODULE_CLASSES.append(MigrateLibraryPaths)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
