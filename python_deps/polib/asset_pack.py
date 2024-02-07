#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import os
import re


def is_library_blend(path: str) -> bool:
    basename = os.path.basename(path)
    # lowercase letters and numbers for prefix, followed by _Library_
    # e.g. "mq_Library_NodeGroups.blend, am154_Library_Materials.blend"
    return re.match(r"^[a-z0-9]+_Library_.+\.blend$", basename) is not None
