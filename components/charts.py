from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots


def _extract_close_series(history, ticker: str):
	if history is None or history.empty:
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


def _history_close(ticker: str, period: str = "6m"):
	history = yf.download(ticker, period=period, progress=False, auto_adjust=False)
	close = _extract_close_series(history, ticker)
	if close is not None:
		return close

	history = yf.Ticker(ticker).history(period=period, auto_adjust=False)
	return _extract_close_series(history, ticker)


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def render_performance_chart(ticker: str):
	clean_ticker = ticker.strip().upper()
	target_close = _history_close(clean_ticker)
	spy_close = _history_close("SPY")
	if target_close is None or spy_close is None:
		st.warning("Unable to load 6-month performance data for the chart.")
		return

	df = target_close.to_frame(name=clean_ticker).join(spy_close.to_frame(name="SPY"), how="inner")
	if df.empty:
		st.warning("Unable to align historical price data for the performance chart.")
		return

	df = (df / df.iloc[0] - 1) * 100

	fig = go.Figure()
	fig.add_trace(
		go.Scatter(
			x=df.index,
			y=df[clean_ticker],
			mode="lines",
			name=clean_ticker,
			line={"color": "#3B82F6", "width": 3},
		)
	)
	fig.add_trace(
		go.Scatter(
			x=df.index,
			y=df["SPY"],
			mode="lines",
			name="S&P 500",
			line={"color": "#9CA3AF", "width": 2, "dash": "dash"},
		)
	)
	fig.update_layout(
		title=f"6-Month Relative Performance: {clean_ticker} vs S&P 500",
		template="plotly_white",
		height=420,
		margin={"t": 70, "b": 40, "l": 40, "r": 40},
		yaxis_title="Return (%)",
	)
	st.plotly_chart(fig, use_container_width=True)


def render_peer_comparison_chart(target_ticker: str, peer_tickers: list):
	clean_target = target_ticker.strip().upper()
	tickers = [clean_target] + [ticker.strip().upper() for ticker in peer_tickers if ticker.strip()]
	unique_tickers = []
	for ticker in tickers:
		if ticker not in unique_tickers:
			unique_tickers.append(ticker)

	if len(unique_tickers) <= 1:
		st.info("Peer comparison chart requires at least one peer.")
		return

	pe_values = []
	margin_values = []
	colors = []
	for ticker in unique_tickers:
		info = yf.Ticker(ticker).info or {}
		pe_values.append(_safe_number(info.get("trailingPE")))
		margin_values.append(_safe_number(info.get("profitMargins")) * 100)
		colors.append("#3B82F6" if ticker == clean_target else "#9CA3AF")

	fig = make_subplots(specs=[[{"secondary_y": True}]])
	fig.add_trace(
		go.Bar(
			name="P/E Ratio",
			x=unique_tickers,
			y=pe_values,
			marker_color=colors,
			offsetgroup="pe",
		),
		secondary_y=False,
	)
	fig.add_trace(
		go.Bar(
			name="Net Margin %",
			x=unique_tickers,
			y=margin_values,
			marker_color=colors,
			offsetgroup="margin",
			opacity=0.8,
		),
		secondary_y=True,
	)
	fig.update_layout(
		title=f"{clean_target} Peer Comparison",
		barmode="group",
		template="plotly_white",
		height=500,
		margin={"t": 80, "b": 40, "l": 40, "r": 40},
	)
	fig.update_yaxes(title_text="P/E Ratio", secondary_y=False)
	fig.update_yaxes(title_text="Net Margin (%)", secondary_y=True)
	st.plotly_chart(fig, use_container_width=True)