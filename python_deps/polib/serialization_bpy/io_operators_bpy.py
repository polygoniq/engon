# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import bpy_extras
import pathlib
import logging
import collections.abc
from . import errors
from . import io_bpy
from .. import log_helpers_bpy
from .. import utils_bpy

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

    pretty_print: bpy.props.BoolProperty(
        name="Pretty Print",
        description="Export the config in a human-readable format",
        default=False,
    )

    @utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        filepath = pathlib.Path(self.filepath)  # type: ignore
        try:
            self.savable.save_custom(filepath, self.pretty_print)
            self.report({'INFO'}, f"'{self.savable.qualified_name}' exported to {filepath}")
        except OSError as e:
            logger.exception(f"Failed to export '{self.savable.qualified_name}' to '{filepath}'")
            self.report(
                {'ERROR'},
                f"Failed to export '{self.savable.qualified_name}' to '{filepath}'. "
                "The file may not be writable or accessible.",
            )
        except Exception as e:
            self.report(
                {'ERROR'},
                f"Failed to export '{self.savable.qualified_name}' to '{filepath}'.",
            )
        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            self.filepath = type(self.savable).addon_name + io_bpy.CONFIG_EXT
        return super().invoke(context, event)


def _import_savable_from_file(
    op: 'ImportSavable | SearchSavables | ImportSavableIgnoreVersion',
    context: bpy.types.Context,
    savable_instance: io_bpy.Savable,
    filepath: pathlib.Path,
    ignore_version: bool = False,
    ignore_version_op_name: str | None = None,
) -> set[str]:
    success = False
    try:
        savable_instance.load_custom(filepath, ignore_version=ignore_version)
        success = True
    except OSError as e:
        logger.exception(f"Failed to read '{savable_instance.qualified_name}' from '{filepath}'.")
        op.report(
            {'ERROR'},
            f"Failed to read '{savable_instance.qualified_name}' from '{filepath}'. "
            "The file may not exist or is not accessible.",
        )
    except errors.UnsupportedVersionError as e:
        logger.exception(
            f"Trying to import unsupported version of '{savable_instance.qualified_name}' from "
            f"'{filepath}'."
        )

        if ignore_version_op_name is not None:
            # If `ignore_version_op_name` is provided, try to get the operator to invoke
            import_ignore_version_op = bpy.ops
            for name in ignore_version_op_name.split("."):
                import_ignore_version_op = getattr(import_ignore_version_op, name, None)
        else:
            import_ignore_version_op = None

        if callable(import_ignore_version_op):
            import_ignore_version_op(
                'INVOKE_DEFAULT', filepath=str(filepath), file_version=e.loaded_version
            )
        else:
            op.report(
                {'ERROR'},
                f"Cannot import '{savable_instance.qualified_name}' from '{filepath}', "
                "the version is unsupported.",
            )
    except errors.InvalidConfigError as e:
        logger.exception(
            f"Invalid config format for '{savable_instance.qualified_name}' imported from '{filepath}'."
        )
        op.report(
            {'ERROR'},
            f"Cannot import '{savable_instance.qualified_name}' from '{filepath}', "
            "the file is invalid or corrupted.",
        )
    except Exception as e:
        logger.exception(f"Failed to import '{savable_instance.qualified_name}' from '{filepath}'.")
        op.report(
            {'ERROR'},
            f"Failed to import '{savable_instance.qualified_name}'. "
            "Only a part or none of the data was imported.",
        )

    op.on_import_callback(context)
    if not success:
        return {'CANCELLED'}

    try:
        savable_instance.save()  # Save to the default location
        op.report({'INFO'}, f"'{savable_instance.qualified_name}' imported from '{filepath}'.")
    except Exception as e:
        logger.exception(f"Failed to save '{savable_instance.qualified_name}' after import.")
        op.report(
            {'WARNING'},
            f"'{savable_instance.qualified_name}' imported from '{filepath}', but saving "
            "to the default location failed. The imported data may be lost on Blender exit.",
        )

    return {'FINISHED'}


