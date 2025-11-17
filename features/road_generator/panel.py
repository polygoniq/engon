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
import logging
from . import props
from . import build_roads_modal
from . import asset_helpers
from .. import feature_utils
from .. import asset_pack_panels
from ... import polib

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES = []


@polib.log_helpers_bpy.logged_operator
class ConvertToMesh(bpy.types.Operator):
    bl_idname = "engon.traffiq_road_generator_convert_to_mesh"
    bl_label = "Convert To Mesh"
    bl_description = "Converts selected roads to editable meshes"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context: bpy.types.Context):
        road_generator_objects = [
            o for o in context.selected_objects if asset_helpers.is_road_generator_obj(o)
        ]

        # Switch all cleanup modifiers to realize instances, so the instances are
        # in the final converted geometry
        for obj in road_generator_objects:
            cleanup_candidates = [
                mod
                for mod in obj.modifiers
                if mod.node_group.name.startswith(asset_helpers.RoadNodegroup.Cleanup)
            ]
            if len(cleanup_candidates) == 0:
                continue

            cleanup_mod_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(
                cleanup_candidates[-1]
            )
            cleanup_mod_view.set_input_value("Realize Instances", True)

        if len(road_generator_objects) == 0:
            return {'CANCELLED'}

        with context.temp_override(selected_objects=road_generator_objects):
            bpy.ops.object.convert(target='MESH')

        return {'FINISHED'}


MODULE_CLASSES.append(ConvertToMesh)


@polib.log_helpers_bpy.logged_operator
class MassChangeResample(bpy.types.Operator):
    bl_idname = "engon.traffiq_road_generator_mass_resample"
    bl_label = "Mass Resample"
    bl_description = "Sets resample of all road generator modifiers to specified value"
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        resample_props = props.get_rg_props(context).resample

        row = layout.row(align=True)
        row.enabled = False
        row.label(text="Changes resolution of generated road geometry.", icon='QUESTION')

        layout.prop(resample_props, "value")

        col = layout.column(align=True)
        col.prop(resample_props, "include_input", toggle=1)
        col.prop(resample_props, "include_markings", toggle=1)
        col.prop(resample_props, "include_profile", toggle=1)
        col.prop(resample_props, "include_register", toggle=1)

        layout.prop(resample_props, "only_selected")

    def execute(self, context: bpy.types.Context):
        resample_props = props.get_rg_props(context).resample
        resample_targets = set()
        if resample_props.include_input:
            resample_targets.add(asset_helpers.RoadNodegroup.Input)
        if resample_props.include_markings:
            resample_targets.add(asset_helpers.RoadNodegroup.Markings)
        if resample_props.include_profile:
            resample_targets.add(asset_helpers.RoadNodegroup.RoadProfile)
        if resample_props.include_register:
            resample_targets.add(asset_helpers.CrossroadNodegroup.Register)

        changed_inputs = []
        resample_targets = tuple(resample_targets)
        for obj in context.selected_objects if resample_props.only_selected else bpy.data.objects:
            if not asset_helpers.is_road_generator_obj(obj):
                continue

            for mod in obj.modifiers:
                mod_named_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
                if not mod.node_group.name.startswith(resample_targets):
                    continue

                for k in ("Resample", "Resample Length"):
                    if k in mod_named_view:
                        mod_named_view.set_input_value(k, resample_props.value)
                        changed_inputs.append(f"{mod}[{k}]")

            obj.update_tag()

        if context.area:
            context.area.tag_redraw()

        logger.info(f"Resampled '{changed_inputs}' to '{resample_props.value}'")
        self.report({'INFO'}, f"Changed {len(changed_inputs)} input(s).")
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)


MODULE_CLASSES.append(MassChangeResample)


