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

# This file contains all the code related to materialiq main panel user interface. There is the
# main MaterialiqPanel which contains the most frequently used features and then there are subpanels
# which extend the amount of displayed information. Those subpanels are displayed based on UI mode.
# Some subpanels like 'ToolsPanel' or 'DisplacementPanel' are displayed in both modes.

# There are two modes how the user interface is displayed. There is 'default (simple)' and
# 'advanced' mode, which is toggled by 'advance_ui' property in PanelProperties. 'Default' mode
# consists of displaying only the most necessary amount of stuffs for users that don't need to
# tweak all the details. There is only one additional subpanel for the 'default' mode -
# - 'DefaultMaterialViewPanel'.
# For the 'advanced' mode there are multiple subpanels and hierarchies constructed where a lot of
# different properties and operators are displayed, so there is a quick access to everything.

import bpy
import typing
import itertools
from .. import polib
from .. import hatchery
from .. import asset_registry
from . import displacement
from . import misc_ops
from . import textures
from .. import preferences
from .. import asset_helpers
from .. import __package__ as base_package


MODULE_CLASSES: typing.List[typing.Any] = []


# Thresholds to convert float value of mapping to enum values
MAPPING_INPUT_THRESHOLDS = {'UV': (0, 1 / 3), 'OBJECT': (1 / 3, 2 / 3), 'WORLD': (2 / 3, 1)}


class MaterialiqPanelMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "polygoniq"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("materialiq")) > 0


class MaterialiqMaterialMixin(MaterialiqPanelMixin):
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is not None:
            return asset_helpers.is_materialiq_material(mat)

        return False


class MaterialiqAdvancedUIPanelMixin(MaterialiqMaterialMixin):
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return super().poll(context) and show_advanced_ui(context)


class MaterialiqWorldsPanelMixin:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "world"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(asset_registry.instance.get_packs_by_engon_feature("materialiq")) > 0


