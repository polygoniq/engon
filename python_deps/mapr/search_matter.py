#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import collections
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


class SearchMatter:
    def __init__(self):
        self.tokens: typing.DefaultDict[str, float] = collections.defaultdict(float)

    def items(self):
        return self.tokens.items()

    def record_token(self, token: str, weight: float = 1.0) -> None:
        if weight <= 0.0:
            raise ValueError("Can't record a token with zero or negative weight")

        _token = token.lower()
        self.tokens[_token] = max(self.tokens[_token], weight)

    @functools.cached_property
    def search_matter(self) -> typing.DefaultDict[str, float]:
        """Return a dictionary of lowercase text searchable tokens, each mapped to its search weight

        Search weight 0 means excluded from search. Weight 1 is the default. Since tokens with
        weight 0 never contribute to the search we exclude them. We guarantee all tokens to map to
        weight > 0.
        """

        ret: typing.DefaultDict[str, float] = self.type_.search_matter
        ret[self.title.lower()] = max(1.0, ret[self.title.lower()])

        for tag in self.tags:
            search_weight = \
                float(known_metadata.TAGS.get(tag, {}).get("search_weight", 1.0))
            if search_weight <= 0.0:
                continue
            token = tag.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.text_parameters.items():
            search_weight = \
                float(known_metadata.TEXT_PARAMETERS.get(name, {}).get("search_weight", 1.0))
            if search_weight <= 0.0:
                continue
            token = value.lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.numeric_parameters.items():
            search_weight = \
                float(known_metadata.NUMERIC_PARAMETERS.get(name, {}).get("search_weight", 1.0))
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        for name, value in self.color_parameters.items():
            search_weight = \
                float(known_metadata.COLOR_PARAMETERS.get(name, {}).get("search_weight", 1.0))
            if search_weight <= 0.0:
                continue
            token = str(value).lower()
            ret[token] = max(search_weight, ret[token])

        return ret

    def clear_search_matter_cache(self) -> None:
        self.__dict__.pop("search_matter", None)
