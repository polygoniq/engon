#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import datetime
import glob
import tempfile
import typing
import time
import logging
import logging.handlers
import os
import shutil
from . import telemetry_module_bpy

LOG_BACKUP_COUNT = (
    2  # Number of backup log files from one session (1 file per hour from TimedRotatingFileHandler)
)
LOG_FILE_RETENTION_DAYS = 7  # Number of days to keep log files from previous sessions


def try_initialize_addon_logging(logger: logging.Logger, from_module: str, from_file: str) -> None:
    root_logger = logging.getLogger("polygoniq")
    if getattr(root_logger, "polygoniq_initialized", False):
        return

    log_dir = os.path.join(tempfile.gettempdir(), "polygoniq_logs")
    # Delete old log files from previous sessions
    for old_file in glob.glob(os.path.join(log_dir, "blender_addons*.txt*")):
        try:
            if (
                time.time() - os.path.getmtime(old_file)
                > datetime.timedelta(days=LOG_FILE_RETENTION_DAYS).total_seconds()
            ):
                os.remove(old_file)
        except OSError:
            pass
    # Setup root logger with a formatter, filter and handlers
    root_logger_formatter = logging.Formatter(
        "P%(process)d:%(asctime)s:%(name)s:%(levelname)s: [%(filename)s:%(lineno)d] %(message)s",
        "%H:%M:%S",
    )
    _pq_base_level = logging.INFO
    try:
        _pq_base_level = int(os.environ.get("POLYGONIQ_LOG_LEVEL", logging.INFO))
    except (ValueError, TypeError):
        pass
    _pq_debug_modules = [
        m.strip() for m in os.environ.get("POLYGONIQ_LOG_DEBUG_MODULES", "").split(",") if m.strip()
    ]

    class _PolygoniqLogFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.levelno >= _pq_base_level:
                return True
            if record.levelno == logging.DEBUG and len(_pq_debug_modules) > 0:
                return any(module in record.name for module in _pq_debug_modules)
            return False

    _pq_log_filter = _PolygoniqLogFilter()

    root_logger.setLevel(logging.DEBUG)
    root_logger.propagate = False
    root_logger_stream_handler = logging.StreamHandler()
    root_logger_stream_handler.setFormatter(root_logger_formatter)
    root_logger_stream_handler.addFilter(_pq_log_filter)
    root_logger.addHandler(root_logger_stream_handler)

    try:
        os.makedirs(log_dir, exist_ok=True)
        root_logger_handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, f"blender_addons_p{os.getpid()}.txt"),
            when="H",
            interval=1,
            backupCount=LOG_BACKUP_COUNT,
            utc=True,
        )
        root_logger_handler.setFormatter(root_logger_formatter)
        root_logger_handler.addFilter(_pq_log_filter)
        root_logger.addHandler(root_logger_handler)
    except:
        logger.exception(
            f"Can't create rotating log handler for polygoniq root logger "
            f"in module \"{from_module}\", file \"{from_file}\""
        )
    setattr(root_logger, "polygoniq_initialized", True)
    logger.info(
        f"polygoniq root logger initialized in module \"{from_module}\", file \"{from_file}\" -----"
    )


