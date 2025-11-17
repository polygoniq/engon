#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import abc
import bpy
import dataclasses
import typing
from . import asset_data
from . import file_provider

try:
    import hatchery
except ImportError:
    from blender_addons import hatchery


@dataclasses.dataclass(frozen=True)
class BlenderAssetData(asset_data.AssetData, abc.ABC):
    primary_blend_file: file_provider.FileID = ""
    dependency_files: set[file_provider.FileID] = dataclasses.field(default_factory=set)

    @abc.abstractmethod
    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.SpawnedData:
        pass


@dataclasses.dataclass(frozen=True)
class BlenderModelAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_model
    lod_level: int = 0

    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.ModelSpawnOptions
    ) -> hatchery.spawn.ModelSpawnedData:
        return hatchery.spawn.spawn_model(path, context, options)


@dataclasses.dataclass(frozen=True)
class BlenderMaterialAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_material

    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.MaterialSpawnOptions
    ) -> hatchery.spawn.MaterialSpawnedData:
        return hatchery.spawn.spawn_material(path, context, options)


@dataclasses.dataclass(frozen=True)
class BlenderParticleSystemAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_particle_system

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.ParticleSystemSpawnOptions,
    ) -> hatchery.spawn.ParticlesSpawnedData:
        return hatchery.spawn.spawn_particles(path, context, options)


@dataclasses.dataclass(frozen=True)
class BlenderSceneAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_scene

    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.SceneSpawnOptions
    ) -> hatchery.spawn.SceneSpawnedData:
        return hatchery.spawn.spawn_scene(path, context, options)


@dataclasses.dataclass(frozen=True)
class BlenderWorldAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_world

    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.WorldSpawnedData:
        return hatchery.spawn.spawn_world(path, context, options)


@dataclasses.dataclass(frozen=True)
class BlenderGeometryNodesAssetData(BlenderAssetData):
    type_ = asset_data.AssetDataType.blender_geometry_nodes

    def spawn(
        self, path: str, context: bpy.types.Context, options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.GeometryNodesSpawnedData:
        return hatchery.spawn.spawn_geometry_nodes(path, context, options)
