from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from data.market_data import StockData, fetch_stock_data


_ACTIVE_STOCK_DATA_CACHE: ContextVar[dict[str, StockData] | None] = ContextVar(
	"active_stock_data_cache",
	default=None,
)


def _clean_ticker(ticker: str) -> str:
	return ticker.strip().upper()


def get_cached_stock_data(ticker: str) -> StockData:
	"""Fetch stock data, reusing the active per-execution cache when one is enabled."""

	clean_ticker = _clean_ticker(ticker)
	cache = _ACTIVE_STOCK_DATA_CACHE.get()
	if cache is None:
		return fetch_stock_data(clean_ticker)
	if clean_ticker not in cache:
		cache[clean_ticker] = fetch_stock_data(clean_ticker)
	return cache[clean_ticker]


def clear_data_cache() -> None:
	"""Clear the active per-execution cache, if one is enabled."""

	cache = _ACTIVE_STOCK_DATA_CACHE.get()
	if cache is not None:
		cache.clear()


@contextmanager
def stock_data_cache_scope() -> Iterator[dict[str, StockData]]:
	"""Enable a temporary in-memory stock-data cache for one analysis execution."""

	existing_cache = _ACTIVE_STOCK_DATA_CACHE.get()
	if existing_cache is not None:
		yield existing_cache
		return

	cache: dict[str, StockData] = {}
	token = _ACTIVE_STOCK_DATA_CACHE.set(cache)
	try:
		yield cache
	finally:
		cache.clear()
		_ACTIVE_STOCK_DATA_CACHE.reset(token)
