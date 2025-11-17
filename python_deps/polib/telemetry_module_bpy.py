#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import addon_utils
import datetime
import json
import multiprocessing
import os
import platform
import socket
import typing
import uuid
import enum
import threading
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


API_VERSION = 2

# useful for debugging
PRINT_MESSAGES = False


class Session:
    def __init__(self):
        self._uuid = uuid.uuid4().hex
        self.telemetry_api_version = API_VERSION
        self.telemetry_implementation_path = os.path.abspath(__file__)
        self.start_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()


class Machine:
    def __init__(self):
        def safe_get(fn, default="N/A") -> str:
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
    def get_blender_window_size() -> tuple[int, int]:
        width = -1
        height = -1

        try:
            width = int(bpy.context.window_manager.windows[0].width)
            height = int(bpy.context.window_manager.windows[0].height)
        except:
            pass

        return width, height

    @staticmethod
    def get_blender_addons() -> dict[str, list[str] | dict[str, typing.Any]]:
        addon_utils_modules: dict[str, dict[str, typing.Any]] = {}
        for module in addon_utils.modules():
            try:
                name = module.__name__
                assert name not in addon_utils_modules
                bl_info = getattr(module, "bl_info", {})
                path = str(module.__file__)
                addon_utils_modules[name] = {"path": path, "bl_info": bl_info}

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
            "addon_utils_modules": addon_utils_modules,
        }


class MessageType(enum.StrEnum):
    SESSION_STARTED = "session_started"
    MACHINE_REGISTERED = "machine_registered"
    # this is used by polygoniq addons to report version, etc...
    ADDON_REPORTED = "addon_reported"
    # this reports all registered addons, polygoniq or other vendors
    ALL_ADDONS_REPORTED = "all_addons_reported"


class Message:
    def __init__(
        self,
        type: MessageType,
        data: typing.Any = None,
        text: str | None = None,
        product: str = "unknown",
    ):
        self._session_uuid: str = "unknown"

        self._timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._type = type
        self.data: typing.Any = None
        if text is not None:
            assert data is None
            self.data = {"text": text}
        else:
            self.data = data
        self.product = product


BOOTSTRAPPED = False
BOOTSTRAP_LOCK = threading.Lock()
SESSION: Session | None = None
MACHINE: Machine | None = None
MESSAGES: list[Message] = []


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

        return json.JSONEncoder.default(self, obj)


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

    _log(
        Message(MessageType.ALL_ADDONS_REPORTED, data=Machine.get_blender_addons(), product="polib")
    )


def bootstrap_telemetry() -> None:
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
        bpy.app.timers.register(lambda: log_installed_addons(), first_interval=5, persistent=True)

        BOOTSTRAPPED = True


class TelemetryWrapper:
    def __init__(self, product: str):
        self.product = product

    def dump(self) -> str:
        global MESSAGES
        return json.dumps(MESSAGES, indent=4, sort_keys=True, cls=TelemetryJSONEncoder)

    def report_addon(self, bl_info, init_path: str) -> None:
        data = {}
        data["__init__path"] = os.path.abspath(init_path)
        data["name"] = bl_info["name"]
        data["version"] = bl_info["version"]
        _log(Message(MessageType.ADDON_REPORTED, data=data, product=self.product))


RETURNED_TELEMETRY_CLASSES: dict[str, TelemetryWrapper] = {}


def get_telemetry(product: str) -> TelemetryWrapper:
    global RETURNED_TELEMETRY_CLASSES

    if product in RETURNED_TELEMETRY_CLASSES:
        return RETURNED_TELEMETRY_CLASSES[product]
    else:
        RETURNED_TELEMETRY_CLASSES[product] = TelemetryWrapper(product)
        return RETURNED_TELEMETRY_CLASSES[product]


__all__ = ["API_VERSION", "bootstrap_telemetry", "get_telemetry"]
