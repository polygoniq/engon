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

from . import addon_updater
from . import addon_updater_ops
import bpy
import bmesh
import enum
import math
import mathutils
import typing
import logging
import collections
import random
from . import polib
from . import hatchery
from . import browser
from . import preferences
from . import blend_maintenance
from . import convert_selection

logger = logging.getLogger(f"polygoniq.{__name__}")


class EngonPanelMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"


MODULE_CLASSES: list[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class SnapToGround(bpy.types.Operator):
    bl_idname = "engon.snap_to_ground"
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
            context.selected_objects
        )
        objects_to_snap_hierarchy = set()
        for obj in objects_to_snap:
            objects_to_snap_hierarchy.update(polib.asset_pack_bpy.get_hierarchy(obj))

        ground_objects = [
            obj
            for obj in context.visible_objects
            if obj.type == 'MESH' and obj not in objects_to_snap_hierarchy
        ]
        if len(ground_objects) == 0:
            logger.warning("Ground object not found")
            self.report(
                {'WARNING'},
                "Ground object was not found, make sure there is "
                "another object under the selected objects",
            )
            return {'FINISHED'}

        snapped_objects_names = []
        no_ground_object_names = []
        wrong_type_object_names = []

        for obj in objects_to_snap:
            is_snapped = False
            if polib.asset_pack_bpy.is_polygoniq_object(obj, lambda x: x == "traffiq"):
                logger.info(f"Determined that {obj.name} is a traffiq asset.")
                # objects with wheels are snapped based on the wheels
                decomposed_car = polib.asset_pack_bpy.decompose_traffiq_vehicle(obj)
                if (
                    decomposed_car is not None and len(decomposed_car.wheels) > 0
                ):  # traffiq vehicle behavior
                    filtered_ground_objects = [
                        obj
                        for obj in ground_objects
                        if not polib.asset_pack_bpy.is_part_of_decomposed_car(obj, decomposed_car)
                    ]
                    logger.debug(
                        f"Was able to decompose {obj.name} as if it was a traffiq vehicle. "
                        f"Using {len(decomposed_car.wheels)} separate wheels to determine final rotation..."
                    )
                    snappable_object = decomposed_car.root_object
                    # if it's a linked car, we want to move the whole collection
                    if obj.instance_type == 'COLLECTION':
                        snappable_object = obj

                    is_snapped = polib.snap_to_ground_bpy.snap_to_ground_separate_wheels(
                        snappable_object, decomposed_car.wheels, filtered_ground_objects
                    )
                else:
                    # other traffiq assets are treated as generic assets
                    logger.info(
                        f"No wheels present in this asset, using generic snapping method for {obj.name}."
                    )
                    is_snapped = polib.snap_to_ground_bpy.snap_to_ground_adjust_rotation(
                        obj, ground_objects
                    )
            elif polib.asset_pack_bpy.is_polygoniq_object(obj, lambda x: x == "botaniq"):
                logger.info(
                    f"Determined that {obj.name} is a botaniq asset. Going to snap without "
                    f"adjusting rotation."
                )
                try:
                    is_snapped = polib.snap_to_ground_bpy.snap_to_ground_no_rotation(
                        obj, ground_objects
                    )
                except ValueError:
                    logger.exception(f"Failed to snap {obj.name} to the ground.")
                    wrong_type_object_names.append(obj.name)
                    continue
            else:  # generic behavior
                logger.info(
                    f"Determined that {obj.name} is a generic asset. Going to snap with "
                    f"adjustment to rotation."
                )
                is_snapped = polib.snap_to_ground_bpy.snap_to_ground_adjust_rotation(
                    obj, ground_objects
                )

            if is_snapped:
                snapped_objects_names.append(obj.name)
            else:
                no_ground_object_names.append(obj.name)

        if len(no_ground_object_names) + len(wrong_type_object_names) > 0:
            problems = []

            if len(no_ground_object_names) > 0:
                problems.append(
                    "Ground object was not found, make sure there is another object under "
                    "the selected objects"
                )
            if len(wrong_type_object_names) > 0:
                problems.append("This object type can not be snapped")

            message = (
                f"{len(no_ground_object_names) + len(wrong_type_object_names)}"
                f" object(s) were not snapped to the ground"
            )

            logger.warning(
                f"{message}. "
                f"Ground object was not found: {no_ground_object_names}, "
                f"Object type can not be snapped: {wrong_type_object_names}."
            )
            problems_string = ". ".join(problems)
            self.report({'WARNING'}, f"{message}. Encountered issues: {problems_string}")

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
            scale_even=True,
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


