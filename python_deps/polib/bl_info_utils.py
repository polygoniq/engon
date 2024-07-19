# copyright (c) 2018- polygoniq xyz s.r.o.

import ast
import re
import typing
import zipfile
import pathlib

BL_INFO_REGEX = r"^bl_info[\s]*=[\s]*(\{[^\}]*\})"


def find_bl_info_in_string(input: str) -> typing.Optional[typing.Dict[str, typing.Any]]:
    match = re.search(BL_INFO_REGEX, input, flags=re.MULTILINE)
    if not match:
        return None

    # Use ast.literal_eval as it restricts evaluation only to literal structures
    # https://docs.python.org/3/library/ast.html#ast.literal_eval
    return ast.literal_eval(match.group(1))


def get_bl_info_from_init_py(init_py_path: str) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Retrieves the bl_info dictionary of given __init__.py file without running it. It only
    evaluates the bl_info dictionary itself. Assumes that bl_info is self-contained. This is
    the same assumption that Blender itself requires.
    """

    with open(init_py_path) as f:
        src = f.read()

    return find_bl_info_in_string(src)


def infer_version_from_bl_info(init_py_path: str) -> typing.Optional[typing.Tuple[int, int, int]]:
    """Figures out the version of given __init__.py file without running the whole thing. Returns
    None in case of failure.
    """

    bl_info = get_bl_info_from_init_py(init_py_path)
    if bl_info is None:
        return None

    return bl_info.get("version")


def infer_version_from_bl_info_from_zip_file(
    zip_file_path: str,
) -> typing.Optional[typing.Tuple[int, int, int]]:
    if not zipfile.is_zipfile(zip_file_path):
        return None

    zip_file = zipfile.ZipFile(zip_file_path, 'r')
    # Find the root __init__.py file
    root_init_py_path = None
    for file_ in zip_file.namelist():
        path = pathlib.Path(file_)
        # one part for the root folder, second for the __init__.py itself
        if len(path.parts) == 2 and path.name == "__init__.py":
            root_init_py_path = file_
            break

    assert root_init_py_path is not None

    with zip_file.open(root_init_py_path) as zf:
        src = zf.read().decode()

    bl_info = find_bl_info_in_string(src)
    if bl_info is None:
        return None

    return bl_info.get("version")
