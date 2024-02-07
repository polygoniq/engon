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
from . import rigs
from . import lights
from .. import preferences
from .. import asset_registry


MODULE_CLASSES: typing.List[typing.Type] = []


TQ_COLLECTION_NAME = "traffiq"


def set_car_paint_color(
    obj: bpy.types.Object,
    color: typing.Tuple[float, float, float, float]
) -> None:
    if polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR in obj:
        obj[polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR] = color
        obj.update_tag(refresh={'OBJECT'})


def get_car_paint_color(obj: bpy.types.Object) -> typing.Tuple[float, float, float, float]:
    assert polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR in obj
    return obj[polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR]


def can_obj_change_car_paint_color(obj: bpy.types.Object) -> bool:
    return polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR in obj


@polib.log_helpers_bpy.logged_operator
class SetColorToRandom(bpy.types.Operator):
    bl_idname = "engon.traffiq_set_color_to_random"
    bl_label = "Set Color to Random"
    bl_description = "Set color of selected assets to random color"

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == 'OBJECT'

    def execute(self, context: bpy.types.Context):
        for obj in context.selected_objects:
            if not can_obj_change_car_paint_color(obj):
                continue

            set_car_paint_color(obj, (1.0, 1.0, 1.0, 1.0))

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


MODULE_CLASSES.append(SetColorToRandom)


class TraffiqPanelInfoMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("traffiq")) > 0


@polib.log_helpers_bpy.logged_panel
class TraffiqPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq"
    bl_label = "traffiq"
    bl_order = 10

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(
            text="", icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("traffiq"))

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        polib.ui_bpy.draw_doc_button(
            self.layout, preferences.__package__, rel_url="panels/traffiq/panel_overview")

    def draw(self, context: bpy.types.Context):
        # TODO: All that was formerly here was replaced with engon universal operators,
        #       only sub-panels remain. Should we reorganize this?
        pass


MODULE_CLASSES.append(TraffiqPanel)


@polib.log_helpers_bpy.logged_panel
class ColorsPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_colors"
    bl_parent_id = TraffiqPanel.bl_idname
    bl_label = "Color Settings"

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='COLOR')

    def draw(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context).traffiq_preferences
        row = self.layout.row()
        changeable_color_objs = [
            obj for obj in context.selected_objects if can_obj_change_car_paint_color(obj)]

        if len(changeable_color_objs) == 0:
            row.label(text="No assets with changeable color selected!")
            return

        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)
        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")
        row = right_col.row()
        row.enabled = False
        row.label(text="Color")
        row.label(text="Clearcoat")
        row.label(text="Flakes Amount")
        for obj in changeable_color_objs:
            row = left_col.row()
            row.label(text=obj.name)
            row = right_col.row()
            current_color = get_car_paint_color(obj)
            if tuple(current_color) == (1.0, 1.0, 1.0, 1.0):
                row.label(text="random")
            else:
                row.prop(
                    obj, f'["{polib.asset_pack_bpy.CustomPropertyNames.TQ_PRIMARY_COLOR}"]', text="")

            if polib.asset_pack_bpy.CustomPropertyNames.TQ_CLEARCOAT in obj:
                row.label(
                    text=f"{obj.get(polib.asset_pack_bpy.CustomPropertyNames.TQ_CLEARCOAT):.2f}")
            else:
                row.label(text="-")

            if polib.asset_pack_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT in obj:
                row.label(
                    text=f"{obj.get(polib.asset_pack_bpy.CustomPropertyNames.TQ_FLAKES_AMOUNT):.2f}")
            else:
                row.label(text="-")

        col = self.layout.column(align=True)
        col.prop(prefs.car_paint_properties, "primary_color")
        col.prop(prefs.car_paint_properties, "clearcoat", slider=True)
        col.prop(prefs.car_paint_properties, "flakes_amount", slider=True)

        row = self.layout.row()
        row.operator(SetColorToRandom.bl_idname, icon='COLOR')


MODULE_CLASSES.append(ColorsPanel)


@polib.log_helpers_bpy.logged_panel
class LightsPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_lights"
    bl_parent_id = TraffiqPanel.bl_idname
    bl_label = "Light Settings"

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='OUTLINER_OB_LIGHT')

    def draw(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context).traffiq_preferences
        col = self.layout.column()
        lights_containers = lights.find_unique_lights_containers(context.selected_objects)
        if len(lights_containers) == 0:
            col.label(text="No assets with lights selected!")
            return

        status_col = col.column(align=True)
        row = status_col.row()
        row.label(text="Selected Assets:")
        row.label(text="Light Status")
        row.enabled = False
        for lights_container in lights_containers:
            row = status_col.row(align=True)
            row.label(text=lights_container.name)
            row.prop(
                lights_container,
                f'["{polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS}"]',
                text=lights.get_main_lights_status_text(
                    lights_container[polib.asset_pack_bpy.CustomPropertyNames.TQ_LIGHTS]
                ),
            )
        col.separator()

        col = col.column(align=True)
        col.label(text="Lights Status:")
        col.prop(prefs.lights_properties, "main_lights_status", text="")

        if context.scene.render.engine != 'CYCLES':
            row = col.row()
            row.alert = True
            row.label(text="Lights are only supported in CYCLES!", icon='ERROR')