@polib.log_helpers_bpy.logged_operator
class MassChangeFillet(bpy.types.Operator):
    bl_idname = "engon.traffiq_road_generator_mass_change_fillet"
    bl_label = "Mass Change Fillet"
    bl_description = (
        "Sets Fillet Radius of all road generator input curve modifiers to a " "specified value"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        fillet_props = props.get_rg_props(context).fillet

        row = layout.row(align=True)
        row.enabled = False
        row.label(text="Changes fillet radius of the input curves.", icon='QUESTION')

        layout.prop(fillet_props, "value")
        layout.prop(fillet_props, "only_selected")

    def execute(self, context: bpy.types.Context):
        fillet_props = props.get_rg_props(context).fillet
        changed_inputs = []
        for obj in context.selected_objects if fillet_props.only_selected else bpy.data.objects:
            if not asset_helpers.is_road_generator_obj(obj):
                continue

            for mod in obj.modifiers:
                mod_named_view = polib.geonodes_mod_utils_bpy.NodesModifierInputsNameView(mod)
                if not mod.node_group.name.startswith(asset_helpers.RoadNodegroup.Input):
                    continue

                if "Fillet Radius" in mod_named_view:
                    mod_named_view.set_input_value("Fillet Radius", fillet_props.value)
                    changed_inputs.append(f"{mod}[Fillet Radius]")

            obj.update_tag()

        if context.area:
            context.area.tag_redraw()

        logger.info(f"Changed fillet of '{changed_inputs}' to '{fillet_props.value}'")
        self.report({'INFO'}, f"Changed {len(changed_inputs)} input(s).")
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(self)


MODULE_CLASSES.append(MassChangeFillet)


@polib.log_helpers_bpy.logged_operator
class AddRoadGeneratorModifier(bpy.types.Operator):
    bl_idname = "engon.traffiq_road_generator_add_modifier"
    bl_label = "Add Modifier"
    bl_description = (
        "Add additional road feature. This links road generator node group and adds "
        "it as a new modifier"
    )

    mod_type: bpy.props.EnumProperty(items=asset_helpers.get_modifiers_enum_items())

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None and context.active_object.type == 'CURVE'

    def execute(self, context: bpy.types.Context):
        lib_path = props.get_rg_props(context).geonodes_lib_path
        with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
            data_to.node_groups = [ng for ng in data_from.node_groups if ng == self.mod_type]

        if len(data_to.node_groups) == 0:
            self.report({'ERROR'}, f"Failed to find node group '{self.mod_type}'")
            return {'CANCELLED'}

        active_object: bpy.types.Object = context.active_object
        mod: bpy.types.NodesModifier = active_object.modifiers.new(self.mod_type, type='NODES')
        mod.node_group = data_to.node_groups[0]

        return {'FINISHED'}


MODULE_CLASSES.append(AddRoadGeneratorModifier)


@feature_utils.register_feature
class RoadGeneratorPanelMixin(
    feature_utils.EngonFeaturePanelMixin,
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
):
    feature_name = "road_generator"
    pass


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorPanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_build_roads_modal"
    bl_label = "Road Generator (Beta)"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(text="", icon='MOD_SIMPLEDEFORM')

    def draw(self, context: bpy.types.Context) -> None:
        rg_props = props.get_rg_props(context)
        layout = self.layout

        # Draw mode user interface
        active_tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if (
            context.active_object is not None
            and context.active_object.mode == 'EDIT'
            and active_tool is not None
            and active_tool.idname == "builtin.draw"
        ):
            layout.label(text="Currently in Draw Mode", icon='GREASEPENCIL')
            row = layout.row()
            row.enabled = False
            row.label(text="Create a stroke to draw road!")
            layout.operator(bpy.ops.object.mode_set.idname(), text="Exit").mode = 'OBJECT'
            return

        col = layout.column(align=True)
        row = col.row()
        row.enabled = False
        row.label(text="Road System Builder")

        row = col.row()
        row.scale_x = row.scale_y = 1.5
        is_build_roads_modal_running = build_roads_modal.BuildRoads.is_running
        row.enabled = not is_build_roads_modal_running
        row.operator(
            build_roads_modal.BuildRoads.bl_idname, text="Build Roads", icon='GP_MULTIFRAME_EDITING'
        )

        if is_build_roads_modal_running:
            col.separator()
            col.prop(rg_props, "current_road_type", text="Road Type")
            col.prop(rg_props, "current_road_height")
            col.separator()

            row = col.row(align=True)
            row.enabled = False
            row.label(text="Crossroad Settings")
            # TODO: Reenable, check note in crossroad_builder:118
            # col.prop(rg_props.crossroad, "type_", text="Type")
            # if rg_props.crossroad.type_ not in ('BLANK', 'TRAFFIC_LIGHTS'):
            #     col.prop(rg_props.crossroad, "yield_method", text="Method")
            row = col.row(align=True)
            row.label(text="", icon='ALIGN_JUSTIFY')
            row.prop(rg_props.crossroad, "build_crosswalks")
            col.separator()
            col.prop(
                rg_props.crossroad,
                "points_offset",
                text="Crossroad Points Offset",
                icon='ORIENTATION_LOCAL',
            )

            col.separator()
            row = col.row(align=True)
            row.enabled = False
            row.label(text="Tool Settings")
            col.prop(rg_props, "grid_scale_multiplier")
            col.prop(rg_props, "debug", text="Debug Overlays")
        else:
            col = layout.column(align=True)
            row = col.row()
            row.enabled = False
            row.label(text="Utilities")
            col.operator(ConvertToMesh.bl_idname, icon='MESH_DATA')
            col.operator_menu_enum(
                AddRoadGeneratorModifier.bl_idname, "mod_type", text="Add Road Generator Modifier"
            )

        row = col.row()
        row.enabled = False
        row.label(text="Global Presets")

        col.operator(MassChangeResample.bl_idname, icon='MOD_SMOOTH')
        col.operator(MassChangeFillet.bl_idname, icon='SPHERECURVE')


MODULE_CLASSES.append(RoadGeneratorPanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorInputCurvePanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_input_curve"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Input Curve"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(asset_helpers.RoadNodegroup.Input)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorInputCurvePanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorInputCurvePanel.template,
        )


MODULE_CLASSES.append(RoadGeneratorInputCurvePanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorProfilePanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_profile"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Road Profile"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.RoadNodegroup.RoadProfile,
        socket_names_drawn_first=["Profile Object", "Material"],
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorProfilePanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorProfilePanel.template,
            draw_modifier_header=True,
            max_occurrences=self.DRAW_ALL,
        )


MODULE_CLASSES.append(RoadGeneratorProfilePanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorRoadMarkingPanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_road_marking"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Road Marking"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.RoadNodegroup.Markings, socket_names_drawn_first=["Material"]
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorRoadMarkingPanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorRoadMarkingPanel.template,
            draw_modifier_header=True,
            max_occurrences=self.DRAW_ALL,
        )


MODULE_CLASSES.append(RoadGeneratorRoadMarkingPanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorDistributePanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_distribute"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Road Decoration"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.RoadNodegroup.Distribute, socket_names_drawn_first=["Collection"]
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorDistributePanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorDistributePanel.template,
            draw_modifier_header=True,
            max_occurrences=self.DRAW_ALL,
        )


MODULE_CLASSES.append(RoadGeneratorDistributePanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorCrosswalkPanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_crosswalk"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Crosswalks"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.RoadNodegroup.Crosswalk, socket_names_drawn_first=["Material"]
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorCrosswalkPanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorCrosswalkPanel.template,
            draw_modifier_header=True,
            max_occurrences=self.DRAW_ALL,
        )


MODULE_CLASSES.append(RoadGeneratorCrosswalkPanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorScatterPanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_scatter"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Scatter"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.RoadNodegroup.Scatter,
        socket_names_drawn_first=["Instance Collection", "Proximity Objects"],
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorScatterPanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            RoadGeneratorScatterPanel.template,
            draw_modifier_header=True,
            max_occurrences=self.DRAW_ALL,
        )


MODULE_CLASSES.append(RoadGeneratorScatterPanel)


@polib.log_helpers_bpy.logged_panel
class RoadGeneratorCleanupPanel(RoadGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_traffiq_road_generator_cleanup"
    bl_parent_id = RoadGeneratorPanel.bl_idname
    bl_label = "Cleanup"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(asset_helpers.RoadNodegroup.Cleanup)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (
            obj is not None
            and len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, RoadGeneratorCleanupPanel.template.name_prefix
                )
            )
            > 0
        )

    def draw(self, context: bpy.types.Context):
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout, context, RoadGeneratorCleanupPanel.template
        )


MODULE_CLASSES.append(RoadGeneratorCleanupPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
