#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import os
import re


def is_library_blend(path: str) -> bool:
    basename = os.path.basename(path)
    # this is the new convention, lowercase letters and numbers for prefix,
    # followed by _Library_, e.g. "mq_Library_NodeGroups.blend, am154_Library_Materials.blend"
    if re.match(r"^[a-z0-9]+_Library_.+\.blend$", basename) is not None:
        return True
    # old convention just started with Library_ with no prefix, e.g. Library_Botaniq_Materials.blend
    if basename.startswith("Library_"):
        return True
    return False