@polib.log_helpers_bpy.logged_panel
class MaterialiqPanel(MaterialiqPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq"
    bl_label = "materialiq"
    bl_category = "polygoniq"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.template_icon(
            icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("materialiq")
        )

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        master_row = self.layout.row(align=True)
        master_row.row().prop(get_panel_props(context), "advanced_ui", text="", icon='MENU_PANEL')
        polib.ui_bpy.draw_doc_button(
            master_row.row(),
            base_package,
            rel_url="panels/materialiq/panel_overview",
        )

    def draw_material_list(self, context: bpy.types.Context) -> None:
        # We use similar code to draw material slots as blender does
        # 'scripts\startup\bl_ui\properties_material.py'
        layout = self.layout
        obj = context.active_object
        if obj is None:
            return

        if not hatchery.utils.can_have_materials_assigned(obj):
            return

        is_sortable = len(obj.material_slots) > 1
        # Draw 5 rows if sort buttons will be shown, otherwise draw only 3
        rows = 5 if is_sortable else 3
        if obj.active_material_index >= len(obj.material_slots):
            slot = None
        else:
            slot = obj.material_slots[obj.active_material_index]

        row = layout.row()
        row.template_list(
            "MATERIAL_UL_matslots",
            "",
            obj,
            "material_slots",
            obj,
            "active_material_index",
            rows=rows,
        )

        col = row.column(align=True)
        col.operator("object.material_slot_add", icon='ADD', text="")
        col.operator("object.material_slot_remove", icon='REMOVE', text="")

        col.separator()
        col.menu("MATERIAL_MT_context_menu", icon='DOWNARROW_HLT', text="")

        if is_sortable:
            col.separator()

            col.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'UP'
            col.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'DOWN'

        row = layout.row()
        row.template_ID(obj, "active_material", new="material.new")

        if slot:
            icon_link = 'MESH_DATA' if slot.link == 'DATA' else 'OBJECT_DATA'
            row.prop(slot, "link", icon=icon_link, icon_only=True)

        if obj.mode == 'EDIT':
            row = layout.row(align=True)
            row.operator("object.material_slot_assign", text="Assign")
            row.operator("object.material_slot_select", text="Select")
            row.operator("object.material_slot_deselect", text="Deselect")

    def draw(self, context: bpy.types.Context) -> None:
        prefs = preferences.prefs_utils.get_preferences(context).browser_preferences
        row = self.layout.row(align=True)
        row.label(text="Default Texture Size:")
        row = row.row()
        row.alignment = 'LEFT'
        row.scale_x = 0.9
        row.prop(prefs.spawn_options, "texture_size", text="")
        self.draw_material_list(context)


MODULE_CLASSES.append(MaterialiqPanel)


@polib.log_helpers_bpy.logged_panel
class ToolsPanel(MaterialiqPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_tools"
    bl_parent_id = MaterialiqPanel.bl_idname
    bl_label = "Tools"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='TOOL_SETTINGS')

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column()
        col.operator(misc_ops.ReplaceMaterial.bl_idname, icon='PIVOT_ACTIVE')

        box = self.layout.box()
        box.label(text="Change Texture Size:")
        row = box.row()
        row.operator_menu_enum(
            textures.ChangeTextureSizeGlobal.bl_idname,
            property="max_size",
            text="All Materials",
            icon='LIGHTPROBE_GRID' if bpy.app.version < (4, 1, 0) else 'LIGHTPROBE_VOLUME',
        )

        row = box.column()
        row.enabled = textures.ChangeTextureSizeActiveMaterial.poll(context)
        row.operator_menu_enum(
            textures.ChangeTextureSizeActiveMaterial.bl_idname,
            property="max_size",
            text="Active Material",
            icon='MATERIAL',
        )


MODULE_CLASSES.append(ToolsPanel)


@polib.log_helpers_bpy.logged_panel
class MaterialPropertiesPanel(MaterialiqMaterialMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_default_view"
    bl_parent_id = MaterialiqPanel.bl_idname
    bl_label = "Material Properties"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='OPTIONS')

    def draw(self, context: bpy.types.Context) -> None:
        pass


MODULE_CLASSES.append(MaterialPropertiesPanel)


@polib.log_helpers_bpy.logged_panel
class MappingPanel(MaterialiqMaterialMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_mapping"
    bl_parent_id = MaterialPropertiesPanel.bl_idname
    bl_label = "Mapping"
    bl_options = {'DEFAULT_CLOSED'}

    basic_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Mapping",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Rot X/Y/Z",
            "Mapping      Scale      XYZ",
            "Bombing      Strength",
            "Bombing      Scale",
            "Bombing      Rotation",
        ),
    )

    advanced_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Mapping",
        filter_=lambda x: not polib.node_utils_bpy.filter_node_socket_name(x, "bombing", "UV 0"),
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='VIEW_PERSPECTIVE')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        layout.row(align=True).prop(get_panel_props(context), "mapping", expand=True)
        col = layout.column(align=True)

        if MaterialiqAdvancedUIPanelMixin.poll(context):
            MappingPanel.advanced_template.draw_from_material(mat, col)
            return

        MappingPanel.basic_template.draw_from_material(mat, col)


MODULE_CLASSES.append(MappingPanel)


