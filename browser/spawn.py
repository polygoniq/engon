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
import math
import mathutils
import itertools
from .. import polib
from .. import mapr
from .. import hatchery
from . import filters
from . import state
from .. import preferences
from .. import asset_registry
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")

SPAWN_ALL_DISPLAYED_ASSETS_WARNING_LIMIT = 30


MODULE_CLASSES: typing.List[typing.Any] = []


class MAPR_SpawnAssetBase(bpy.types.Operator):
    bl_options = {'REGISTER', 'UNDO'}

    def _spawn(
        self,
        context: bpy.types.Context,
        asset: mapr.asset.Asset,
        spawn_options: hatchery.spawn.DatablockSpawnOptions,
    ) -> typing.Optional[hatchery.spawn.SpawnedData]:
        asset_provider = asset_registry.instance.master_asset_provider
        file_provider = asset_registry.instance.master_file_provider
        spawner = mapr.blender_asset_spawner.AssetSpawner(asset_provider, file_provider)
        return spawner.spawn(context, asset, spawn_options)

    def _spawn_multiple(
        self, context: bpy.types.Context, assets: typing.List[mapr.asset.Asset]
    ) -> None:
        """Spawns multiple assets at once into the scene.

        Adjust spawning options so this creates desirable result and doesn't spawn e. g. all
        geometry nodes on the same object and crash Blender.
        """
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        for asset in assets:
            can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
            if not can_spawn:
                logger.warning(f"Couldn't spawn asset '{asset.id_}': '{why_fail}'")
                continue

            spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
            # assets that are spawned into selected objects, e.g. materials or geonodes
            # would all spawn into the one selected object
            # overwrite the target_objects to spawn a default target object per asset.
            if getattr(spawn_options, "target_objects", None) is not None:
                spawn_options.target_objects = set()
            if isinstance(spawn_options, hatchery.spawn.SceneSpawnOptions):
                spawn_options.activate_spawned = False

            # TODO: We use MAPR_SpawnAssetBase instead of self here, because of how the
            # MAPR_SpawnAllDisplayed operator is implemented out of the hierarchy, this is not ideal.
            MAPR_SpawnAssetBase._spawn(self, context, asset, spawn_options)

    def _remove_duplicates(self):
        pack_paths = asset_registry.instance.get_packs_paths()
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


