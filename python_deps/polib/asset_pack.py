#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import os
import re

# Maps asset pack names to blender Collection color_tags
ASSET_PACK_COLLECTION_COLOR_MAP = {
    "botaniq": 'COLOR_04',  # green
    "traffiq": 'COLOR_02',  # orange
    "materialiq": 'COLOR_01',  # red
    "aquatiq": 'COLOR_05',  # blue
    "interniq": 'COLOR_03',  # yellow
    "engon_particle_systems": 'COLOR_04',  # green
    "engon_geometry_nodes": 'COLOR_04',  # green
}


PARTICLE_SYSTEM_TOKEN = "pps"


BOTANIQ_SEASONS = ["spring", "summer", "autumn", "winter"]


# order matters, assets often have multiple seasons, color is set according to the first
# matched season
BOTANIQ_SEASONS_WITH_COLOR_CHANNEL = (
    ("summer", 1.0),
    ("spring", 0.75),
    ("winter", 0.5),
    ("autumn", 0.25),
)

BOTANIQ_ANIMATED_CATEGORIES = {
    "coniferous",
    "deciduous",
    "shrubs",
    "flowers",
    "grass",
    "ivy",
    "plants",
    "sapling",
    "tropical",
    "vine",
    "weed",
}


def is_pps_name(name: str) -> bool:
    split = name.split("_")
    if len(split) < 3:
        return False

    return split[1] == PARTICLE_SYSTEM_TOKEN


def is_library_blend(path: str) -> bool:
    basename = os.path.basename(path)
    # lowercase letters and numbers for prefix, followed by _Library_
    # e.g. "mq_Library_NodeGroups.blend, am154_Library_Materials.blend"
    return re.match(r"^[a-z0-9]+_Library_.+\.blend$", basename) is not None
