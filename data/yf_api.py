from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass
class StockData:
	info: dict[str, Any]
	quarterly_income_stmt: pd.DataFrame
	annual_cashflow: pd.DataFrame
	annual_balance_sheet: pd.DataFrame
	annual_income_stmt: pd.DataFrame


def _prepare_frame(frame: pd.DataFrame | None, ticker: str) -> pd.DataFrame:
	if frame is None:
		prepared = pd.DataFrame()
	else:
		prepared = frame.copy()
	prepared.attrs["ticker"] = ticker.upper()
	return prepared


def fetch_stock_data(ticker: str) -> StockData:
	stock = yf.Ticker(ticker)
	info = stock.info or {}
	quarterly_income_stmt = stock.quarterly_income_stmt
	annual_cashflow = stock.cashflow
	annual_balance_sheet = stock.balance_sheet
	annual_income_stmt = stock.financials

	if quarterly_income_stmt is None or quarterly_income_stmt.empty:
		quarterly_income_stmt = stock.quarterly_financials

	quarterly_income_stmt = _prepare_frame(quarterly_income_stmt, ticker)
	annual_cashflow = _prepare_frame(annual_cashflow, ticker)
	annual_balance_sheet = _prepare_frame(annual_balance_sheet, ticker)
	annual_income_stmt = _prepare_frame(annual_income_stmt, ticker)

	return StockData(
		info=info,
		quarterly_income_stmt=quarterly_income_stmt,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)