MODULE_CLASSES.append(LightsPanel)


@polib.log_helpers_bpy.logged_panel
class WearPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_wear"
    bl_parent_id = TraffiqPanel.bl_idname
    bl_label = "Wear Sliders"

    def format_wear_node_input_value(
        self,
        obj: bpy.types.Object,
        prop_name: str
    ) -> str:
        prop = obj.get(prop_name, None)
        return f"{prop:.2f}" if prop is not None else "-"

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='UV')

    def draw(self, context: bpy.types.Context):
        prefs = preferences.get_preferences(context).traffiq_preferences
        row = self.layout.row()
        wear_props_set = {
            polib.asset_pack_bpy.CustomPropertyNames.TQ_DIRT,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_SCRATCHES,
            polib.asset_pack_bpy.CustomPropertyNames.TQ_BUMPS
        }
        objs_with_wear = [ob for ob in context.selected_objects if len(
            wear_props_set.intersection(set(ob.keys()))) > 0]

        if len(objs_with_wear) == 0:
            row.label(text="No assets with wear selected!")
            return

        left_col = row.column(align=True)
        left_col.scale_x = 2.0
        right_col = row.column(align=True)
        row = left_col.row()
        row.enabled = False
        row.label(text="Selected Assets:")
        row = right_col.row()
        row.enabled = False
        row.label(text="Dirt")
        row.label(text="Scratches")
        row.label(text="Bumps")
        for obj in objs_with_wear:
            row = left_col.row()
            row.label(text=obj.name)
            row = right_col.row()
            row.label(text=self.format_wear_node_input_value(
                obj, polib.asset_pack_bpy.CustomPropertyNames.TQ_DIRT))
            row.label(text=self.format_wear_node_input_value(
                obj, polib.asset_pack_bpy.CustomPropertyNames.TQ_SCRATCHES))
            row.label(text=self.format_wear_node_input_value(
                obj, polib.asset_pack_bpy.CustomPropertyNames.TQ_BUMPS))

        any_object_with_applicable_dirt = any(
            polib.asset_pack_bpy.CustomPropertyNames.TQ_DIRT in obj for obj in objs_with_wear)
        any_object_with_applicable_scratches = any(
            polib.asset_pack_bpy.CustomPropertyNames.TQ_SCRATCHES in obj for obj in objs_with_wear)
        any_object_with_applicable_bumps = any(
            polib.asset_pack_bpy.CustomPropertyNames.TQ_BUMPS in obj for obj in objs_with_wear)

        col = self.layout.column(align=True)
        for wear_strength_prop, any_obj_with_applicable_wear in zip(
                ["dirt_wear_strength", "scratches_wear_strength", "bumps_wear_strength"],
                [any_object_with_applicable_dirt, any_object_with_applicable_scratches, any_object_with_applicable_bumps]):
            row = col.row(align=True)
            row.prop(prefs.wear_properties, wear_strength_prop, slider=True)
            row.enabled = any_obj_with_applicable_wear


MODULE_CLASSES.append(WearPanel)


@polib.log_helpers_bpy.logged_panel
class RigsPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_rigs"
    bl_parent_id = TraffiqPanel.bl_idname
    bl_label = "Rigs"

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='AUTO')

    def draw(self, context: bpy.types.Context):
        layout = self.layout.column()
        layout.use_property_decorate = False
        layout.use_property_split = True
        if context.active_object is None:
            layout.label(text="No active object!")
            return

        if not polib.rigs_shared_bpy.is_object_rigged(context.active_object):
            layout.label(text="Active object doesn't contain rig!")
            return

        layout.prop(context.scene, "tq_target_path_object", text="Path", icon='CON_FOLLOWPATH')
        layout.prop(context.scene, "tq_ground_object", text="Ground", icon='IMPORT')
        col = layout.column(align=True)
        row = col.row()
        row.scale_x = row.scale_y = 1.5
        row.operator(rigs.FollowPath.bl_idname, icon='TRACKING')
        row = col.row()
        row.scale_x = row.scale_y = 1.25
        row.operator(rigs.ChangeFollowPathSpeed.bl_idname, icon='FORCE_FORCE')

        layout.separator()

        col = layout.column(align=True)
        col.operator(rigs.BakeSteering.bl_idname, icon='GIZMO')
        col.operator(rigs.BakeWheelRotation.bl_idname, icon='PHYSICS')
        layout.separator()

        self.layout.operator(rigs.RemoveAnimation.bl_idname, icon='PANEL_CLOSE')