@polib.log_helpers_bpy.logged_operator
class SpreadObjects(bpy.types.Operator):
    bl_idname = "engon.spread_objects"
    bl_label = "Spread Objects"
    bl_description = "Spreads selected objects into a grid"
    bl_options = {'REGISTER', 'UNDO'}

    class DistributionType(enum.StrEnum):
        LINE = "Line"
        ROWS = "Rows"
        SQUARE_GRID = "Square Grid"

    distribution_type: bpy.props.EnumProperty(
        name="Distribution Type",
        description="How to spread the objects",
        items=[
            (DistributionType.LINE, DistributionType.LINE, "Spread assets in one line"),
            (
                DistributionType.ROWS,
                DistributionType.ROWS,
                "Spread assets in rows and colums",
            ),
            (
                DistributionType.SQUARE_GRID,
                DistributionType.SQUARE_GRID,
                "Spread assets in grid",
            ),
        ],
        default=DistributionType.LINE,
    )

    use_bounding_box_for_offset: bpy.props.BoolProperty(
        name="Use Bounding Box for Offset",
        description="If enabled, each objects bounding box is used in addition to the fixed "
        "X, Y Offset. Otherwise just the fixed X and Y offset is used",
        default=True,
    )

    column_x_offset: bpy.props.FloatProperty(name="X Offset", default=0.1, min=0.0)

    row_y_offset: bpy.props.FloatProperty(name="Y Offset", default=0.1, min=0.0)

    automatic_square_grid: bpy.props.BoolProperty(
        name="Automatic Square Grid",
        description="If enabled, the number of objects in one row is automatically calculated to "
        "make the grid close to a square",
        default=True,
    )

    objects_in_a_row: bpy.props.IntProperty(
        name="Objects in a Row",
        description="How many objects are there in one row of the grid. Only used if Automatic "
        "Square Grid is disabled",
        default=10,
        min=1,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        # at least two objects required to do anything useful
        return len(context.selected_objects) >= 2

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=False)
        row.prop(self, "use_bounding_box_for_offset", text="")
        row.label(text="Use Bounding Box for Offset")

        row = layout.row(align=False)
        row.prop(self, "column_x_offset", text="X Offset")
        row.prop(self, "row_y_offset", text="Y Offset")

        row = layout.row(align=False)
        row.label(text="Distribution Type")
        row.prop(self, "distribution_type", text="")

        if self.distribution_type == self.DistributionType.ROWS:
            row = layout.row(align=False)
            row.prop(self, "objects_in_a_row", text="")

    def execute(self, context: bpy.types.Context):
        if self.distribution_type == self.DistributionType.LINE:
            row_size = len(context.selected_objects)
        elif self.distribution_type == self.DistributionType.ROWS:
            row_size = self.objects_in_a_row
        elif self.distribution_type == self.DistributionType.SQUARE_GRID:
            row_size = math.ceil(math.sqrt(len(context.selected_objects)))
        else:
            raise ValueError("Invalid distribution option")

        number_of_rows = math.ceil(len(context.selected_objects) / row_size)

        cursor_location = bpy.context.scene.cursor.location
        current_row_y = cursor_location.y
        selected_objects_sorted = sorted(context.selected_objects, key=lambda obj: obj.name)
        for i in range(number_of_rows):
            current_column_x = cursor_location.x
            objects_in_row = selected_objects_sorted[i * row_size : (i + 1) * row_size]
            # we need to build up a future_row_y based on placed bounding boxes if using offset
            # by bounding boxes. if fixed offset is used this will just stay at current_row_y
            future_row_y = current_row_y
            for obj in objects_in_row:
                obj.matrix_world.translation = mathutils.Vector((0.0, 0.0, 0.0))
                bbox_at_origin = hatchery.bounding_box.BoundingBox()
                bbox_at_origin.extend_by_object(obj)

                if not bbox_at_origin.is_valid():
                    bbox_at_origin.extend_by_world_point(mathutils.Vector((0.0, 0.0, 0.0)))

                obj.matrix_world.translation = mathutils.Vector(
                    (current_column_x, current_row_y, cursor_location[2])
                )

                if self.use_bounding_box_for_offset:
                    min_offset = bbox_at_origin.get_min()
                    min_offset[2] = 0.0
                    obj.matrix_world.translation -= min_offset

                    bbox_placed = hatchery.bounding_box.BoundingBox()
                    bbox_placed.extend_by_object(obj)

                    if not bbox_placed.is_valid():
                        bbox_placed.extend_by_world_point(obj.location)

                    current_column_x = bbox_placed.get_max().x
                    future_row_y = max(future_row_y, bbox_placed.get_max().y)

                current_column_x += self.column_x_offset

            current_row_y = future_row_y + self.row_y_offset

        return {'FINISHED'}


