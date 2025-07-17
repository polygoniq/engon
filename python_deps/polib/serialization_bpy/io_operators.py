# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import bpy_extras
import pathlib
import logging
import typing
from . import io_bpy
from .. import log_helpers_bpy

logger = logging.getLogger(f"polygoniq.{__name__}")


class ExportSavable(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """Operator for exporting content of a `Savable` class to a file.

    If `filepath` is not set when invoked, export dialog will
    be shown with the default filename set to the addon name.

    Override `bl_idname` and `savable` property to specify the
    savable instance that should be exported.
    """

    bl_label = "Export"

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    filename_ext: bpy.props.StringProperty(
        default=io_bpy.CONFIG_EXT,
        options={'HIDDEN'},
    )

    def execute(self, context: bpy.types.Context):
        filepath = pathlib.Path(self.filepath)  # type: ignore
        try:
            self.savable.save_custom(filepath)
            self.report({'INFO'}, f"{self.savable.config_name.capitalize()} exported to {filepath}")
        except Exception as e:
            self.report(
                {'ERROR'},
                f"Failed to export {self.savable.config_name}",
            )
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            self.filepath = type(self.savable).addon_name + io_bpy.CONFIG_EXT
        return super().invoke(context, event)


def _import_savable_from_file(
    op: bpy.types.Operator,
    context: bpy.types.Context,
    savable_instance: io_bpy.Savable,
    filepath: pathlib.Path,
) -> typing.Set[str]:
    try:
        savable_instance.load_custom(filepath)
        savable_instance.save()  # Save to the default location
        op.report({'INFO'}, f"{savable_instance.config_name.capitalize()} imported from {filepath}")
    except Exception as e:
        op.report(
            {'ERROR'},
            f"Failed to import {savable_instance.config_name}.",
        )
    return {'FINISHED'}


class ImportSavable(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Operator for importing content of a `Savable` class from a file.

    If `filepath` is not set when invoked, import dialog will be shown.

    Override `bl_idname` and `savable` property to specify the
    savable instance that should be imported.
    """

    bl_label = "Import"

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    filter_glob: bpy.props.StringProperty(
        default=f"*{io_bpy.CONFIG_EXT}",
        options={'HIDDEN'},
    )

    def execute(self, context: bpy.types.Context):
        filepath = pathlib.Path(self.filepath)
        return _import_savable_from_file(self, context, self.savable, filepath)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            self.filepath = type(self.savable).addon_name + io_bpy.CONFIG_EXT
        return super().invoke(context, event)


class FoundSavableItem(bpy.types.PropertyGroup):
    """Property group for storing information about found instances of savable."""

    name: bpy.props.StringProperty(
        name="Name",
        description="Name of the found savable instance",
    )
    filepath: bpy.props.StringProperty(
        name="Filepath",
        description="Filepath of the found savable instance",
    )
    tooltip: bpy.props.StringProperty(
        name="Tooltip",
    )


class SearchSavables(bpy.types.Operator):
    """Operator that will find and list all saved instances of savable from other blender versions.

    Override `bl_idname` and `savable` property to specify the
    savable instance that should be imported.
    """

    bl_label = "Search"

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    active_index: bpy.props.IntProperty(
        name="Index of the active item",
        default=0,
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    found_savables: bpy.props.CollectionProperty(
        type=FoundSavableItem,
        name="Found Savables",
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        if len(self.found_savables) == 0:
            row = layout.row()
            row.alert = True
            row.label(
                text=f"No {self.savable.config_name} found in known directories.",
                icon='ERROR',
            )
            return

        layout.label(text=f"Found {self.savable.config_name}:")
        layout.template_list(
            bpy.types.UI_UL_list.__name__,  # type: ignore
            "found_savables",
            self,
            "found_savables",
            self,
            "active_index",
            item_dyntip_propname="tooltip",
        )

    def execute(self, context: bpy.types.Context):
        if len(self.found_savables) == 0:
            return {'CANCELLED'}
        selected_item = self.found_savables[self.active_index]
        filepath = pathlib.Path(selected_item.filepath)
        return _import_savable_from_file(self, context, self.savable, filepath)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        savable_type = type(self.savable)
        for version, filepath in io_bpy.list_versions_with_config(
            addon_name=savable_type.addon_name,
            config_name=self.savable.config_name,
            exclude_current=True,
        ):
            item = self.found_savables.add()
            item.name = "Blender " + version
            item.filepath = str(filepath)
            item.tooltip = f"Import {self.savable.config_name} from '{filepath}'"
        self.active_index = len(self.found_savables) - 1  # Select the last item by default
        return context.window_manager.invoke_props_dialog(self, width=400)


def savable_operators_factory(
    bl_idname_addon_prefix: str,
    savable_name: str,
    savable_getter: typing.Callable[[typing.Any], io_bpy.Savable],
) -> typing.Tuple[ExportSavable, ImportSavable, FoundSavableItem, SearchSavables]:
    """Factory function to create export, import, and search operators.

    Returns a tuple of:
        - Export operator class
        - Import operator class
        - FoundSavableItem class (used in search operator, must be registered before search operator)
        - Search operator class
    """
    description_name = bl_idname_addon_prefix.replace("_", " ")
    # Create new dynamic classes for export, import, and search operators
    # These will create a new class derived from the base classes
    # with the specified bl_idname, description, and savable properties
    export_op = log_helpers_bpy.logged_operator(
        type(
            f"Export{savable_name.capitalize()}",
            (ExportSavable,),
            {
                'bl_idname': f"{bl_idname_addon_prefix}.export_{savable_name}",
                'bl_description': f"Export {description_name} {savable_name} to a file",
                'savable': property(savable_getter),
            },
        )
    )
    import_op = log_helpers_bpy.logged_operator(
        type(
            f"Import{savable_name.capitalize()}",
            (ImportSavable,),
            {
                'bl_idname': f"{bl_idname_addon_prefix}.import_{savable_name}",
                'bl_description': f"Import {description_name} {savable_name} from a file",
                'savable': property(savable_getter),
            },
        )
    )
    found_savable_item = type(f"Found{savable_name.capitalize()}Item", (FoundSavableItem,), {})
    search_op = log_helpers_bpy.logged_operator(
        type(
            f"Search{savable_name.capitalize()}",
            (SearchSavables,),
            {
                'bl_idname': f"{bl_idname_addon_prefix}.search_{savable_name}",
                'bl_description': f"Look for {description_name} {savable_name} in other Blender versions",
                'savable': property(savable_getter),
            },
        )
    )
    # Override `found_savables` annotation with the correct type
    search_op.__annotations__["found_savables"] = bpy.props.CollectionProperty(
        type=found_savable_item,
        name="Found Savables",
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    return export_op, import_op, found_savable_item, search_op  # type: ignore


def draw_import_export_savable_panel(
    layout: bpy.types.UILayout,
    savable_name: str,
    export_operator: typing.Optional[str] = None,
    import_operator: typing.Optional[str] = None,
    look_for_operator: typing.Optional[str] = None,
) -> None:
    box = layout.box()
    box.label(text=f"Import/Export {savable_name}", icon='IMPORT')
    row = box.row()
    if export_operator is not None:
        row.operator(export_operator, icon='EXPORT')
    if import_operator is not None:
        row.operator(import_operator, icon='IMPORT')
    if look_for_operator is not None:
        row.operator(look_for_operator, icon='FILEBROWSER')
