from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
	from data.cache import get_cached_stock_data, stock_data_cache_scope
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
	get_cached_stock_data = None  # type: ignore[assignment]
	stock_data_cache_scope = None  # type: ignore[assignment]


@unittest.skipUnless(get_cached_stock_data is not None, "market-data dependencies are not installed in this interpreter")
class DataCacheTests(unittest.TestCase):
	def test_cache_reuses_fetches_only_within_one_scope(self) -> None:
		first = SimpleNamespace(info={"shortName": "First"})
		second = SimpleNamespace(info={"shortName": "Second"})

		with patch("data.cache.fetch_stock_data", side_effect=[first, second]) as mocked_fetch:
			with stock_data_cache_scope():
				cached_once = get_cached_stock_data("aapl")
				cached_twice = get_cached_stock_data(" AAPL ")
			with stock_data_cache_scope():
				refetched = get_cached_stock_data("aapl")

		self.assertIs(cached_once, first)
		self.assertIs(cached_twice, first)
		self.assertIs(refetched, second)
		self.assertEqual(mocked_fetch.call_count, 2)

	def test_nested_scope_reuses_parent_cache(self) -> None:
		stock = SimpleNamespace(info={"shortName": "Nested"})

		with patch("data.cache.fetch_stock_data", return_value=stock) as mocked_fetch:
			with stock_data_cache_scope():
				outer = get_cached_stock_data("msft")
				with stock_data_cache_scope():
					inner = get_cached_stock_data("MSFT")

		self.assertIs(outer, stock)
		self.assertIs(inner, stock)
		self.assertEqual(mocked_fetch.call_count, 1)


if __name__ == "__main__":
	unittest.main()
