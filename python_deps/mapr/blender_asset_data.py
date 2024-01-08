#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import abc
import bpy
from . import asset_data
from . import file_provider
try:
    import hatchery
except ImportError:
    from blender_addons import hatchery


class BlenderAssetData(asset_data.AssetData, abc.ABC):
    def __init__(self):
        super().__init__()
        self.primary_blend_file: file_provider.FileID = ""
        self.dependency_files: typing.Set[file_provider.FileID] = set()

    @abc.abstractmethod
    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.SpawnedData:
        pass


class BlenderModelAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_model
        self.lod_level: int = 0

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.ModelSpawnOptions
    ) -> hatchery.spawn.ModelSpawnedData:
        return hatchery.spawn.spawn_model(path, context, options)


class BlenderMaterialAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_material

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.MaterialSpawnOptions
    ) -> hatchery.spawn.MaterialSpawnedData:
        return hatchery.spawn.spawn_material(path, context, options)


class BlenderParticleSystemAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_particle_system

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.ParticleSystemSpawnOptions
    ) -> hatchery.spawn.ParticlesSpawnedData:
        return hatchery.spawn.spawn_particles(path, context, options)


class BlenderSceneAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_scene

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.SceneSpawnedData:
        return hatchery.spawn.spawn_scene(path, context, options)


class BlenderWorldAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_world

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.WorldSpawnedData:
        return hatchery.spawn.spawn_world(path, context, options)


class BlenderGeometryNodesAssetData(BlenderAssetData):
    def __init__(self):
        super().__init__()
        self.type_ = asset_data.AssetDataType.blender_geometry_nodes

    def spawn(
        self,
        path: str,
        context: bpy.types.Context,
        options: hatchery.spawn.DatablockSpawnOptions
    ) -> hatchery.spawn.GeometryNodesSpawnedData:
        return hatchery.spawn.spawn_geometry_nodes(path, context, options)
