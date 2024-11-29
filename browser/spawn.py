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
from .. import polib
from .. import mapr
from .. import hatchery
from . import filters
from .. import preferences
from .. import asset_registry
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")

SPAWN_ALL_DISPLAYED_ASSETS_WARNING_LIMIT = 30


MODULE_CLASSES: typing.List[typing.Any] = []


class MAPR_SpawnAssetBase(bpy.types.Operator):
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

    def _get_asset(self) -> typing.Optional[mapr.asset.Asset]:
        return asset_registry.instance.master_asset_provider.get_asset(self.asset_id)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnAsset(MAPR_SpawnAssetBase):
    bl_idname = "engon.browser_spawn_asset"
    bl_label = "Spawn Asset"

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        self._spawn(context, asset, prefs.spawn_options.get_spawn_options(asset, context))
        # Make editable and remove duplicates is currently out of hatchery and works based on
        # assumption of correct context, which is suboptimal, but at current time the functions
        # either don't support passing the right context, or we don't have it.
        if (
            asset.type_ == mapr.asset_data.AssetDataType.blender_model
            and prefs.spawn_options.use_collection == 'PARTICLE_SYSTEM'
        ):
            # When spawning blender model to PARTICLE_SYSTEM collection we always convert to
            # editable as particle systems wouldn't be able to instance collection.
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True
            )

            if (
                context.active_object is not None
                and context.active_object.particle_systems.active is not None
            ):
                ps = context.active_object.particle_systems.active
                if ps.settings.instance_collection is not None:
                    # Update instance collection to propagate changes
                    ps.settings.instance_collection = ps.settings.instance_collection

        elif prefs.spawn_options.make_editable:
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True
            )

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnAsset)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnAllDisplayed(bpy.types.Operator):
    bl_idname = "engon.browser_spawn_all_displayed"
    bl_label = "Spawn All Displayed"
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
        for asset in assets:
            MAPR_SpawnAssetBase._spawn(
                self, context, asset, prefs.spawn_options.get_spawn_options(asset, context)
            )
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnAllDisplayed)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserDrawGeometryNodesAsset(MAPR_SpawnAssetBase):
    """Specialized spawn operator to add geometry nodes asset and start draw mode."""

    bl_idname = "engon.browser_draw_geometry_nodes"
    bl_label = "Draw Geometry Nodes"

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id {props.asset_id} cannot be spawned"

        return (
            f"Spawn and draw the '{asset.title}' geometry nodes asset. "
            f"Switches to Edit mode to draw the asset"
        )

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        # We spawn the container object to spawn all modifiers and dependencies with it.
        # Then we clear the data (currently splines, mesh) so the object data is empty, and
        # then we run the draw tool.
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        spawned_data = self._spawn(
            context, asset, prefs.spawn_options.get_spawn_options(asset, context)
        )

        assert asset.type_ == mapr.asset_data.AssetDataType.blender_geometry_nodes
        assert spawned_data is not None and isinstance(
            spawned_data, hatchery.spawn.GeometryNodesSpawnedData
        )

        container_obj = spawned_data.container_obj
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

        # We run the "tool_set_by_id" instead of the bpy.ops.curve.draw, as it also setups strokes.
        bpy.ops.wm.tool_set_by_id(name="builtin.draw", space_type='VIEW_3D')
        # Setup the tool with some sensible defaults
        context.tool_settings.curve_paint_settings.depth_mode = 'SURFACE'
        context.tool_settings.curve_paint_settings.surface_offset = 0.05

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserDrawGeometryNodesAsset)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnModelIntoParticleSystem(MAPR_SpawnAssetBase):
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

    def execute(self, context: bpy.types.Context):
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        asset = self._get_asset()
        if asset is None:
            self.report({'ERROR'}, f"Asset with id {self.asset_id} not found")
            return {'CANCELLED'}

        # Override the spawn options to link the model directly into the instance collection
        # and then convert it to editable below.
        spawn_options = prefs.spawn_options.get_spawn_options(asset, context)
        instance_collection = (
            context.active_object.particle_systems.active.settings.instance_collection
        )

        assert instance_collection is not None
        spawn_options.parent_collection = instance_collection
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

        # This refreshes the particle system's dupli weights collection
        context.active_object.particle_systems.active.settings.instance_collection = (
            instance_collection
        )

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserSpawnModelIntoParticleSystem)


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserReplaceSelected(MAPR_SpawnAssetBase):
    bl_idname = "engon.browser_replace_selected"
    bl_label = "Replace Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        asset = asset_registry.instance.master_asset_provider.get_asset(props.asset_id)
        if asset is None:
            return f"Asset with id '{props.asset_id}' cannot be spawned"

        return f"Replace selected objects with '{asset.title}'. Empty objects are not considered for replacing"

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

        objects_to_replace = MAPR_BrowserReplaceSelected.get_objects_to_replace(context)
        spawn_options: hatchery.spawn.ModelSpawnOptions = prefs.spawn_options.get_spawn_options(
            asset, context
        )
        spawn_options.parent_collection = None
        spawn_options.select_spawned = False
        spawned_data = self._spawn(context, asset, spawn_options)

        if spawned_data is None:
            logger.error(f"Failed to spawn asset to replace selected objects '{self.asset_id}'!")
            return {'CANCELLED'}

        if isinstance(spawned_data, hatchery.spawn.ModelSpawnedData):
            new_object = spawned_data.instancer
        elif isinstance(spawned_data, hatchery.spawn.GeometryNodesSpawnedData):
            new_object = spawned_data.container_obj
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
            obj_copy.matrix_world = obj.matrix_world
            obj_copy.select_set(True)

        if prefs.spawn_options.remove_duplicates:
            self._remove_duplicates()

        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserReplaceSelected)


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
        col.prop(spawning_options, "include_base_material")
        col.prop(spawning_options, "preserve_density")
        if spawning_options.preserve_density:
            col.prop(prefs.general_preferences.scatter_props, "max_particle_count")
        else:
            col.prop(spawning_options, "count")
        col.separator()


MODULE_CLASSES.append(SpawnOptionsPopoverPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
