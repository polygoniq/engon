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
import enum
import math
import mathutils
import typing
import logging
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


MODULE_CLASSES: typing.List[typing.Any] = []


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

    class DistributionType(enum.Enum):
        LINE = "Line"
        ROWS = "Rows"
        SQUARE_GRID = "Square Grid"

    distribution_type: bpy.props.EnumProperty(
        name="Distribution Type",
        description="How to spread the objects",
        items=[
            (DistributionType.LINE.value, DistributionType.LINE.value, "Spread assets in one line"),
            (
                DistributionType.ROWS.value,
                DistributionType.ROWS.value,
                "Spread assets in rows and colums",
            ),
            (
                DistributionType.SQUARE_GRID.value,
                DistributionType.SQUARE_GRID.value,
                "Spread assets in grid",
            ),
        ],
        default=DistributionType.LINE.value,
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

        if self.distribution_type == self.DistributionType.ROWS.value:
            row = layout.row(align=False)
            row.prop(self, "objects_in_a_row", text="")

    def execute(self, context: bpy.types.Context):
        if self.distribution_type == self.DistributionType.LINE.value:
            row_size = len(context.selected_objects)
        elif self.distribution_type == self.DistributionType.ROWS.value:
            row_size = self.objects_in_a_row
        elif self.distribution_type == self.DistributionType.SQUARE_GRID.value:
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
                bbox_at_origin = hatchery.bounding_box.AlignedBox()
                bbox_at_origin.extend_by_object(obj)

                if not bbox_at_origin.is_valid():
                    bbox_at_origin.extend_by_point(mathutils.Vector((0.0, 0.0, 0.0)))

                obj.matrix_world.translation = mathutils.Vector(
                    (current_column_x, current_row_y, cursor_location[2])
                )

                if self.use_bounding_box_for_offset:
                    min_offset = bbox_at_origin.min
                    min_offset[2] = 0.0
                    obj.matrix_world.translation -= min_offset

                    bbox_placed = hatchery.bounding_box.AlignedBox()
                    bbox_placed.extend_by_object(obj)

                    if not bbox_placed.is_valid():
                        bbox_placed.extend_by_point(obj.location)

                    current_column_x = bbox_placed.max.x
                    future_row_y = max(future_row_y, bbox_placed.max.y)

                current_column_x += self.column_x_offset

            current_row_y = future_row_y + self.row_y_offset

        return {'FINISHED'}


MODULE_CLASSES.append(SpreadObjects)


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
        row = col.row()
        row.operator(SpreadObjects.bl_idname, icon='IMGDISPLAY')


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