def logged_operator(cls: type[bpy.types.Operator]):
    assert issubclass(
        cls, bpy.types.Operator
    ), "logged_operator only accepts classes inheriting bpy.types.Operator"

    logger = logging.getLogger(f"polygoniq.{cls.__module__}")

    if hasattr(cls, "poll"):
        cls._original_poll = cls.poll

        @classmethod
        def new_poll(klass, context: bpy.types.Context):
            try:
                return cls._original_poll(context)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.poll",
                    extra={
                        "_log_data": {
                            "event": "operator_poll_exception",
                            "operator": cls.bl_idname,
                        },
                    },
                )
                return False

        cls.poll = new_poll

    if hasattr(cls, "draw"):
        cls._original_draw = cls.draw

        def new_draw(self, context: bpy.types.Context):
            try:
                return cls._original_draw(self, context)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.draw",
                    extra={
                        "_log_data": {
                            "event": "operator_draw_exception",
                            "operator_args": self.as_keywords(),
                            "operator": cls.bl_idname,
                        },
                    },
                )

        cls.draw = new_draw

    if hasattr(cls, "modal"):
        cls._original_modal = cls.modal

        def new_modal(self, context: bpy.types.Context, event: bpy.types.Event):
            try:
                return cls._original_modal(self, context, event)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.modal",
                    extra={
                        "_log_data": {
                            "event": "operator_modal_exception",
                            "event_type": event.type,
                            "operator": cls.bl_idname,
                        },
                    },
                )
                # If exception is thrown out of the modal we want to exit it. If there are possible
                # exceptions that can occur, they should be handled in the modal itself.
                return {'FINISHED'}

        cls.modal = new_modal

    if hasattr(cls, "execute"):
        cls._original_execute = cls.execute

        def new_execute(self, context: bpy.types.Context):
            logger.info(
                f"{cls.__name__} operator execute started with arguments {self.as_keywords()}"
            )
            start_time = time.time()
            try:
                ret = cls._original_execute(self, context)
                execute_time = time.time() - start_time
                logger.info(
                    f"{cls.__name__} operator execute finished in {execute_time:.3f} "
                    f"seconds with result {ret}",
                    extra={
                        "_log_data": {
                            "event": "operator_execute",
                            "operator": cls.bl_idname,
                            "result": ret,
                            "execute_time": execute_time,
                            "operator_args": self.as_keywords(),
                        },
                    },
                )
                return ret
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.execute",
                    extra={
                        "_log_data": {
                            "event": "operator_exception",
                            "operator": cls.bl_idname,
                        },
                    },
                )
                # We return finished even in case an error happened, that way the user will be able
                # to undo any changes the operator has made up until the error happened
                return {'FINISHED'}

        cls.execute = new_execute

    if hasattr(cls, "invoke"):
        cls._original_invoke = cls.invoke

        def new_invoke(self, context: bpy.types.Context, event: bpy.types.Event):
            logger.debug(f"{cls.__name__} operator invoke started")
            try:
                ret = cls._original_invoke(self, context, event)
                logger.info(
                    f"{cls.__name__} operator invoke finished",
                    extra={
                        "_log_data": {
                            "event": "operator_invoke",
                            "operator": cls.bl_idname,
                            "invoke_result": ret,
                            "operator_args": self.as_keywords(),
                        },
                    },
                )
                return ret
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.invoke",
                    extra={
                        "_log_data": {
                            "event": "operator_invoke_exception",
                            "operator": cls.bl_idname,
                        },
                    },
                )
                # We return finished even in case an error happened, that way the user will be able
                # to undo any changes the operator has made up until the error happened
                return {'FINISHED'}

        cls.invoke = new_invoke

    # The 'report' method is defined in C API and cannot be wrapped like the previous methods
    # We have to use custom __getattribute__ hack to achieve it
    original_getattribute = cls.__getattribute__

    def new_getattribute(self, name: str) -> typing.Any:
        if name == "report":
            orig_report = original_getattribute(self, name)

            def new_report(type_: set[str], message: str) -> None:
                type_value = list(type_)[0]
                type_value_log_fn_map = {
                    'ERROR': logger.error,
                    'WARNING': logger.warning,
                    'DEBUG': logger.debug,
                    'INFO': logger.info,
                }
                # There are Blender report types starting with "ERROR"
                if type_value.startswith("ERROR"):
                    log_fn = logger.error
                else:
                    log_fn = type_value_log_fn_map.get(type_value, logger.info)
                log_fn(f"{cls.__name__} operator report: {message}")
                return orig_report(type_, message)

            return new_report
        return original_getattribute(self, name)

    cls.__getattribute__ = new_getattribute

    return cls


def logged_panel(cls: type[bpy.types.Panel]):
    assert issubclass(
        cls, bpy.types.Panel
    ), "logged_panel only accepts classes inheriting bpy.types.Panel"

    logger = logging.getLogger(f"polygoniq.{cls.__module__}")

    if hasattr(cls, "draw_header"):
        cls._original_draw_header = cls.draw_header

        def new_draw_header(self, context: bpy.types.Context):
            try:
                return cls._original_draw_header(self, context)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.draw_header",
                    extra={
                        "_log_data": {
                            "event": "panel_draw_header_exception",
                            "panel": cls.bl_idname,
                        },
                    },
                )

        cls.draw_header = new_draw_header

    if hasattr(cls, "draw"):
        cls._original_draw = cls.draw

        def new_draw(self, context: bpy.types.Context):
            try:
                return cls._original_draw(self, context)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.draw",
                    extra={
                        "_log_data": {
                            "event": "panel_draw_exception",
                            "panel": cls.bl_idname,
                        },
                    },
                )

        cls.draw = new_draw

    return cls


def logged_preferences(cls: type[bpy.types.AddonPreferences]):
    assert issubclass(
        cls, bpy.types.AddonPreferences
    ), "logged_preferences only accepts classes inheriting bpy.types.AddonPreferences"

    logger = logging.getLogger(f"polygoniq.{cls.__module__}")

    if hasattr(cls, "draw"):
        cls._original_draw = cls.draw

        def new_draw(self, context: bpy.types.Context):
            try:
                return cls._original_draw(self, context)
            except:
                logger.exception(
                    f"Uncaught exception raised in {cls}.draw",
                    extra={
                        "_log_data": {
                            "event": "prefs_draw_exception",
                            "prefs": cls.bl_idname,
                        },
                    },
                )

        cls.draw = new_draw

    return cls


def pack_logs(telemetry: telemetry_module_bpy.TelemetryWrapper) -> str:
    """Pack all logs into zip, create new timestamped directory in tempdir and save the zip there."""
    temp_folder = tempfile.gettempdir()
    log_path = os.path.join(temp_folder, "polygoniq_logs")
    os.makedirs(log_path, exist_ok=True)
    with open(os.path.join(log_path, "latest_telemetry.txt"), "w") as f:
        f.write(telemetry.dump())
    now = datetime.datetime.now()
    output_folder_name = f"polygoniq_logs--{now.year:04d}-{now.month:02d}-{now.day:02d}T{now.hour:02d}-{now.minute:02d}-{now.second:02d}"
    output_folder_path = os.path.join(temp_folder, output_folder_name)
    os.mkdir(output_folder_path)
    shutil.make_archive(os.path.join(output_folder_path, "polygoniq_logs"), "zip", log_path)
    return output_folder_path
