# copyright (c) 2018- polygoniq xyz s.r.o.
# Utilities for working with bpy particle systems

import bpy
import typing


def get_settings_instancing_objects(
    objects: typing.Iterable[bpy.types.Object],
) -> set[bpy.types.ParticleSettings]:
    """Returns particle settings whose instance collection directly contains any of 'objects'."""
    object_collections = {collection for obj in objects for collection in obj.users_collection}
    return {
        particle_settings
        for particle_settings in bpy.data.particles
        if particle_settings.instance_collection in object_collections
    }


def get_instance_weight_object_name(weight: bpy.types.ParticleDupliWeight) -> str:
    """Returns object name from 'weight.name', which stores "OBJECT_NAME: COUNT"."""
    return weight.name.split(":", 1)[0]


def refresh_instance_collection(particle_settings: bpy.types.ParticleSettings) -> None:
    """Re-assigns the instance collection, Blender rebuilds instance weights only on assignment."""
    particle_settings.instance_collection = particle_settings.instance_collection


def transfer_instance_weights(
    affected_particle_settings: typing.Iterable[bpy.types.ParticleSettings],
    replaced_object_names: dict[str, str],
) -> None:
    """Carries over instance weight counts from replaced objects to their replacements.

    'replaced_object_names' maps replaced object name to the name of its replacement.
    """
    for particle_settings in affected_particle_settings:
        counts = {
            replaced_object_names[obj_name]: weight.count
            for weight in particle_settings.instance_weights
            if (obj_name := get_instance_weight_object_name(weight)) in replaced_object_names
        }

        refresh_instance_collection(particle_settings)
        for weight in particle_settings.instance_weights:
            count = counts.get(get_instance_weight_object_name(weight), None)
            if count is not None:
                weight.count = count
