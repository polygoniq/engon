#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import addon_utils
import datetime
import functools
import hashlib
import json
import multiprocessing
import os
import platform
import socket
import traceback
import typing
import uuid
import enum
import threading
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


API_VERSION = 2

# useful for debugging
PRINT_MESSAGES = False

BOOTSTRAPPED = False
BOOTSTRAP_LOCK = threading.Lock()
SESSION = None
MACHINE = None
MESSAGES = []


class VerboseLevel(enum.IntEnum):
    """Determines what messages are printed to console when logging
    Lower number -> Lower restrictions (DEBUG includes all categories)
    """
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    NONE = 4


VERBOSE_LEVEL = getattr(VerboseLevel, os.environ.get("PQ_TELEMETRY", "WARNING"))


class Session:
    def __init__(self):
        self._uuid = uuid.uuid4().hex
        self.telemetry_api_version = API_VERSION
        self.telemetry_implementation_path = os.path.abspath(__file__)
        self.start_timestamp = datetime.datetime.utcnow().isoformat()


class Machine:
    def __init__(self):
        def safe_get(fn, default="N/A"):
            """Run given functor to retrieve data. Catch all exceptions and provide
            a default value in case of failure.
            """
            try:
                return fn()
            except:
                return default

        self._uuid = uuid.UUID(int=uuid.getnode()).hex

        self.hardware = {
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": multiprocessing.cpu_count(),
        }

        self.operating_system = (platform.system(), platform.release(), platform.version())

        self.networking = {
            "hostname": safe_get(lambda: socket.gethostname()),
            "ip-address": safe_get(lambda: socket.gethostbyname(socket.gethostname())),
            "has-ipv6": socket.has_ipv6,
        }

        self.python = {
            "version": platform.python_version(),
            "build": platform.python_build(),
        }

        self.blender = {
            "version": bpy.app.version_string,
            "path": bpy.app.binary_path,
            "window_size": Machine.get_blender_window_size(),
        }

    @staticmethod
    def get_blender_window_size():
        width = -1
        height = -1

        try:
            width = int(bpy.context.window_manager.windows[0].width)
            height = int(bpy.context.window_manager.windows[0].height)
        except:
            pass

        return width, height

    @staticmethod
    def get_blender_addons() -> typing.Dict[str, typing.Union[typing.List[str], typing.Dict[str, typing.Any]]]:
        addon_utils_modules: typing.Dict[str, typing.Dict[str, typing.Any]] = {}
        for module in addon_utils.modules():
            try:
                name = module.__name__
                assert name not in addon_utils_modules
                bl_info = getattr(module, "bl_info", {})
                path = str(module.__file__)
                addon_utils_modules[name] = {
                    "path": path,
                    "bl_info": bl_info
                }

            except Exception as e:
                addon_utils_modules[uuid.uuid4().hex] = {
                    "error": f"Uncaught Exception while querying modules: {e}"
                }

        loaded_modules = []
        missing_modules = []

        for addon in bpy.context.preferences.addons:
            loaded_default, loaded_state = addon_utils.check(addon.module)
            if not loaded_default:
                continue

            if loaded_state:
                loaded_modules.append(str(addon.module))
            else:
                missing_modules.append(str(addon.module))

        return {
            "loaded": loaded_modules,
            "missing": missing_modules,
            "addon_utils_modules": addon_utils_modules
        }


class MessageType:
    SESSION_STARTED = "session_started"
    MACHINE_REGISTERED = "machine_registered"
    # this is used by polygoniq addons to report version, etc...
    ADDON_REPORTED = "addon_reported"
    # this reports all registered addons, polygoniq or other vendors
    ALL_ADDONS_REPORTED = "all_addons_reported"
    UNCAUGHT_EXCEPTION = "uncaught_exception"
    WARNING_MESSAGE = "warning_message"
    ERROR_MESSAGE = "error_message"
    DEBUG_MESSAGE = "debug_message"


