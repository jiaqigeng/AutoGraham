from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass
class StockData:
	info: dict[str, Any]
	quarterly_income_stmt: pd.DataFrame


def fetch_stock_data(ticker: str) -> StockData:
	stock = yf.Ticker(ticker)
	info = stock.info or {}
	quarterly_income_stmt = stock.quarterly_income_stmt

	if quarterly_income_stmt is None or quarterly_income_stmt.empty:
		quarterly_income_stmt = stock.quarterly_financials

	if quarterly_income_stmt is None:
		quarterly_income_stmt = pd.DataFrame()

	quarterly_income_stmt = quarterly_income_stmt.copy()
	quarterly_income_stmt.attrs["ticker"] = ticker.upper()

	return StockData(
		info=info,
		quarterly_income_stmt=quarterly_income_stmt,
	)