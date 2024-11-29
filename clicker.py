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

# Code inspired by the 'CLICKR' addon by Oliver J Post

import bpy
import bpy_extras
import math
import mathutils
import typing
import logging
import random
from . import polib
from . import hatchery
from . import panel
from . import preferences

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


def get_target_collection(context: bpy.types.Context) -> bpy.types.Collection:
    if context.scene.pq_clicker_target_collection is None:
        context.scene.pq_clicker_target_collection = polib.asset_pack_bpy.collection_get(
            context, "Clicker"
        )
    return context.scene.pq_clicker_target_collection


def get_collision_collection(context: bpy.types.Context) -> bpy.types.Collection:
    if context.scene.pq_clicker_collision_collection is None:
        return context.scene.collection

    return context.scene.pq_clicker_collision_collection


def get_clicker_props(
    context: bpy.types.Context,
) -> preferences.general_preferences.ClickerProperties:
    return preferences.prefs_utils.get_preferences(context).general_preferences.clicker_props


@polib.log_helpers_bpy.logged_operator
class Clicker(bpy.types.Operator):
    bl_idname = "engon.clicker"
    bl_label = "Clicker"
    bl_description = (
        "Select objects and place them interactively under your cursor directly in the "
        "scene. Customize variability with options to randomize rotation, tilt, and scale. Hold "
        "CTRL to align objects to the surface. Rotate the placed objects with mouse movement. "
        "Automatically aligns origins of meshes to the bottom of the object if specified"
    )
    bl_options = {'REGISTER', 'UNDO'}

    ROTATION_SPEED = 0.01
    SCALE_SPEED = 0.01

    draw_2d_handler_ref = None

    is_running = False

    def __init__(self):
        self.models_collection: typing.Optional[bpy.types.Collection] = None
        self.target_collection: typing.Optional[bpy.types.Collection] = None
        self.collision_collection = bpy.context.scene.collection

        self.current_object: typing.Optional[bpy.types.Object] = None
        self.placed_object: typing.Optional[bpy.types.Object] = None
        self.place_mouse_position: typing.Optional[mathutils.Vector] = None
        self.current_object_hierarchy_names: typing.Set[str] = set()
        # Store the last adjustment of z rotation, so next placed objects continue with the same
        # base rotation.
        self.last_z_rotation_adjustment = 0.0
        # Store the base rotation matrix of the current object so we can take it into account after
        # aligning with surface normal.
        self.current_object_base_rotation = mathutils.Matrix()

        # Properties controlling the UI state - e. g. tint of the buttons, based on the events
        self.is_scaling = False

        Clicker.draw_2d_handler_ref = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_px, (), 'WINDOW', 'POST_PIXEL'
        )

    @staticmethod
    def remove_draw_handlers() -> None:
        if hasattr(Clicker, "draw_2d_handler_ref") and Clicker.draw_2d_handler_ref is not None:
            bpy.types.SpaceView3D.draw_handler_remove(Clicker.draw_2d_handler_ref, 'WINDOW')
            Clicker.draw_2d_handler_ref = None

    def __del__(self):
        Clicker.remove_draw_handlers()

    def draw_px(self):
        clicker_props = get_clicker_props(bpy.context)
        ui_scale = bpy.context.preferences.system.ui_scale
        half_width = bpy.context.region.width / 2.0

        polib.render_bpy.mouse_info(
            half_width - 440 * ui_scale,
            20,
            "Place object",
            left_click=True,
        )

        polib.render_bpy.mouse_info(
            half_width - 300 * ui_scale,
            20,
            "Rotate",
            left_click=True,
            indicate_left=True,
            indicate_right=True,
        )

        # Click and hold ALT
        polib.render_bpy.mouse_info(
            half_width - 200 * ui_scale,
            20,
            "",
            left_click=True,
            indicate_left=True,
            indicate_right=True,
        )
        polib.render_bpy.key_info(
            half_width - 175 * ui_scale, 20, "ALT", "Scale", pressed=self.is_scaling
        )

        polib.render_bpy.key_info(
            half_width - 90 * ui_scale,
            20,
            "CTRL",
            "Align to surface (Hold)",
            pressed=clicker_props.align_to_surface,
        )
        polib.render_bpy.key_info(half_width + 120 * ui_scale, 20, "R", "Select random object")

        polib.render_bpy.key_info(half_width + 330 * ui_scale, 20, "ESC", "Exit")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(context.selected_objects) > 0 and context.mode == 'OBJECT'

    def execute(self, context: bpy.types.Context):
        return {'FINISHED'}

    def _cleanup(
        self,
        context: bpy.types.Context,
        event: typing.Optional[bpy.types.Event] = None,
        exception: typing.Optional[Exception] = None,
    ) -> typing.Set[str]:
        Clicker.is_running = False
        Clicker.remove_draw_handlers()

        context.window.cursor_modal_restore()
        if self.models_collection is not None:
            try:
                bpy.data.collections.remove(self.models_collection)
            except ReferenceError:
                logger.exception(f"Reference to the model collection was lost, couldn't clean up.")

        if self.current_object is not None:
            try:
                bpy.data.objects.remove(self.current_object)
            except ReferenceError:
                logger.exception(f"Reference to the current object was lost, couldn't clean up.")

        return {'CANCELLED'}

    @polib.utils_bpy.safe_modal(on_exception=_cleanup)
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.current_object is None:
            self.report({'ERROR'}, "No object to place, select at least one object.")
            return {'CANCELLED'}

        if event.type == 'ESC':
            self._cleanup(context, event)
            return {'FINISHED'}

        self.is_scaling = False

        # PASS_THROUGH for events that are in N-panel so user can control the clicker properties.
        area, region = polib.ui_bpy.get_mouseovered_region(context, event)
        if (
            area is not None
            and region is not None
            and area.type == 'VIEW_3D'
            and region.type == 'UI'
        ):
            context.window.cursor_modal_restore()
            return {'PASS_THROUGH'}

        if area is not None and area.type != 'VIEW_3D':
            context.window.cursor_modal_set('STOP')
            return {'RUNNING_MODAL'}

        context.window.cursor_modal_set('CROSSHAIR')
        if event.type == 'MOUSEMOVE':
            if self.placed_object is not None:
                if event.alt:
                    self.is_scaling = True
                    self.update_placed_object_scale(event)
                else:
                    self.update_placed_object_rotation(event)
            else:
                self.update_current_object_transform(context, event)
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                self.place_object(event)
            if event.value == 'RELEASE':
                self.choose_next_object(context)
            return {'RUNNING_MODAL'}

        elif event.type == 'R':
            if event.value == 'RELEASE':
                self.choose_next_object(context)
                self.update_current_object_transform(context, event)

            return {'RUNNING_MODAL'}

        elif event.type in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            clicker_props = get_clicker_props(context)
            if event.value == 'PRESS':
                clicker_props.align_to_surface = True
            elif event.value == 'RELEASE':
                clicker_props.align_to_surface = False
                self.reset_current_object_rotation()

            self.update_current_object_transform(context, event)

            return {'RUNNING_MODAL'}

        # PASS_THROUGH for navigation events, otherwise user could control blender data
        # under our hands, which wouldn't be nice!
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    def update_current_object_transform(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> None:
        assert self.current_object is not None
        raycast_hit = polib.linalg_bpy.raycast_screen_to_world(
            context,
            (event.mouse_region_x, event.mouse_region_y),
            self.current_object_hierarchy_names,
            self.collision_collection,
        )
        # If we didn't hit anything, place the object at the mouse cursor position with reset rotation
        if raycast_hit is None:
            pos = (event.mouse_region_x, event.mouse_region_y)
            region = context.region
            region3d = context.region_data
            view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, region3d, pos)
            position = bpy_extras.view3d_utils.region_2d_to_location_3d(
                region, region3d, pos, view_vector
            )
            self.reset_current_object_rotation(position)
            return

        self.current_object.location = raycast_hit.position

        if get_clicker_props(context).align_to_surface:
            normal: mathutils.Vector = raycast_hit.normal.normalized()
            surface_normal_quaternion = normal.to_track_quat('Z', 'Y')
            _, _, scale = self.current_object.matrix_world.decompose()
            scale_matrix = mathutils.Matrix.Diagonal(scale).to_4x4()

            rotation_matrix = (
                surface_normal_quaternion.to_matrix().to_4x4() @ self.current_object_base_rotation
            )

            self.current_object.matrix_world = (
                mathutils.Matrix.Translation(raycast_hit.position) @ rotation_matrix @ scale_matrix
            )

    def reset_current_object_rotation(
        self, position: typing.Optional[mathutils.Vector] = None
    ) -> None:
        assert self.current_object is not None
        current_position, _, scale = self.current_object.matrix_world.decompose()
        if position is None:
            position = current_position

        scale_matrix = mathutils.Matrix.Diagonal(scale).to_4x4()
        self.current_object.matrix_world = (
            mathutils.Matrix.Translation(position)
            @ self.current_object_base_rotation
            @ scale_matrix
        )

    def update_placed_object_rotation(self, event: bpy.types.Event) -> None:
        assert self.placed_object is not None
        rotation_diff = (event.mouse_x - event.mouse_prev_x) * Clicker.ROTATION_SPEED

        rotation_local_z_matrix = mathutils.Matrix.Rotation(rotation_diff, 4, 'Z')
        self.placed_object.matrix_world @= rotation_local_z_matrix
        self.last_z_rotation_adjustment += rotation_diff

    def update_placed_object_scale(self, event: bpy.types.Event) -> None:
        assert self.placed_object is not None
        self.placed_object.scale += mathutils.Vector(
            ((event.mouse_x - event.mouse_prev_x) * Clicker.SCALE_SPEED,) * 3
        )

    def place_object(self, event: bpy.types.Event) -> None:
        assert self.current_object is not None
        self.placed_object = self.current_object.copy()
        polib.asset_pack_bpy.collection_add_object(self.target_collection, self.placed_object)
        self.current_object.hide_viewport = True
        self.place_mouse_position = mathutils.Vector([event.mouse_region_x, event.mouse_region_y])
        logger.info(f"Object placed: '{self.placed_object.name}'")

    def choose_next_object(self, context: bpy.types.Context) -> None:
        clicker_props = get_clicker_props(context)
        if self.current_object is not None:
            bpy.data.objects.remove(self.current_object)

        # If there was a previously placed object, choosing next object starts right after it was
        # finished - it's rotation and scale is set, and we can log the information.
        if self.placed_object is not None:
            logger.info(
                f"Object '{self.placed_object.name}' finalized at {self.placed_object.location} "
                f"with scale {self.placed_object.scale} and rotation {self.placed_object.rotation_euler}"
            )

        self.current_object_hierarchy_names.clear()
        random_object = random.choice(self.models_collection.objects)
        self.current_object = random_object.copy()
        assert self.current_object is not None
        polib.asset_pack_bpy.collection_add_object(self.target_collection, self.current_object)

        # Add current hierarchy and the instancer to the current_object_hierarchy_names, that
        # will be further used when raycasting on the geometry to completely exclude the currently
        # placed object from raycasting.
        for obj in polib.asset_pack_bpy.get_entire_object_hierarchy(self.current_object):
            self.current_object_hierarchy_names.add(obj.name)
        self.current_object_hierarchy_names.add(self.current_object.name)

        # Rotation randomization, use rotation from the last object if it exists so next clicked
        # asset base rotation aligned with the previous one.
        location, rotation, scale = self.current_object.matrix_world.decompose()
        rotation_matrix = rotation.to_matrix().to_4x4()
        rotation_matrix = (
            mathutils.Euler((0, 0, self.last_z_rotation_adjustment), 'XYZ').to_matrix()
            @ rotation.to_matrix()
        ).to_4x4()

        rotation_matrix @= self._get_randomized_rotation_matrix(context)
        self.current_object_base_rotation = rotation_matrix

        # Scale randomization
        random_scale = random.uniform(-clicker_props.random_scale, clicker_props.random_scale)
        scale_matrix = mathutils.Matrix.Diagonal(
            (
                scale[0] + random_scale,
                scale[1] + random_scale,
                math.fabs(scale[2] + random_scale),
                1.0,
            )
        )
        self.current_object.matrix_world = (
            mathutils.Matrix.Translation(location) @ rotation_matrix @ scale_matrix
        )

        self.current_object.select_set(False)

        self.placed_object = None
        self.place_mouse_position = None

        logger.info(f"Chosen next object: '{self.current_object.name}'")

    def adjust_origin(self, obj: bpy.types.Object) -> None:
        if obj.type != 'MESH':
            return

        bbox = hatchery.bounding_box.AlignedBox()
        bbox.extend_by_object(obj)
        eccentricity = bbox.get_eccentricity()
        offset = bbox.min + mathutils.Vector((eccentricity.x, eccentricity.y, 0.0))
        offset_local = obj.matrix_world.inverted() @ offset
        obj.data.transform(mathutils.Matrix.Translation(-offset_local))

    def prepare_instanced_objects(
        self, context: bpy.types.Context, root_objs: typing.Set[bpy.types.Object]
    ) -> None:
        """Prepare a set of root objects for instancing. Populates the 'self.models_collection'.

        In case of instanced objects, create a new baseline copy that will be instanced.
        In case of editable objects, duplicate the hierarchy and wrap the hierarchy into a collection
        that will be then instanced.
        """
        clicker_props = get_clicker_props(context)
        for obj in root_objs:
            if (
                obj.type == 'EMPTY'
                and obj.instance_collection is not None
                and obj.instance_type == 'COLLECTION'
            ):
                # Don't use the original object, copy the instanced collection
                obj_copy = obj.copy()
                self.models_collection.objects.link(obj_copy)
            else:
                # Create a new collection for the object's hierarchy and instance the empty
                # out of the editable objects.
                coll = bpy.data.collections.new(f"{obj.name}_clicker_instance")
                hierarchy = list(polib.asset_pack_bpy.get_entire_object_hierarchy(obj))
                with context.temp_override(selected_objects=hierarchy, undo=False):
                    # We can link mesh data only if we don't need to adjust the origin
                    bpy.ops.object.duplicate(linked=not clicker_props.origin_to_bottom)
                    new_root = polib.asset_pack_bpy.find_root_objects(
                        context.selected_objects, only_polygoniq=False
                    ).pop()
                    new_root.location = (0, 0, 0)

                for obj in hierarchy:
                    self.adjust_origin(obj)

                polib.asset_pack_bpy.collection_link_hierarchy(coll, new_root)

                empty = bpy.data.objects.new(obj.name, None)
                empty.instance_type = 'COLLECTION'
                empty.instance_collection = coll
                self.models_collection.objects.link(empty)

    def cancel(self, context: bpy.types.Context):
        self._cleanup(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if Clicker.is_running:
            logger.error("Another instance of the clicker operator is already running!")
            return {'CANCELLED'}

        models_collection = polib.asset_pack_bpy.collection_get(context, "tmp_Clicker_Models")
        root_objs = polib.asset_pack_bpy.find_root_objects(
            context.selected_objects, only_polygoniq=False
        )

        if len(root_objs) == 0:
            self.report({'ERROR'}, "Please select at least one object to place!")
            return {'CANCELLED'}

        self.models_collection = models_collection
        self.target_collection = get_target_collection(context)
        self.collision_collection = get_collision_collection(context)

        self.prepare_instanced_objects(context, root_objs)

        self.models_collection.hide_render = True
        self.models_collection.hide_viewport = True

        self.choose_next_object(context)
        context.window_manager.modal_handler_add(self)
        Clicker.is_running = True
        logger.info(
            f"Clicker started with '{[obj.name for obj in self.models_collection.objects]}' objects."
        )
        return {'RUNNING_MODAL'}

    def _get_randomized_rotation_matrix(self, context: bpy.types.Context) -> mathutils.Matrix:
        clicker_props = get_clicker_props(context)
        rotation_matrix = mathutils.Matrix.Rotation(
            # random tilt in X axis between -90 and 90 degrees
            random.uniform(-clicker_props.random_tilt, clicker_props.random_tilt) * 0.5 * math.pi,
            4,
            'X',
        )
        rotation_matrix @= mathutils.Matrix.Rotation(
            # random tilt in Y axis between -90 and 90 degrees
            random.uniform(-clicker_props.random_tilt, clicker_props.random_tilt) * 0.5 * math.pi,
            4,
            'Y',
        )
        rotation_matrix @= mathutils.Matrix.Rotation(
            # random rotation in Z axis between -180 and 180 degrees
            random.uniform(-clicker_props.random_rotation_z, clicker_props.random_rotation_z)
            * math.pi,
            4,
            'Z',
        )
        return rotation_matrix

    def _sanity_check_collections(self) -> bool:
        try:
            return self.models_collection is not None and self.target_collection is not None
        except RuntimeError:
            return False


MODULE_CLASSES.append(Clicker)


@polib.log_helpers_bpy.logged_panel
class ClickerPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_clicker"
    bl_parent_id = panel.EngonPanel.bl_idname
    bl_label = "Clicker"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='PIVOT_CURSOR')

    def draw(self, context: bpy.types.Context) -> None:
        props = preferences.prefs_utils.get_preferences(context).general_preferences.clicker_props
        layout = self.layout
        row = layout.row(align=True)
        row.scale_x = row.scale_y = 1.3
        if Clicker.is_running:
            row.label(text="Click in the scene to place assets", icon='RESTRICT_SELECT_ON')
        else:
            row.operator(Clicker.bl_idname, text="Click Assets", icon='PIVOT_CURSOR')

        col = layout.column(align=True)
        col.enabled = not Clicker.is_running
        col.label(text="Output Collection")
        col.prop(context.scene, "pq_clicker_target_collection", text="")

        col = layout.column(align=True)
        col.enabled = not Clicker.is_running
        col.label(text="Surface Collection")
        col.prop(context.scene, "pq_clicker_collision_collection", text="")

        layout.prop(props, "align_to_surface")
        layout.prop(props, "origin_to_bottom")

        col = layout.column(align=True)
        col.label(text="Randomization")
        col.prop(props, "random_rotation_z")
        col.prop(props, "random_tilt")
        col.prop(props, "random_scale")


MODULE_CLASSES.append(ClickerPanel)


def register():
    bpy.types.Scene.pq_clicker_target_collection = bpy.props.PointerProperty(
        name="Clicker Output Collection",
        description="Collection where the clicked objects will be automatically placed, default "
        "is 'Clicker'",
        type=bpy.types.Collection,
    )

    bpy.types.Scene.pq_clicker_collision_collection = bpy.props.PointerProperty(
        name="Clicker Collision Surface Collection",
        description="Objects from this collection will act as a surface to click on, if nothing "
        "is specified  the 'Scene Collection' is used. Use this to limit the placement area or to "
        "gain performance in large scenes",
        type=bpy.types.Collection,
    )

    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    Clicker.remove_draw_handlers()
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.pq_clicker_collision_collection
    del bpy.types.Scene.pq_clicker_target_collection
