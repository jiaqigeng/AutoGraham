from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def render_peer_comparison_chart(target_ticker: str, peer_tickers: list) -> None:
	tickers = [target_ticker.strip().upper()] + [ticker.strip().upper() for ticker in peer_tickers if ticker.strip()]

	unique_tickers = []
	for ticker in tickers:
		if ticker not in unique_tickers:
			unique_tickers.append(ticker)

	if len(unique_tickers) <= 1:
		st.info("Peer comparison chart requires at least one peer ticker.")
		return

	pe_values = []
	margin_values = []
	bar_colors = []

	for ticker in unique_tickers:
		info = yf.Ticker(ticker).info or {}
		pe_values.append(_safe_number(info.get("trailingPE")))
		margin_values.append(_safe_number(info.get("profitMargins")) * 100)
		bar_colors.append("#3B82F6" if ticker == unique_tickers[0] else "#9CA3AF")

	fig = make_subplots(specs=[[{"secondary_y": True}]])
	fig.add_trace(
		go.Bar(
			name="P/E Ratio",
			x=unique_tickers,
			y=pe_values,
			marker_color=bar_colors,
			offsetgroup="pe",
		),
		secondary_y=False,
	)
	fig.add_trace(
		go.Bar(
			name="Net Margin %",
			x=unique_tickers,
			y=margin_values,
			marker_color=bar_colors,
			offsetgroup="margin",
			opacity=0.8,
		),
		secondary_y=True,
	)

	fig.update_layout(
		title=f"{unique_tickers[0]} vs Peers: Valuation and Profitability",
		barmode="group",
		template="plotly_white",
		height=500,
		legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
		margin={"t": 80, "b": 40, "l": 40, "r": 40},
	)
	fig.update_yaxes(title_text="Trailing P/E", secondary_y=False)
	fig.update_yaxes(title_text="Net Margin (%)", secondary_y=True)

	st.plotly_chart(fig, use_container_width=True)