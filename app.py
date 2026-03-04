import streamlit as st
import yfinance as yf
import plotly.graph_objects as go


st.set_page_config(page_title="AutoGraham", page_icon="🤖", layout="wide")


@st.cache_data(ttl=3600)
def fetch_company_info(ticker: str) -> dict:
	stock = yf.Ticker(ticker)
	info = stock.info

	company_name = info.get("longName")
	sector = info.get("sector")
	current_price = info.get("currentPrice")

	if not company_name or current_price is None:
		raise ValueError("Invalid ticker or missing company data.")

	return {
		"longName": company_name,
		"sector": sector or "N/A",
		"currentPrice": current_price,
	}


st.sidebar.title("AutoGraham 🤖")
ticker = st.sidebar.text_input("Enter Stock Ticker", value="AAPL").strip().upper()


st.title("AutoGraham 🤖")

try:
	company_data = fetch_company_info(ticker)
	st.subheader(f"{company_data['longName']} ({ticker})")
	st.write(f"**Sector:** {company_data['sector']}")
	st.write(f"**Current Price:** ${company_data['currentPrice']}")
except Exception:
	st.error("Invalid ticker symbol or data unavailable. Please try another ticker.")


@st.cache_data(ttl=3600)
def fetch_income_statement_metrics(ticker: str, period_type: str):
	stock = yf.Ticker(ticker)
	statement = stock.quarterly_financials if period_type == "Quarterly" else stock.financials

	if statement is None or statement.empty:
		raise ValueError("Income statement data is unavailable.")

	latest_period = statement.columns[0]
	row = statement[latest_period].fillna(0)

	total_revenue_raw = float(row.get("Total Revenue", 0) or 0)
	if total_revenue_raw == 0:
		total_revenue_raw = float(row.get("Revenue", 0) or 0)

	cost_of_revenue_raw = float(row.get("Cost Of Revenue", 0) or 0)
	gross_profit_raw = float(row.get("Gross Profit", 0) or 0)
	operating_expense_raw = float(row.get("Operating Expense", 0) or 0)
	if operating_expense_raw == 0:
		operating_expense_raw = float(row.get("Operating Expenses", 0) or 0)
	operating_income_raw = float(row.get("Operating Income", 0) or 0)
	net_income_raw = float(row.get("Net Income", 0) or 0)

	if gross_profit_raw == 0 and total_revenue_raw > 0:
		gross_profit_raw = max(total_revenue_raw - cost_of_revenue_raw, 0)
	if operating_expense_raw == 0 and gross_profit_raw > 0:
		operating_expense_raw = max(gross_profit_raw - operating_income_raw, 0)

	period_label = latest_period.strftime("%Y-%m-%d") if hasattr(latest_period, "strftime") else str(latest_period)

	return {
		"Total Revenue": total_revenue_raw / 1_000_000_000,
		"Cost Of Revenue": cost_of_revenue_raw / 1_000_000_000,
		"Gross Profit": gross_profit_raw / 1_000_000_000,
		"Operating Expense": operating_expense_raw / 1_000_000_000,
		"Operating Income": operating_income_raw / 1_000_000_000,
		"Net Income": net_income_raw / 1_000_000_000,
	}, period_label


@st.cache_data(ttl=3600)
def fetch_dcf_baseline_inputs(ticker: str) -> dict:
	stock = yf.Ticker(ticker)
	info = stock.info
	cashflow = stock.cashflow

	shares_outstanding = float(info.get("sharesOutstanding") or 0)
	current_price = float(info.get("currentPrice") or 0)

	base_fcf = 0.0
	if cashflow is not None and not cashflow.empty and "Free Cash Flow" in cashflow.index:
		value = cashflow.loc["Free Cash Flow"].iloc[0]
		if value is not None:
			base_fcf = float(value)

	return {
		"shares_outstanding": shares_outstanding,
		"current_price": current_price,
		"base_fcf": base_fcf,
	}


section = st.sidebar.radio(
	"Section",
	[
		"💰 Earnings Breakdown",
		"🧮 Interactive DCF",
	],
	key="active_section",
)

