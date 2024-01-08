#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import addon_utils
import sys
import typing
import os

ICON_DIR_NAME = "icons"


class SocialMediaURL:
    DISCORD = "https://polygoniq.com/discord/"
    FACEBOOK = "https://www.facebook.com/polygoniq/"
    INSTAGRAM = "https://www.instagram.com/polygoniq.xyz/"
    BLENDERMARKET = "https://blendermarket.com/creators/polygoniq"
    WEBPAGE = "https://polygoniq.com/"
    GUMROAD = "https://gumroad.com/polygoniq"


class IconManager:
    def __init__(self, include_polib_icons: bool = True, additional_paths: typing.Optional[typing.List[str]] = None):
        self.icon_previews = bpy.utils.previews.new()
        self.include_polib_icons = include_polib_icons
        self.additional_paths = additional_paths if additional_paths is not None else []
        self.supported_extensions = (".jpg", ".png")
        self.load_all()

    def load_all(self) -> None:
        if self.include_polib_icons:
            icons_dir = os.path.join(os.path.dirname(__file__), ICON_DIR_NAME)
            self._load_icons_from_path(icons_dir)

        for path in self.additional_paths:
            self._load_icons_from_path(path)

    def get_icon_id(self, icon_name: str) -> int:
        if icon_name in self.icon_previews:
            return self.icon_previews[icon_name].icon_id
        else:
            return 1  # questionmark icon_id

    def get_polygoniq_addon_icon_id(self, addon_name: str) -> int:
        return self.get_icon_id(f"logo_{addon_name}")

    def get_engon_feature_icon_id(self, feature_name: str) -> int:
        return self.get_icon_id(f"logo_{feature_name}_features")

    def clear(self):
        self.icon_previews.clear()

    def reload(self) -> None:
        self.clear()
        self.load_all()

    # These methods for loading icons shouldn't be used from outside of load_all() because paths
    # used to load icons here wouldn't be stored in additional_paths for reload() to work. Let's
    # implement API that stores additional paths post-init if this is needed.
    def _load_icons_from_path(self, path: str) -> None:
        """Loads icon from the given path

        If given path points to directory, only icons directly in this directory are loaded, not
        nested ones.
        """
        if os.path.isfile(path):
            icon_name, ext = os.path.splitext(os.path.basename(path))
            if ext not in self.supported_extensions:
                raise RuntimeError(f"Cannot load icon from {path}, its extension is not one of "
                                   f"'{self.supported_extensions}'!")
            self._load_icon(icon_name, path)
        elif os.path.isdir(path):
            for icon_filename in os.listdir(path):
                icon_name, ext = os.path.splitext(icon_filename)
                if ext in self.supported_extensions:
                    self._load_icon(icon_name, os.path.join(path, icon_filename))
        else:
            raise RuntimeError(
                f"Cannot load icons from {path}, it is not a valid file or directory!")

    def _load_icon(self, icon_name: str, filepath: str) -> None:
        assert os.path.splitext(filepath)[1] in self.supported_extensions
        if icon_name in self.icon_previews:
            return
        # TODO: Load icons on demand instead of loading everything
        self.icon_previews.load(icon_name, filepath, "IMAGE")


icon_manager = IconManager()


def get_asset_pack_icon_parameters(icon_id: typing.Optional[int], bpy_icon_name: str) -> typing.Dict:
    """Returns dict of parameters that can be expanded in UILayout.label()

    Uses our icon with given 'icon_id' and populates the 'icon_value',
    or populates the 'icon' by the Blender's icon name 'bpy_icon' as fallback.
    """
    if icon_id is not None:
        return {"icon_value": icon_id}
    else:
        return {"icon": bpy_icon_name}


def draw_social_media_buttons(layout: bpy.types.UILayout, show_text: bool = False):
    layout.operator("wm.url_open",
                    text="Discord" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_discord")
                    ).url = SocialMediaURL.DISCORD

    layout.operator("wm.url_open",
                    text="Facebook" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_facebook")
                    ).url = SocialMediaURL.FACEBOOK

    layout.operator("wm.url_open",
                    text="Instagram" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_instagram")
                    ).url = SocialMediaURL.INSTAGRAM

    layout.operator("wm.url_open",
                    text="BlenderMarket" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_blendermarket")
                    ).url = SocialMediaURL.BLENDERMARKET

    layout.operator("wm.url_open",
                    text="Gumroad" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_gumroad")
                    ).url = SocialMediaURL.GUMROAD

    layout.operator("wm.url_open",
                    text="Website" if show_text else "",
                    icon_value=icon_manager.get_icon_id("logo_polygoniq")
                    ).url = SocialMediaURL.WEBPAGE


def draw_settings_footer(layout: bpy.types.UILayout):
    row = layout.row(align=True)
    row.alignment = 'CENTER'
    row.scale_x = 1.27
    row.scale_y = 1.27
    draw_social_media_buttons(row, show_text=False)
    row.label(text="© polygoniq xyz s.r.o")


