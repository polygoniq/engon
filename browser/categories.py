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


MODULE_CLASSES: list[typing.Any] = []


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
    category_parts: list[str] = list(filter(None, current_category.split("/")))
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
    category_parts: list[str] = list(filter(None, current_category.split("/")))
    # Always insert empty entry so the join starts with "/"
    category_parts.insert(0, "")
    max_nesting = len(category_parts)

    separator_factor = 1.0
    col = layout.box().column(align=True)
    master_provider = asset_registry.instance.master_asset_provider
    category_to_icon_id = asset_registry.instance.get_category_icons_map()

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


def draw_ui_list_tree_category_navigation(
    context: bpy.types.Context, layout: bpy.types.UILayout
) -> None:
    layout.template_list(
        MAPR_UL_CategoryNavigationList.__name__,
        "",
        get_category_navigation(context),
        "categories",
        get_category_navigation(context),
        "active_category_index",
        rows=10,
    )


@polib.log_helpers_bpy.logged_operator
class ExpandCategory(bpy.types.Operator):
    bl_idname = "engon.browser_expand_category"
    bl_description = "Expand the category to show content inside"
    bl_label = "Expand Category"
    bl_options = {'REGISTER'}

    category_id: bpy.props.StringProperty(
        default="/",
        options={'HIDDEN'},
    )

    def execute(self, context: bpy.types.Context):
        get_category_navigation(context).toggle_expand_category(self.category_id)
        return {'FINISHED'}


MODULE_CLASSES.append(ExpandCategory)


class CategoryNavigationEntry(bpy.types.PropertyGroup):
    """Entry in category navigation list, used by Category_UL_NavigationList.

    This data is not directly presented to the user, but is used to render the UI list.
    """

    # the default bpy.types.PropertyGroup.name is used as the category ID
    title: bpy.props.StringProperty()
    level: bpy.props.IntProperty()
    is_expanded: bpy.props.BoolProperty()
    is_leaf: bpy.props.BoolProperty(default=False)
    icon_id: bpy.props.IntProperty(default=-1)


MODULE_CLASSES.append(CategoryNavigationEntry)


class MAPR_UL_CategoryNavigationList(bpy.types.UIList):
    """Displays single entry in the category navigation list."""

    def draw_item(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        data: typing.Any,
        item: CategoryNavigationEntry,
        icon: int,
        active_data: typing.Any,
        active_propname: str,
        index: int,
        flt_flag: int,
    ) -> None:
        self.use_filter_show = False

        row = layout.row(align=True)
        row.alignment = 'LEFT'
        padding = " " * (item.level * 2)
        # Root doesn't have any padding
        if item.level != 0:
            row.label(text=padding)

        if not item.is_leaf:
            row.operator(
                ExpandCategory.bl_idname,
                text="",
                icon='TRIA_DOWN' if item.is_expanded else 'TRIA_RIGHT',
                emboss=False,
            ).category_id = item.name
        else:
            # blank icon to keep alignment
            row.label(icon='BLANK1')

        if item.icon_id != -1:
            row.label(text=f"{item.title}", icon_value=item.icon_id)
        else:
            row.label(text=f"{item.title}", icon='FILE_FOLDER')


MODULE_CLASSES.append(MAPR_UL_CategoryNavigationList)


class CategoryNavigation(bpy.types.PropertyGroup):
    """Holds the state for category navigation UI list.

    The categories collection needs to be rebuild whenever category is expanded as the collection
    has to contain only currently visible categories, because the UIList draws each item in the
    collection. First level is always expanded.
    """

    categories: bpy.props.CollectionProperty(type=CategoryNavigationEntry)
    active_category_index: bpy.props.IntProperty(
        name="Enter Category",
        update=lambda self, context: self.category_index_changed(context),
    )

    def category_index_changed(self, context: bpy.types.Context) -> None:
        if self.active_category_index < 0 or self.active_category_index >= len(self.categories):
            return
        category_id = self.categories[self.active_category_index].name
        MAPR_BrowserEnterCategory.enter_category(context, category_id)

    def toggle_expand_category(self, category_id: str) -> None:
        category_item = self.categories.get(category_id)
        category_item.is_expanded = not category_item.is_expanded
        self.rebuild_categories()

    def rebuild_categories(self) -> None:
        # save the state of expanded categories
        previously_expanded_categories = {item.name for item in self.categories if item.is_expanded}
        previous_active_category = (
            self.categories[self.active_category_index].name
            if (0 <= self.active_category_index < len(self.categories))
            else None
        )

        self.categories.clear()
        master_provider = asset_registry.instance.master_asset_provider
        category_to_icon_id = asset_registry.instance.get_category_icons_map()

        def build_category(category_id: str, level: int) -> None:
            # Recursively build the list of categories to display. Include the category and
            # include it's children if the category is expanded.
            category = master_provider.get_category_safe(category_id)
            child_categories = list(master_provider.list_sorted_categories(category_id))
            is_leaf = len(child_categories) == 0
            item = self.categories.add()
            item.name = category.id_
            item.title = category.title
            item.level = level
            item.is_leaf = is_leaf
            item.is_expanded = category.id_ in previously_expanded_categories or level == 0
            item.icon_id = category_to_icon_id.get(category_id.strip("/"), -1)
            if item.is_expanded and not is_leaf:
                for child_category in child_categories:
                    build_category(child_category.id_, level + 1)

        build_category("/", 0)

        # Ensure correct category is still active even when the list was rebuilt
        if previous_active_category is not None and previous_active_category in self.categories:
            for i, item in enumerate(self.categories):
                if item.name == previous_active_category:
                    self.active_category_index = i
                    break
        else:
            # The previously active category is no longer visible
            self.active_category_index = -1


MODULE_CLASSES.append(CategoryNavigation)


def get_category_navigation(context: bpy.types.Context) -> CategoryNavigation:
    return context.window_manager.pq_category_navigation


def on_registry_refreshed() -> None:
    get_category_navigation(bpy.context).rebuild_categories()


@bpy.app.handlers.persistent
def on_post_load(_) -> None:
    get_category_navigation(bpy.context).rebuild_categories()


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.pq_category_navigation = bpy.props.PointerProperty(
        type=CategoryNavigation
    )
    asset_registry.instance.on_refresh.append(on_registry_refreshed)
    bpy.app.handlers.load_post.append(on_post_load)


def unregister():
    bpy.app.handlers.load_post.remove(on_post_load)
    asset_registry.instance.on_refresh.remove(on_registry_refreshed)

    del bpy.types.WindowManager.pq_category_navigation
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