if section == "💰 Earnings Breakdown":
	st.header("💰 Earnings Breakdown")
	st.caption("Dynamic Sankey diagram from the latest reported income statement.")
	period_type = st.segmented_control(
		"Period",
		options=["Annual", "Quarterly"],
		default="Annual",
		key="earnings_period",
	)
	if period_type is None:
		period_type = "Annual"
	try:
		metrics, period_label = fetch_income_statement_metrics(ticker, period_type)

		total_revenue = metrics.get("Total Revenue", 0)
		cost_of_revenue = metrics.get("Cost Of Revenue", 0)
		gross_profit = metrics.get("Gross Profit", 0)
		operating_expenses = metrics.get("Operating Expense", 0)
		operating_income = metrics.get("Operating Income", 0)
		net_income = metrics.get("Net Income", 0)
		taxes_other = operating_income - net_income

		total_revenue_label = "Total Revenue" if total_revenue >= 0 else "Revenue Reversal"
		cost_of_revenue_label = "Cost of Revenue" if cost_of_revenue >= 0 else "Cost Recovery"
		gross_profit_label = "Gross Profit" if gross_profit >= 0 else "Gross Loss"
		operating_expenses_label = "Operating Expenses" if operating_expenses >= 0 else "Operating Credit"
		operating_income_label = "Operating Income" if operating_income >= 0 else "Operating Loss"
		taxes_other_label = "Taxes & Other" if taxes_other >= 0 else "Tax Benefit & Other Income"
		net_income_label = "Net Income" if net_income >= 0 else "Net Loss"

		labels_base = [
			total_revenue_label,
			cost_of_revenue_label,
			gross_profit_label,
			operating_expenses_label,
			operating_income_label,
			taxes_other_label,
			net_income_label,
		]

		label_amounts = [
			total_revenue,
			cost_of_revenue,
			gross_profit,
			operating_expenses,
			operating_income,
			taxes_other,
			net_income,
		]
		labels = [f"{label}<br>${amount:,.1f}B" for label, amount in zip(labels_base, label_amounts)]

		sources = [0, 0, 2, 2, 4, 4]
		targets = [1, 2, 3, 4, 5, 6]
		values = [
			abs(cost_of_revenue),
			abs(gross_profit),
			abs(operating_expenses),
			abs(operating_income),
			abs(taxes_other),
			abs(net_income),
		]
		expense_node_indices = set()
		if cost_of_revenue >= 0:
			expense_node_indices.add(1)
		if operating_expenses >= 0:
			expense_node_indices.add(3)
		if taxes_other >= 0:
			expense_node_indices.add(5)
		if gross_profit < 0:
			expense_node_indices.add(2)
		if operating_income < 0:
			expense_node_indices.add(4)
		if net_income < 0:
			expense_node_indices.add(6)
		if total_revenue < 0:
			expense_node_indices.add(0)
		node_colors = ["#D32F2F" if idx in expense_node_indices else "#2E7D32" for idx in range(len(labels))]
		link_colors = [
			"rgba(211,47,47,0.45)" if target in expense_node_indices else "rgba(46,125,50,0.45)"
			for target in targets
		]
		node_x = [0.02, 0.30, 0.30, 0.58, 0.58, 0.86, 0.86]
		node_y = [0.50, 0.22, 0.78, 0.22, 0.78, 0.22, 0.78]

		fig = go.Figure(
			data=[
				go.Sankey(
					arrangement="snap",
					textfont={"size": 14, "color": "#111111", "family": "Arial, sans-serif"},
					hoverlabel={"font": {"size": 13, "color": "#111111"}},
					node={
						"label": labels,
						"pad": 28,
						"thickness": 22,
						"x": node_x,
						"y": node_y,
						"color": node_colors,
						"line": {"color": "rgba(0,0,0,0.18)", "width": 1},
					},
					link={
						"source": sources,
						"target": targets,
						"value": values,
						"color": link_colors,
					},
				)
			]
		)
		fig.update_layout(
			title=f"{ticker} Income Statement Flow ({period_label})",
			margin={"t": 60, "l": 0, "r": 0, "b": 0},
			font={"size": 13, "color": "#111111", "family": "Arial, sans-serif"},
			title_font={"size": 20, "color": "#111111"},
			paper_bgcolor="rgba(0,0,0,0)",
			plot_bgcolor="rgba(0,0,0,0)",
		)
		st.plotly_chart(fig, use_container_width=True)

		c1, c2, c3 = st.columns(3)
		cogs_pct = (cost_of_revenue / total_revenue) if total_revenue else 0.0
		gross_margin = (gross_profit / total_revenue) if total_revenue else 0.0
		net_margin = (net_income / total_revenue) if total_revenue else 0.0
		c1.metric("COGS % of Revenue", f"{cogs_pct:.1%}")
		c2.metric("Gross Margin", f"{gross_margin:.1%}")
		c3.metric("Net Margin", f"{net_margin:.1%}")
	except Exception as exc:
		st.error(f"Unable to load earnings breakdown: {exc}")