@polib.log_helpers_bpy.logged_panel
class TextureBombingPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_tex_bomb"
    bl_parent_id = MappingPanel.bl_idname
    bl_label = "Texture Bombing"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Mapping",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "bombing",
        ),
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='STICKY_UVS_LOC')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        TextureBombingPanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(TextureBombingPanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsPanel(MaterialiqMaterialMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments"
    bl_parent_id = MaterialPropertiesPanel.bl_idname
    bl_label = "Adjustments"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Adjust",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            "Base   Color",
            "Diffuse + Roughness + Normal",
            "Diffuse   Brightness",
            "Diffuse   Contrast",
            "Diffuse   Saturation",
            "Specular Brightness",
            "Specular Contrast",
            "Roughness Value",
            "Roughness Brightness",
            "Roughness Contrast",
            "Normal Map Strength",
        ),
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if not super().poll(context):
            return False

        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return False

        nodegroups = itertools.chain(
            polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Adjust"),
            polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Transparent"),
        )
        return len(set(nodegroups)) > 0

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='SHADERFX')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        if MaterialiqAdvancedUIPanelMixin.poll(context):
            return
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return
        col = layout.column(align=True)
        AdjustmentsPanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(AdjustmentsPanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsDiffusePanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments_diffuse"
    bl_parent_id = AdjustmentsPanel.bl_idname
    bl_label = "Diffuse"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Adjust",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(
            x,
            # Yes it is named 'Base   Color'. For anyone editing this in the future - breathe in
            # breathe out.
            "Base   Color",
            "diffuse",
            "brightness",
            "contrast",
            "hue",
        ),
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='IMAGE_PLANE')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        AdjustmentsDiffusePanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(AdjustmentsDiffusePanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsSpecularPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments_specular"
    bl_parent_id = AdjustmentsPanel.bl_idname
    bl_label = "Specular"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Adjust",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "specular"),
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='INDIRECT_ONLY_ON')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        AdjustmentsSpecularPanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(AdjustmentsSpecularPanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsRoughnessPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments_roughness"
    bl_parent_id = AdjustmentsPanel.bl_idname
    bl_label = "Roughness"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Adjust",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "roughness"),
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_NOISE')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        AdjustmentsRoughnessPanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(AdjustmentsRoughnessPanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsNormalPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments_normal"
    bl_parent_id = AdjustmentsPanel.bl_idname
    bl_label = "Normal"
    bl_options = {'DEFAULT_CLOSED'}

    adjustment_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Adjust",
        filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "normal"),
    )

    # There should be only one Bevel node on top level of materialiq material
    bevel_template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "Bevel", filter_=lambda x: polib.node_utils_bpy.filter_node_socket_name(x, "radius")
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='ORIENTATION_NORMAL')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        AdjustmentsNormalPanel.adjustment_template.draw_from_material(mat, col)
        AdjustmentsNormalPanel.bevel_template.draw_from_material(mat, col)


MODULE_CLASSES.append(AdjustmentsNormalPanel)


@polib.log_helpers_bpy.logged_panel
class TransparentAdjustmentsPanel(MaterialiqMaterialMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_transparent_adjustments"
    bl_parent_id = AdjustmentsPanel.bl_idname
    bl_label = "Transparency"
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        "mq_Transparent",
    )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='NODE_TEXTURE')

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if not super().poll(context):
            return False

        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return False

        nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Transparent")
        return len(nodegroups) > 0

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        col = layout.column(align=True)
        TransparentAdjustmentsPanel.template.draw_from_material(mat, col)


MODULE_CLASSES.append(TransparentAdjustmentsPanel)


@polib.log_helpers_bpy.logged_panel
class TexturesPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_textures"
    bl_parent_id = MaterialPropertiesPanel.bl_idname
    bl_label = "Textures"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='IMAGE_DATA')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = get_panel_props(context)
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        # We need to search for mq_Texture by node name here, node_trees are named according
        # to materials as they need to be unique per material.
        nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(
            mat.node_tree, "mq_Textures", use_node_tree_name=False
        )
        if len(nodegroups) == 0:
            layout.label(text="No textures nodegroup found")
            return

        first_ng = nodegroups.pop()

        layout.operator(textures.SyncTextureNodes.bl_idname, icon='ANIM').node_tree_name = (
            first_ng.node_tree.name
        )

        channel_nodes_map = polib.node_utils_bpy.get_channel_nodes_map(first_ng.node_tree)
        for i, filepath in enumerate(sorted(channel_nodes_map)):
            nodes = channel_nodes_map.get(filepath, [])
            if len(nodes) == 0:
                continue

            first_node = nodes[0]
            box = layout.box()
            row = box.row()
            row.enabled = False
            row.label(text=f"{first_node.name} ({', '.join(n.name for n in nodes[1:])})")

            # We have only len(props.show_texture_nodes) toggle button available
            if i >= len(props.show_texture_nodes):
                first_node.draw_buttons(context, box)
                return

            row = box.row(align=True)
            row.prop(
                props,
                "show_texture_nodes",
                index=i,
                emboss=False,
                text="",
                icon='TRIA_DOWN' if props.show_texture_nodes[i] else 'TRIA_RIGHT',
            )

            # Draw whole node if this texture node should be shown, otherwise draw only image
            # heading.
            if props.show_texture_nodes[i]:
                first_node.draw_buttons(context, box)
            else:
                # To achieve similar look we draw using 'template_ID' if there is image
                # and 'template_image' (which draws New and Open buttons) when there is no image
                if first_node.image is not None:
                    row.template_ID(first_node, "image")
                else:
                    row.template_image(first_node, "image", first_node.image_user)


