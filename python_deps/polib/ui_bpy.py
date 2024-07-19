#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import addon_utils
import sys
import typing
import re
import functools
import textwrap
import os
from . import utils_bpy
from . import preview_manager_bpy
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


# Global icon manager for polib icons, it NEEDS to be CLEARED  from each addon module separately
# as we cannot detect from inside of polib, whether it is in use or not.
# This means the preview manager can be cleared even if it is already used, but the icons will
# be reloaded on demand on the next use.
ICON_DIR_NAME = "icons"
icon_manager = preview_manager_bpy.PreviewManager()
icon_manager.add_preview_path(os.path.join(os.path.dirname(__file__), ICON_DIR_NAME))


class SocialMediaURL:
    DISCORD = "https://polygoniq.com/discord/"
    FACEBOOK = "https://www.facebook.com/polygoniq/"
    INSTAGRAM = "https://www.instagram.com/polygoniq.xyz/"
    BLENDERMARKET = "https://blendermarket.com/creators/polygoniq?ref=673"
    WEBPAGE = "https://polygoniq.com/"
    GUMROAD = "https://gumroad.com/polygoniq"


def get_asset_pack_icon_parameters(
    icon_id: typing.Optional[int], bpy_icon_name: str
) -> typing.Dict:
    """Returns dict of parameters that can be expanded in UILayout.label()

    Uses our icon with given 'icon_id' and populates the 'icon_value',
    or populates the 'icon' by the Blender's icon name 'bpy_icon' as fallback.
    """
    if icon_id is not None:
        return {"icon_value": icon_id}
    else:
        return {"icon": bpy_icon_name}


