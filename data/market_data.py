from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf

from valuation.common import safe_number


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

	return StockData(
		info=info,
		quarterly_income_stmt=_prepare_frame(quarterly_income_stmt, ticker),
		annual_cashflow=_prepare_frame(annual_cashflow, ticker),
		annual_balance_sheet=_prepare_frame(annual_balance_sheet, ticker),
		annual_income_stmt=_prepare_frame(annual_income_stmt, ticker),
	)


def _extract_close_series(history: pd.DataFrame | pd.Series | None, ticker: str):
	if history is None or getattr(history, "empty", True):
		return None

	if "Close" in history:
		close = history["Close"]
		if hasattr(close, "columns"):
			if ticker in close.columns:
				close = close[ticker]
			else:
				close = close.iloc[:, 0]
		close = close.dropna()
		return close if not close.empty else None

	if getattr(history, "columns", None) is not None and len(history.columns) > 0:
		first_column = history.iloc[:, 0].dropna()
		return first_column if not first_column.empty else None

	return None


def get_price_history_close(ticker: str, period: str = "6m"):
	history = yf.download(ticker, period=period, progress=False, auto_adjust=False)
	close = _extract_close_series(history, ticker)
	if close is not None:
		return close

	history = yf.Ticker(ticker).history(period=period, auto_adjust=False)
	return _extract_close_series(history, ticker)


def get_relative_performance_frame(ticker: str, benchmark: str = "SPY", period: str = "6m") -> pd.DataFrame:
	clean_ticker = ticker.strip().upper()
	target_close = get_price_history_close(clean_ticker, period=period)
	benchmark_close = get_price_history_close(benchmark, period=period)
	if target_close is None or benchmark_close is None:
		raise ValueError("Unable to load historical price data.")

	frame = target_close.to_frame(name=clean_ticker).join(benchmark_close.to_frame(name=benchmark), how="inner")
	if frame.empty:
		raise ValueError("Unable to align historical price data.")
	return (frame / frame.iloc[0] - 1) * 100


def get_peer_snapshot(target_ticker: str, peer_tickers: list[str]) -> list[dict[str, float | str]]:
	tickers = [target_ticker.strip().upper()] + [ticker.strip().upper() for ticker in peer_tickers if ticker.strip()]
	unique_tickers: list[str] = []
	for ticker in tickers:
		if ticker not in unique_tickers:
			unique_tickers.append(ticker)

	rows: list[dict[str, float | str]] = []
	for ticker in unique_tickers:
		info = yf.Ticker(ticker).info or {}
		rows.append(
			{
				"ticker": ticker,
				"trailing_pe": safe_number(info.get("trailingPE")),
				"net_margin_pct": safe_number(info.get("profitMargins")) * 100,
			}
		)
	return rows
