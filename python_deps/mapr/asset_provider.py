#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import abc
from . import category
from . import asset
from . import asset_data
import logging
logger = logging.getLogger(f"polygoniq.{__name__}")


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
    def list_child_category_ids(self, parent_id: category.CategoryID) -> typing.Iterable[category.CategoryID]:
        """Lists IDs of all categories that are direct children of given parent category

        This is low level API, consider using list_categories instead of this.
        """
        pass

    @abc.abstractmethod
    def list_child_asset_ids(self, parent_id: category.CategoryID) -> typing.Iterable[asset.AssetID]:
        """Lists IDs of all assets that are direct children of given parent category

        This is low level API, consider using list_assets instead of this.
        """
        pass

    @abc.abstractmethod
    def list_asset_data_ids(self, asset_id: asset.AssetID) -> typing.Iterable[asset_data.AssetDataID]:
        """List all asset data IDs of given asset ID.

        This is low level API, consider using list_asset_data instead of this.
        """
        pass

    @abc.abstractmethod
    def get_category(self, category_id: category.CategoryID) -> typing.Optional[category.Category]:
        """Returns metadata of a category with given ID
        """
        pass

    @abc.abstractmethod
    def get_asset(self, asset_id: asset.AssetID) -> typing.Optional[asset.Asset]:
        """Returns metadata of an asset with given ID
        """
        pass

    @abc.abstractmethod
    def get_asset_data(self, asset_data_id: asset_data.AssetDataID) -> typing.Optional[asset_data.AssetData]:
        """Returns metadata of asset data with given ID
        """
        pass

    def list_categories(self, parent_id: category.CategoryID, recursive: bool = False) -> typing.Iterable[category.Category]:
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
        self,
        parent_id: category.CategoryID,
        recursive: bool = False
    ) -> typing.Iterable[category.Category]:
        yield from sorted(
            self.list_categories(parent_id),
            key=lambda x: x.title
        )

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

    def list_assets(self, parent_id: category.CategoryID, recursive: bool = False) -> typing.Iterable[asset.Asset]:
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
        """Lists asset data of given asset
        """
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

    def list_child_category_ids(self, parent_id: category.CategoryID) -> typing.Iterable[category.CategoryID]:
        # Two different asset providers can provide the same CategoryID, for example
        # botaniq/deciduous coming from core botaniq and an asset pack. That's why we have to
        # deduplicate the result.
        ret: typing.Set[category.CategoryID] = set()
        for asset_provider in self._asset_providers:
            ret.update(asset_provider.list_child_category_ids(parent_id))
        yield from ret

    def list_child_asset_ids(self, parent_id: category.CategoryID) -> typing.Iterable[asset.AssetID]:
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

    def get_asset_data(self, asset_data_id: asset_data.AssetDataID) -> typing.Optional[asset_data.AssetData]:
        # TODO: reversed because providers added later override, does that make sense?
        for asset_provider in reversed(self._asset_providers):
            ret = asset_provider.get_asset_data(asset_data_id)
            if ret is not None:
                return ret
        return None