class MAPR_SpawnSingleAssetBase(MAPR_SpawnAssetBase):
    asset_id: bpy.props.StringProperty(name="Asset ID", description="ID of asset to spawn")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id {props.asset_id} cannot be spawned"

        type_ = str(asset.type_).replace("AssetDataType.blender_", "").replace("_", " ")
        return f"Spawn {type_}: '{asset.title}'"

    def draw(self, context: bpy.types.Context) -> None:
        # Draw is currently only used when there is an error when spawning the asset
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.alignment = 'CENTER'
        row.alert = True
        row.label(text=f"Failed to spawn this asset", icon='ERROR')
        why_fail = getattr(self, "why_fail", None)

        if why_fail is None:
            return

        reason, suggestion = why_fail
        box.row().label(text=str(reason))
        box = layout.box()
        box.label(text=str(suggestion), icon='QUESTION')
        box.label(text="Or adjust your spawning options.", icon='OPTIONS')

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset_provider = asset_registry.instance.master_asset_provider
        asset = asset_provider.get_asset(self.asset_id)
        if asset is None:
            self.report({'ERROR'}, f"No asset found for '{self.asset_id}'")
            return {'CANCELLED'}

        can_spawn, self.why_fail = prefs.spawn_options.can_spawn(asset, context)
        if can_spawn:
            return self.execute(context)
        else:
            return context.window_manager.invoke_popup(self, width=500)

    def _get_asset(self) -> typing.Optional[mapr.asset.Asset]:
        return asset_registry.instance.master_asset_provider.get_asset(self.asset_id)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserMainAssetAction(MAPR_SpawnSingleAssetBase):
    # NOTE: This operator was extended to allow selection of assets, but we want to keep the bl_idname
    # the same, so if it is used in scripts, it will still work.
    bl_idname = "engon.browser_spawn_asset"
    bl_label = "Spawn Asset"

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        return super().description(context, props) + ". Hold 'SHIFT' or 'CTRL' to select the asset"

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        # This is checked also in 'invoke', but we check in execute too, so the operator reports
        # errors and fails when used in scripts.
        can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
        if not can_spawn:
            logger.error(f"Cannot spawn asset {self.asset_id}: {why_fail}")
            return {'CANCELLED'}

        spawn_options = prefs.spawn_options.get_spawn_options(asset, context)

        self._spawn(context, asset, spawn_options)

        # Make editable and remove duplicates is currently out of hatchery and works based on
        # assumption of correct context, which is suboptimal, but at current time the functions
        # either don't support passing the right context, or we don't have it.
        if prefs.spawn_options.make_editable:
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True
            )

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.shift or event.ctrl:
            # Select the asset (range)
            return self._handle_selection(event)
        else:
            # Spawn the asset
            return super().invoke(context, event)

    def _handle_selection(self, event: bpy.types.Event):
        browser_state = state.get_browser_state(bpy.context)
        if event.shift and browser_state.active_asset_id != "":
            # Select or deselect range of assets
            if not event.ctrl:
                # Deselect all before selecting a new range
                browser_state.select_asset_range(browser_state.selected_asset_ids, False)

            # Select the new range
            current_view = filters.asset_repository.current_view
            selection_start_idx, _ = current_view.find_asset_by_id(browser_state.active_asset_id)
            selection_end_idx, _ = current_view.find_asset_by_id(self.asset_id)
            new_selection_state = (
                True
                if not event.ctrl
                else browser_state.is_asset_selected(browser_state.active_asset_id)
            )  # Only shift => select, shift + ctrl => use state of the active asset
            selection = itertools.islice(
                current_view.assets,
                min(selection_start_idx, selection_end_idx),
                max(selection_start_idx, selection_end_idx) + 1,
            )
            browser_state.select_asset_range(
                (asset.id_ for asset in selection), new_selection_state
            )
            logger.info(
                f"Selected assets from '{browser_state.active_asset_id}' to '{self.asset_id}'"
            )
        else:
            # Select or deselect individual asset
            desired_select = not browser_state.is_asset_selected(self.asset_id)
            browser_state.select_asset(self.asset_id, desired_select)
            logger.info(f"Selected asset '{self.asset_id}' '{desired_select}'")
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserMainAssetAction)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnDisplayed(bpy.types.Operator):
    bl_idname = "engon.browser_spawn_displayed"
    bl_label = "Spawn Displayed"
    bl_description = "Spawn all currently displayed assets"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if len(filters.asset_repository.current_assets) > SPAWN_ALL_DISPLAYED_ASSETS_WARNING_LIMIT:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.label(
            text=f"This operation will spawn {len(filters.asset_repository.current_assets)} assets, continue?"
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        assets = filters.asset_repository.current_assets
        prev_objects = set(bpy.context.selectable_objects)

        # TODO: This is suboptimal, we should correct the inheritance of this operator, so we don't
        # pass arbitrary self to MAPR_SpawnAssetBase.
        MAPR_SpawnAssetBase._spawn_multiple(self, context, assets)

        spawned_objects = set(bpy.context.selectable_objects) - prev_objects
        for obj in spawned_objects:
            obj.select_set(True)

        if prefs.spawn_options.make_editable:
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True
            )

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnDisplayed)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserDrawGeometryNodesAsset(MAPR_SpawnSingleAssetBase):
    """Specialized spawn operator to add geometry nodes asset and start draw mode."""

    bl_idname = "engon.browser_draw_geometry_nodes"
    bl_label = "Draw Geometry Nodes"

    draw_2d_handler_ref = None
    is_running = False

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id {props.asset_id} cannot be spawned"

        return (
            f"Spawn and draw the '{asset.title}' geometry nodes asset. "
            f"Switches to Edit mode to draw the asset"
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.original_tool_idname: typing.Optional[str] = None
        self.original_curve_paint_depth_mode: typing.Optional[str] = None
        self.original_curve_paint_surface_offset: typing.Optional[float] = None

    @staticmethod
    def remove_draw_handler() -> None:
        draw_handler = getattr(MAPR_BrowserDrawGeometryNodesAsset, "draw_2d_handler_ref", None)
        if draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
            MAPR_BrowserDrawGeometryNodesAsset.draw_2d_handler_ref = None

    def _cleanup(
        self,
        context: bpy.types.Context,
        event: typing.Optional[bpy.types.Event] = None,
        exception: typing.Optional[Exception] = None,
    ) -> None:
        MAPR_BrowserDrawGeometryNodesAsset.remove_draw_handler()
        MAPR_BrowserDrawGeometryNodesAsset.is_running = False

        # Restore the original tool and tools settings
        if self.original_tool_idname is not None:
            bpy.ops.wm.tool_set_by_id(name=self.original_tool_idname, space_type='VIEW_3D')
        if self.original_curve_paint_depth_mode is not None:
            context.tool_settings.curve_paint_settings.depth_mode = (
                self.original_curve_paint_depth_mode
            )
        if self.original_curve_paint_surface_offset is not None:
            context.tool_settings.curve_paint_settings.surface_offset = (
                self.original_curve_paint_surface_offset
            )

        # Switch to object mode and select the generated curve
        # if the user didn't switch to another mode already
        if context.mode == 'EDIT_CURVE':
            bpy.ops.object.mode_set(mode='OBJECT')
        if context.mode == 'OBJECT' and context.active_object is not None:
            context.active_object.select_set(True)

    def __del__(self):
        MAPR_BrowserDrawGeometryNodesAsset.remove_draw_handler()
        MAPR_BrowserDrawGeometryNodesAsset.is_running = False

    def draw_px(self):
        ui_scale = bpy.context.preferences.system.ui_scale
        half_width = bpy.context.region.width / 2.0

        polib.render_bpy.mouse_info(half_width - 120 * ui_scale / 2, 20, "Draw", left_click=True)
        polib.render_bpy.key_info(
            half_width + 20 * ui_scale, 20, polib.render_bpy.ESCAPE_KEY, "Exit"
        )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return not MAPR_BrowserDrawGeometryNodesAsset.is_running

    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        # We spawn the container object to spawn all modifiers and dependencies with it.
        # Then we clear the data (currently splines, mesh) so the object data is empty, and
        # then we run the draw tool.
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        # This is checked also in 'invoke', but we check in execute too, so the operator reports
        # errors and fails when used in scripts.
        can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
        if not can_spawn:
            logger.error(f"Cannot spawn asset {self.asset_id}: {why_fail}")
            return {'CANCELLED'}

        # Spawn with no target object so we spawn the container object
        options = prefs.spawn_options.get_spawn_options(asset, context)
        assert isinstance(options, hatchery.spawn.GeometryNodesSpawnOptions)
        options.target_objects = set()
        spawned_data = self._spawn(context, asset, options)

        assert asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes
        assert spawned_data is not None and isinstance(
            spawned_data, hatchery.spawn.GeometryNodesSpawnedData
        )
        assert len(spawned_data.container_objs_to_mods_map) == 1

        container_obj = spawned_data.container_objs_to_mods_map.popitem()[0]
        # We remove the splines of the original object, so user starts with blank space
        if isinstance(container_obj.data, bpy.types.Curve):
            container_obj.data.splines.clear()

        # Reset state
        polib.asset_pack_bpy.clear_selection(context)
        for obj in context.editable_objects:
            if obj.mode == 'OBJECT':
                continue

            with context.temp_override(active_object=obj):
                bpy.ops.object.mode_set(mode='OBJECT')

        # Switch to edit mode from any other mode
        context.view_layer.objects.active = container_obj
        bpy.ops.object.mode_set(mode='EDIT')

        # Save original tool and tool settings
        self.original_tool_idname = context.workspace.tools.from_space_view3d_mode(
            mode='EDIT_CURVE'
        ).idname
        self.original_curve_paint_depth_mode = context.tool_settings.curve_paint_settings.depth_mode
        self.original_curve_paint_surface_offset = (
            context.tool_settings.curve_paint_settings.surface_offset
        )

        # We run the "tool_set_by_id" instead of the bpy.ops.curve.draw, as it also setups strokes.
        bpy.ops.wm.tool_set_by_id(name="builtin.draw", space_type='VIEW_3D')
        # Setup the tool with some sensible defaults
        context.tool_settings.curve_paint_settings.depth_mode = 'SURFACE'
        context.tool_settings.curve_paint_settings.surface_offset = 0.05

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}

    @polib.utils_bpy.safe_modal(on_exception=_cleanup)
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            self._cleanup(context)
            return {'FINISHED'}

        if context.mode != 'EDIT_CURVE':
            # User switched to another mode, we need to cleanup and exit
            self._cleanup(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context: bpy.types.Context) -> None:
        self._cleanup(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # Setup the draw mode
        invoke_result = super().invoke(context, event)
        if invoke_result != {'FINISHED'}:
            # If the invoke failed, we don't want to run the draw tool
            return invoke_result

        # Register the draw handler and run modal
        assert (
            MAPR_BrowserDrawGeometryNodesAsset.draw_2d_handler_ref is None
        ), f"{MAPR_BrowserDrawGeometryNodesAsset.__name__} draw handler is already registered!"
        MAPR_BrowserDrawGeometryNodesAsset.draw_2d_handler_ref = (
            bpy.types.SpaceView3D.draw_handler_add(self.draw_px, (), 'WINDOW', 'POST_PIXEL')
        )

        context.window_manager.modal_handler_add(self)
        MAPR_BrowserDrawGeometryNodesAsset.is_running = True
        return {'RUNNING_MODAL'}


MODULE_CLASSES.append(MAPR_BrowserDrawGeometryNodesAsset)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnModelIntoParticleSystem(MAPR_SpawnSingleAssetBase):
    bl_idname = "engon.browser_spawn_model_into_particle_system"
    bl_label = "Spawn Model Into Active Particle System"

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id {props.asset_id} cannot be spawned"

        return f"Spawn model '{asset.title}' into active particle system"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            asset_helpers.has_active_object_with_particle_system(context)
            and context.active_object.particle_systems.active.settings.instance_collection
            is not None
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        if asset.type_ != mapr.asset_data.AssetDataType.blender_model:
            self.report({'WARNING'}, f"Only model assets can be spawned into particle systems")
            return {'CANCELLED'}

        # This is checked also in 'invoke', but we check in execute too, so the operator reports
        # errors and fails when used in scripts.
        can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
        if not can_spawn:
            logger.error(f"Cannot spawn asset {self.asset_id}: {why_fail}")
            return {'CANCELLED'}

        # Override the spawn options to link the model to the scene collection.
        # (The instance collection can be unlinked or hidden, but wee need the model in
        # the ViewLayer to be able to select it and make it editable.)
        spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
        spawn_options.collection_factory_method = lambda: context.scene.collection

        spawned_data = self._spawn(context, asset, spawn_options)

        assert asset.type_ == mapr.asset_data.AssetDataType.blender_model
        assert spawned_data is not None and isinstance(
            spawned_data, hatchery.spawn.ModelSpawnedData
        )

        spawned_data.instancer.location = context.active_object.location - mathutils.Vector(
            (0, 0, 10)
        )
        spawned_data.instancer.rotation_euler = mathutils.Euler((0, math.radians(90), 0), 'XYZ')
        polib.asset_pack_bpy.make_selection_editable(
            context, True, keep_selection=True, keep_active=True
        )

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        # Re-link the spawned object to the particle system's instance collection
        instance_collection = (
            context.active_object.particle_systems.active.settings.instance_collection
        )
        assert instance_collection is not None
        for obj in context.selected_objects:
            instance_collection.objects.link(obj)
            context.scene.collection.objects.unlink(obj)

        # This refreshes the particle system's dupli weights collection
        context.active_object.particle_systems.active.settings.instance_collection = (
            instance_collection
        )

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnModelIntoParticleSystem)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserReplaceSelected(MAPR_SpawnSingleAssetBase):
    bl_idname = "engon.browser_replace_selected"
    bl_label = "Replace Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id '{props.asset_id}' cannot be spawned"

        return (
            f"Replace selected objects in scene with '{asset.title}'. "
            "Empty objects are not considered for replacing"
        )

    @classmethod
    def get_objects_to_replace(cls, context: bpy.types.Context) -> typing.Set[bpy.types.Object]:
        return {
            obj
            for obj in context.selected_objects
            if not (obj.type == 'EMPTY' and obj.instance_collection is None)
        }

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(cls.get_objects_to_replace(context)) > 0

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        # This is checked also in 'invoke', but we check in execute too, so the operator reports
        # errors and fails when used in scripts.
        can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
        if not can_spawn:
            logger.error(f"Cannot spawn asset {self.asset_id}: {why_fail}")
            return {'CANCELLED'}

        if asset.type_ != mapr.asset_data.AssetDataType.blender_model:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} is not a model asset")
            return {'CANCELLED'}

        objects_to_replace = MAPR_BrowserReplaceSelected.get_objects_to_replace(context)
        spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
        assert isinstance(spawn_options, hatchery.spawn.ModelSpawnOptions)
        spawn_options.collection_factory_method = None
        spawn_options.select_spawned = False
        spawned_data = self._spawn(context, asset, spawn_options)

        if spawned_data is None:
            logger.error(f"Failed to spawn asset '{self.asset_id}' to replace selected objects!")
            return {'CANCELLED'}

        if isinstance(spawned_data, hatchery.spawn.ModelSpawnedData):
            new_object = spawned_data.instancer
        else:
            raise ValueError(
                f"Unsupported spawned data type: '{type(spawned_data)}'. This should be handled by the caller."
            )

        # We go through all selected objects and replace them with the new object. We keep
        # the old objects in the `bpy.data.` - they will be removed when the .blend file is saved
        # if there are no more users of the object.
        for i, obj in enumerate(objects_to_replace):
            # Use the spawned object for the first iteration, otherwise create a copy
            obj_copy = new_object.copy() if i > 0 else new_object
            for old_collection in obj.users_collection:
                old_collection.objects.unlink(obj)
                old_collection.objects.link(obj_copy)
            obj_copy.parent = obj.parent
            for child in obj.children:
                child.parent = obj_copy
            obj_copy.matrix_world = obj.matrix_world
            obj_copy.select_set(True)

        if prefs.spawn_options.make_editable:
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True
            )

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReplaceSelected)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserReplaceActiveMaterials(MAPR_SpawnSingleAssetBase):
    bl_idname = "engon.browser_replace_active_materials"
    bl_label = "Replace Active Materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id '{props.asset_id}' cannot be spawned"

        message = (
            f"Replace active materials of selected objects with '{asset.title}' for all objects using them. "
            f"{len(cls.get_affected_objects(context))} objects will be affected"
        )
        return message

    @classmethod
    def get_materials_to_replace(cls, context: bpy.types.Context) -> typing.Set[bpy.types.Material]:
        return {obj.active_material for obj in cls.get_affected_objects(context)}

    @classmethod
    def get_affected_objects(cls, context: bpy.types.Context) -> typing.Set[bpy.types.Object]:
        return {
            obj
            for obj in context.selected_objects
            if hatchery.utils.can_have_materials_assigned(obj) and obj.active_material is not None
        }

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(cls.get_materials_to_replace(context)) > 0

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        # This is checked also in 'invoke', but we check in execute too, so the operator reports
        # errors and fails when used in scripts.
        can_spawn, why_fail = prefs.spawn_options.can_spawn(asset, context)
        if not can_spawn:
            logger.error(f"Cannot spawn asset {self.asset_id}: {why_fail}")
            return {'CANCELLED'}

        if asset.type_ != mapr.asset_data.AssetDataType.blender_material:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} is not a material asset")
            return {'CANCELLED'}

        materials_to_replace = MAPR_BrowserReplaceActiveMaterials.get_materials_to_replace(context)
        spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
        assert isinstance(spawn_options, hatchery.spawn.MaterialSpawnOptions)
        spawn_options.collection_factory_method = None
        spawn_options.select_spawned = False

        if context.mode == 'EDIT_MESH':
            # We don't want to assign materials to faces in edit mode, just replace the active materials
            bpy.ops.object.mode_set(mode='OBJECT')
            spawned_mat = self._spawn(context, asset, spawn_options)
            bpy.ops.object.mode_set(mode='EDIT')
        else:
            spawned_mat = self._spawn(context, asset, spawn_options)

        if spawned_mat is None:
            logger.error(f"Failed to replace active materials with '{self.asset_id}'!")
            return {'CANCELLED'}

        assert isinstance(spawned_mat, hatchery.spawn.MaterialSpawnedData)

        polib.material_utils_bpy.replace_materials(
            materials_to_replace,
            spawned_mat.material,
            bpy.data.objects,
        )

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReplaceActiveMaterials)


