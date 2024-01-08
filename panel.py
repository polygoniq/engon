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
import random
import polib
from . import mapr_browser
from . import asset_registry
from . import preferences
from . import blend_maintenance
logger = logging.getLogger(f"polygoniq.{__name__}")


class EngonPanelMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class MakeSelectionEditable(bpy.types.Operator):
    bl_idname = "engon.make_selection_editable"
    bl_label = "Convert to Editable"
    bl_description = "Converts Collections into Mesh Data with Editable Materials"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context):
        selected_objects_and_parents_names = polib.asset_pack_bpy.make_selection_editable(
            context, True, keep_selection=True, keep_active=True)
        pack_paths = asset_registry.instance.get_packs_paths()

        logger.info(
            f"Resulting objects and parents: {selected_objects_and_parents_names}")

        if preferences.get_preferences(context).general_preferences.remove_duplicates:
            filters = [polib.remove_duplicates_bpy.polygoniq_duplicate_data_filter]
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.materials, filters, pack_paths)
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.images, filters, pack_paths)
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.node_groups, filters, pack_paths)

        return {'FINISHED'}


MODULE_CLASSES.append(MakeSelectionEditable)


@polib.log_helpers_bpy.logged_operator
class MakeSelectionLinked(bpy.types.Operator):
    bl_idname = "engon.make_selection_linked"
    bl_label = "Convert to Linked"
    bl_description = "Converts selected objects to their linked variants from " \
        "engon asset packs. WARNING: This operation removes " \
        "all local changes. Doesn't work on particle systems, " \
        "only polygoniq assets are supported by this operator"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT' and next(
            polib.asset_pack_bpy.get_polygoniq_objects(
                context.selected_objects, include_linked=False),
            None
        ) is not None

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        converted_objects = polib.asset_pack_bpy.make_selection_linked(
            context, asset_registry.instance.get_install_paths_by_engon_feature())
        logger.info(f"Resulting converted objects: {converted_objects}")

        return {'FINISHED'}


MODULE_CLASSES.append(MakeSelectionLinked)


@polib.log_helpers_bpy.logged_operator
class SnapToGround(bpy.types.Operator):
    bl_idname = "engon.snap_to_ground_bpy"
    bl_label = "Snap to Ground"
    bl_description = "Put selected assets as close to the ground as possible"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        # We have no way to know which objects are part of ground so we ray-cast all of them except
        # what's selected. The objects that the user wants to snap to ground are the selected objects.
        # Since we are going to be moving all of those we can't do self-collisions.

        objects_to_snap = polib.asset_pack_bpy.filter_out_descendants_from_objects(
            context.selected_objects)
        objects_to_snap_hierarchy = set()
        for obj in objects_to_snap:
            objects_to_snap_hierarchy.update(polib.asset_pack_bpy.get_hierarchy(obj))

        ground_objects = [obj for obj in context.visible_objects if obj.type ==
                          'MESH' and obj not in objects_to_snap_hierarchy]
        snapped_objects_names = []

        for obj in objects_to_snap:
            if polib.asset_pack_bpy.is_polygoniq_object(obj, lambda x: x == "traffiq"):
                logger.info(f"Determined that {obj.name} is a traffiq asset.")
                # if editable car is selected with all its child objects -> skip these child objects
                if polib.asset_pack_bpy.is_traffiq_asset_part(obj, polib.asset_pack_bpy.TraffiqAssetPart.Wheel):
                    continue
                if polib.asset_pack_bpy.is_traffiq_asset_part(obj, polib.asset_pack_bpy.TraffiqAssetPart.Brake):
                    continue
                if polib.asset_pack_bpy.is_traffiq_asset_part(obj, polib.asset_pack_bpy.TraffiqAssetPart.Lights):
                    continue

                root_object, body, lights, wheels, brakes = \
                    polib.asset_pack_bpy.decompose_traffiq_vehicle(obj)
                if root_object is not None:  # traffiq behavior
                    logger.debug(
                        f"Was able to decompose {obj.name} as if it was a traffiq vehicle. "
                        f"Snapping to ground using the traffiq behavior.")
                    if len(wheels) > 0:
                        logger.info(
                            f"Using {len(wheels)} separate wheels to determine final rotation...")
                        polib.snap_to_ground_bpy.snap_to_ground_separate_wheels(
                            obj,
                            root_object,
                            wheels,
                            ground_objects
                        )
                    else:
                        logger.info(
                            f"No wheels present in this asset, using snap normal to determine "
                            f"final rotation...")
                        polib.snap_to_ground_bpy.snap_to_ground_adjust_rotation(
                            obj,
                            root_object,
                            ground_objects
                        )

                    snapped_objects_names.append(obj.name)

            elif polib.asset_pack_bpy.is_polygoniq_object(obj, lambda x: x == "botaniq"):
                logger.info(
                    f"Determined that {obj.name} is a botaniq asset. Going to snap without "
                    f"adjusting rotation.")

                if obj.type == 'MESH':
                    polib.snap_to_ground_bpy.snap_to_ground_no_rotation(obj, obj, ground_objects)
                    snapped_objects_names.append(obj.name)
                elif obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION':
                    collection = obj.instance_collection
                    if len(collection.objects) >= 1:
                        for collection_object in collection.objects:
                            if collection_object.type == 'MESH':
                                polib.snap_to_ground_bpy.snap_to_ground_no_rotation(
                                    obj, collection_object, ground_objects)
                                snapped_objects_names.append(obj.name)
                                break

            else:  # generic behavior
                logger.info(
                    f"Determined that {obj.name} is a generic asset. Going to snap with "
                    f"adjustment to rotation.")

                if obj.type == 'MESH':
                    polib.snap_to_ground_bpy.snap_to_ground_adjust_rotation(
                        obj, obj, ground_objects)
                    snapped_objects_names.append(obj.name)
                elif obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION':
                    collection = obj.instance_collection
                    if len(collection.objects) >= 1:
                        for collection_object in collection.objects:
                            if collection_object.type == 'MESH':
                                polib.snap_to_ground_bpy.snap_to_ground_adjust_rotation(
                                    obj, collection_object, ground_objects)
                                snapped_objects_names.append(obj.name)
                                break

        logger.info(f"Snapped the following objects to the ground: {snapped_objects_names}")
        return {'FINISHED'}


