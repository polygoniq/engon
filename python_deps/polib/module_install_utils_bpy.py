# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import importlib
import importlib.util
import dataclasses
import sys
import os
import bpy
import logging
logger = logging.getLogger(__name__)


if "utils_bpy" not in locals():
    from . import utils_bpy
else:
    import importlib
    utils_bpy = importlib.reload(utils_bpy)


@dataclasses.dataclass
class RequiredModule:
    """Container class for defining required module names

    Example: RequiredModule("PIL.Image", "Pillow")
    """
    import_name: str  # Name used to import the module in source code
    install_name: str  # Name used to install the module with pip


class ModuleProvider:
    """Class that encapsulates installation of additional Python modules.

    It is supposed to be used as singleton with only one instance and one 'install_path'. Because
    all addons using ModuleProvider should install their dependencies to the same place.
    Otherwise they could install potentially incompatible modules.

    TODO: Adjust this after transition to engon
    Currently 'install_path' is stored in preferences in each addon using ModuleProvider and nothing
    enforces they store the same path. This will be inherently resolved after transition to one
    common addon - engon which would define only one 'install_path' property in preferences.
    It shouldn't be problem till that as we won't release multiple addons that needs additional
    modules before full transition to engon.
    """

    def __init__(self) -> None:
        self._install_path: typing.Optional[str] = None
        # Cache which allows fast query if module given by name is installed.
        # If module is not in the cache, we try to import it (which is slow) and then store boolean
        # indicating whether the module can be imported or not.
        self._installed_modules_cache: typing.Dict[str, bool] = {}

    def is_initialized(self) -> bool:
        return self._install_path is not None

    @property
    def install_path(self) -> str:
        if not self.is_initialized():
            raise RuntimeError("Accessing uninitialized install path in ModuleProvider!")
        assert self._install_path is not None
        return self._install_path

    @install_path.setter
    def install_path(self, value: str) -> None:
        if not os.path.isdir(value):
            raise ValueError("Provided install_path is not a valid, existing directory!")
        self._install_path = value
        # installed path changed, clear the cache of available modules
        self._installed_modules_cache.clear()

    def is_module_installed(self, module_name: str) -> bool:
        """Returns True if module is installed either in sys.path or in self.install_path
        """
        if module_name in self._installed_modules_cache:
            return self._installed_modules_cache[module_name]
        module_found = self._get_module_spec(module_name) is not None
        logger.debug(f"Module '{module_name}' was {'found' if module_found else 'not found'}")
        self._installed_modules_cache[module_name] = module_found
        return module_found

    def install_modules(self, module_install_names: typing.Iterable[str]) -> None:
        # Toggle console to show progress to users.
        # Console is available only on Windows :( and we can't check if it's already opened,
        # so we expect users don't have it usually opened.
        if sys.platform == "win32":
            bpy.ops.wm.console_toggle()
        python_exe = sys.executable
        logger.info(f"Preparing to install modules '{module_install_names}'")

        try:
            args = [python_exe, "-m", "ensurepip", "--default-pip"]
            logger.info(f"Running ensurepip")

            if utils_bpy.run_logging_subprocess(args) != 0:
                logger.error("Couldn't ensured pip in Blender's python!")

            for module_install_name in module_install_names:
                args = [python_exe, "-m", "pip", "install", "--upgrade",
                        module_install_name, "--target", self.install_path]
                logger.info(f"Installing '{module_install_name}'")

                if utils_bpy.run_logging_subprocess(args) == 0:
                    logger.info(f"Modules '{module_install_name}' successfully installed")
                    self._installed_modules_cache[module_install_name] = True
                else:
                    logger.error(f"Error occurred while installing '{module_install_name}' module!")

        finally:
            if sys.platform == "win32":
                bpy.ops.wm.console_toggle()

    def enable_module(self, module_name: str) -> None:
        """Stores module into sys.modules, so we can import it later from any other place
        """
        if module_name in sys.modules:
            return

        module_spec = self._get_module_spec(module_name)
        if module_spec is None:
            raise RuntimeError(f"Module {module_name} is not installed, can't enable it!")
        else:
            # Load module from module_spec
            import importlib

            try:
                was_in_path = self.install_path in sys.path
                if not was_in_path:
                    sys.path.insert(0, self.install_path)
                importlib.import_module(module_name)
                logger.debug(
                    f"Module '{module_name}' successfully enabled, it can be imported now!")
            finally:
                if not was_in_path and self.install_path in sys.path:
                    sys.path.remove(self.install_path)

    def _get_module_spec(self, module_name: str) -> typing.Optional[importlib.machinery.ModuleSpec]:
        was_in_path = self.install_path in sys.path
        try:
            if not was_in_path:
                sys.path.insert(0, self.install_path)

            return importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            # Module was found but it's not valid (doesn't contain __path__), we need to re-install
            return None
        finally:
            if not was_in_path and self.install_path in sys.path:
                sys.path.remove(self.install_path)
