#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import dataclasses
import typing
import logging
from . import file_provider

logger = logging.getLogger(f"polygoniq.{__name__}")


# Search weight of the category, used as 'foreign_search_matter' in `asset.py:Asset`.
TITLE_SEARCH_WEIGHT = 2.0


CategoryID = str


@dataclasses.dataclass(frozen=True)
class Category:
    id_: CategoryID = ""
    title: str = ""
    preview_file: typing.Optional[file_provider.FileID] = None


DEFAULT_ROOT_CATEGORY = Category(id_="/", title="All")


def infer_parent_category_id(category_id: CategoryID) -> CategoryID:
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
