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
from . import feature_utils
from .. import polib
from .. import asset_helpers

from . import asset_pack_panels


MODULE_CLASSES = []


def get_emergency_lights_container_from_hierarchy_with_root(
    obj: bpy.types.Object,
) -> typing.Tuple[typing.Optional[bpy.types.Object], typing.Optional[bpy.types.Object]]:
    """Returns the first object in the hierarchy that contains emergency lights and the root of the hierarchy

    Returns None if no such object is found in the hierarchy of the given object.
    """

    def _contains_emergency_lights(obj: bpy.types.Object) -> bool:
        return (
            len(
                polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
                    obj, asset_helpers.TQ_EMERGENCY_LIGHTS_NODE_GROUP_NAME
                )
            )
            > 0
        )

    emergency_lights = list(
        polib.asset_pack_bpy.get_root_objects_with_matched_child(
            [obj], lambda obj, _: _contains_emergency_lights(obj)
        )
    )
    if len(emergency_lights) == 0:
        return None, None
    assert len(emergency_lights) == 1
    return emergency_lights[0]


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class EmergencyLightsPanel(
    bpy.types.Panel,
    feature_utils.EngonAssetFeatureControlPanelMixin,
    polib.geonodes_mod_utils_bpy.GeoNodesModifierInputsPanelMixin,
):
    bl_idname = "VIEW_3D_PT_engon_feature_emergency_lights"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_label = "Emergency Lights"
    feature_name = "emergency_lights"

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.TQ_EMERGENCY_LIGHTS_NODE_GROUP_NAME, filter_=lambda _: True
    )

    @classmethod
    def get_possible_assets(
        cls,
        context: bpy.types.Context,
    ) -> typing.Iterable[bpy.types.ID]:
        if context.active_object is not None:
            return [context.active_object]
        return []

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        lights: typing.Iterable[bpy.types.Object] = []
        for obj in possible_assets:
            _, emergency_lights = get_emergency_lights_container_from_hierarchy_with_root(obj)
            if emergency_lights is not None:
                lights.append(emergency_lights)

        return lights

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='LIGHT_SUN')

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        raise NotImplementedError()

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column()

        emergency_lights: typing.Optional[bpy.types.Object] = None
        if self.conditionally_draw_warning_no_adjustable_active_object(
            context,
            col,
            warning_text=f"Active asset does not support {self.get_feature_name_readable()} feature or is not editable!",
        ):
            return
        possible_asset_list = list(self.filter_adjustable_assets(self.get_possible_assets(context)))
        assert len(possible_asset_list) == 1
        obj = possible_asset_list[0]

        root_object, emergency_lights = get_emergency_lights_container_from_hierarchy_with_root(obj)
        # TODO: differentiate between linked asset and asset without emergency lights
        assert emergency_lights is not None
        assert root_object is not None

        modifiers = polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
            emergency_lights, asset_helpers.TQ_EMERGENCY_LIGHTS_NODE_GROUP_NAME
        )
        mod = modifiers[0]
        row = col.row()
        left_col = row.column()
        left_col.enabled = False
        left_col.label(text=root_object.name)
        right_col = row.column()
        row = right_col.row(align=True)
        row.alignment = 'RIGHT'
        self.draw_show_viewport_and_render(row, mod)
        self.draw_object_modifiers_node_group_inputs_template(
            emergency_lights, col, EmergencyLightsPanel.template
        )


MODULE_CLASSES.append(EmergencyLightsPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