class MAPR_BrowserSelectedAssetsOperatorBase(MAPR_SpawnAssetBase):
    """Base class for manipulating selected assets from engon browser."""

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return state.get_browser_state(context).is_at_least_one_asset_selected()


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnSelected(MAPR_BrowserSelectedAssetsOperatorBase):
    bl_idname = "engon.browser_spawn_selected"
    bl_label = "Spawn Selected"
    bl_description = "Spawn all currently selected assets"

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):

        assets = list(state.get_browser_state(context).selected_assets)
        self._spawn_multiple(context, assets)
        self.report({'INFO'}, f"Spawned {len(assets)} asset(s)")
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnSelected)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserScatterSelected(MAPR_BrowserSelectedAssetsOperatorBase):
    bl_idname = "engon.browser_scatter_selected"
    bl_label = "Scatter Selected Models"
    bl_description = "Creates scatter on selected objects using selected assets"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            super().poll(context)
            and context.active_object is not None
            and state.get_browser_state(context).is_at_least_one_asset_of_type_selected(
                mapr.asset_data.AssetDataType.blender_model
            )
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        selected_models = [
            asset
            for asset in state.get_browser_state(context).selected_assets
            if asset.type_ == mapr.asset_data.AssetDataType.blender_model
        ]
        if len(selected_models) == 0:
            self.report({'WARNING'}, "Select at least one model asset to scatter!")
            return {'CANCELLED'}

        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, f"Active object '{context.active_object.name}' must be a mesh!")
            return {'CANCELLED'}

        bpy.ops.engon.scatter_add_empty(name="Selection Scatter", count=20)

        added_models = set()
        unsupported_models = set()
        for asset in selected_models:
            if bpy.ops.engon.browser_spawn_model_into_particle_system.poll():
                ret = bpy.ops.engon.browser_spawn_model_into_particle_system(asset_id=asset.id_)
                if ret == {'FINISHED'}:
                    added_models.add(asset.id_)
                else:
                    unsupported_models.add(asset.id_)
            else:
                logger.error(
                    f"Asked to scatter model '{asset.id_}', but it couldn't be spawned "
                    "into a particle system!"
                )

        self.report(
            {'INFO'},
            (
                f"Scattered {len(added_models)} model(s). "
                + (
                    f"{len(unsupported_models)} models do not support scattering."
                    if len(unsupported_models) > 0
                    else ""
                )
            ),
        )
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserScatterSelected)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserClickSelected(MAPR_BrowserSelectedAssetsOperatorBase):
    bl_idname = "engon.browser_click_selected"
    bl_label = "Click Selected Assets"
    bl_description = "Spawns the assets and enables clicker mode"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return super().poll(context) and state.get_browser_state(
            context
        ).is_at_least_one_asset_of_type_selected(mapr.asset_data.AssetDataType.blender_model)

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        selected_models = [
            asset
            for asset in state.get_browser_state(context).selected_assets
            if asset.type_ == mapr.asset_data.AssetDataType.blender_model
        ]
        if len(selected_models) == 0:
            self.report({'WARNING'}, "Select at least one model asset to click!")
            return {'CANCELLED'}

        # Run clicker in the first VIEW_3D found
        window = context.window_manager.windows[0]
        view_3d_area = None
        view_3d_main_region = None
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue

            for region in area.regions:
                if region.type == 'WINDOW':
                    view_3d_area = area
                    view_3d_main_region = region
                    break

            if view_3d_main_region is not None:
                break

        if view_3d_area is None or view_3d_main_region is None:
            self.report({'ERROR'}, "No 3D View found to start clicker.")
            return {'CANCELLED'}

        spawned_objects = []
        failed_assets = []
        for asset in selected_models:
            spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
            spawned_data = self._spawn(context, asset, spawn_options)
            if spawned_data is None:
                logger.error(f"Failed to spawn asset '{asset.id_}'!")
                failed_assets.append(asset)
                continue

            assert isinstance(spawned_data, hatchery.spawn.ModelSpawnedData)
            spawned_objects.append(spawned_data.instancer)

        if not spawned_objects:
            self.report({'WARNING'}, "No assets were successfully spawned!")
            return {'CANCELLED'}

        polib.asset_pack_bpy.clear_selection(context)
        for obj in spawned_objects:
            obj.select_set(True)

        with context.temp_override(window=window, area=view_3d_area, region=view_3d_main_region):
            bpy.ops.engon.clicker('INVOKE_DEFAULT', remove_initial_objects=True)

        self.report(
            {'INFO'},
            (
                f"Clicker started with {len(spawned_objects)} asset(s)."
                + (f"{len(failed_assets)} couldn't spawn." if len(failed_assets) > 0 else "")
            ),
        )

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserClickSelected)