MODULE_CLASSES.append(SnapToGround)


@polib.log_helpers_bpy.logged_operator
class RandomizeTransform(bpy.types.Operator):
    bl_idname = "engon.randomize_transform"
    bl_label = "Random Transform"
    bl_description = "Randomize Scale and Rotation of Selected Objects"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected_objects_names = [obj.name for obj in context.selected_objects]
        logger.info(f"Working on selected objects: {selected_objects_names}")
        bpy.ops.object.randomize_transform(
            random_seed=random.randint(0, 10000),
            use_loc=False,
            rot=(0.0349066, 0.0349066, 3.14159),
            scale=(1.1, 1.1, 1.1),
            scale_even=True
        )

        return {'FINISHED'}


MODULE_CLASSES.append(RandomizeTransform)


@polib.log_helpers_bpy.logged_operator
class ResetTransform(bpy.types.Operator):
    bl_idname = "engon.reset_transform"
    bl_label = "Reset Transform"
    bl_description = "Reset Rotation and Scale of Selected Objects to (0,0,0)"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        selected_objects_names = [obj.name for obj in context.selected_objects]
        logger.info(f"Working on selected objects: {selected_objects_names}")

        bpy.ops.object.rotation_clear()
        bpy.ops.object.scale_clear()

        return {'FINISHED'}


MODULE_CLASSES.append(ResetTransform)


@polib.log_helpers_bpy.logged_panel
class EngonPanel(EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon"
    bl_label = "engon"
    bl_category = "polygoniq"
    bl_order = 0
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.template_icon(
            icon_value=polib.ui_bpy.icon_manager.get_polygoniq_addon_icon_id("engon"))

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            mapr_browser.browser.MAPR_BrowserOpenAssetPacksPreferences.bl_idname, text="", icon='SETTINGS')

    def draw(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context)
        col = self.layout.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.5
        if mapr_browser.browser.MAPR_BrowserChooseArea.is_running:
            row.label(text="Select area with mouse!", icon='RESTRICT_SELECT_ON')
        else:
            row.operator(
                mapr_browser.browser.MAPR_BrowserChooseArea.bl_idname,
                text="Browse Assets",
                icon='RESTRICT_SELECT_OFF'
            )
            row.operator(
                mapr_browser.browser.MAPR_BrowserOpen.bl_idname,
                text="",
                icon='WINDOW'
            )
        if prefs.mapr_preferences.prefs_hijacked:
            row = row.row(align=True)
            row.scale_x = 1.2
            row.alert = True
            row.operator(
                mapr_browser.browser.MAPR_BrowserClose.bl_idname,
                text="",
                icon='PANEL_CLOSE'
            )
        col.separator()

        col.label(text="Convert selection:")
        row = polib.ui_bpy.scaled_row(col, 1.5, align=True)
        row.operator(MakeSelectionLinked.bl_idname, text="Linked", icon='LINKED')
        row.operator(MakeSelectionEditable.bl_idname, text="Editable", icon='MESH_DATA')
        row.prop(prefs.general_preferences, "remove_duplicates",
                 text="", toggle=1, icon='FULLSCREEN_EXIT')
        col.separator()

        col.label(text="Transform selection:")
        row = polib.ui_bpy.scaled_row(col, 1.5, align=True)
        row.operator(SnapToGround.bl_idname, text="Ground", icon='IMPORT')
        row.operator(RandomizeTransform.bl_idname, text="Random", icon='ORIENTATION_GIMBAL')
        row.operator(ResetTransform.bl_idname, text="", icon='LOOP_BACK')
        col.separator()


MODULE_CLASSES.append(EngonPanel)


@polib.log_helpers_bpy.logged_panel
class MaintenancePanel(EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_migrator"
    bl_parent_id = EngonPanel.bl_idname
    bl_label = ".blend maintenance"
    bl_options = {'DEFAULT_CLOSED'}
    # We want to display the maintenance sub-panel last, as it won't be a frequently used feature
    bl_order = 99

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator(blend_maintenance.migrator.RemoveDuplicates.bl_idname, icon='FULLSCREEN_EXIT')
        col.operator(blend_maintenance.migrator.FindMissingFiles.bl_idname, icon='ZOOM_ALL')
        col.operator(blend_maintenance.migrator.MigrateLibraryPaths.bl_idname, icon='SHADERFX')
        col.operator(blend_maintenance.migrator.MigrateFromMaterialiq4.bl_idname, icon='SHADERFX')


MODULE_CLASSES.append(MaintenancePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
