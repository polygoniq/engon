#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import sys
import typing
import re
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
    SUPERHIVEMARKET = "https://superhivemarket.com/creators/polygoniq?ref=673"
    WEBPAGE = "https://polygoniq.com/"
    GUMROAD = "https://gumroad.com/polygoniq"


def get_asset_pack_icon_parameters(icon_id: int | None, bpy_icon_name: str) -> dict:
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
        text="SuperHive" if show_text else "",
        icon_value=icon_manager.get_icon_id("logo_superhive"),
    ).url = SocialMediaURL.SUPERHIVEMARKET

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


def draw_message_in_lines(
    layout: bpy.types.UILayout, message: str, max_chars: int | None = None
) -> None:
    lines = message.split("\n")
    for line in lines:
        chunks = []
        if max_chars is not None:
            chunks = textwrap.wrap(line, width=max_chars)
        else:
            chunks = [line]
        for chunk in chunks:
            row = layout.row()
            row.label(text=chunk)


def show_message_box(
    message: str, title: str, icon: str = 'INFO', max_chars: int | None = None
) -> None:
    if bpy.app.background:
        logger.warning(
            f"Message box functionality is not available in background mode!\n"
            f"Title: {title}\n"
            f"Message: {message}"
        )
        return

    bpy.context.window_manager.popup_menu(
        lambda popup_menu, _: draw_message_in_lines(popup_menu.layout, message, max_chars),
        title=title,
        icon=icon,
    )


def multi_column(
    layout: bpy.types.UILayout, column_sizes: list[float], align: bool = False
) -> list[bpy.types.UILayout]:
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
    docs_module: str | None = None,
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
    left_side = row.row()
    left_side.alignment = 'LEFT'
    left_side.prop(
        data,
        show_prop_name,
        icon='DISCLOSURE_TRI_DOWN' if show else 'DISCLOSURE_TRI_RIGHT',
        text=title,
        emboss=False,
    )
    right_side = row.row()
    right_side.alignment = 'RIGHT'
    if docs_module is not None:
        draw_doc_button(right_side, docs_module, docs_rel_url)
    if show:
        content_draw(box)

    return box


def get_mouseovered_region(
    context: bpy.types.Context, event: bpy.types.Event
) -> tuple[bpy.types.Area | None, bpy.types.Region | None]:
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


def get_area_region_space(
    screen: bpy.types.Screen, area_type: str, region_type: str, space_type: str | None
) -> tuple[
    bpy.types.Area | None,
    bpy.types.Region | None,
    bpy.types.Space | None,
]:
    """Returns tuple (area, region, space) of area, region and space based on their types

    If space type is None, the active space of the area is returned.
    If any of the input types is not found, (None, None, None) is returned.
    """

    for area in screen.areas:
        if area.type == area_type:
            break
    else:
        return None, None, None

    for region in area.regions:
        if region.type == region_type:
            break
    else:
        return None, None, None

    if space_type is None:
        return area, region, area.spaces.active
    for space in area.spaces:
        if space.type == space_type:
            return area, region, space

    return None, None, None


def tag_areas_redraw(context: bpy.types.Context, area_types: set[str] | None = None) -> None:
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area_types is None or area.type in area_types:
                area.tag_redraw()


def get_all_space_types() -> dict[str, bpy.types.Space]:
    """Returns mapping of space type to its class - 'VIEW_3D -> bpy.types.SpaceView3D"""

    # Code taken and adjusted from ScreenCastKeys addon -> https://github.com/nutti/Screencast-Keys/
    def add_if_exist(
        cls_name: str, space_name: str, space_types: dict[str, bpy.types.Space]
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
    context: bpy.types.Context,
    module_name: str,
    release_tag: str = "",
    update_operator_bl_idname: str = "",
) -> None:
    def draw(layout: bpy.types.UILayout, body: str):
        draw_markdown_text(layout, text=body, max_length=100)
        if update_operator_bl_idname != "":
            row = layout.row()
            row.scale_x = 1.2
            row.scale_y = 1.2
            row.operator(update_operator_bl_idname, text="Update", icon='IMPORT')

    if not bpy.app.online_access:
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
    error_msg = f"Release info cannot be retrieved for {addon_name} {release_tag}"
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
        lambda self, _: draw(self.layout, body),
        title=f"{addon_name} {version} Release Notes",
        icon='INFO',
    )


def draw_conflicting_addons(
    layout: bpy.types.UILayout, module_name: str, conflicts: list[str]
) -> None:
    """Draws a list of conflicting addons based on the 'module_name' name in 'layout'."""
    if len(conflicts) == 0:
        return

    box = layout.box()
    row = box.row()
    sub = row.row()
    sub.alert = True
    sub.label(text="Conflicting addons found!", icon='ERROR')
    draw_doc_button(
        row.row(), module_name, "getting_started/installation#addon-installation-conflicts"
    )
    col = box.column(align=True)
    for message in conflicts:
        col.label(text=f"- {message}")

    sub = box.column(align=True)
    sub.enabled = False
    sub.label(
        text="This message will disappear after RESTARTING Blender with the conflicting addons removed!"
    )
    sub.label(text="Click documentation button in the corner for more info.", icon='HELP')