class Message:
    def __init__(self, type: str, data: typing.Any = None, text: typing.Optional[str] = None, product: str = "unknown"):
        self._session_uuid: str = "unknown"

        self._timestamp = datetime.datetime.utcnow().isoformat()
        self._type = type
        self.data: typing.Any = None
        if text is not None:
            assert data is None
            self.data = {"text": text}
        else:
            self.data = data
        self.product = product


class PrivateWrapper:
    """Used to wrap private data such as object names in a way that can be recovered
    locally but is hidden when telemetry is sent remotely.

    This allows more information to be used in local debugging without leaking
    users scene.
    """

    def __init__(self, value: str):
        self.value = value

    @property
    def private_value(self):
        return "private:" + hashlib.sha256(self.value.encode("utf-8")).hexdigest()


class TelemetryJSONEncoder(json.JSONEncoder):
    def default(self, obj: typing.Any) -> typing.Any:
        if isinstance(obj, Machine):
            altered_dict = obj.__dict__.copy()
            altered_dict["__class__"] = "telemetry.Machine"
            return altered_dict

        elif isinstance(obj, Session):
            altered_dict = obj.__dict__.copy()
            altered_dict["__class__"] = "telemetry.Session"
            return altered_dict

        elif isinstance(obj, Message):
            altered_dict = obj.__dict__.copy()
            altered_dict["__class__"] = "telemetry.Message"
            return altered_dict

        elif isinstance(obj, PrivateWrapper):
            return obj.value

        return json.JSONEncoder.default(self, obj)


class RemoteTelemetryJSONEncoder(TelemetryJSONEncoder):
    def default(self, obj: typing.Any) -> typing.Any:
        if isinstance(obj, PrivateWrapper):
            return obj.private_value

        return TelemetryJSONEncoder.default(self, obj)


def _log(msg: Message) -> None:
    global SESSION
    global MESSAGES
    global PRINT_MESSAGES

    if SESSION is not None:
        msg._session_uuid = SESSION._uuid

    MESSAGES.append(msg)
    if PRINT_MESSAGES:
        print(json.dumps(msg, indent=4, sort_keys=True, cls=TelemetryJSONEncoder))


def log_installed_addons() -> None:
    global MACHINE
    assert MACHINE is not None, "logging before telemetry has been bootstrapped!"

    _log(Message(MessageType.ALL_ADDONS_REPORTED, data=Machine.get_blender_addons(), product="polib"))


def bootstrap_telemetry():
    global BOOTSTRAPPED
    global BOOTSTRAP_LOCK
    global MACHINE
    global SESSION

    # it is very unlikely but 2 addons might concurrently bootstrap telemetry which
    # would result in multiple machine definitions and overwrites
    with BOOTSTRAP_LOCK:
        if BOOTSTRAPPED:
            return
            # due to reloading of modules this can happen multiple times!
            # raise RuntimeError("Telemetry already bootstrapped!")

        SESSION = Session()
        _log(Message(MessageType.SESSION_STARTED, data=SESSION, product="polib"))

        MACHINE = Machine()
        _log(Message(MessageType.MACHINE_REGISTERED, data=MACHINE, product="polib"))

        # wait 5 seconds to give all addons time to register
        bpy.app.timers.register(lambda: log_installed_addons(), first_interval=5)

        BOOTSTRAPPED = True


