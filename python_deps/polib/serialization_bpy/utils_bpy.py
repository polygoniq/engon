# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import logging
import typing
from . import io_bpy

logger = logging.getLogger(f"polygoniq.{__name__}")


def post_register_load(savable_getter: typing.Callable[[], io_bpy.Savable]) -> None:
    """This will register timer that will load the `Savable` class right
    after `register()` is finished.
    """

    def load():
        try:
            savable = savable_getter()
            if savable.save_file_exists():
                savable.load()
                logger.info(f"Loaded '{savable.addon_name}.{savable.config_name}' on startup.")
            else:
                logger.info(
                    f"No save file found for '{savable.addon_name}.{savable.config_name}' on startup."
                )
        except Exception as e:
            logger.exception("Failed to load savable on startup")

    bpy.app.timers.register(
        load,
        first_interval=0,  # type: ignore
        persistent=True,  # type: ignore
    )
