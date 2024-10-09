#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import abc
import functools
from . import category
from . import asset
from . import asset_data
from . import query
from . import filters
from . import parameter_meta
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


class DataView:
    """One view of data - lists of assets based on provided Query and AssetProvider."""

    def __init__(self, asset_provider: 'AssetProvider', query_: query.Query):
        self.assets: typing.List[asset.Asset] = []
        for asset_ in asset_provider.list_assets(query_.category_id, query_.recursive):
            if all(f.filter_(asset_) for f in query_.filters):
                self.assets.append(asset_)

        sort_lambda, reverse = self._get_sort_parameters(query_.sort_mode)
        self.assets.sort(key=lambda x: sort_lambda(x), reverse=reverse)

        self.parameters_meta = parameter_meta.AssetParametersMeta(self.assets)
        self.used_query = query_
        logger.debug(f"Created DataView {self}")

    def _get_sort_parameters(
        self, sort_mode: str
    ) -> typing.Tuple[typing.Callable[[asset.Asset], str], bool]:
        """Return lambda and reverse bool to pass into Python sort() based on sort mode

        Returns tuple of (lambda, reverse)
        """
        if sort_mode == query.SortMode.ALPHABETICAL_ASC:
            return (lambda x: x.title, False)
        elif sort_mode == query.SortMode.ALPHABETICAL_DESC:
            return (lambda x: x.title, True)
        elif sort_mode == query.SortMode.MOST_RELEVANT:
            return (lambda x: filters.SEARCH_ASSET_SCORE.get(x.id_, 1.0), True)
        else:
            raise NotImplementedError(f"Unknown sort mode {sort_mode}")

    def __repr__(self) -> str:
        return (
            f"DataView at {id(self)} based on query:\n {self.used_query} "
            f"containing {len(self.assets)} assets"
        )


class EmptyDataView(DataView):
    """Data view containing no data - useful on places, where DataView cannot be constructed yet."""

    def __init__(self):
        self.assets = []
        self.parameters_meta = parameter_meta.AssetParametersMeta(self.assets)
        self.used_query = None
        logger.debug(f"Created EmptyDataView {self}")


class AssetProvider(abc.ABC):
    def __init__(self):
        pass

    def get_root_category_id(self) -> category.CategoryID:
        """Get the ID of the root category

        You can list categories provided by this asset provider by listing child categories of the
        root category.

        There can only be one root category. The asset provider is not required to return valid
        metadata for the root category, it is a special category serving as a common root between
        multiple asset providers.

        This is intended as a final method, should not be overridden!
        """

        return "/"

    @abc.abstractmethod
    def list_child_category_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[category.CategoryID]:
        """Lists IDs of all categories that are direct children of given parent category

        This is low level API, consider using list_categories instead of this.
        """
        pass

    @abc.abstractmethod
    def list_child_asset_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[asset.AssetID]:
        """Lists IDs of all assets that are direct children of given parent category

        This is low level API, consider using list_assets instead of this.
        """
        pass

    @abc.abstractmethod
    def list_asset_data_ids(
        self, asset_id: asset.AssetID
    ) -> typing.Iterable[asset_data.AssetDataID]:
        """List all asset data IDs of given asset ID.

        This is low level API, consider using list_asset_data instead of this.
        """
        pass

    @abc.abstractmethod
    def get_category(self, category_id: category.CategoryID) -> typing.Optional[category.Category]:
        """Returns metadata of a category with given ID"""
        pass

    @abc.abstractmethod
    def get_asset(self, asset_id: asset.AssetID) -> typing.Optional[asset.Asset]:
        """Returns metadata of an asset with given ID"""
        pass

    @abc.abstractmethod
    def get_asset_data(
        self, asset_data_id: asset_data.AssetDataID
    ) -> typing.Optional[asset_data.AssetData]:
        """Returns metadata of asset data with given ID"""
        pass

    def query(self, query_: query.Query) -> DataView:
        """Queries the asset provider for assets based on given query

        This is a high level API, consider using this instead of list_assets.
        """
        return DataView(self, query_)

    def list_categories(
        self, parent_id: category.CategoryID, recursive: bool = False
    ) -> typing.Iterable[category.Category]:
        """List child categories of a given parent category

        parent_id: ID of the parent category, see get_root_category_id
        recursive: if False we only list direct children, if True we list all descendant categories
        """
        for id_ in self.list_child_category_ids(parent_id):
            category_ = self.get_category(id_)
            if category_ is not None:
                yield category_
            if recursive:
                yield from self.list_categories(id_, True)

    def list_sorted_categories(
        self, parent_id: category.CategoryID, recursive: bool = False
    ) -> typing.Iterable[category.Category]:
        yield from sorted(self.list_categories(parent_id), key=lambda x: x.title)

    def get_category_id_from_string(self, category_id_str: str) -> category.CategoryID:
        """Finds category ID provided based on given 'category_id_str'

        If no category with 'category_id_str' as id is found, then root category is returned.
        """
        category_ = self.get_category(category_id_str)
        if category_ is None:
            return self.get_root_category_id()

        return category_.id_

    def get_category_safe(self, category_id: category.CategoryID) -> category.Category:
        """Returns category based on 'category_id' if no such category found returns root category

        If no category is found - for example with no provider registered, this returns the
        default root category defined by mapr.
        """
        category_ = self.get_category(category_id)
        if category_ is None:
            # As a fallback try to return root category from the provider
            root_category = self.get_category(self.get_root_category_id())
            if root_category is None:
                # If no root category is found (in case of no providers), return DEFAULT_ROOT_CATEGORY
                # instead of returning None
                return category.DEFAULT_ROOT_CATEGORY
            else:
                return root_category

        return category_

    def list_assets(
        self, parent_id: category.CategoryID, recursive: bool = False
    ) -> typing.Iterable[asset.Asset]:
        """List child assets of a given parent category

        parent_id: ID of the parent category, see get_root_category_id
        recursive: if False we only list direct children, if True we list assets contained in this
                   and all descendant categories
        """
        for id_ in self.list_child_asset_ids(parent_id):
            asset_ = self.get_asset(id_)
            if asset_ is not None:
                yield asset_

        if recursive:
            for id_ in self.list_child_category_ids(parent_id):
                yield from self.list_assets(id_, True)

    def list_asset_data(self, asset_id: asset.AssetID) -> typing.Iterable[asset_data.AssetData]:
        """Lists asset data of given asset"""
        for id_ in self.list_asset_data_ids(asset_id):
            asset_data_ = self.get_asset_data(id_)
            if asset_data_ is not None:
                yield asset_data_