MODULE_CLASSES.append(TexturesPanel)


@polib.log_helpers_bpy.logged_panel
class DisplacementPanel(MaterialiqMaterialMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_displace"
    bl_parent_id = MaterialPropertiesPanel.bl_idname
    bl_label = "Displacement"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MOD_DISPLACE')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator(
            displacement.AddDisplacement.bl_idname,
            text=displacement.AddDisplacement.bl_label,
            icon='ADD',
        )
        col.operator(
            displacement.RemoveDisplacement.bl_idname,
            text=displacement.RemoveDisplacement.bl_label,
            icon='REMOVE',
        )


MODULE_CLASSES.append(DisplacementPanel)


@polib.log_helpers_bpy.logged_panel
class AdaptiveSubdivPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adaptive_subdiv"
    bl_parent_id = DisplacementPanel.bl_idname
    bl_label = "Scene Subdivision"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return displacement.is_scene_setup_adaptive_subdiv(context)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.template_icon(
            icon_value=polib.ui_bpy.icon_manager.get_icon_id("icon_adaptive_subdivision")
        )

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column(align=True)
        col.prop(context.scene.cycles, "dicing_rate", text="Render Dicing Rate", slider=True)
        col.prop(
            context.scene.cycles, "preview_dicing_rate", text="Viewport Dicing Rate", slider=True
        )


MODULE_CLASSES.append(AdaptiveSubdivPanel)


@polib.log_helpers_bpy.logged_panel
class ModifiersDisplacementPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_modifiers_displacement"
    bl_parent_id = DisplacementPanel.bl_idname
    bl_label = "Modifiers"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MODIFIER_DATA')

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        if context.active_object is None:
            return

        displacement_related_modifiers = [
            x for x in context.active_object.modifiers if x.name in displacement.DRAW_MODIFIER_PROPS
        ]

        if len(displacement_related_modifiers) == 0:
            col.label(text="No displacement related modifiers found")
            return

        for mod in displacement_related_modifiers:
            col.label(text=mod.name)
            for prop in displacement.DRAW_MODIFIER_PROPS[mod.name]:
                col.prop(mod, prop)
        # Dicing Rate property is located in modifier UI but belongs to object so we draw it separately
        # and don't store it in DRAW_MODIFIER_PROPS
        if mod.name == "mq_Subdivision_Adaptive" and displacement.is_scene_setup_adaptive_subdiv(
            context
        ):
            obj = context.active_object
            col.prop(obj.cycles, "dicing_rate")

        layout = self.layout.column(align=True)


MODULE_CLASSES.append(ModifiersDisplacementPanel)


@polib.log_helpers_bpy.logged_panel
class AdjustmentsDisplacementPanel(MaterialiqAdvancedUIPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_adjustments_displacement"
    bl_parent_id = DisplacementPanel.bl_idname
    bl_label = "Shader Displacement"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return displacement.is_scene_setup_adaptive_subdiv(context)

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='NODE_MATERIAL')

    def draw(self, context: bpy.types.Context) -> None:
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        layout = self.layout.column(align=True)

        material_output_nodes = list(
            polib.node_utils_bpy.find_nodes_by_bl_idname(
                mat.node_tree.nodes, "ShaderNodeOutputMaterial"
            )
        )
        material_output_node = material_output_nodes[0]

        displacement_link = polib.node_utils_bpy.find_link_connected_to(
            mat.node_tree.links, material_output_node, "Displacement"
        )

        nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Displacement")
        if len(nodegroups) == 0:
            layout.label(text="No displacement nodegroup found")
            return

        displacement_nodegroup = nodegroups.pop()

        if displacement_link is None:
            layout.label(text="No links to displacement input found")
            return

        if displacement_link.from_node != displacement_nodegroup:
            layout.label(
                text="mq_Displacement nodegroup not connected directly to Displacement Output"
            )
            return

        polib.node_utils_bpy.draw_node_inputs_filtered(layout, displacement_nodegroup)


