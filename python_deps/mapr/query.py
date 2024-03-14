# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import json
from . import category
from . import filters


class SortMode:
    ALPHABETICAL_ASC = "ABC (A)"
    ALPHABETICAL_DESC = "ABC (D)"


class Query:
    def __init__(
        self,
        category_id: category.CategoryID,
        filters: typing.Iterable[filters.Filter],
        sort_mode: str,
        recursive: bool = True,
    ):
        self.category_id = category_id
        self.filters = list(filters)
        self.sort_mode = sort_mode
        self.recursive = recursive
        # We need to construct the dict representation of the query when it is initialized
        # because we reference the filters and those can change (mutate) after the Query is
        # constructed. Resulting in values provided by the filters being always equal to the filters
        # dict representation when the query would be converted to dict.
        self._dict = self._as_dict()

    def _as_dict(self) -> typing.Dict:
        ret = {}
        ret["category_id"] = self.category_id
        ret["recursive"] = self.recursive
        ret["sort_mode"] = self.sort_mode
        for filter_ in self.filters:
            ret.update(filter_.as_dict())

        return ret

    def __hash__(self) -> int:
        return hash(json.dumps(self._dict))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Query):
            return self._dict == other._dict

        return False

    def __repr__(self) -> str:
        return str(self._dict)
