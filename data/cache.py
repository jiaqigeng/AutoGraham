from __future__ import annotations

from functools import lru_cache

from data.market_data import StockData, fetch_stock_data


@lru_cache(maxsize=32)
def get_cached_stock_data(ticker: str) -> StockData:
	"""Simple in-process cache for frequently revisited tickers."""

	return fetch_stock_data(ticker)


def clear_data_cache() -> None:
	get_cached_stock_data.cache_clear()