MODULE_CLASSES.append(AdjustmentsDisplacementPanel)


@polib.log_helpers_bpy.logged_panel
class EditNodeTreePanel(MaterialiqPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_edit_material"
    bl_description = "Shows values of nodes connected to the material output in the N panel"
    bl_parent_id = MaterialiqPanel.bl_idname
    bl_label = "Edit Material"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='MODIFIER')

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return False

        return not asset_helpers.is_materialiq_material(mat)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        row = layout.row()
        row.alignment = 'RIGHT'
        row.label(text="Display Depth")
        row = row.row()
        row.scale_x = 0.5
        row.prop(get_panel_props(context), "node_tree_display_depth", text="")

        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        polib.node_utils_bpy.draw_node_tree(
            layout, mat.node_tree, get_panel_props(context).node_tree_display_depth
        )


MODULE_CLASSES.append(EditNodeTreePanel)


@polib.log_helpers_bpy.logged_panel
class DisplaySettingsPanel(MaterialiqPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_materialiq_material_settings"
    bl_parent_id = MaterialiqPanel.bl_idname
    bl_label = "Material Settings"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            super().poll(context)
            and polib.material_utils_bpy.safe_get_active_material(context.active_object) is not None
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='SETTINGS')

    def draw_eevee_material_settings(
        self, mat: bpy.types.Material, layout: bpy.types.UILayout, advanced_ui: bool
    ) -> None:
        row = layout.row()
        row.enabled = False
        row.label(text="Eevee / Material Preview")
        layout.prop(mat, "blend_method")
        layout.prop(mat, "shadow_method")
        layout.prop(mat, "alpha_threshold")
        layout.prop(mat, "use_screen_refraction")
        if not advanced_ui:
            return
        layout.prop(mat, "refraction_depth")
        layout.prop(mat, "use_sss_translucency")
        layout.prop(mat, "use_backface_culling")

    def draw_cycles_material_settings(
        self, mat: bpy.types.Material, layout: bpy.types.UILayout, advanced_ui: bool
    ) -> None:
        if not advanced_ui:
            row = layout.row()
            row.enabled = False
            row.label(text="Cycles")
            if bpy.app.version < (4, 1, 0):
                layout.prop(mat.cycles, "displacement_method", text="Displacement")
            else:
                layout.prop(mat, "displacement_method", text="Displacement")
            return

        row = layout.row()
        row.enabled = False
        row.label(text="Cycles Surface")
        layout.prop(mat.cycles, "use_transparent_shadow")
        if bpy.app.version < (4, 1, 0):
            layout.prop(mat.cycles, "displacement_method", text="Displacement")
        else:
            layout.prop(mat, "displacement_method", text="Displacement")
        layout.separator()
        row = layout.row()
        row.enabled = False
        row.label(text="Cycles Volume")
        layout.prop(mat.cycles, "volume_sampling", text="Sampling")
        layout.prop(mat.cycles, "volume_interpolation", text="Interpolation")
        layout.prop(mat.cycles, "homogeneous_volume", text="Homogeneous")
        layout.prop(mat.cycles, "volume_step_rate")

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        mat = polib.material_utils_bpy.safe_get_active_material(context.active_object)
        if mat is None:
            return

        advanced_ui = show_advanced_ui(context)

        row = layout.row()
        row.enabled = False
        row.label(text="Viewport Display")

        col = layout.column(align=True)
        col.prop(mat, "diffuse_color", text="Color")
        if advanced_ui:
            col.prop(mat, "metallic")
            col.prop(mat, "roughness")
            col.prop(mat, "pass_index")
        col.separator()
        col.label(text="Engine Specific Settings")
        if context.engine == 'CYCLES':
            self.draw_cycles_material_settings(mat, col, advanced_ui)

        # Always draw eevee settings, as they might be useful for material preview
        self.draw_eevee_material_settings(mat, col, advanced_ui)