def show_message_box(message: str, title: str, icon: str = 'INFO') -> None:
    lines = message.split("\n")

    def draw(self, context):
        for line in lines:
            row = self.layout.row()
            row.label(text=line)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def multi_column(
    layout: bpy.types.UILayout,
    column_sizes: typing.List[float],
    align: bool = False
) -> typing.List[bpy.types.UILayout]:
    columns = []
    for i in range(len(column_sizes)):
        # save first column, create split from the other with recalculated size
        size = 1.0 - sum(column_sizes[:i]) if i > 0 else 1.0

        s = layout.split(factor=column_sizes[i] / size, align=align)
        a = s.column(align=align)
        b = s.column(align=align)
        columns.append(a)
        layout = b

    return columns


def scaled_row(
    layout: bpy.types.UILayout,
    scale: float,
    align: bool = False
) -> bpy.types.UILayout:
    row = layout.row(align=align)
    row.scale_x = row.scale_y = scale
    return row


def row_with_label(
    layout: bpy.types.UILayout,
    text: str = "",
    align: bool = False,
    enabled: bool = False,
    icon: str = 'NONE'
) -> bpy.types.UILayout:
    """Creates a row with label based on 'layout'.

    Additional parameters specify appearance of this row and label. For example enabled = False can
    be used to display row that is grayed out. This can be useful to separate UI flow.
    """
    row = layout.row(align=align)
    row.enabled = enabled
    row.label(text=text, icon=icon)
    return row


def center_mouse(context: bpy.types.Context) -> None:
    region = context.region
    x = region.width // 2 + region.x
    y = region.height // 2 + region.y
    context.window.cursor_warp(x, y)


def get_mouseovered_region(
    context: bpy.types.Context,
    event: bpy.types.Event
) -> typing.Tuple[typing.Optional[bpy.types.Area], typing.Optional[bpy.types.Region]]:
    """Returns tuple (area, region) of underlying area and region in mouse event 'event'"""

    # Method taken from the 'Screencast Keys' addon
    # available at: https://github.com/nutti/Screencast-Keys
    x, y = event.mouse_x, event.mouse_y
    for area in context.screen.areas:
        for region in area.regions:
            if region.type == "":
                continue
            within_x = region.x <= x < region.x + region.width
            within_y = region.y <= y < region.y + region.height
            if within_x and within_y:
                return area, region

    return None, None


def get_all_space_types() -> typing.Dict[str, bpy.types.Space]:
    """Returns mapping of space type to its class - 'VIEW_3D -> bpy.types.SpaceView3D"""
    # Code taken and adjusted from ScreenCastKeys addon -> https://github.com/nutti/Screencast-Keys/
    def add_if_exist(
        cls_name: str,
        space_name: str,
        space_types: typing.Dict[str, bpy.types.Space]
    ) -> None:
        cls = getattr(sys.modules["bpy.types"], cls_name, None)
        if cls is not None:
            space_types[space_name] = cls

    space_types = {}
    add_if_exist("SpaceView3D", 'VIEW_3D', space_types)
    add_if_exist("SpaceClipEditor", 'CLIP_EDITOR', space_types)
    add_if_exist("SpaceConsole", 'CONSOLE', space_types)
    add_if_exist("SpaceDopeSheetEditor", 'DOPESHEET_EDITOR', space_types)
    add_if_exist("SpaceFileBrowser", 'FILE_BROWSER', space_types)
    add_if_exist("SpaceGraphEditor", 'GRAPH_EDITOR', space_types)
    add_if_exist("SpaceImageEditor", 'IMAGE_EDITOR', space_types)
    add_if_exist("SpaceInfo", 'INFO', space_types)
    add_if_exist("SpaceLogicEditor", 'LOGIC_EDITOR', space_types)
    add_if_exist("SpaceNLA", 'NLA_EDITOR', space_types)
    add_if_exist("SpaceNodeEditor", 'NODE_EDITOR', space_types)
    add_if_exist("SpaceOutliner", 'OUTLINER', space_types)
    add_if_exist("SpacePreferences", 'PREFERENCES', space_types)
    add_if_exist("SpaceUserPreferences", 'PREFERENCES', space_types)
    add_if_exist("SpaceProperties", 'PROPERTIES', space_types)
    add_if_exist("SpaceSequenceEditor", 'SEQUENCE_EDITOR', space_types)
    add_if_exist("SpaceSpreadsheet", 'SPREADSHEET', space_types)
    add_if_exist("SpaceTextEditor", 'TEXT_EDITOR', space_types)
    add_if_exist("SpaceTimeline", 'TIMELINE', space_types)

    return space_types


def expand_addon_prefs(module_name: str) -> None:
    """Opens preferences of an add-on based on its module name"""
    for mod in addon_utils.modules(refresh=False):
        if mod.__name__ == module_name:
            mod_info = addon_utils.module_bl_info(mod)
            mod_info["show_expanded"] = True
            return
    raise ValueError(f"No module '{module_name}' was found!")
