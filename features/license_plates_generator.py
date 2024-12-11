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
from . import feature_utils
from . import asset_pack_panels
from .. import asset_helpers
from .. import polib
from .. import utils

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Type] = []


FRONT_PLATE_PARENT_NAME_SUFFIX = "_License-Plate_F"
BACK_PLATE_PARENT_NAME_SUFFIX = "_License-Plate_B"


def get_license_plate_modifier(obj: bpy.types.Object) -> typing.Optional[bpy.types.NodesModifier]:
    mods = polib.geonodes_mod_utils_bpy.get_geometry_nodes_modifiers_by_node_group(
        obj,
        asset_helpers.TQ_LICENSE_PLATE_NODE_GROUP_NAME_PREFIX,
    )
    if len(mods) == 0:
        return None
    elif len(mods) == 1:
        return mods[0]
    else:
        logger.warning(f"Multiple license plate modifiers found on object '{obj.name}'!")
        return mods[0]


@feature_utils.register_feature
class LicensePlatesGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "license_plates_generator"
    node_group_name = asset_helpers.TQ_LICENSE_PLATE_NODE_GROUP_NAME_PREFIX
    exact_match = False


@polib.log_helpers_bpy.logged_panel
class LicensePlatesGeneratorPanel(
    LicensePlatesGeneratorPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_license_plates_generator"
    bl_parent_id = asset_pack_panels.TraffiqPanel.bl_idname
    bl_label = "License Plates"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='EVENT_L')

    def draw(self, context: bpy.types.Context):
        layout: bpy.types.UILayout = self.layout
        self.conditionally_draw_warning_no_adjustable_active_object(
            context,
            layout,
            include_children=True,
            warning_text=f"Active asset does not support {self.get_feature_name_readable()} feature or is not editable!",
        )


MODULE_CLASSES.append(LicensePlatesGeneratorPanel)


class LicensePlatesAdjustmentsPanelMixin(
    LicensePlatesGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
):
    bl_parent_id = LicensePlatesGeneratorPanel.bl_idname
    bl_options = {'DEFAULT_CLOSED'}

    # Differentiate front, back and generic panels
    filter_: typing.Callable[[bpy.types.Object], bool] = lambda obj: True

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.TQ_LICENSE_PLATE_NODE_GROUP_NAME_PREFIX, exact_match=False
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if context.active_object is None:
            return False
        possible_assets = filter(
            cls.filter_,
            polib.asset_pack_bpy.get_entire_object_hierarchy(context.active_object),
        )
        return (
            len(list(LicensePlatesGeneratorPanelMixin.filter_adjustable_assets(possible_assets)))
            > 0
        )

    def draw(self, context: bpy.types.Context):
        if context.active_object is None:
            return
        for obj in polib.asset_pack_bpy.get_entire_object_hierarchy(context.active_object):
            if self.__class__.filter_(
                obj
            ) and LicensePlatesGeneratorPanelMixin.filter_adjustable_assets([obj]):
                break
        else:
            return
        with context.temp_override(active_object=obj):
            self.draw_active_object_modifiers_node_group_inputs_template(
                self.layout,
                context,
                self.__class__.template,
            )


class FrontPlatePanel(
    LicensePlatesAdjustmentsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_license_plates_generator_front"
    bl_label = "Front Plate"

    filter_ = lambda obj: obj.parent is not None and polib.utils_bpy.remove_object_duplicate_suffix(
        obj.parent.name
    ).endswith(FRONT_PLATE_PARENT_NAME_SUFFIX)

    def draw(self, context: bpy.types.Context) -> None:
        if context.active_object is None:
            return

        decomposed_car = polib.asset_pack_bpy.decompose_traffiq_vehicle(context.active_object)
        if decomposed_car is None:
            return

        front_plate = decomposed_car.front_plate
        back_plate = decomposed_car.back_plate
        assert front_plate is not None
        if back_plate is not None:
            op = self.layout.operator(
                utils.copy_nodes_mod_values.CopyGeonodesModifierValues.bl_idname,
                text="Copy To Back",
                icon='PASTEDOWN',
            )
            op.src_name = front_plate.name
            op.dst_name = back_plate.name
            # The license plates modifiers are always at index 0. This operator won't be drawn
            # in the UI if there is not back plate and front plate.
            op.src_mod_idx = 0
            op.dst_mod_idx = 0

        self.layout.separator()
        super().draw(context)


MODULE_CLASSES.append(FrontPlatePanel)


class BackPlatePanel(
    LicensePlatesAdjustmentsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_license_plates_generator_back"
    bl_label = "Back Plate"

    filter_ = lambda obj: obj.parent is not None and polib.utils_bpy.remove_object_duplicate_suffix(
        obj.parent.name
    ).endswith(BACK_PLATE_PARENT_NAME_SUFFIX)

    def draw(self, context: bpy.types.Context) -> None:
        if context.active_object is None:
            return

        decomposed_car = polib.asset_pack_bpy.decompose_traffiq_vehicle(context.active_object)
        if decomposed_car is None:
            return

        front_plate = decomposed_car.front_plate
        back_plate = decomposed_car.back_plate
        assert back_plate is not None
        if front_plate is not None:
            op = self.layout.operator(
                utils.copy_nodes_mod_values.CopyGeonodesModifierValues.bl_idname,
                text="Copy To Front",
                icon='PASTEDOWN',
            )
            op.src_name = back_plate.name
            op.dst_name = front_plate.name
            # The license plates modifiers are always at index 0. This operator won't be drawn
            # in the UI if there is not back plate and front plate.
            op.src_mod_idx = 0
            op.dst_mod_idx = 0

        self.layout.separator()
        super().draw(context)


MODULE_CLASSES.append(BackPlatePanel)


class GenericPlatePanel(
    LicensePlatesAdjustmentsPanelMixin,
    bpy.types.Panel,
):
    bl_idname = "VIEW_3D_PT_engon_license_plates_generator_generic"
    bl_label = "Generic Plate"

    filter_ = lambda obj: obj.parent is None or not (
        polib.utils_bpy.remove_object_duplicate_suffix(obj.parent.name).endswith(
            FRONT_PLATE_PARENT_NAME_SUFFIX
        )
        or polib.utils_bpy.remove_object_duplicate_suffix(obj.parent.name).endswith(
            BACK_PLATE_PARENT_NAME_SUFFIX
        )
    )


MODULE_CLASSES.append(GenericPlatePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