class TelemetryWrapper:
    def __init__(self, product: str):
        self.product = product
        self.PrivateWrapper = PrivateWrapper

    def log(self, msg: Message) -> None:
        _log(msg)

    def dump(self) -> str:
        global MESSAGES
        return json.dumps(MESSAGES, indent=4, sort_keys=True, cls=TelemetryJSONEncoder)

    def report_addon(self, bl_info, init_path: str) -> None:
        data = {}
        data["__init__path"] = os.path.abspath(init_path)
        data["name"] = bl_info["name"]
        data["version"] = bl_info["version"]
        self.log(Message(MessageType.ADDON_REPORTED, data=data, product=self.product))

    def log_exception(self, e: Exception) -> None:
        """Deprecated!

        Use the python logging module (logger.exception) instead..
        """
        self.log(
            Message(
                MessageType.UNCAUGHT_EXCEPTION,
                data=traceback.format_exception(type(e), e, e.__traceback__),
                product=self.product
            )
        )

    def exception(self, f):
        """A decorator that wraps the passed in function and logs
        exceptions in telemetry should they occur
        """
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Uncaught exception raised in {f}")
                raise e
        return wrapped

    def log_warning(self, message: str) -> None:
        """Deprecated!

        Use the python logging module (logger.warning) instead..
        """

        global VERBOSE_LEVEL

        self.log(
            Message(
                MessageType.WARNING_MESSAGE,
                data=[message] + traceback.extract_stack().format(),
                product=self.product
            )
        )
        if VERBOSE_LEVEL <= VerboseLevel.WARNING:
            print(f"WARNING[{self.product}]: {message}")

    def log_debug(self, message: str) -> None:
        """Deprecated!

        Use the python logging module (logger.debug) instead..
        """
        global VERBOSE_LEVEL

        self.log(
            Message(
                MessageType.DEBUG_MESSAGE,
                data=[message] + traceback.extract_stack().format(),
                product=self.product
            )
        )
        if VERBOSE_LEVEL <= VerboseLevel.DEBUG:
            print(f"DEBUG[{self.product}]: {message}")

    def log_error(self, message: str) -> None:
        """Deprecated!

        Use the python logging module (logger.error) instead..
        """
        global VERBOSE_LEVEL

        self.log(
            Message(
                MessageType.ERROR_MESSAGE,
                data=[message] + traceback.extract_stack().format(),
                product=self.product
            )
        )
        if VERBOSE_LEVEL <= VerboseLevel.ERROR:
            print(f"ERROR[{self.product}]: {message}")

    def wrap_blender_class(self, cls_):
        if hasattr(cls_, "__init__"):
            cls_.__init__ = self.exception(cls_.__init__)

        # we have to use these wrappers because bpy doesn't accept decorators for some reason
        # shows up as "ValueError: expected Operator, ... class "draw" function to have 2 args, found 0"
        def draw_wrapper(self_, context):
            try:
                return self_._original_draw(context)
            except Exception as e:
                logger.exception(f"Uncaught exception raised in {cls_}.draw")
                raise e

        def invoke_wrapper(self_, context, event):
            try:
                return self_._original_invoke(context, event)
            except Exception as e:
                logger.exception(f"Uncaught exception raised in {cls_}.invoke")
                raise e

        def execute_wrapper(self_, context):
            try:
                return self_._original_execute(context)
            except Exception as e:
                logger.exception(f"Uncaught exception raised in {cls_}.execute")
                raise e

        if hasattr(cls_, "draw"):
            if not hasattr(cls_, "_original_draw"):
                cls_._original_draw = cls_.draw
                cls_.draw = draw_wrapper

        if hasattr(cls_, "invoke"):
            if not hasattr(cls_, "_original_invoke"):
                cls_._original_invoke = cls_.invoke
                cls_.invoke = invoke_wrapper

        if hasattr(cls_, "execute"):
            if not hasattr(cls_, "_original_execute"):
                cls_._original_execute = cls_.execute
                cls_.execute = execute_wrapper

    def Message(self, type: str, data: typing.Any = None, text: typing.Optional[str] = None):
        return Message(type, data, text, self.product)


RETURNED_TELEMETRY_CLASSES: typing.Dict[str, TelemetryWrapper] = {}


def get_telemetry(product: str) -> TelemetryWrapper:
    global RETURNED_TELEMETRY_CLASSES

    if product in RETURNED_TELEMETRY_CLASSES:
        return RETURNED_TELEMETRY_CLASSES[product]
    else:
        RETURNED_TELEMETRY_CLASSES[product] = TelemetryWrapper(product)
        return RETURNED_TELEMETRY_CLASSES[product]


__all__ = ["API_VERSION", "bootstrap_telemetry", "get_telemetry"]
