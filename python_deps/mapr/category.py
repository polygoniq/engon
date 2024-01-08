#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
from . import file_provider
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


CategoryID = str


class Category:
    def __init__(self):
        self.id_: CategoryID = ""
        self.title: str = ""
        self.preview_file: typing.Optional[file_provider.FileID] = None


DEFAULT_ROOT_CATEGORY = Category()
DEFAULT_ROOT_CATEGORY.id_ = "/"
DEFAULT_ROOT_CATEGORY.title = "All"


def infer_parent_category_id(
    category_id: CategoryID
) -> CategoryID:
    """Infers parent category_id from 'category_id' by removing the last part.

    If root category provided then empty string is returned as there is nothing to split
    '/botaniq/coniferous' -> '/botaniq'
    '/' -> ''
    """
    if category_id == "/":
        return ""

    split = category_id.split("/")
    if len(split) == 1 or len(split) == 2:
        return "/"

    return "/".join(split[:-1])
