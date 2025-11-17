# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import logging
import collections.abc
from . import io_bpy
from . import errors
from .. import ui_bpy

logger = logging.getLogger(f"polygoniq.{__name__}")


def post_register_load(savable_getter: collections.abc.Callable[[], io_bpy.Savable]) -> None:
    """This will register timer that will load the `Savable` class right
    after `register()` is finished.
    """

    def load():
        error_popup_message = None
        savable = savable_getter()
        if savable.save_file_exists():
            try:
                savable.load()
                logger.info(f"Loaded '{savable.qualified_name}' on startup.")
            except errors.UnsupportedVersionError as e:
                logger.exception(
                    f"Failed to load '{savable.qualified_name}' on startup due to unsupported version: {e}."
                )
                try:
                    savable.load(ignore_version=True)
                    logger.info(
                        f"Loaded '{savable.qualified_name}' on startup with ignored version."
                    )
                    error_popup_message = (
                        f"{savable.config_name} of {type(savable).addon_name} was saved with an "
                        f"unsupported version of the addon. Some settings may not have been loaded correctly."
                    )
                except Exception as e:
                    logger.exception(
                        f"Failed to load '{savable.qualified_name}' on startup with ignored version."
                    )
                    error_popup_message = (
                        f"{savable.config_name} of {type(savable).addon_name} could not be loaded. "
                        f"Please check the console for more information."
                    )
            except Exception as e:
                logger.exception(f"Failed to load '{savable.qualified_name}' on startup")
                error_popup_message = (
                    f"{savable.config_name} of {type(savable).addon_name} could not be loaded. "
                    f"Please check the console for more information."
                )
        else:
            try:
                # This is not considered an error
                # There is not a good way of knowing if this is the first run or that prefs were deleted
                logger.info(
                    f"No save file found for '{savable.qualified_name}' on startup. Saving current state..."
                )
                savable.save()
            except Exception as e:
                # No special handling, just log
                logger.exception(f"Failed to generate '{savable.qualified_name}' on startup")

        if error_popup_message:
            ui_bpy.show_message_box(
                error_popup_message,
                title=f"{type(savable).addon_name}: {savable.config_name}",
                icon='ERROR',
                max_chars=100,
            )

    bpy.app.timers.register(
        load,
        first_interval=0,  # type: ignore
        persistent=True,  # type: ignore
    )
