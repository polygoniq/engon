#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import unittest
from blender_test_helpers import blender_addon_test_main
import mapr
import mathutils


class LocalJSONProviderTestCase(unittest.TestCase):
    """Tests the API of the LocalJSONProvider.

    Doesn't test materializing files, we use mocked up `mock_mapr_index.json` for testing.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setUp(self):
        # The path to the provider is based on where the py_test rule is defined in
        self.provider = mapr.local_json_provider.LocalJSONProvider(
            "blender_addons/mapr/tests/mock_mapr_index.json", "/mock_pack", "/"
        )

    def test_get_asset(self):
        asset = self.provider.get_asset("asset_id_1")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.id_, "asset_id_1")

    def test_get_category(self):
        category = self.provider.get_category("/mock_pack/category_1")
        self.assertIsNotNone(category)
        self.assertEqual(category.id_, "/mock_pack/category_1")

    def test_list_assets(self):
        assets = self.provider.list_assets("/", recursive=True)
        self.assertEqual(len(list(assets)), 4)
        assets = self.provider.list_assets("/mock_pack", recursive=True)
        self.assertEqual(len(list(assets)), 4)
        assets = self.provider.list_assets("/mock_pack/category_1")
        self.assertEqual(len(list(assets)), 2)
        assets = self.provider.list_assets("/mock_pack/category_2")
        self.assertEqual(len(list(assets)), 2)

    def test_list_asset_data(self):
        asset_data = list(self.provider.list_asset_data("asset_id_1"))
        self.assertEqual(len(asset_data), 1)
        self.assertEqual(asset_data[0].id_, "data_id_1")

    def test_list_categories(self):
        categories = list(self.provider.list_categories("/mock_pack"))
        self.assertEqual(len(categories), 2)
        self.assertSetEqual(
            {c.id_ for c in categories}, {"/mock_pack/category_1", "/mock_pack/category_2"}
        )

    def test_query_all(self):
        data_view = self.provider.query(
            mapr.query.Query("/", filters=[], sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC)
        )
        self.assertEqual(len(data_view.assets), 4)
        self.assertSetEqual(
            {a.id_ for a in data_view.assets},
            {"asset_id_1", "asset_id_2", "asset_id_3", "asset_id_4"},
        )

    def test_query_search(self):
        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[mapr.filters.SearchFilter("Rectangular")],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )
        self.assertEqual(len(data_view.assets), 1)
        self.assertEqual(data_view.assets[0].id_, "asset_id_1")

        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[mapr.filters.SearchFilter("Minimalist")],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )
        self.assertEqual(len(data_view.assets), 2)
        self.assertSetEqual({a.id_ for a in data_view.assets}, {"asset_id_1", "asset_id_3"})

    def test_color_to_vector_transition(self):
        # We transitioned "color_parameters" to be a part of "vector_parameters", in order to ensure
        # backward compatibility with asset packs released before engon 1.2.0, we test that
        asset = self.provider.get_asset("asset_id_1")
        self.assertIn("viewport_color", asset.vector_parameters)

    def test_query_filters(self):
        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[mapr.filters.NumericParameterFilter("num:width", 0.0, 1.0)],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )
        self.assertEqual(len(data_view.assets), 1)
        self.assertEqual(data_view.assets[0].id_, "asset_id_3")

        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[
                    mapr.filters.NumericParameterFilter("num:width", 1.0, 10.0),
                    mapr.filters.NumericParameterFilter("num:price_usd", 500, 9999),
                ],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )
        self.assertEqual(len(data_view.assets), 2)
        self.assertSetEqual({a.id_ for a in data_view.assets}, {"asset_id_2", "asset_id_4"})

    def test_query_filters_vector_range(self):
        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[
                    mapr.filters.VectorParameterFilter(
                        "vec:introduced_in",
                        mapr.filters.VectorLexicographicComparator(
                            mathutils.Vector((1, 0, 0)), mathutils.Vector((2, 0, 0))
                        ),
                    ),
                ],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )

        self.assertEqual(len(data_view.assets), 2)
        self.assertSetEqual({a.id_ for a in data_view.assets}, {"asset_id_1", "asset_id_2"})

    def test_query_filters_vector_distance(self):
        data_view = self.provider.query(
            mapr.query.Query(
                "/",
                filters=[
                    mapr.filters.VectorParameterFilter(
                        "vec:introduced_in",
                        mapr.filters.VectorDistanceComparator(mathutils.Vector((2, 0, 0)), 1),
                    ),
                ],
                sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC,
            )
        )

        self.assertEqual(len(data_view.assets), 2)
        self.assertSetEqual({a.id_ for a in data_view.assets}, {"asset_id_2", "asset_id_3"})


class CachedAssetProviderTestCase(LocalJSONProviderTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setUp(self):
        local_json_provider = mapr.local_json_provider.LocalJSONProvider(
            "blender_addons/mapr/tests/mock_mapr_index.json", "/mock_pack", "/"
        )
        self.provider = mapr.asset_provider.CachedAssetProviderMultiplexer()
        self.provider.add_asset_provider(local_json_provider)

    def test_query_cache_hit(self):
        # Test two queries with the same parameters return the exactly same DataView object
        query = mapr.query.Query("/", filters=[], sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC)

        first_view = self.provider.query(query)
        second_view = self.provider.query(query)

        self.assertEqual(id(first_view), id(second_view))

    def test_query_cache_miss(self):
        # Test different query parameters return different DataView object
        first_view = self.provider.query(
            mapr.query.Query("/", filters=[], sort_mode=mapr.query.SortMode.ALPHABETICAL_ASC)
        )

        second_view = self.provider.query(
            mapr.query.Query("/", filters=[], sort_mode=mapr.query.SortMode.ALPHABETICAL_DESC)
        )

        self.assertNotEqual(id(first_view), id(second_view))


if __name__ == "__main__":
    blender_addon_test_main()