MODULE_CLASSES.append(RigsPanel)


def get_position_display_name(position: str) -> str:
    """Returns human readable form of our wheel position naming conventions
    (e. g. BL_0 -> Back Left (0))
    """

    raw_position_to_display_map = {
        "BL": "Back Left",
        "BR": "Back Right",
        "FR": "Front Right",
        "FL": "Front Left",
        "F": "Front",
        "B": "Back"
    }

    position_split = position.split("_", 1)
    if len(position_split) == 2:
        position, index = position_split
    else:
        position, index = position_split[0], "0"

    index_suffix = f" ({index})" if int(index) > 0 else ""
    return f"{raw_position_to_display_map.get(position, '')}{index_suffix}"


@polib.log_helpers_bpy.logged_panel
class RigsGroundSensorsPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_rigs_ground_sensors"
    bl_parent_id = RigsPanel.bl_idname
    bl_label = "Ground Sensors"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return polib.rigs_shared_bpy.is_object_rigged(context.active_object)

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='IMPORT')

    def draw(self, context: bpy.types.Context):
        layout = self.layout.column()
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(context.scene, "tq_ground_object", text="Ground", icon='IMPORT')
        layout.operator(rigs.SetGroundSensors.bl_idname, text="Set Ground Object For All")
        layout.separator()

        sensors_manipulator = rigs.GroundSensorsManipulator(context.active_object.pose)
        for name, constraint in sensors_manipulator.ground_sensors_constraints.items():
            if constraint is None:
                continue

            layout.label(text=self.get_ground_sensor_display_name(name), icon='IMPORT')
            layout.prop(constraint, "target", text="Ground")
            layout.prop(constraint, "shrinkwrap_type")
            layout.prop(constraint, "project_limit")
            layout.prop(constraint, "influence")
            layout.separator()

    def get_ground_sensor_display_name(self, name: str):
        if "Axle" in name:
            _, _, position = name.split("_", 2)
            return f"{get_position_display_name(position)} Axle [{name}]"
        else:
            _, position = name.split("_", 1)
            return f"{get_position_display_name(position)} [{name}]"


MODULE_CLASSES.append(RigsGroundSensorsPanel)


@polib.log_helpers_bpy.logged_panel
class RigsRigPropertiesPanel(TraffiqPanelInfoMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_traffiq_rigs_rig_properties"
    bl_parent_id = RigsPanel.bl_idname
    bl_label = "Rig Properties"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return polib.rigs_shared_bpy.is_object_rigged(context.active_object) and \
            rigs.check_rig_drivers(context.active_object)

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='OPTIONS')

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        active_object = context.active_object
        layout.label(text="Wheels")
        for prop in active_object.keys():
            if prop.startswith(polib.rigs_shared_bpy.TraffiqRigProperties.WHEEL_ROTATION):
                self.display_custom_property(active_object, layout, prop)

        layout.label(text="Suspension")
        self.display_custom_property(
            active_object,
            layout,
            polib.rigs_shared_bpy.TraffiqRigProperties.SUSPENSION_FACTOR
        )
        self.display_custom_property(
            active_object,
            layout,
            polib.rigs_shared_bpy.TraffiqRigProperties.SUSPENSION_ROLLING_FACTOR
        )

        layout.label(text="Steering")
        self.display_custom_property(
            active_object,
            layout,
            polib.rigs_shared_bpy.TraffiqRigProperties.STEERING
        )

    def display_custom_property(
        self,
        obj: bpy.types.Object,
        layout: bpy.types.UILayout,
        prop_name: str
    ) -> None:
        if prop_name.startswith("tq_"):
            prop_display_name = prop_name[len("tq_"):]
        else:
            prop_display_name = prop_name

        if prop_name.startswith(polib.rigs_shared_bpy.TraffiqRigProperties.WHEEL_ROTATION):
            _, position = prop_display_name.split("_", 1)
            prop_display_name = f"{get_position_display_name(position)}"

        if prop_name in obj.keys():
            layout.prop(obj, f'["{prop_name}"]', text=prop_display_name)
        else:
            layout.label(text=f"Property {prop_name} N/A")


MODULE_CLASSES.append(RigsRigPropertiesPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
