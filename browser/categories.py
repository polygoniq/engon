# copyright (c) 2018- polygoniq xyz s.r.o.

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import typing
import logging
from .. import polib
from . import filters
from . import utils
from .. import asset_registry

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES: typing.List[typing.Any] = []


@polib.log_helpers_bpy.logged_operator
class MAPR_BrowserEnterCategory(bpy.types.Operator):
    bl_idname = "engon.browser_enter_category"
    bl_description = "Enters category specified by category_id"
    bl_label = "Enter Category"
    bl_options = {'REGISTER'}

    category_id: bpy.props.StringProperty(
        default="/",
        options={'HIDDEN'},
    )

    loading = False

    @staticmethod
    def enter_category(context: bpy.types.Context, category: str):
        filters.get_filters().query_and_reconstruct(category)

    def execute(self, context: bpy.types.Context):
        MAPR_BrowserEnterCategory.enter_category(context, self.category_id)
        return {'FINISHED'}


MODULE_CLASSES.append(MAPR_BrowserEnterCategory)


def draw_category_pills_header(
    context: bpy.types.Context, layout: bpy.types.UILayout, width: float
) -> None:
    master_provider = asset_registry.instance.master_asset_provider
    ui_scale = context.preferences.system.ui_scale
    estimated_row_width_px = 0
    current_category = master_provider.get_category_id_from_string(
        filters.asset_repository.current_category_id
    )
    col = layout.column()
    row = col.row(align=True)
    row.alignment = 'LEFT'
    # Split first row into two sub-rows, 'left' containing the non-embossed clickable buttons
    # to return to the previous categories and 'right' containing first row of all child
    # categories of 'current_category'
    left = row.row(align=True)
    left.alignment = 'LEFT'

    right = row.row()
    right.alignment = 'LEFT'

    # Draw non-embossed clickable operator buttons of 'current_category' and parent categories
    category_parts: typing.List[str] = list(filter(None, current_category.split("/")))
    # Always insert empty entry so the join starts with "/"
    category_parts.insert(0, "")

    for i, category_part in enumerate(category_parts):
        category_id = "/".join(category_parts[:i] + [category_part])
        is_embossed = i < len(category_parts) - 1
        # Always display first button as root category "/"
        if i == 0:
            category_part = "/"
        left.operator(
            MAPR_BrowserEnterCategory.bl_idname, text=category_part, emboss=is_embossed
        ).category_id = category_id
        # Prepend arbitrary spaces to embossed buttons, so it aligns nicely
        left.label(text="   >" if is_embossed else ">")
        estimated_row_width_px += ui_scale * (len(category_id) * utils.EST_LETTER_WIDTH_PX + 20)

    # Add some margin after the last category label to keep the UI spaces consistent
    left.label(text="   ")

    # Draw child categories buttons, wrap if the estimated width is larger than wrap_width
    for category in master_provider.list_sorted_categories(current_category):
        last_part = category.id_.split("/")[-1]
        right.operator(MAPR_BrowserEnterCategory.bl_idname, text=last_part).category_id = (
            category.id_
        )
        # 20 * ui_scale as a margin width for each button
        estimated_row_width_px += ui_scale * (len(last_part) * utils.EST_LETTER_WIDTH_PX + 20)
        if estimated_row_width_px > width:
            # Reset estimated width and create new row from the base column aligning to left
            estimated_row_width_px = 0
            right = col.row()
            right.alignment = 'LEFT'


def draw_tree_category_navigation(
    context: bpy.types.Context,
    layout: bpy.types.UILayout,
) -> None:
    current_category = filters.asset_repository.current_category_id
    child_categories = asset_registry.instance.master_asset_provider.list_sorted_categories(
        current_category
    )

    # Draw non-embossed clickable operator buttons of 'current_category' and parent categories
    category_parts: typing.List[str] = list(filter(None, current_category.split("/")))
    # Always insert empty entry so the join starts with "/"
    category_parts.insert(0, "")
    max_nesting = len(category_parts)

    separator_factor = 1.0
    col = layout.box().column(align=True)
    master_provider = asset_registry.instance.master_asset_provider

    asset_packs = asset_registry.instance.get_registered_packs()
    category_to_icon_id: typing.Dict[str, int] = {}
    for asset_pack in asset_packs:
        # Theoretically asset packs may override icons registered by the previous pack in this loop
        # if they have the same file_id_prefix. We don't have any way how to find the best icon
        # in that case, so the last one is as good as any.
        # TODO: Currently file_id_prefix is the same as main asset pack category. But it doesn't
        # need to hold in the future. E.g. when someone would release asset pack with
        # file_id_prefix="coniferous" we would display their icon also for botaniq/coniferous.
        category_name = asset_pack.file_id_prefix.strip("/")
        asset_pack_icon_id = asset_pack.get_pack_icon_id()
        if asset_pack_icon_id is not None:
            category_to_icon_id[category_name] = asset_pack_icon_id

    for i, category_part in enumerate(category_parts):
        category = master_provider.get_category_safe(
            master_provider.get_category_id_from_string(
                "/".join(category_parts[:i] + [category_part])
            )
        )
        # In case no category is found in the providers (or no providers are available),

        # Always display first button as root category "/"
        if i == 0:
            category_part = "/"

        icon_parameters = polib.ui_bpy.get_asset_pack_icon_parameters(
            category_to_icon_id.get(category.id_.lstrip("/"), None), 'FOLDER_REDIRECT'
        )

        row = col.row(align=True)
        row.separator(factor=i * separator_factor)
        row.operator(
            MAPR_BrowserEnterCategory.bl_idname, text=category.title, **icon_parameters
        ).category_id = category.id_

    for category in child_categories:
        icon_parameters = polib.ui_bpy.get_asset_pack_icon_parameters(
            category_to_icon_id.get(category.id_.lstrip("/"), None), 'FILE_FOLDER'
        )
        row = col.row(align=True)
        row.separator(factor=max_nesting * separator_factor)
        row.operator(
            MAPR_BrowserEnterCategory.bl_idname, text=category.title, **icon_parameters
        ).category_id = category.id_


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