@polib.log_helpers_bpy.logged_panel
class SpawnOptionsPopoverPanel(bpy.types.Panel):
    bl_idname = "PREFERENCES_PT_mapr_spawn_options"
    bl_label = "Spawn Options"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'HEADER'

    def draw(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context)
        spawning_options = prefs.browser_preferences.spawn_options
        layout = self.layout
        col = layout.column()
        col.label(text="Asset Spawn Options", icon='OPTIONS')
        col.prop(spawning_options, "remove_duplicates")
        col.prop(spawning_options, "make_editable")
        col.separator()

        col.label(text="Model", icon='OBJECT_DATA')
        col.prop(spawning_options, "use_collection", text="")
        col.separator()

        col.label(text="materialiq Materials", icon='MATERIAL')
        # Creating row with 'use_property_split' makes the enum item align more nicely
        row = col.row()
        row.use_property_split = True
        row.use_property_decorate = False
        row.prop(spawning_options, "texture_size", text="Texture Size")
        col.prop(spawning_options, "use_displacement")
        col.separator()

        col.label(text="Particle Systems", icon='PARTICLES')
        row = col.row()
        row.use_property_split = True
        row.use_property_decorate = False
        row.prop(spawning_options, "display_type", text="Display Type")
        col.prop(spawning_options, "display_percentage")
        col.prop(spawning_options, "link_instance_collection")
        if spawning_options.link_instance_collection:
            col.prop(spawning_options, "enable_instance_collection")
        col.prop(spawning_options, "include_base_material")
        col.prop(spawning_options, "preserve_density")
        if spawning_options.preserve_density:
            col.prop(prefs.general_preferences.scatter_props, "max_particle_count")
        else:
            col.prop(spawning_options, "count")
        col.separator()

        col.label(text="Geometry Nodes", icon='GEOMETRY_NODES')
        col.prop(spawning_options, "link_target_collections")
        if spawning_options.link_target_collections:
            col.prop(spawning_options, "enable_target_collections")
        col.separator()


MODULE_CLASSES.append(SpawnOptionsPopoverPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
