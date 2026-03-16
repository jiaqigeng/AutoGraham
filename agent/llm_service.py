from __future__ import annotations

import math
import os
from textwrap import dedent

from dotenv import load_dotenv

from data.yf_api import fetch_stock_data

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if math.isnan(numeric_value):
		return 0.0
	return numeric_value


def _format_currency(value: object) -> str:
	amount = _safe_number(value)
	if amount == 0:
		return "$0.00"
	prefix = "-" if amount < 0 else ""
	abs_amount = abs(amount)
	if abs_amount >= 1_000_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000_000:,.2f}T"
	if abs_amount >= 1_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000:,.2f}B"
	if abs_amount >= 1_000_000:
		return f"{prefix}${abs_amount / 1_000_000:,.2f}M"
	return f"{prefix}${abs_amount:,.2f}"


def _format_price(value: object) -> str:
	price = _safe_number(value)
	if price <= 0:
		return "N/A"
	return f"${price:,.2f}"


def _format_ratio(value: object) -> str:
	ratio = _safe_number(value)
	if ratio <= 0:
		return "N/A"
	return f"{ratio:,.2f}"


def _format_percent(value: object) -> str:
	percent = _safe_number(value)
	if percent < 0:
		return "N/A"
	if percent > 0.25:
		percent = percent / 100
	return f"{percent:.2%}"


def _format_period_label(period_column) -> str:
	if hasattr(period_column, "strftime"):
		return f"Quarter Ended: {period_column.strftime('%b %d, %Y')}"
	return str(period_column)


def _unavailable_peer_message(ticker: str, reason: str) -> str:
	return (
		f"DATA_UNAVAILABLE for {ticker}: {reason} "
		"Exclude this ticker from the peer set and continue the analysis with other public competitors."
	)


def _info_supports_analysis(info: dict[str, object]) -> bool:
	quote_type = str(info.get("quoteType") or "").upper()
	if quote_type and quote_type != "EQUITY":
		return False
	if info.get("shortName") or info.get("longName"):
		return True
	if info.get("currentPrice") is not None or info.get("regularMarketPrice") is not None:
		return True
	return False


def _extract_latest_quarter_metrics(ticker: str) -> dict[str, object]:
	stock_data = fetch_stock_data(ticker)
	income_stmt = stock_data.quarterly_income_stmt
	if income_stmt is None or income_stmt.empty:
		raise ValueError(f"Quarterly income statement data is unavailable for {ticker}.")

	income_stmt = income_stmt[income_stmt.columns.sort_values(ascending=False)]
	latest_period = income_stmt.columns[0]
	period_series = income_stmt[latest_period].fillna(0)

	revenue = _safe_number(period_series.get("Total Revenue", period_series.get("Revenue", 0)))
	cost_of_revenue = abs(_safe_number(period_series.get("Cost Of Revenue", 0)))
	gross_profit = _safe_number(period_series.get("Gross Profit", revenue - cost_of_revenue))
	operating_expenses = abs(_safe_number(period_series.get("Operating Expense", period_series.get("Operating Expenses", 0))))
	net_profit = _safe_number(period_series.get("Net Income", period_series.get("Net Income Common Stockholders", 0)))

	gross_margin = (gross_profit / revenue) if revenue else None
	net_margin = (net_profit / revenue) if revenue else None

	return {
		"period": _format_period_label(latest_period),
		"revenue": revenue,
		"gross_profit": gross_profit,
		"operating_expenses": operating_expenses,
		"net_profit": net_profit,
		"gross_margin": gross_margin,
		"net_margin": net_margin,
	}


@tool
def get_valuation_metrics(ticker: str) -> str:
	"""Fetch valuation metrics for a publicly traded company."""
	clean_ticker = ticker.strip().upper()
	try:
		stock_data = fetch_stock_data(clean_ticker)
		info = stock_data.info
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, f"Unable to load valuation data from Yahoo Finance ({exc}).")

	if not _info_supports_analysis(info):
		return _unavailable_peer_message(clean_ticker, "Yahoo Finance does not expose a valid equity profile for this ticker.")

	return dedent(
		f"""
		Valuation Metrics for {clean_ticker}:
		- Current Price: {_format_price(info.get('currentPrice', info.get('regularMarketPrice')))}
		- Market Cap: {_format_currency(info.get('marketCap'))}
		- Trailing P/E: {_format_ratio(info.get('trailingPE'))}
		- Forward P/E: {_format_ratio(info.get('forwardPE'))}
		- Trailing EPS: {_format_price(info.get('trailingEps'))}
		- Dividend Yield: {_format_percent(info.get('dividendYield')) if info.get('dividendYield') is not None else 'N/A'}
		"""
	).strip()


@tool
def get_income_statement(ticker: str) -> str:
	"""Fetch the latest quarterly income statement metrics for a company."""
	clean_ticker = ticker.strip().upper()
	try:
		metrics = _extract_latest_quarter_metrics(clean_ticker)
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, str(exc))

	return dedent(
		f"""
		Latest Quarterly Income Statement for {clean_ticker} ({metrics['period']}):
		- Revenue: {_format_currency(metrics['revenue'])}
		- Gross Profit: {_format_currency(metrics['gross_profit'])}
		- Operating Expenses: {_format_currency(metrics['operating_expenses'])}
		- Net Profit: {_format_currency(metrics['net_profit'])}
		- Gross Margin: {f"{metrics['gross_margin']:.2%}" if metrics['gross_margin'] is not None else 'N/A'}
		- Net Margin: {f"{metrics['net_margin']:.2%}" if metrics['net_margin'] is not None else 'N/A'}
		"""
	).strip()