def draw_social_media_buttons(layout: bpy.types.UILayout, show_text: bool = False):
    layout.operator(
        "wm.url_open",
        text="Discord" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_discord"),
    ).url = SocialMediaURL.DISCORD

    layout.operator(
        "wm.url_open",
        text="Facebook" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_facebook"),
    ).url = SocialMediaURL.FACEBOOK

    layout.operator(
        "wm.url_open",
        text="Instagram" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_instagram"),
    ).url = SocialMediaURL.INSTAGRAM

    layout.operator(
        "wm.url_open",
        text="BlenderMarket" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_blendermarket"),
    ).url = SocialMediaURL.BLENDERMARKET

    layout.operator(
        "wm.url_open",
        text="Gumroad" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_gumroad"),
    ).url = SocialMediaURL.GUMROAD

    layout.operator(
        "wm.url_open",
        text="Website" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_polygoniq"),
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
    layout: bpy.types.UILayout, column_sizes: typing.List[float], align: bool = False
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


def scaled_row(layout: bpy.types.UILayout, scale: float, align: bool = False) -> bpy.types.UILayout:
    row = layout.row(align=align)
    row.scale_x = row.scale_y = scale
    return row


def row_with_label(
    layout: bpy.types.UILayout,
    text: str = "",
    align: bool = False,
    enabled: bool = False,
    icon: str = 'NONE',
) -> bpy.types.UILayout:
    """Creates a row with label based on 'layout'.

    Additional parameters specify appearance of this row and label. For example enabled = False can
    be used to display row that is grayed out. This can be useful to separate UI flow.
    """
    row = layout.row(align=align)
    row.enabled = enabled
    row.label(text=text, icon=icon)
    return row


def collapsible_box(
    layout: bpy.types.UILayout,
    data: typing.Any,
    show_prop_name: str,
    title: str,
    content_draw: typing.Callable[[bpy.types.UILayout], None],
    docs_module: typing.Optional[str] = None,
    docs_rel_url: str = "",
) -> bpy.types.UILayout:
    """Creates a collapsible box with 'title' and 'content' inside, based on 'layout'.

    The box is shown based on the 'show_prop_name' property of 'data' object. Optionally, a button
    leading to a documentation page can be added based on 'docs_module' and 'docs_rel_url'.
    """
    show = getattr(data, show_prop_name)
    if show is None:
        raise ValueError(f"Property '{show_prop_name}' not found in data object!")
    box = layout.box()
    row = box.row()
    row.prop(
        data,
        show_prop_name,
        icon='DISCLOSURE_TRI_DOWN' if show else 'DISCLOSURE_TRI_RIGHT',
        text="",
        emboss=False,
    )
    row.label(text=title)
    if docs_module is not None:
        draw_doc_button(row, docs_module, docs_rel_url)
    if show:
        content_draw(box)

    return box


def center_mouse(context: bpy.types.Context) -> None:
    region = context.region
    x = region.width // 2 + region.x
    y = region.height // 2 + region.y
    context.window.cursor_warp(x, y)


def get_mouseovered_region(
    context: bpy.types.Context, event: bpy.types.Event
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
        cls_name: str, space_name: str, space_types: typing.Dict[str, bpy.types.Space]
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
    mod_info = utils_bpy.get_addon_mod_info(module_name)
    mod_info["show_expanded"] = True


def draw_doc_button(layout: bpy.types.UILayout, module: str, rel_url: str = "") -> None:
    """Draws a button leading to an add-on's docs URL based on its module name.

    Points to the homepage by default, but can be changed by passing 'rel_url' parameter.
    """

    url = f"{utils_bpy.get_addon_docs_page(module)}/{rel_url}"
    layout.operator("wm.url_open", text="", icon='HELP', emboss=False).url = url


def draw_markdown_text(layout: bpy.types.UILayout, text: str, max_length: int = 100) -> None:
    col = layout.column(align=True)

    # Remove unicode characters from the text
    # We do this to remove emojis, because Blender does not support them
    text = text.encode("ascii", "ignore").decode()

    # Remove markdown images
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

    # Convert markdown links to just the description
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # Convert bold and italic text to UPPERCASE
    text = re.sub(r"(\*\*|__)(.*?)\1", lambda match: match.group(2).upper(), text)
    text = re.sub(r"(\*|_)(.*?)\1", lambda match: match.group(2).upper(), text)

    # Replace bullet list markers with classic bullet character (•), respecting indentation
    text = re.sub(r"(^|\n)(\s*)([-*+])\s", r"\1\2• ", text)

    # Regex for matching markdown headings
    headings = re.compile(r"^#+")

    lines = text.split("\r\n")
    # Let's offset the text based on the heading level to make it more readable
    offset = 0
    for line in lines:
        heading = headings.search(line)
        if heading:
            offset = len(heading.group()) - 1
            line = line.replace(heading.group(), "")
            line = line.strip().upper()

        # Let's do a separator for empty lines
        if len(line) == 0:
            col.separator()
            continue
        split_lines = textwrap.wrap(line, max_length)
        for split_line in split_lines:
            col.label(text=4 * offset * " " + split_line)


def show_release_notes_popup(
    context: bpy.types.Context, module_name: str, release_tag: str = ""
) -> None:
    if bpy.app.version >= (4, 2, 0) and not bpy.app.online_access:
        show_message_box(
            "This requires online access. You have to \"Allow Online Access\" in "
            "\"Preferences -> System -> Network\" to proceed",
            "Online Access Disabled",
            icon='INTERNET',
        )
        return

    mod_info = utils_bpy.get_addon_mod_info(module_name)
    # Get only the name without suffix (_full, _lite, etc.)
    addon_name = mod_info["name"].split("_", 1)[0]

    release_info = utils_bpy.get_addon_release_info(addon_name, release_tag)
    error_msg = f"Cannot retrieve release info for {addon_name}!"
    if release_info is None:
        logger.error(error_msg)
        show_message_box(error_msg, "Error", icon='ERROR')
        return

    version = release_info.get("tag_name", None)
    if version is None:
        logger.error("Release info does not contain version!")
        show_message_box(error_msg, "Error", icon='ERROR')
        return

    body = release_info.get("body", None)
    if not body:
        logger.error("Release info does not contain body!")
        show_message_box(error_msg, "Error", icon='ERROR')
        return

    context.window_manager.popup_menu(
        lambda self, context: draw_markdown_text(self.layout, text=body, max_length=100),
        title=f"{addon_name} {version} Release Notes",
        icon='INFO',
    )
