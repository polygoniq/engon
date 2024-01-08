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
import polib
import mapr
from .. import preferences
from .. import asset_registry
logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserSpawnAsset(bpy.types.Operator):
    bl_idname = "engon.browser_spawn_asset"
    bl_label = "Spawn"

    asset_id: bpy.props.StringProperty(
        name="Asset ID",
        description="ID of asset to spawn into scene"
    )

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
        box.label(text="Or adjust your spawning options.", icon='FILE_TICK')

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context).mapr_preferences
        asset_provider = asset_registry.instance.master_asset_provider
        file_provider = asset_registry.instance.master_file_provider
        asset = asset_provider.get_asset(self.asset_id)
        if asset is None:
            self.report({'ERROR'}, f"No asset found for '{self.asset_id}'")
            return {'CANCELLED'}

        spawner = mapr.blender_asset_spawner.AssetSpawner(
            asset_provider, file_provider)

        spawner.spawn(context, asset, prefs.spawn_options.get_spawn_options(asset, context))

        # Make editable and remove duplicates is currently out of hatchery and works based on
        # assumption of correct context, which is suboptimal, but at current time the functions
        # either don't support passing the right context, or we don't have it.

        # When spawning blender model to PARTICLE_SYSTEM collection we always convert to editable
        # as particle systems wouldn't be able to instance collection.
        if prefs.spawn_options.make_editable or (
           asset.type_ == mapr.asset_data.AssetDataType.blender_model and
           prefs.spawn_options.use_collection == 'PARTICLE_SYSTEM'):
            polib.asset_pack_bpy.make_selection_editable(
                context, True, keep_selection=True, keep_active=True)

        if prefs.spawn_options.remove_duplicates:
            pack_paths = asset_registry.instance.get_packs_paths()
            filters = [polib.remove_duplicates_bpy.polygoniq_duplicate_data_filter]
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.materials, filters, pack_paths)
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.images, filters, pack_paths)
            polib.remove_duplicates_bpy.remove_duplicate_datablocks(
                bpy.data.node_groups, filters, pack_paths)

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        prefs = preferences.get_preferences(context).mapr_preferences
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


MODULE_CLASSES.append(MAPR_BrowserSpawnAsset)


@polib.log_helpers_bpy.logged_panel
class SpawnOptionsPopoverPanel(bpy.types.Panel):
    bl_idname = "PREFERENCES_PT_mapr_spawn_options"
    bl_label = "Spawn Options"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'HEADER'

    def draw(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context)
        spawning_options = prefs.mapr_preferences.spawn_options
        layout = self.layout
        col = layout.column()
        col.label(text="Asset Spawn Options", icon='FILE_TICK')
        col.prop(spawning_options, "remove_duplicates")
        col.prop(spawning_options, "make_editable")
        col.separator()

        col.label(text="Model", icon='OBJECT_DATA')
        col.prop(spawning_options, "use_collection", text="")
        col.separator()

        col.label(text="Materials", icon='MATERIAL')
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