MODULE_CLASSES.append(DisplaySettingsPanel)


@polib.log_helpers_bpy.logged_panel
class MaterialiqWorldPanel(MaterialiqWorldsPanelMixin, bpy.types.Panel):
    bl_idname = "WORLD_PT_materialiq"
    bl_label = "materialiq"
    bl_order = 10

    def draw_header(self, context: bpy.types.Context):
        self.layout.template_icon(
            icon_value=polib.ui_bpy.icon_manager.get_engon_feature_icon_id("materialiq")
        )

    def draw(self, context: bpy.types.Context) -> None:
        world = context.scene.world
        if world is None:
            return

        if world.node_tree is None:
            return

        col = self.layout.column(align=True)
        mapping_node = world.node_tree.nodes.get("Mapping", None)
        if mapping_node is not None:
            col.template_node_view(world.node_tree, mapping_node, mapping_node.inputs["Rotation"])

        background_node = world.node_tree.nodes.get("Background", None)
        if background_node is not None:
            col.template_node_view(
                world.node_tree, background_node, background_node.inputs["Strength"]
            )


MODULE_CLASSES.append(MaterialiqWorldPanel)


class PanelProperties(bpy.types.PropertyGroup):
    node_tree_display_depth: bpy.props.IntProperty(
        name="Display Depth",
        description="Number of displayed levels of connections from the 'Material Output' node",
        default=5,
        min=1,
    )

    show_texture_nodes: bpy.props.BoolVectorProperty(
        name="Show Texture Nodes",
        description="Toggle detailed displayed of texture node",
        size=3,  # We use at max 3 (Diffuse, Height, Normal)
    )

    advanced_ui: bpy.props.BoolProperty(
        name="Advanced UI",
        description="Toggle to display more advanced UI with more properties",
        default=False,
    )

    mapping: bpy.props.EnumProperty(
        name="Mapping",
        items=[
            ('UV', "UV", "Use UV Map for texture mapping"),
            ('OBJECT', "Object", "Use object coordinates for texture mapping"),
            ('WORLD', "World", "Use world coordinates for texture mapping"),
        ],
        description="Switch mapping of active material",
        get=lambda self: self.mapping_get(),
        set=lambda self, value: self.mapping_set(value),
    )

    def mapping_get(self) -> int:
        # We return 0 in case of no material or node found, as panel where this property is shown is
        # displayed only if there is active material and nodegroup is found.
        mat = polib.material_utils_bpy.safe_get_active_material(bpy.context.active_object)
        if mat is None:
            return 0
        if mat.node_tree is None:
            return 0

        nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Mapping")
        if len(nodegroups) == 0:
            return 0

        ng = nodegroups.pop()
        current_value = ng.inputs[0].default_value
        for i, mapping in enumerate(MAPPING_INPUT_THRESHOLDS):
            low, high = MAPPING_INPUT_THRESHOLDS[mapping]
            if current_value > low and current_value <= high:
                return i

        return 0

    def mapping_set(self, value: int) -> None:
        mat = polib.material_utils_bpy.safe_get_active_material(bpy.context.active_object)
        if mat is None:
            return
        if mat.node_tree is None:
            return

        nodegroups = polib.node_utils_bpy.find_nodegroups_by_name(mat.node_tree, "mq_Mapping")
        if len(nodegroups) == 0:
            return

        ng = nodegroups.pop()
        # We set the value based on the position in the enum items (value) and multiply by the
        # number of thresholds that there are - 1. This maps the values from 0, 1, 2 to 0, 0.5, 1.0
        ng.inputs[0].default_value = value * 1 / (len(MAPPING_INPUT_THRESHOLDS) - 1)


MODULE_CLASSES.append(PanelProperties)


def get_panel_props(context: bpy.types.Context) -> PanelProperties:
    return context.window_manager.mq_panel_props


def show_advanced_ui(context: bpy.types.Context) -> bool:
    return get_panel_props(context).advanced_ui


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.mq_panel_props = bpy.props.PointerProperty(type=PanelProperties)


def unregister():
    del bpy.types.WindowManager.mq_panel_props

    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