@tool
def get_cash_flow_health(ticker: str) -> str:
	"""Fetch cash flow and balance sheet safety metrics for a company."""
	clean_ticker = ticker.strip().upper()
	try:
		stock_data = fetch_stock_data(clean_ticker)
		info = stock_data.info
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, f"Unable to load cash flow data from Yahoo Finance ({exc}).")

	if not _info_supports_analysis(info):
		return _unavailable_peer_message(clean_ticker, "Yahoo Finance does not expose a valid equity profile for this ticker.")

	net_cash = _safe_number(info.get('totalCash')) - _safe_number(info.get('totalDebt'))

	return dedent(
		f"""
		Cash Flow Health for {clean_ticker}:
		- Free Cash Flow (FCFE): {_format_currency(info.get('freeCashflow'))}
		- Total Cash: {_format_currency(info.get('totalCash'))}
		- Total Debt: {_format_currency(info.get('totalDebt'))}
		- Net Cash / (Debt): {_format_currency(net_cash)}
		"""
	).strip()


@tool
def search_market_context(query: str) -> str:
	"""Search recent market context, news, or competitor information."""
	try:
		from langchain_community.tools import DuckDuckGoSearchRun
	except ImportError as exc:
		raise ImportError(
			"DuckDuckGo search support is unavailable. Install langchain-community and duckduckgo-search."
		) from exc

	search = DuckDuckGoSearchRun()
	return search.run(query)


def _build_agent_executor(target_ticker: str, model_name: str):
	try:
		from langchain.agents import AgentExecutor, create_tool_calling_agent
		from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
		from langchain_openai import ChatOpenAI
	except ImportError as exc:
		raise ImportError(
			"LangChain dependencies are missing. Install langchain, langchain-community, and langchain-openai."
		) from exc

	load_dotenv()
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		raise ValueError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

	tools = [
		get_valuation_metrics,
		get_income_statement,
		get_cash_flow_health,
		search_market_context,
	]
	llm = ChatOpenAI(
		model=model_name,
		temperature=0.1,
		api_key=api_key,
	)

	system_prompt = dedent(
		f"""
		You are an elite equity analyst. The user is analyzing the ticker: {target_ticker}. Identify its top 2-3 publicly traded competitors. Use your financial tools to pull their valuation and margin data.

		If any tool returns a message beginning with DATA_UNAVAILABLE, immediately drop that ticker from the peer set, do not discuss it as a peer, and continue with another publicly traded competitor that has usable data.

		You MUST structure your final Markdown report using EXACTLY these 8 headings:
		1. **Business Strategy & Outlook**: A brief overview of how the company makes money and its growth runway.
		2. **Economic Moat**: Categorize the moat as 'Wide', 'Narrow', or 'None'. Justify this based on their margins and competitive advantages (e.g., network effects, switching costs).
		3. **Bull Case**: Lay out the main upside scenario in 2-4 concrete points, focusing on the drivers that would cause earnings power or valuation to beat expectations.
		4. **Bear Case**: Lay out the main downside scenario in 2-4 concrete points, focusing on the drivers that would impair margins, growth, or multiple.
		5. **Fair Value & Valuation**: Compare the target's valuation (P/E, Yield) against the peers you researched. State if it is undervalued, fairly valued, or overvalued. In this section, include a compact Markdown table comparing the target and peers on key valuation fields.
		6. **Risk & Uncertainty**: Categorize the risk profile as 'Low', 'Medium', 'High', or 'Extreme'. Identify the top fundamental risk to the business.
		7. **Capital Allocation**: Assess management's track record as 'Exemplary', 'Standard', or 'Poor' based on debt management, share buybacks, and ROI.
		8. **Conclusion**: State the single strongest value opportunity among the target and peers, and give a concise final investment takeaway.

		At the very end of your report, provide a comma-separated list of the competitor tickers you used, formatted exactly like this: `PEERS: MSFT, GOOGL, AMZN`
		"""
	).strip()

	prompt = ChatPromptTemplate.from_messages(
		[
			("system", system_prompt),
			("human", "{input}"),
			MessagesPlaceholder("agent_scratchpad"),
		]
	)

	agent = create_tool_calling_agent(llm, tools, prompt)
	return AgentExecutor(
		agent=agent,
		tools=tools,
		verbose=False,
		handle_parsing_errors=True,
		max_iterations=12,
	)


def run_competitor_analysis(
	target_ticker: str,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	ticker = target_ticker.strip().upper()
	if not ticker:
		raise ValueError("A target ticker is required.")

	resolved_model = model_name or os.getenv("AUTOGRAHAM_AGENT_MODEL", "gpt-4.1-mini")
	executor = _build_agent_executor(ticker, resolved_model)
	request_suffix = ""
	if analysis_focus and analysis_focus.strip():
		request_suffix = f" Additional user focus: {analysis_focus.strip()}"
	result = executor.invoke(
		{
			"input": (
				f"Write a comprehensive investment memo for {ticker}. "
				"Compare it against its top 2-3 public competitors and conclude with the strongest value opportunity."
				f"{request_suffix}"
			)
		}
	)
	return result["output"]