class AssetProviderMultiplexer(AssetProvider):
    """Allows you to add multiple asset providers and treat them as one asset provider.

    If two providers contain the same category ID the categories are equivalent and will be merged.
    The first asset provider that contains category metadata provides it.
    """

    def __init__(self):
        super().__init__()
        self._asset_providers: typing.List[AssetProvider] = []

    def add_asset_provider(self, asset_provider: AssetProvider) -> None:
        self._asset_providers.append(asset_provider)

    def remove_asset_provider(self, asset_provider: AssetProvider) -> None:
        self._asset_providers.remove(asset_provider)

    def clear_providers(self) -> None:
        self._asset_providers.clear()

    def list_child_category_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[category.CategoryID]:
        # Two different asset providers can provide the same CategoryID, for example
        # botaniq/deciduous coming from core botaniq and an asset pack. That's why we have to
        # deduplicate the result.
        ret: typing.Set[category.CategoryID] = set()
        for asset_provider in self._asset_providers:
            ret.update(asset_provider.list_child_category_ids(parent_id))
        yield from ret

    def list_child_asset_ids(
        self, parent_id: category.CategoryID
    ) -> typing.Iterable[asset.AssetID]:
        # We assume no two asset providers provide the same AssetID
        for asset_provider in self._asset_providers:
            yield from asset_provider.list_child_asset_ids(parent_id)

    def list_asset_data_ids(self, asset_id: asset.AssetID) -> typing.Iterable[asset.AssetID]:
        # We assume no two asset providers provide the same AssetDataID
        for asset_provider in self._asset_providers:
            yield from asset_provider.list_asset_data_ids(asset_id)

    def get_category(self, category_id: category.CategoryID) -> typing.Optional[category.Category]:
        # TODO: reversed because providers added later override, does that make sense?
        for asset_provider in reversed(self._asset_providers):
            ret = asset_provider.get_category(category_id)
            if ret is not None:
                return ret
        return None

    def get_asset(self, asset_id: asset.AssetID) -> typing.Optional[asset.Asset]:
        # TODO: reversed because providers added later override, does that make sense?
        for asset_provider in reversed(self._asset_providers):
            ret = asset_provider.get_asset(asset_id)
            if ret is not None:
                return ret
        return None

    def get_asset_data(
        self, asset_data_id: asset_data.AssetDataID
    ) -> typing.Optional[asset_data.AssetData]:
        # TODO: reversed because providers added later override, does that make sense?
        for asset_provider in reversed(self._asset_providers):
            ret = asset_provider.get_asset_data(asset_data_id)
            if ret is not None:
                return ret
        return None


class CachedAssetProviderMultiplexer(AssetProviderMultiplexer):
    """Wraps the 'query' call and caches the results using LRU cache."""

    def __init__(self, maxsize: int = 128):
        super().__init__()
        # Create 'cached_query' method wrapped with lru_cache for each instance of the
        # cached asset provider, that wraps the actual call to self._cached_query.
        # The decorator version keeps hard reference to self, which may cause memory leaks
        # when the instances are deleted.
        # More info: https://rednafi.com/python/lru_cache_on_methods/
        self.query = functools.lru_cache(maxsize=maxsize)(self._cached_query)

    def add_asset_provider(self, asset_provider: AssetProvider) -> None:
        super().add_asset_provider(asset_provider)
        self.clear_cache()

    def remove_asset_provider(self, asset_provider: AssetProvider) -> None:
        super().remove_asset_provider(asset_provider)
        self.clear_cache()

    def clear_providers(self) -> None:
        super().clear_providers()
        self.clear_cache()

    def _cached_query(self, query_: query.Query) -> DataView:
        logger.debug(f"Cache miss for query {query_}, querying...")
        return super().query(query_)

    def clear_cache(self) -> None:
        self.query.cache_clear()
