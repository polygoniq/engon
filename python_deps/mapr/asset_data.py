#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import abc
import dataclasses
import enum
import typing
import collections
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


AssetDataID = str


class AssetDataType(enum.Enum):
    unknown = "unknown"

    blender_model = "blender_model"
    blender_material = "blender_material"
    blender_particle_system = "blender_particle_system"
    blender_scene = "blender_scene"
    blender_world = "blender_world"
    blender_geometry_nodes = "blender_geometry_nodes"

    @property
    def search_matter(self) -> typing.DefaultDict[str, float]:
        """Returns a dictionary of keywords mapped to their search weight

        Removes "blender" prefix. Example results:
        "blender_material" -> {"material": 1.0},
        "blender_particle_system" -> {"particle": 1.0, "system": 1.0}
        """
        ret = collections.defaultdict(float)
        split = self.value.split("_")
        if len(split) == 1:
            ret[split[0]] = 1.0
            return ret

        # Types can contain values like "blender_model", "blender_material",
        # "blender_particle_system" we return only the tail of the split
        # ["model"], ["material"], ["particle", "system"]
        if split[0] == "blender":
            for token in split[1:]:
                ret[token] = max(1.0, ret[token])
            return ret

        for token in split:
            ret[token] = max(1.0, ret[token])
        return ret


@dataclasses.dataclass(frozen=True)
class AssetData(abc.ABC):
    id_: AssetDataID = ""
    type_: AssetDataType = AssetDataType.unknown
