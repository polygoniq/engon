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
import itertools
import logging
import math
import mathutils
from . import polib
from . import hatchery
from . import asset_helpers
from . import panel
from . import preferences

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []

WEIGHT_PAINT_VERTICES_WARNING_THRESHOLD = 16


def find_modifier_containing_particle_system(
    modifiers: typing.Iterable[bpy.types.Modifier], particle_system: bpy.types.ParticleSystem
) -> bpy.types.ParticleSystemModifier:
    found_modifier = None
    for modifier in modifiers:
        if modifier.type != 'PARTICLE_SYSTEM':
            continue

        if modifier.particle_system == particle_system:
            found_modifier = modifier
            break

    return found_modifier


def change_collection_display_type(collection: bpy.types.Context, display_type: str) -> None:
    """Changes display type of all objects in the given collection."""
    for obj in collection.all_objects:
        obj.display_type = display_type


@polib.log_helpers_bpy.logged_operator
class AddEmptyScatter(bpy.types.Operator):
    bl_idname = "engon.scatter_add_empty"
    bl_label = "Add Empty Scatter"
    bl_description = "Adds empty scatter system that can be further customized"
    bl_options = {'REGISTER', 'UNDO'}

    link_instance_collection: bpy.props.BoolProperty(
        description="If true, the particle system instance collection will be linked to the scene. "
        "Objects from the instance collection are spawned on (0, 0, -10)",
        name="Link Instance Collection To Scene",
        default=True,
    )

    name: bpy.props.StringProperty(
        name="Particle System Name",
        description="Name of custom particle system",
        default="Particle System",
    )

    count: bpy.props.IntProperty(
        name="Count",
        description="Amount of particles to spawn",
        default=1000,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT' and context.active_object is not None

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        col = layout.column()

        row = col.row()
        row.scale_x = row.scale_y = 1.3
        row.prop(self, "name", text="Name")
        col.separator()
        col.prop(self, "link_instance_collection")
        col.prop(self, "count")
        col.separator()
        col.prop(props, "display_type")
        col.prop(props, "display_percentage")

    @polib.utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        active_object = context.active_object
        logger.info(f"Working on {active_object.name}")
        modifier = active_object.modifiers.new(
            f"{asset_helpers.PARTICLE_SYSTEM_PREFIX}{self.name}", type='PARTICLE_SYSTEM'
        )
        particle_system = modifier.particle_system
        particle_system.settings.name = modifier.name
        particle_system.settings.count = self.count
        self.configure_default_ps_settings(particle_system.settings)
        particle_system_data = [(modifier, particle_system, particle_system.settings)]

        for modifier, particle_system, _ in particle_system_data:
            hatchery.utils.ensure_particle_naming_consistency(modifier, particle_system)
            particle_system.settings.display_percentage = props.display_percentage
            instance_collection = particle_system.settings.instance_collection
            assert instance_collection is not None
            for obj in instance_collection.all_objects:
                obj.display_type = props.display_type

            if self.link_instance_collection:
                particle_systems_coll = polib.asset_pack_bpy.collection_get(
                    context,
                    asset_helpers.PARTICLE_SYSTEMS_COLLECTION,
                )
                particle_systems_coll.children.link(instance_collection)

        # area doesn't automatically redraw if the props dialog is overlaying the list
        # context.area is None in headless mode (e.g. while testing from Bazel)
        if context.area is not None:
            context.area.tag_redraw()
        return {'FINISHED'}

    def configure_default_ps_settings(self, ps_settings: bpy.types.ParticleSettings) -> None:
        # Chosen values that make most sense for a base scatter particle system setup
        ps_settings.render_type = 'COLLECTION'
        ps_settings.use_collection_count = True
        ps_settings.use_rotation_instance = True
        ps_settings.use_advanced_hair = True
        ps_settings.hair_length = 1.0
        ps_settings.type = 'HAIR'
        ps_settings.particle_size = 1.0
        ps_settings.use_rotations = True
        ps_settings.rotation_mode = 'GLOB_Z'
        ps_settings.phase_factor = 1.0
        ps_settings.phase_factor_random = 2.0
        ps_settings.distribution = 'RAND'
        ps_settings.use_modifier_stack = True
        instance_collection = bpy.data.collections.new(ps_settings.name)
        ps_settings.instance_collection = instance_collection


MODULE_CLASSES.append(AddEmptyScatter)


@polib.log_helpers_bpy.logged_operator
class MakeParticleDataUnique(bpy.types.Operator):
    bl_idname = "engon.scatter_make_particle_data_unique"
    bl_label = "Make Particle System Unique"
    bl_description = (
        "Displays number of users of current data " "(Click to create new unique instance of data)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    particle_system_name: bpy.props.StringProperty(
        name="particle_system_name", default="", options={'HIDDEN'}
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return asset_helpers.has_active_object_with_particle_system(context)

    def execute(self, context: bpy.types.Context):
        particle_system = context.active_object.particle_systems[self.particle_system_name]
        ps_settings_copy = particle_system.settings.copy()

        if ps_settings_copy.instance_collection is not None:
            ps_settings_copy.instance_collection = ps_settings_copy.instance_collection.copy()
            coll = polib.asset_pack_bpy.collection_get(
                context,
                asset_helpers.PARTICLE_SYSTEMS_COLLECTION,
            )
            coll.children.link(ps_settings_copy.instance_collection)

        particle_system.settings = ps_settings_copy
        hatchery.utils.ensure_particle_naming_consistency(
            find_modifier_containing_particle_system(
                context.active_object.modifiers, particle_system
            ),
            particle_system,
        )
        return {'FINISHED'}


MODULE_CLASSES.append(MakeParticleDataUnique)


class ENGON_UL_ScatterAssetsList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # The dupli_object name should consist of "{name}: {count}", but sometimes
        # there can be state where dupli_object == 'No Object'
        if ":" not in item.name:
            layout.label(text=item.name)
            return

        asset_name, _ = item.name.split(":")
        split = layout.split(factor=0.8)
        split.label(text=asset_name)
        split.prop(item, "count", text="")

    def draw_filter(self, context: bpy.types.Context, layout: bpy.types.UILayout) -> None:
        layout.prop(self, "filter_name", text="", icon='VIEWZOOM')


MODULE_CLASSES.append(ENGON_UL_ScatterAssetsList)


class ENGON_UL_ScatterParticlesList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        ps_settings = item.settings
        # TODO:
        if ps_settings.name.startswith(asset_helpers.PARTICLE_SYSTEM_PREFIX):
            _, _, name = ps_settings.name.split("_", 2)
        else:
            name = ps_settings.name

        row = layout.row(align=True)
        row.label(text=name)
        modifier = find_modifier_containing_particle_system(data.modifiers, item)
        if ps_settings.users > 1:
            col = row.column()
            col.scale_x = 0.5
            col.operator(
                MakeParticleDataUnique.bl_idname, text=f"{ps_settings.users}"
            ).particle_system_name = item.name
        row.prop(modifier, "show_viewport", icon_only=True)
        row.prop(modifier, "show_render", icon_only=True)


MODULE_CLASSES.append(ENGON_UL_ScatterParticlesList)


@polib.log_helpers_bpy.logged_operator
class ScatterWeightPaint(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_paint"
    bl_label = "Weight Paint"
    bl_description = "Paint weight of active particle system on active object"
    bl_options = {'REGISTER'}

    target: bpy.props.StringProperty(
        name="Target Vertex Group",
        description="Target vertex group name (density, length, ...) from particle system settings",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return asset_helpers.has_active_object_with_particle_system(context)

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        if len(active_object.data.vertices) <= WEIGHT_PAINT_VERTICES_WARNING_THRESHOLD:
            self.report({'WARNING'}, "Subdivide the mesh more for better weight paint results")

        particle_system: bpy.types.ParticleSystem = active_object.particle_systems.active

        target_vertex_group_prop = f"vertex_group_{self.target}"
        if not hasattr(particle_system, target_vertex_group_prop):
            logger.error(f"Invalid vertex group '{target_vertex_group_prop}' for weight paint!")
            return {'CANCELLED'}

        # Default name of polygoniq vertex group is inherited from the particle system name
        # We create new vertex group if nothing is selected
        vertex_group_name = getattr(particle_system, target_vertex_group_prop, "")
        vertex_group = active_object.vertex_groups.get(vertex_group_name, None)
        if vertex_group is None:
            vertex_group = active_object.vertex_groups.new(
                name=f"{polib.asset_pack.PARTICLE_SYSTEM_TOKEN}_{self.target}"
            )
            setattr(particle_system, target_vertex_group_prop, vertex_group.name)

        # Set vertex group as active so it can be painted on in the weight paint mode
        active_object.vertex_groups.active = vertex_group
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

        logger.info(
            f"Weight painting target {active_object.name}, using particles "
            f"{particle_system.name}, vertex group {vertex_group.name}"
        )

        return {'FINISHED'}


MODULE_CLASSES.append(ScatterWeightPaint)


@polib.log_helpers_bpy.logged_operator
class DuplicateVertexGroupWeights(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_duplicate_weights"
    bl_label = "Duplicate Vertex Group Weights"
    bl_description = "Duplicate Vertex Group Weights"
    bl_options = {'REGISTER'}

    target_vertex_group: bpy.props.StringProperty(
        name="Target Vertex Group",
        description="The vertex group to duplicate the weights for",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return asset_helpers.has_active_object_with_particle_system(context)

    @classmethod
    def description(cls, context: bpy.types.Context, props: bpy.types.OperatorProperties) -> str:
        return (
            f"Duplicates {props.target_vertex_group} vertex group weights into a new vertex group"
        )

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        particle_system = active_object.particle_systems.active
        vertex_group_name = getattr(particle_system, self.target_vertex_group, "")
        if vertex_group_name == "":
            self.report({'WARNING'}, "Can't duplicate density weight - no vertex group was found")
            return {'CANCELLED'}
        vertex_group = active_object.vertex_groups[vertex_group_name]

        active_vertex_group = active_object.vertex_groups.active
        active_object.vertex_groups.active = vertex_group
        bpy.ops.object.vertex_group_copy()
        active_object.vertex_groups.active = active_vertex_group

        return {'FINISHED'}


MODULE_CLASSES.append(DuplicateVertexGroupWeights)


@polib.log_helpers_bpy.logged_operator
class RenameParticleSystem(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_rename"
    bl_label = "Rename Particle System"
    bl_description = "Renames selected engon scatter particle system"
    bl_options = {'REGISTER', 'UNDO'}

    new_name: bpy.props.StringProperty(
        name="New Name", description="This is going to be particle system new name"
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        factor = 0.3

        split = layout.split(factor=factor)
        split.label(text="Old name:")
        split.label(text=self.old_name)

        split = layout.split(factor=factor)
        split.label(text="New name:")
        split.prop(self, "new_name", text="")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return asset_helpers.has_active_object_with_particle_system(context)

    def execute(self, context: bpy.types.Context):
        if self.old_name == self.new_name:
            return {'FINISHED'}

        if not polib.asset_pack.is_pps_name(self.new_name):
            self.new_name = f"{asset_helpers.PARTICLE_SYSTEM_PREFIX}{self.new_name}"
        active_object = context.active_object
        active_particle_system = active_object.particle_systems.active
        instance_collection = active_particle_system.settings.instance_collection
        modifier = find_modifier_containing_particle_system(
            active_object.modifiers, active_particle_system
        )
        if modifier is None:
            self.report(
                {'WARNING'},
                f"Failed to find corresponding particles modifier with name {active_particle_system.name}",
            )
            return {'CANCELLED'}

        if instance_collection is None:
            self.report(
                {'WARNING'}, f"No related instance collection in {active_particle_system.name}"
            )
            return {'CANCELLED'}

        # change the names
        modifier.name = self.new_name
        active_particle_system.settings.name = self.new_name
        active_particle_system.name = self.new_name
        instance_collection.name = self.new_name

        logger.info(f"Renamed particle system {self.old_name} to {self.new_name}")
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # If the particle system contains prefix "engon_pps", then we know its ours and we
        # treat it without prefix. Otherwise take the full name.
        if polib.asset_pack.is_pps_name(context.active_object.particle_systems.active.name):
            _, _, name = context.active_object.particle_systems.active.name.split("_", 2)
        else:
            name = context.active_object.particle_systems.active.name

        self.old_name = name
        self.new_name = name
        return context.window_manager.invoke_props_dialog(self)


MODULE_CLASSES.append(RenameParticleSystem)


@polib.log_helpers_bpy.logged_operator
class ReturnToObjectMode(bpy.types.Operator):
    bl_idname = "engon.scatter_return_to_object_mode"
    bl_label = "Return To Object Mode"
    bl_description = "If not in object mode go back to object mode"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode in {'PAINT_WEIGHT', 'PAINT_GPENCIL'}

    def execute(self, context: bpy.types.Context):
        if context.mode != 'OBJECT':
            logger.info(f"Returning from mode {context.mode} to OBJECT mode")
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}


MODULE_CLASSES.append(ReturnToObjectMode)


@polib.log_helpers_bpy.logged_operator
class RemoveParticleSystem(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_remove"
    bl_label = "Remove Particle System"
    bl_description = "Removes active particle system from selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return asset_helpers.has_active_object_with_particle_system(context)

    def execute(self, context: bpy.types.Context):
        active_object = context.active_object
        particle_systems = active_object.particle_systems
        ps_to_remove = particle_systems.active
        # Keep references to particle system settings and name
        # because the 'ps_to_remove' data are removed with
        # the modifier
        ps_settings_to_remove = ps_to_remove.settings
        ps_settings_to_remove_name = ps_settings_to_remove.name

        logger.info(
            f"Going to remove {ps_settings_to_remove_name} from {[obj.name for obj in context.selected_objects]}"
        )

        # Remove particle system from selected objects only
        for obj in context.selected_objects:
            for modifier in obj.modifiers:
                if modifier.type != 'PARTICLE_SYSTEM':
                    continue
                if modifier.particle_system.settings.name == ps_settings_to_remove_name:
                    # Store previous index, so we can keep it on the next item from deleted.
                    prev_index = particle_systems.active_index
                    obj.modifiers.remove(modifier)
                    particle_systems.active_index = max(0, prev_index - 1)

        # If some users of the particle system still exist, we can keep the particle system data
        if ps_settings_to_remove.users > 0:
            return {'FINISHED'}

        instance_collection = ps_settings_to_remove.instance_collection

        # We remove only from scatter and botaniq animation collections,
        # we don't want to delete other user's setup
        collection_candidates: typing.Set[bpy.types.Collection] = set()
        hierarchies: typing.List[typing.List[bpy.types.ID]] = []
        if instance_collection is not None:
            collection_candidates.add(instance_collection)

            # Gather all objects children out of instanced objects, those objects don't necessarily
            # have to be linked in the collection, they can be just parented to the object.
            hierarchies = [
                polib.asset_pack_bpy.get_hierarchy(obj) for obj in instance_collection.all_objects
            ]
        else:
            self.report({'WARNING'}, f"No related instance collection in {ps_to_remove.name}")

        # If the empties collection is present, consider it too.
        if asset_helpers.ANIMATION_EMPTIES_COLL_NAME in bpy.data.collections:
            animation_empties_coll = asset_helpers.get_animation_empties_collection(context)
            collection_candidates.add(animation_empties_coll)

        # unpack hierarchies into one set and check if they are in any of searched collections, if
        # yes then unlink the object and if it is not used anywhere anymore, remove it from the
        # bpy.data.
        for obj in set(itertools.chain(*hierarchies)):
            for coll in collection_candidates:
                if obj.name in coll.all_objects:
                    coll.objects.unlink(obj)

            if obj.users == 0 and obj.use_fake_user is False:
                bpy.data.objects.remove(obj)

        # Remove the collection if there aren't any remaining objects
        for coll in collection_candidates:
            if len(coll.all_objects) == 0 and coll.use_fake_user is False:
                bpy.data.collections.remove(coll)

        if ps_settings_to_remove.users == 0:
            bpy.data.particles.remove(ps_settings_to_remove)

        return {'FINISHED'}


MODULE_CLASSES.append(RemoveParticleSystem)


@polib.log_helpers_bpy.logged_operator
class ParticleSystemAppendSelection(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_append_selection"
    bl_label = "Append Selection"
    bl_description = "Appends all selected objects to active particle system collection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if not asset_helpers.has_active_object_with_particle_system(context):
            return False

        if context.active_object.particle_systems.active.settings.instance_collection is None:
            return False

        return True

    def execute(self, context: bpy.types.Context):
        selection = context.selected_objects
        active_object = context.active_object
        active_particle_system = active_object.particle_systems.active
        instance_collection = active_particle_system.settings.instance_collection

        logger.info(
            f"Working with {active_object.name}, "
            f"active particle system: {active_particle_system.name}"
        )

        for obj in selection:
            if obj.type != 'MESH':
                msg = f"Cannot append {obj.name}, it is not a mesh."
                logger.warning(msg)
                self.report({'WARNING'}, msg)
                continue

            if obj == active_object:
                continue

            if obj.name in instance_collection.all_objects:
                msg = f"Cannot append {obj.name}, it is already in the particle system."
                logger.warning(msg)
                self.report({'WARNING'}, msg)
                continue

            # Rotate the spawned asset 90° around Y axis to make it straight in particle systems.
            obj.rotation_euler = mathutils.Euler((0, math.radians(90), 0), 'XYZ')
            instance_collection.objects.link(obj)
            logger.info(f"Appended {obj.name}")

        # Update instance collection to propagate changes
        active_particle_system.settings.instance_collection = instance_collection
        return {'FINISHED'}


MODULE_CLASSES.append(ParticleSystemAppendSelection)


@polib.log_helpers_bpy.logged_operator
class ParticleSystemRemoveAsset(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_remove_asset"
    bl_label = "Remove Asset"
    bl_description = "Removes selected asset from active particle system collection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if not asset_helpers.has_active_object_with_particle_system(context):
            return False

        settings = context.active_object.particle_systems.active.settings
        if settings.instance_collection is None:
            return False

        if settings.active_instanceweight_index >= len(settings.instance_collection.all_objects):
            return False

        return True

    def execute(self, context: bpy.types.Context):
        particle_settings: bpy.types.ParticleSettings = (
            context.active_object.particle_systems.active.settings
        )
        instance_collection = particle_settings.instance_collection
        prev_index = particle_settings.active_instanceweight_index
        # instanceweight.name stores "name: COUNT" for some reason
        root_object_to_unlink_name, _ = particle_settings.active_instanceweight.name.split(":", 1)
        # instanceweights use the object it has to be in the bpy.data.objects
        assert root_object_to_unlink_name in bpy.data.objects
        root_object_to_unlink = bpy.data.objects.get(root_object_to_unlink_name)
        hierarchy = polib.asset_pack_bpy.get_hierarchy(root_object_to_unlink)
        unlinked_object_names: typing.Set[str] = set()
        for obj in reversed(hierarchy):
            unlinked_object_names.add(obj.name)
            if obj.name in instance_collection.objects:
                instance_collection.objects.unlink(obj)

            # We have to manually update the collection every iteration in order to propagate the
            # changes to it to the instance_weights list. I would've expected doing this after the
            # for loop to work (or using .update_tag()), but unfortunately it doesn't.
            # Ideally we would use the bpy.ops.particle.dupliobj_remove(), but only when somebody
            # figures out what is the right context override for that one...
            particle_settings.instance_collection = instance_collection
            # If there is no user or only one user of the object we can assume the particle system
            # is the last user.
            if obj.users <= 1:
                bpy.data.objects.remove(obj)

        # Update the active instance weight index for better UX (so after removing assets the
        # index doesn't isn't set to zero).
        particle_settings.active_instanceweight_index = max(
            0, min(prev_index, len(instance_collection.all_objects)) - 1
        )

        logger.info(
            f"Removed {unlinked_object_names} from particle system {particle_settings.name} on "
            f"target object {context.active_object.name}"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ParticleSystemRemoveAsset)


@polib.log_helpers_bpy.logged_operator
class ParticleSystemRecalculateDensity(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_recalculate_density"
    bl_label = "Recalculate Density"
    bl_description = "Recalculates density based on area of the mesh of active particle system"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.mode in {'OBJECT', 'PAINT_WEIGHT'}
            and context.active_object is not None
            and context.active_object.particle_systems.active is not None
        )

    def execute(self, context: bpy.types.Context):
        particle_system = context.active_object.particle_systems.active
        ps_settings = particle_system.settings
        ps_settings.count, overflow = hatchery.utils.get_area_based_particle_count(
            context.active_object,
            ps_settings.pps_density,
            preferences.prefs_utils.get_preferences(
                context
            ).general_preferences.scatter_props.max_particle_count,
            include_weights=particle_system.vertex_group_density != "",
        )
        if overflow > 0:
            self.report({'WARNING'}, f"Particle system exceeded maximum by: {int(overflow)}")

        logger.info(
            f"Scatter density recalculated for object {context.active_object.name}, particle system "
            f"{particle_system.name}, new count: {ps_settings.count}, overflow: {overflow}"
        )
        return {'FINISHED'}


MODULE_CLASSES.append(ParticleSystemRecalculateDensity)


@polib.log_helpers_bpy.logged_operator
class ParticleSystemRefresh(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_refresh"
    bl_label = "Particles Refresh"
    bl_description = "Refreshes and updates instance collection objects of active particle system"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != 'OBJECT':
            return False

        if context.active_object is None:
            return False

        active_particle_system = context.active_object.particle_systems.active
        if active_particle_system is None:
            return False

        return True

    def execute(self, context: bpy.types.Context):
        ps_settings = context.active_object.particle_systems.active.settings
        ps_settings.instance_collection = ps_settings.instance_collection

        return {'FINISHED'}


MODULE_CLASSES.append(ParticleSystemRefresh)


@polib.log_helpers_bpy.logged_operator
class ParticlesChangeDisplay(bpy.types.Operator):
    bl_idname = "engon.scatter_particles_change_display"
    bl_label = "Change Display"
    bl_description = (
        "Changes visibility of all polygoniq particle systems " "on active object or in whole scene"
    )
    bl_options = {'REGISTER'}

    class Behavior:
        ACTIVE = "active"
        SELECTED = "selected"
        SCENE = "scene"

    behavior: bpy.props.EnumProperty(
        name="Operator Behaviour",
        description="How this operator influences the scene",
        items=[
            (Behavior.ACTIVE, "Active", "Only active object"),
            (Behavior.SELECTED, "Selected", "All selected objects"),
            (Behavior.SCENE, "Scene", "All objects in the scene"),
        ],
        default=Behavior.ACTIVE,
    )

    all_systems: bpy.props.BoolProperty(
        name="Influence All Particle Systems",
        description="If true this operator influences all particle systems on found objects. "
        "Active particle system is influenced if this is False",
        default=True,
    )

    only_pps: bpy.props.BoolProperty(
        name="Only engon_pps_",
        description="If true this operator influences only polygoniq particle systems",
        default=True,
    )

    @classmethod
    def poll(cls, context: bpy.types.Object) -> bool:
        return context.mode == 'OBJECT'

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        layout.prop(self, "all_systems")
        layout.prop(self, "only_pps")
        layout.prop(self, "behavior", text="Objects")
        layout.prop(props, "display_type")
        layout.prop(props, "display_percentage", text="Viewport Display Percentage")

    def find_particle_systems(self, obj: bpy.types.Object) -> typing.List[bpy.types.ParticleSystem]:
        if self.all_systems:
            return list(
                filter(
                    lambda x: polib.asset_pack.is_pps_name(x.name) if self.only_pps else True,
                    obj.particle_systems,
                )
            )
        else:
            active_system = obj.particle_systems.active
            if active_system is None:
                return []
            if self.only_pps and polib.asset_pack.is_pps_name(active_system.name):
                return [active_system]
            elif not polib.asset_pack.is_pps_name(active_system.name):
                return [active_system]
            else:
                return []

    def execute(self, context: bpy.types.Context):
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        particle_systems = []

        if self.behavior == self.Behavior.ACTIVE:
            if context.active_object is not None:
                particle_systems.extend(self.find_particle_systems(context.active_object))
        elif self.behavior == self.Behavior.SELECTED:
            for obj in context.selected_objects:
                particle_systems.extend(self.find_particle_systems(obj))
        elif self.behavior == self.Behavior.SCENE:
            for obj in context.scene.objects:
                particle_systems.extend(self.find_particle_systems(obj))
        else:
            raise RuntimeError(f"Invalid behavior enum value: {self.behavior}")

        for particle_system in particle_systems:
            particle_system.settings.display_percentage = props.display_percentage

            instance_collection = particle_system.settings.instance_collection
            if instance_collection is None:
                continue

            for obj in instance_collection.all_objects:
                obj.display_type = props.display_type

        return {'FINISHED'}


MODULE_CLASSES.append(ParticlesChangeDisplay)


class SCATTER_MT_Utilities(bpy.types.Menu):
    bl_label = "Scatter Utilities"
    bl_idname = "SCATTER_MT_Utilities"

    def draw(self, context: typing.Optional[bpy.types.Context]) -> None:
        layout = self.layout
        layout.operator(RenameParticleSystem.bl_idname, text="Rename", icon='GREASEPENCIL')
        layout.operator("particle.duplicate_particle_system", text="Duplicate", icon='DUPLICATE')


MODULE_CLASSES.append(SCATTER_MT_Utilities)


@polib.log_helpers_bpy.logged_panel
class ScatterPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_scatter"
    bl_parent_id = panel.EngonPanel.bl_idname
    bl_label = "Scatter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='FILE_VOLUME')

    def draw_emitter_visibility(self, layout: bpy.types.UILayout, obj: bpy.types.Object) -> None:
        if obj is None:
            return

        emitter_render = obj.show_instancer_for_render
        emitter_viewport = obj.show_instancer_for_viewport
        layout.prop(
            obj,
            "show_instancer_for_viewport",
            text="",
            icon='RESTRICT_VIEW_OFF' if emitter_viewport else 'RESTRICT_VIEW_ON',
        )
        layout.prop(
            obj,
            "show_instancer_for_render",
            text="",
            icon='RESTRICT_RENDER_OFF' if emitter_render else 'RESTRICT_RENDER_ON',
        )

    def draw_object_mode_ui(self, context: bpy.types.Context) -> None:
        layout = self.layout
        row = layout.row(align=True)
        polib.ui_bpy.scaled_row(row, 1.3, align=True).prop_search(
            context.view_layer.objects, "active", context.collection, "objects", text="Target"
        )
        self.draw_emitter_visibility(row, context.active_object)

        if context.active_object is None or context.active_object.type != 'MESH':
            return

        layout.separator()

        col = layout.column(align=True)
        row = col.row(align=True)
        row.scale_x = row.scale_y = 1.1
        row.alignment = 'RIGHT'
        row.operator(AddEmptyScatter.bl_idname, text="", icon='ADD')
        row.operator(RemoveParticleSystem.bl_idname, text="", icon='REMOVE')
        sub = row.column()
        sub.menu(SCATTER_MT_Utilities.bl_idname, icon='DOWNARROW_HLT', text="")

        row = col.row()
        row.template_list(
            "ENGON_UL_ScatterParticlesList",
            "",
            context.active_object,
            "particle_systems",
            context.active_object.particle_systems,
            "active_index",
        )

    def draw(self, context: bpy.types.Context) -> None:
        """Draws UI for scatter"""
        self.draw_object_mode_ui(context)


MODULE_CLASSES.append(ScatterPanel)


@polib.log_helpers_bpy.logged_panel
class ScatterParticlesSettingsPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_scatter_particle_properties"
    bl_parent_id = ScatterPanel.bl_idname
    bl_label = "Particle Settings"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.mode == 'OBJECT'
            and context.active_object is not None
            and asset_helpers.has_active_particle_system(context.active_object)
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='PARTICLES')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        particle_system = context.active_object.particle_systems.active

        col = layout.column(align=True)
        col.label(text="Emission")
        col.prop(particle_system.settings, "count", text="Number")
        col.prop(particle_system, "seed", text="Seed")

        col = layout.column(align=True)
        col.label(text="Size")
        col.prop(particle_system.settings, "particle_size", text="Scale")
        col.prop(particle_system.settings, "size_random", text="Scale Randomness")

        col = layout.column(align=True)
        col.label(text="Rotation")
        col.prop(particle_system.settings, "rotation_mode", text="")
        col.prop(particle_system.settings, "rotation_factor_random", text="Randomize")
        col.prop(particle_system.settings, "phase_factor")
        col.prop(particle_system.settings, "phase_factor_random")

        col = layout.column(align=True)
        col.label(text="Density")
        col.prop(particle_system.settings, "pps_density", text="Particles per m^2")
        col.prop(props, "max_particle_count", text="Max Particles")
        polib.ui_bpy.scaled_row(col, 1.5).operator(
            ParticleSystemRecalculateDensity.bl_idname,
            icon="OUTLINER_OB_LIGHTPROBE",
            text="Recalculate Density",
        )


MODULE_CLASSES.append(ScatterParticlesSettingsPanel)


@polib.log_helpers_bpy.logged_panel
class ScatterVisibilitySettingsPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_scatter_visibility"
    bl_parent_id = ScatterPanel.bl_idname
    bl_label = "Visibility Settings"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='HIDE_OFF')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = preferences.prefs_utils.get_preferences(context).general_preferences.scatter_props
        polib.ui_bpy.scaled_row(layout, 1.5).operator(
            ParticlesChangeDisplay.bl_idname,
            icon='RESTRICT_VIEW_OFF',
            text="Manage Viewport Display",
        )

        if context.active_object is None:
            return

        if not asset_helpers.has_active_particle_system(context.active_object):
            return

        layout.separator()
        particle_system = context.active_object.particle_systems.active
        layout.label(text=particle_system.name, icon='PARTICLES')

        row = layout.row(align=True)
        row.prop(particle_system.settings, "display_percentage")

        # update active display type
        instance_collection = particle_system.settings.instance_collection
        if instance_collection is not None:
            if len(instance_collection.all_objects) > 0:
                display_type = instance_collection.all_objects[0].display_type
                if display_type != props.active_display_type:
                    props.active_display_type = display_type
            row.prop(props, "active_display_type", text="")

        col = layout.column()
        displayed_particles = (
            particle_system.settings.count * particle_system.settings.display_percentage // 100
        )
        if displayed_particles <= props.max_particle_count:
            col.label(
                text=f"Displayed particles: {displayed_particles}",
            )
        else:
            overflow = displayed_particles - props.max_particle_count
            col.label(
                text=f"Displayed particles: {props.max_particle_count}",
            )
            row = col.row()
            row.alert = True
            row.label(text=f"Warning: Overflow by: {overflow}", icon='ERROR')


MODULE_CLASSES.append(ScatterVisibilitySettingsPanel)


@polib.log_helpers_bpy.logged_panel
class ScatterWeightPaintPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_scatter_weight_paint"
    bl_parent_id = ScatterPanel.bl_idname
    bl_label = "Paint"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.mode in {'OBJECT', 'PAINT_WEIGHT'}
            and context.active_object is not None
            and asset_helpers.has_active_particle_system(context.active_object)
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='BRUSH_DATA')

    def draw_vertex_group_ui(
        self,
        layout: bpy.types.UILayout,
        obj: bpy.types.Object,
        particle_system: bpy.types.ParticleSystem,
        target_group: str,
        icon: str = 'BLANK1',
    ) -> None:
        row = layout.row(align=True)
        row.label(text=target_group.capitalize(), icon=icon)
        row.prop_search(
            particle_system,
            f"vertex_group_{target_group}",
            obj,
            "vertex_groups",
            text="",
        )
        row.operator(ScatterWeightPaint.bl_idname, text="", icon='BRUSH_DATA').target = target_group
        row.prop(
            particle_system, f"invert_vertex_group_{target_group}", text="", icon='ARROW_LEFTRIGHT'
        )
        row.operator(
            DuplicateVertexGroupWeights.bl_idname, text="", icon='DUPLICATE'
        ).target_vertex_group = f"vertex_group_{target_group}"

    def draw_object_mode_ui(self, context: bpy.types.Context) -> None:
        layout = self.layout
        active_object = context.active_object
        if len(active_object.data.vertices) <= WEIGHT_PAINT_VERTICES_WARNING_THRESHOLD:
            row = layout.row()
            row.alert = True
            row.label(text="Subdivide the mesh for better weight paint results!", icon='ERROR')

        particle_system = active_object.particle_systems.active
        self.draw_vertex_group_ui(
            layout, active_object, particle_system, "density", 'OUTLINER_DATA_LIGHTPROBE'
        )
        self.draw_vertex_group_ui(
            layout, active_object, particle_system, "length", 'EMPTY_SINGLE_ARROW'
        )

    def draw_weight_paint_mode_ui(self, context: bpy.types.Context) -> None:
        layout = self.layout
        active_object = context.active_object
        if active_object is not None and active_object.vertex_groups.active is not None:
            layout.label(text=f"{active_object.vertex_groups.active.name}", icon='GROUP_VERTEX')

        layout.operator(ParticleSystemRecalculateDensity.bl_idname, icon='OUTLINER_OB_LIGHTPROBE')
        layout.operator(ReturnToObjectMode.bl_idname, icon='LOOP_BACK', text="Go Back")

    def draw(self, context: bpy.types.Context) -> None:
        if context.mode == 'OBJECT':
            self.draw_object_mode_ui(context)

        elif context.mode == 'PAINT_WEIGHT':
            self.draw_weight_paint_mode_ui(context)


MODULE_CLASSES.append(ScatterWeightPaintPanel)


@polib.log_helpers_bpy.logged_panel
class ScatterInstancerDetailPanel(panel.EngonPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_scatter_instancer_detail"
    bl_parent_id = ScatterPanel.bl_idname
    bl_label = "Objects"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            context.active_object is not None
            and context.mode == 'OBJECT'
            and asset_helpers.has_active_particle_system(context.active_object)
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OUTLINER_OB_GROUP_INSTANCE')

    def draw_selected_asset_detail(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        particle_system: bpy.types.ParticleSystem,
    ) -> None:
        dupli_object = particle_system.settings.active_instanceweight
        if dupli_object is None:
            return

        # The dupli_object name should consist of "{name}: {count}", but sometimes
        # there can be state where dupli_object == 'No Object', refreshing particle system
        # collection removes those 'No Object' entries.
        if ":" not in dupli_object.name:
            col = layout.column(align=True)
            col.label(text=dupli_object.name, icon='QUESTION')
            row = col.row(align=True)
            row.label(text="Please refresh the particle system collection!")
            row.operator(ParticleSystemRefresh.bl_idname, text="", icon='FILE_REFRESH')
            return

        orig_name, _ = dupli_object.name.split(":")
        layout.label(text=orig_name, icon='OBJECT_DATA')

        actual_object = bpy.data.objects.get(orig_name, None)
        # Actual object can be none if instance weights are not refreshed
        if actual_object is None:
            return

        col = layout.column()
        col.prop(actual_object, "scale")

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        particle_system = context.active_object.particle_systems.active

        layout.prop(particle_system.settings, "instance_collection", text="")
        if particle_system.settings.instance_collection is None:
            return

        row = layout.row()
        row.alignment = 'RIGHT'
        row.operator(ParticleSystemRefresh.bl_idname, icon='FILE_REFRESH', text="")

        row = row.row(align=True)
        row.operator(ParticleSystemAppendSelection.bl_idname, icon='STICKY_UVS_DISABLE', text="")
        row.operator(ParticleSystemRemoveAsset.bl_idname, icon='REMOVE', text="")

        row = layout.row()
        row.template_list(
            "ENGON_UL_ScatterAssetsList",
            "",
            particle_system.settings,
            "instance_weights",
            particle_system.settings,
            "active_instanceweight_index",
        )

        self.draw_selected_asset_detail(context, layout, particle_system)


MODULE_CLASSES.append(ScatterInstancerDetailPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.ParticleSettings.pps_density = bpy.props.FloatProperty(
        name="Particles per m2",
        description="Density per square meter of active particle system",
        default=20.0,
        min=0.0,
    )


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.ParticleSettings.pps_density