MODULE_CLASSES.append(SpreadObjects)


@polib.log_helpers_bpy.logged_operator
class MakeObjectsInstanced(bpy.types.Operator):
    bl_idname = "engon.tools_make_objects_instances"
    bl_label = "Make Objects Instanced"
    bl_description = (
        "Makes selected objects with the same mesh data instanced using collection instances"
    )
    bl_options = {'UNDO', 'REGISTER'}

    INSTANCES_COLL_NAME = "instances"
    INSTANCES_COLL_COLOR = 'COLOR_07'

    use_common_collection: bpy.props.BoolProperty(
        name="Use Common Collection",
        description="If True new instances are created in one common collection, otherwise active "
        "collection is used",
        default=True,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            next(
                filter(
                    lambda obj: obj.type == 'MESH' and obj.data is not None,
                    context.selected_objects,
                ),
                None,
            )
            is not None
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        mesh_data_obj_map: collections.defaultdict[bpy.types.Mesh, set[bpy.types.Object]] = (
            collections.defaultdict(set)
        )

        for obj in context.selected_objects:
            if obj.type != 'MESH' or obj.data is None:
                continue

            assert isinstance(obj.data, bpy.types.Mesh)
            mesh_data_obj_map[obj.data].update({obj})

        for mesh in mesh_data_obj_map:
            obj_users = list(mesh_data_obj_map[mesh])
            matrices = [o.matrix_world.copy() for o in obj_users]

            first_obj: bpy.types.Object = obj_users[0]
            # Reset first object transform with identity matrix
            first_obj.matrix_world = mathutils.Matrix()

            for coll in first_obj.users_collection:
                coll.objects.unlink(first_obj)

            instance_coll = bpy.data.collections.new("Instance_" + mesh.name)

            if self.use_common_collection:
                instances_master_coll = polib.asset_pack_bpy.collection_get(
                    context, self.INSTANCES_COLL_NAME
                )
                instances_master_coll.color_tag = self.INSTANCES_COLL_COLOR
                instances_master_coll.children.link(instance_coll)
            else:
                context.scene.collection.children.link(instance_coll)

            instance_coll.objects.link(first_obj)
            layer_collection = polib.asset_pack_bpy.find_layer_collection(
                context.view_layer.layer_collection, instance_coll
            )
            if layer_collection is not None:
                layer_collection.exclude = True

            for matrix in matrices:
                empty: bpy.types.Object = bpy.data.objects.new(mesh.name, None)
                empty.matrix_world = matrix
                empty.instance_collection = instance_coll
                empty.instance_type = 'COLLECTION'
                context.scene.collection.objects.link(empty)
                empty.select_set(True)

            for obj in obj_users[1:]:
                bpy.data.objects.remove(obj)

        return {'FINISHED'}


MODULE_CLASSES.append(MakeObjectsInstanced)


@polib.log_helpers_bpy.logged_operator
class GroupObjects(bpy.types.Operator):
    bl_idname = "engon.group_objects"
    bl_label = "Group Selected Objects"
    bl_description = (
        "Surround selected objects with a mesh bounding box and parent them to it."
        "That makes them easily movable together while keeping everything editable"
    )
    bl_options = {'UNDO', 'REGISTER'}

    BBOX_NAME = "grouped_objects_bbox"

    axis_aligned_bbox: bpy.props.BoolProperty(
        name="Axis Aligned Bounding Box",
        description=(
            "If enabled, bounding box will be created as an axis-aligned box. "
            "If disabled, bounding box will be created with the orientation of the active object."
        ),
        default=True,
    )

    only_mesh: bpy.props.BoolProperty(
        name="Only Mesh Objects",
        description="If enabled, only mesh objects are considered for bounding box calculation",
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(context.selected_objects) > 0

    def execute(self, context: bpy.types.Context):
        assert len(context.selected_objects) > 0

        # We need to force-update matrix world of all selected objects
        # they are reset to identity matrix when the operator is called from redo panel
        context.view_layer.update()

        if not self.axis_aligned_bbox and context.active_object is not None:
            _, bbox_rot, _ = context.active_object.matrix_world.decompose()
            bbox_matrix = context.active_object.matrix_world
        else:
            bbox_rot = mathutils.Quaternion()
            bbox_matrix = mathutils.Matrix.Identity(4)

        bbox = hatchery.bounding_box.BoundingBox(bbox_matrix)
        object_filter = lambda o: o.type == 'MESH' if self.only_mesh else lambda o: True
        for obj in context.selected_objects:
            bbox.extend_by_object(obj, object_filter=object_filter)

        bbox_center = bbox.get_center(world=True)
        bbox_dimensions = bbox.get_size(world=True)

        bbox_bmesh = bmesh.new()
        bbox_mesh = bpy.data.meshes.new(self.BBOX_NAME)
        # Create a cube with correct scale
        bmesh.ops.create_cube(
            bbox_bmesh, size=1, matrix=mathutils.Matrix.Diagonal((*bbox_dimensions, 1))
        )
        bbox_bmesh.to_mesh(bbox_mesh)
        bbox_bmesh.free()
        bbox_obj = bpy.data.objects.new(self.BBOX_NAME, bbox_mesh)
        bbox_obj.location = bbox_center
        rot_mode = bbox_obj.rotation_mode
        bbox_obj.rotation_mode = 'QUATERNION'
        bbox_obj.rotation_quaternion = bbox_rot
        bbox_obj.rotation_mode = rot_mode
        bbox_obj.hide_render = True
        context.scene.collection.objects.link(bbox_obj)

        bbox_obj.display_type = 'BOUNDS'

        ancestors = polib.asset_pack_bpy.filter_out_descendants_from_objects(
            context.selected_objects
        )

        # NOTE: Typically using an operator is not desired,
        # but in this case the parent_set operator handles for us complicated transformations
        # and edge cases in existing parenting relations of ancestors
        with context.temp_override(
            selected_objects=ancestors, active_object=bbox_obj, object=bbox_obj
        ):
            bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

        context.view_layer.objects.active = bbox_obj
        bbox_obj.select_set(True)
        surrounding_object_names = ", ".join(o.name for o in context.selected_objects)
        logger.info(f"Bounding box surrounding objects {surrounding_object_names} created")
        return {'FINISHED'}


MODULE_CLASSES.append(GroupObjects)


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
            icon_value=polib.ui_bpy.icon_manager.get_polygoniq_addon_icon_id("engon")
        )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        master_row = self.layout.row(align=True)
        if addon_updater.Updater.update_ready:
            op = master_row.operator(
                preferences.ShowReleaseNotes.bl_idname, text="Update", icon='IMPORT'
            )
            op.release_tag = ""
            op.update_operator_bl_idname = addon_updater_ops.AddonUpdaterUpdateNow.bl_idname
        master_row.row().operator(
            browser.browser.MAPR_BrowserOpenAssetPacksPreferences.bl_idname,
            text="",
            icon='SETTINGS',
        )
        polib.ui_bpy.draw_doc_button(
            master_row.row(), __package__, rel_url="panels/engon/panel_overview"
        )

    def draw(self, context: bpy.types.Context):
        polib.ui_bpy.draw_conflicting_addons(
            self.layout, __package__, preferences.CONFLICTING_ADDONS
        )
        prefs = preferences.prefs_utils.get_preferences(context)
        mapr_prefs = prefs.browser_preferences
        what_is_new_prefs = prefs.what_is_new_preferences
        col = self.layout.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.5
        if browser.browser.MAPR_BrowserChooseArea.is_running:
            row.label(text="Select area with mouse!", icon='RESTRICT_SELECT_ON')
        else:
            new_packs = browser.what_is_new.get_updated_asset_packs(context)
            is_something_new = what_is_new_prefs.display_what_is_new and len(new_packs) > 0
            row.operator(
                browser.browser.MAPR_BrowserChooseArea.bl_idname,
                text="Browse NEW Assets" if is_something_new else "Browse Assets",
                icon='OUTLINER_OB_LIGHT' if is_something_new else 'RESTRICT_SELECT_OFF',
            )
            row.operator(browser.browser.MAPR_BrowserOpen.bl_idname, text="", icon='WINDOW')
        if mapr_prefs.prefs_hijacked:
            row = row.row(align=True)
            row.scale_x = 1.2
            row.alert = True
            row.operator(browser.browser.MAPR_BrowserClose.bl_idname, text="", icon='PANEL_CLOSE')
        col.separator()

        col.label(text="Convert selection:")
        row = polib.ui_bpy.scaled_row(col, 1.5, align=True)
        row.operator(convert_selection.MakeSelectionLinked.bl_idname, text="Linked", icon='LINKED')
        row.operator(
            convert_selection.MakeSelectionEditable.bl_idname, text="Editable", icon='MESH_DATA'
        )
        row.prop(
            mapr_prefs.spawn_options, "remove_duplicates", text="", toggle=1, icon='FULLSCREEN_EXIT'
        )
        col.separator()

        col.label(text="Transform selection:")
        row = polib.ui_bpy.scaled_row(col, 1.5, align=True)
        row.operator(SnapToGround.bl_idname, text="Ground", icon='IMPORT')
        row.operator(RandomizeTransform.bl_idname, text="Random", icon='ORIENTATION_GIMBAL')
        row.operator(ResetTransform.bl_idname, text="", icon='LOOP_BACK')
        col.separator()

        col.label(text="Object tools:")
        col.operator(SpreadObjects.bl_idname, icon='IMGDISPLAY')
        col.operator(MakeObjectsInstanced.bl_idname, icon='OUTLINER_OB_GROUP_INSTANCE')
        col.operator(GroupObjects.bl_idname, icon='SELECT_SET')


MODULE_CLASSES.append(EngonPanel)


@polib.log_helpers_bpy.logged_panel
class MaintenancePanel(EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_migrator"
    bl_parent_id = EngonPanel.bl_idname
    bl_label = ".blend maintenance"
    bl_options = {'DEFAULT_CLOSED'}
    # We want to display the maintenance sub-panel last, as it won't be a frequently used feature
    bl_order = 99

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='BLENDER')

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
