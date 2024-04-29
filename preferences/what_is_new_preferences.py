# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
from .. import ui_utils
from . import prefs_utils


MODULE_CLASSES: typing.List[typing.Any] = []


class SeenAssetPackVersion(bpy.types.PropertyGroup):
    version: bpy.props.IntVectorProperty(
        size=3
    )


MODULE_CLASSES.append(SeenAssetPackVersion)


class WhatIsNewPreferences(bpy.types.PropertyGroup):
    display_what_is_new: bpy.props.BoolProperty(
        name="Display \"See What's New\" button",
        description="Show button in the engon browser to filter for newly added asset after updating an asset pack."
                    "These only displays if there is a newly updated asset pack that wasn't explored before",
        default=True
    )

    latest_seen_asset_packs: bpy.props.CollectionProperty(
        name="Latest Seen Asset Pack Versions",
        description="Dictionary with key of asset pack name (in the implicit name paramater) "
                    "and value of asset pack version",
        type=SeenAssetPackVersion
    )

    def see_asset_pack(self, asset_pack_name: str, version: typing.Tuple[int, int, int]) -> None:
        """Marks asset pack as seen. If an asset pack is seen, its version is stored in preferences.

        What's new compares this value to currently installed asset packs when deciding whether
        to display the 'What's New' button or not.
        """
        asset_pack = self.latest_seen_asset_packs.get(asset_pack_name)
        if asset_pack is None:
            asset_pack = self.latest_seen_asset_packs.add()
            asset_pack.name = asset_pack_name
        asset_pack.version = version


MODULE_CLASSES.append(WhatIsNewPreferences)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
