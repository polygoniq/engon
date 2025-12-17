#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
from . import custom_props_bpy


class RigDrivers:
    """Class used to generate back drivers for rig variables

    Unfortunately blender operator duplicates_make_real doesn't
    append animation data, where drivers are stored https://developer.blender.org/T81577

    Our version of rigacar generates the drivers in the source files, but they aren't
    available after duplicates_make_real is called in converted to editable, thus this class
    exists and is used to create those drivers dynamically based on bone names.
    """

    INFLUENCE_VAR_NAME = "influence"
    ROTATION_EULER_X_VAR_NAME = "rotationAngle"

    def __init__(self, obj: bpy.types.Object):
        assert "tq_Car_Rig" in obj.data
        self.target_obj = obj
        self.pose = obj.pose

    def create_all_drivers(self):
        for bone in self.pose.bones.values():
            if bone.name.startswith("MCH_WheelRotation"):
                _, _, suffix = bone.name.split("_", 2)
                data_path = f'["{custom_props_bpy.CustomPropertyNames.TQ_WHEEL_ROTATION}_{suffix}"]'
                self.__create_rotation_euler_x_driver(bone, data_path)
            elif bone.name == "MCH_SteeringRotation":
                self.__create_translation_x_driver(
                    bone, f'["{custom_props_bpy.CustomPropertyNames.TQ_STEERING}"]'
                )
            elif bone.name == "MCH_Axis":
                front_constraint = bone.constraints.get("Rotation from MCH_Axis_F", None)
                if front_constraint is not None:
                    self.__create_constraint_influence_driver(
                        front_constraint,
                        f'["{custom_props_bpy.CustomPropertyNames.TQ_SUSPENSION_ROLLING_FACTOR}"]',
                        1.0,
                    )
                rear_constraint = bone.constraints.get("Rotation from MCH_Axis_B", None)
                if rear_constraint is not None:
                    self.__create_constraint_influence_driver(
                        rear_constraint,
                        f'["{custom_props_bpy.CustomPropertyNames.TQ_SUSPENSION_ROLLING_FACTOR}"]',
                        0.5,
                    )

    def __create_constraint_influence_driver(
        self,
        constraint: bpy.types.CopyLocationConstraint,
        driver_data_path: str,
        base_influence: float = 1.0,
    ) -> None:
        fcurve = constraint.driver_add("influence")
        drv = fcurve.driver
        drv.type = 'AVERAGE'
        var = drv.variables.get(RigDrivers.INFLUENCE_VAR_NAME, None)
        if var is None:
            var = drv.variables.new()
            var.name = RigDrivers.INFLUENCE_VAR_NAME
            var.type = 'SINGLE_PROP'

        targ = var.targets[0]
        targ.id_type = 'OBJECT'
        targ.id = self.target_obj
        targ.data_path = driver_data_path

        if base_influence != 1.0:
            if bpy.app.version < (5, 0, 0):
                # See https://projects.blender.org/blender/blender/pulls/148875
                fmod = fcurve.modifiers[0]
            else:
                fmod = fcurve.modifiers.new(type='GENERATOR')
            assert isinstance(fmod, bpy.types.FModifierGenerator)
            fmod.mode = 'POLYNOMIAL'
            fmod.poly_order = 1
            fmod.coefficients = (0, base_influence)

    def __create_translation_x_driver(self, bone: bpy.types.PoseBone, driver_data_path: str):
        fcurve = bone.driver_add("location", 0)
        drv = fcurve.driver
        drv.type = 'AVERAGE'
        var = drv.variables.get(RigDrivers.ROTATION_EULER_X_VAR_NAME, None)
        if var is None:
            var = drv.variables.new()
            var.name = RigDrivers.ROTATION_EULER_X_VAR_NAME
            var.type = 'SINGLE_PROP'

        targ = var.targets[0]
        targ.id_type = 'OBJECT'
        targ.id = self.target_obj
        targ.data_path = driver_data_path

    def __create_rotation_euler_x_driver(self, bone: bpy.types.PoseBone, driver_data_path: str):
        fcurve = bone.driver_add("rotation_euler", 0)
        drv = fcurve.driver
        drv.type = 'AVERAGE'
        var = drv.variables.get(RigDrivers.ROTATION_EULER_X_VAR_NAME, None)
        if var is None:
            var = drv.variables.new()
            var.name = RigDrivers.ROTATION_EULER_X_VAR_NAME
            var.type = 'SINGLE_PROP'

        targ = var.targets[0]
        targ.id_type = 'OBJECT'
        targ.id = self.target_obj
        targ.data_path = driver_data_path


def is_object_rigged(obj: bpy.types.Object) -> bool:
    if obj is None:
        return False

    if obj.data is None:
        return False

    return (
        custom_props_bpy.CustomPropertyNames.TQ_CAR_RIG in obj.data
        and obj.data[custom_props_bpy.CustomPropertyNames.TQ_CAR_RIG] == 1
    )