class ImportSavable(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Operator for importing content of a `Savable` class from a file.

    If `filepath` is not set when invoked, import dialog will be shown.

    Override `bl_idname` and `savable` property to specify the
    savable instance that should be imported.
    """

    bl_label = "Import"
    import_savable_ignore_version_op_name: str | None = None

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    def on_import_callback(self, context: bpy.types.Context) -> None:
        """Callback that will be invoked after an import operation finishes."""
        pass

    filter_glob: bpy.props.StringProperty(
        default=f"*{io_bpy.CONFIG_EXT}",
        options={'HIDDEN'},
    )

    @utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        filepath = pathlib.Path(self.filepath)
        return _import_savable_from_file(
            self,
            context,
            self.savable,
            filepath,
            ignore_version_op_name=type(self).import_savable_ignore_version_op_name,
        )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if self.filepath == "":
            self.filepath = type(self.savable).addon_name + io_bpy.CONFIG_EXT
        return super().invoke(context, event)


class ImportSavableIgnoreVersion(bpy.types.Operator):
    """Utility operator for importing content of a `Savable` class from a file, ignoring version mismatches.

    Shows a confirmation popup before importing. Should be used only for importing with unsupported versions.
    """

    bl_label = "Import (Ignore Version)"

    filepath: bpy.props.StringProperty(
        name="Filepath",
        description="Path to the config file to import",
        default="",
        subtype='FILE_PATH',
    )
    file_version: bpy.props.IntProperty(
        name="File Version",
        description="Version of the config file to import",
        default=1,
    )

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    def on_import_callback(self, context: bpy.types.Context) -> None:
        """Callback that will be invoked after an import operation finishes."""
        pass

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        col = layout.column()
        col.alert = True
        col.label(
            text="The selected file has an unsupported version.",
            icon='ERROR',
        )

        layout.separator()
        layout.label(
            text=f"File version: {self.file_version}",
        )
        layout.label(
            text=f"Supported version: {self.savable.save_version}",
        )

        layout.separator()
        col = layout.column()
        col.alert = True
        col.label(
            text="Importing this file may result in data loss.",
        )
        col.label(
            text="Backup your current configuration before proceeding.",
        )

    @utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context):
        filepath = pathlib.Path(self.filepath)
        return _import_savable_from_file(
            self,
            context,
            self.savable,
            filepath,
            ignore_version=True,
        )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_props_dialog(
            self, title="Unsupported Version", confirm_text="Import Anyway"
        )


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

    bl_label = "Import from version..."

    @property
    def savable(self) -> io_bpy.Savable:
        raise NotImplementedError(
            "The 'savable' property must be overridden to return the "
            "savable instance for this operator."
        )

    def on_import_callback(self, context: bpy.types.Context) -> None:
        """Callback that will be invoked after an import operation finishes."""
        pass

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
            col = layout.column()
            col.alert = True
            col.label(
                text=f"No {self.savable.config_name} found.",
                icon='ERROR',
            )
            col.label(
                text="Note that preferences saved with portable Blender versions",
            )
            col.label(
                text="or in custom locations cannot be found automatically.",
            )
            col.label(
                text=f"You can import the {self.savable.config_name} manually using the Import button.",
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

    @utils_bpy.blender_cursor('WAIT')
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
        if len(self.found_savables) == 0:
            return context.window_manager.invoke_popup(self, width=450)
        return context.window_manager.invoke_props_dialog(self, width=450)


def savable_operators_factory(
    bl_idname_addon_prefix: str,
    savable_name: str,
    savable_getter: collections.abc.Callable[['ImportSavable | SearchSavables'], io_bpy.Savable],
    on_import_callback: (
        collections.abc.Callable[
            ['ImportSavable | SearchSavables | ImportSavableIgnoreVersion', bpy.types.Context], None
        ]
        | None
    ) = None,
) -> tuple[
    ExportSavable, ImportSavable, FoundSavableItem, SearchSavables, ImportSavableIgnoreVersion
]:
    """Factory function to create export, import, and search operators.

    Args:
        bl_idname_addon_prefix: The prefix for the `bl_idname` of the operators. (e.g. "engon")
        savable_name: The name of the savable instance. Affects the exported file name. (e.g. "preferences")
        savable_getter: A callable that takes the operator instance as argument and returns
            the savable instance to be saved or loaded by the operators.
        on_import_callback: Optional callable that will be invoked after an import operation finishes.
            Arguments are the operator instance and context.

    Returns a tuple of:
        - Export operator class
        - Import operator class
        - FoundSavableItem class (used in search operator, must be registered before search operator)
        - Search operator class
        - Import operator class that ignores version mismatches
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
                'import_savable_ignore_version_op_name': f"{bl_idname_addon_prefix}.import_{savable_name}_ignore_version",
                'savable': property(savable_getter),
                'on_import_callback': (
                    on_import_callback
                    if on_import_callback is not None
                    else lambda self, context: None
                ),
            },
        )
    )
    import_ignore_version_op = log_helpers_bpy.logged_operator(
        type(
            f"Import{savable_name.capitalize()}IgnoreVersion",
            (ImportSavableIgnoreVersion,),
            {
                'bl_idname': f"{bl_idname_addon_prefix}.import_{savable_name}_ignore_version",
                'bl_description': f"Import {description_name} {savable_name} from a file",
                'savable': property(savable_getter),
                'on_import_callback': (
                    on_import_callback
                    if on_import_callback is not None
                    else lambda self, context: None
                ),
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
                'bl_description': f"Import {description_name} {savable_name} from a different Blender version",
                'savable': property(savable_getter),
                'on_import_callback': (
                    on_import_callback
                    if on_import_callback is not None
                    else lambda self, context: None
                ),
            },
        )
    )
    # Override `found_savables` annotation with the correct type
    search_op.__annotations__["found_savables"] = bpy.props.CollectionProperty(
        type=found_savable_item,
        name="Found Savables",
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    return export_op, import_op, found_savable_item, search_op, import_ignore_version_op  # type: ignore


def draw_import_export_savable_panel(
    layout: bpy.types.UILayout,
    savable_name: str,
    export_operator: str | None = None,
    import_operator: str | None = None,
    search_operator: str | None = None,
) -> None:
    box = layout.box()
    box.label(text=f"Import/Export {savable_name}", icon='IMPORT')
    row = box.row()
    if search_operator is not None:
        row.operator(search_operator, icon='BLENDER')
    if import_operator is not None:
        row.operator(import_operator, icon='IMPORT')
    if export_operator is not None:
        row.operator(export_operator, icon='EXPORT')