elif section == "🧮 Interactive DCF":
	st.header("🧮 Interactive DCF")
	st.caption("Adjust assumptions to estimate intrinsic value per share in real time.")

	try:
		baseline = fetch_dcf_baseline_inputs(ticker)
		base_fcf_default = baseline["base_fcf"] / 1_000_000_000 if baseline["base_fcf"] else 10.0
		shares_outstanding = baseline["shares_outstanding"]
		current_price = baseline["current_price"]

		col1, col2 = st.columns(2)
		base_fcf_b = col1.number_input("Base FCF (USD, billions)", min_value=0.1, value=float(base_fcf_default), step=0.5)
		years = col2.slider("Forecast Years", min_value=3, max_value=15, value=10)

		col3, col4, col5 = st.columns(3)
		growth_rate = col3.slider("FCF Growth (%)", min_value=-5.0, max_value=30.0, value=8.0, step=0.5) / 100
		discount_rate = col4.slider("Discount Rate (%)", min_value=5.0, max_value=20.0, value=10.0, step=0.5) / 100
		terminal_growth = col5.slider("Terminal Growth (%)", min_value=0.0, max_value=5.0, value=2.5, step=0.1) / 100

		net_cash_b = st.number_input("Net Cash / (Debt) Adjustment (USD, billions)", value=0.0, step=1.0)

		if discount_rate <= terminal_growth:
			st.warning("Discount rate must be greater than terminal growth rate.")
		else:
			base_fcf = base_fcf_b * 1_000_000_000
			net_cash = net_cash_b * 1_000_000_000
			projected_fcfs = []
			discounted_fcfs = []

			for year in range(1, years + 1):
				fcf = base_fcf * ((1 + growth_rate) ** year)
				discounted = fcf / ((1 + discount_rate) ** year)
				projected_fcfs.append(fcf)
				discounted_fcfs.append(discounted)

			terminal_fcf = projected_fcfs[-1] * (1 + terminal_growth)
			terminal_value = terminal_fcf / (discount_rate - terminal_growth)
			terminal_pv = terminal_value / ((1 + discount_rate) ** years)

			enterprise_value = sum(discounted_fcfs) + terminal_pv
			equity_value = enterprise_value + net_cash

			intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding else 0.0

			k1, k2, k3 = st.columns(3)
			k1.metric("Intrinsic Value / Share", f"${intrinsic_value_per_share:,.2f}")
			k2.metric("Current Price", f"${current_price:,.2f}" if current_price else "N/A")
			if current_price:
				diff = (intrinsic_value_per_share / current_price) - 1
				k3.metric("Upside / Downside", f"{diff:.1%}")
			else:
				k3.metric("Upside / Downside", "N/A")

			dcf_chart = st.line_chart(
				{
					"Projected FCF": projected_fcfs,
					"Discounted FCF": discounted_fcfs,
				}
			)
			_ = dcf_chart

	except Exception:
		st.warning("DCF inputs are unavailable for this ticker.")
