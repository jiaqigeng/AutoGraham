from __future__ import annotations

import json
import os
import re
from textwrap import dedent
from typing import Any, Mapping

from dotenv import load_dotenv

from data.yf_api import fetch_stock_data
from utils.formatting import format_compact_currency, format_percent, format_price, format_ratio, safe_number
from utils.dcf_calculator import (
	calculate_apv,
	calculate_ddm_h_model,
	calculate_ddm_single_stage,
	calculate_ddm_three_stage,
	calculate_ddm_two_stage,
	calculate_fcfe_single_stage,
	calculate_fcfe_three_stage,
	calculate_fcfe_two_stage,
	calculate_fcff_single_stage,
	calculate_fcff_three_stage,
	calculate_fcff_two_stage,
	calculate_rim,
	default_valuation_inputs,
)

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


def _format_currency(value: object) -> str:
	return format_compact_currency(value)


def _format_price(value: object) -> str:
	return format_price(value)


def _format_ratio(value: object) -> str:
	return format_ratio(value)


def _format_percent(value: object) -> str:
	return format_percent(value)


def _format_period_label(period_column) -> str:
	if hasattr(period_column, "strftime"):
		return f"Quarter Ended: {period_column.strftime('%b %d, %Y')}"
	return str(period_column)


MODEL_NAME_MAP = {
	"FCFF": "Free Cash Flow to Firm (FCFF)",
	"FCFE": "Free Cash Flow to Equity (FCFE)",
	"DDM": "Dividend Discount Model (DDM)",
	"APV": "Adjusted Present Value (APV)",
	"RIM": "Residual Income Model (RIM)",
}

ASSUMPTION_LABELS = {
	"current_price": "Current Price",
	"shares_outstanding": "Shares Outstanding",
	"starting_fcff": "Starting FCFF",
	"starting_fcfe": "Starting FCFE",
	"dividend_per_share": "Dividend per Share",
	"book_value_per_share": "Book Value per Share",
	"wacc": "WACC",
	"cost_of_equity": "Cost of Equity",
	"cost_of_debt": "Cost of Debt",
	"required_return": "Required Return",
	"unlevered_cost": "Unlevered Cost of Capital",
	"high_growth": "High Growth",
	"stable_growth": "Stable Growth",
	"terminal_growth": "Terminal Growth",
	"short_term_growth": "Short-Term Growth",
	"projection_years": "Projection Years",
	"high_growth_years": "High Growth Years",
	"transition_years": "Fade Years",
	"half_life_years": "H-Model Half-Life",
	"total_debt": "Total Debt",
	"cash": "Cash",
	"tax_rate": "Tax Rate",
	"return_on_equity": "Forward ROE",
	"payout_ratio": "Payout Ratio",
}

YAHOO_LOCKED_ASSUMPTIONS = {
	"current_price",
	"shares_outstanding",
	"starting_fcff",
	"starting_fcfe",
	"dividend_per_share",
	"book_value_per_share",
	"total_debt",
	"cash",
	"tax_rate",
	"cost_of_debt",
	"return_on_equity",
	"payout_ratio",
}


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


def _build_chat_model(model_name: str, temperature: float = 0.1):
	try:
		from langchain_openai import ChatOpenAI
	except ImportError as exc:
		raise ImportError(
			"LangChain OpenAI support is unavailable. Install langchain-openai to run the AI analysis."
		) from exc

	load_dotenv()
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		raise ValueError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

	return ChatOpenAI(
		model=model_name,
		temperature=temperature,
		api_key=api_key,
	)


def _extract_latest_quarter_metrics(ticker: str) -> dict[str, object]:
	stock_data = fetch_stock_data(ticker)
	income_stmt = stock_data.quarterly_income_stmt
	if income_stmt is None or income_stmt.empty:
		raise ValueError(f"Quarterly income statement data is unavailable for {ticker}.")

	income_stmt = income_stmt[income_stmt.columns.sort_values(ascending=False)]
	latest_period = income_stmt.columns[0]
	period_series = income_stmt[latest_period].fillna(0)

	revenue = safe_number(period_series.get("Total Revenue", period_series.get("Revenue", 0)))
	cost_of_revenue = abs(safe_number(period_series.get("Cost Of Revenue", 0)))
	gross_profit = safe_number(period_series.get("Gross Profit", revenue - cost_of_revenue))
	operating_expenses = abs(safe_number(period_series.get("Operating Expense", period_series.get("Operating Expenses", 0))))
	net_profit = safe_number(period_series.get("Net Income", period_series.get("Net Income Common Stockholders", 0)))

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

	net_cash = safe_number(info.get('totalCash')) - safe_number(info.get('totalDebt'))

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
	except ImportError as exc:
		raise ImportError(
			"LangChain dependencies are missing. Install langchain, langchain-community, and langchain-openai."
		) from exc

	tools = [
		get_valuation_metrics,
		get_income_statement,
		get_cash_flow_health,
		search_market_context,
	]
	llm = _build_chat_model(model_name, temperature=0.1)

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

def _company_descriptor(info: Mapping[str, Any]) -> str:
	return " ".join(
		str(info.get(key) or "").lower()
		for key in ("sector", "industry", "longBusinessSummary", "shortName", "longName")
	)


def _is_financial_company(info: Mapping[str, Any]) -> bool:
	descriptor = _company_descriptor(info)
	financial_keywords = (
		"financial services",
		"bank",
		"insurance",
		"asset management",
		"capital markets",
		"credit services",
		"brokerage",
		"exchange",
		"payment processing",
	)
	return any(keyword in descriptor for keyword in financial_keywords)


def _is_tech_or_platform_company(info: Mapping[str, Any]) -> bool:
	descriptor = _company_descriptor(info)
	tech_keywords = (
		"technology",
		"software",
		"internet",
		"semiconductor",
		"cloud",
		"communication services",
		"interactive media",
		"digital advertising",
		"consumer electronics",
	)
	return any(keyword in descriptor for keyword in tech_keywords)


def _is_dividend_model_candidate(info: Mapping[str, Any], defaults: Mapping[str, float], focus_text: str) -> bool:
	descriptor = _company_descriptor(info)
	dividend_positive = defaults["dividend_per_share"] > 0
	payout_meaningful = defaults["payout_ratio"] >= 0.25 or safe_number(info.get("dividendYield")) >= 0.015
	income_focus = any(keyword in focus_text for keyword in ("income", "yield", "dividend"))
	mature_income_profile = any(
		keyword in descriptor
		for keyword in ("utility", "telecom", "reit", "real estate", "pipeline", "consumer defensive", "insurance", "bank")
	)
	return dividend_positive and (payout_meaningful or income_focus or mature_income_profile)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
	text = raw_text.strip()
	fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
	if fenced_match:
		text = fenced_match.group(1)
	else:
		start = text.find("{")
		end = text.rfind("}")
		if start != -1 and end != -1 and end > start:
			text = text[start : end + 1]
	try:
		payload = json.loads(text)
	except json.JSONDecodeError as exc:
		raise ValueError(f"Failed to parse valuation recommendation JSON: {exc}") from exc
	if not isinstance(payload, dict):
		raise ValueError("Valuation recommendation payload must be a JSON object.")
	return payload


def _valuation_selection_feedback(
	info: Mapping[str, Any],
	defaults: Mapping[str, float],
	recommendation: Mapping[str, Any],
	analysis_focus: str | None = None,
) -> list[str]:
	focus_text = (analysis_focus or "").lower()
	market_cap = max(safe_number(info.get("marketCap")), defaults["current_price"] * defaults["shares_outstanding"])
	debt_to_market_cap = defaults["total_debt"] / market_cap if market_cap > 0 else 0.0
	book_anchor_usable = defaults["book_value_per_share"] > 0 and defaults["return_on_equity"] > 0
	financial_company = _is_financial_company(info)
	tech_company = _is_tech_or_platform_company(info)
	dividend_candidate = _is_dividend_model_candidate(info, defaults, focus_text)
	leverage_heavy = debt_to_market_cap >= 0.45 and defaults["cost_of_debt"] > 0
	high_growth_company = defaults["high_growth"] >= 0.09
	selected_model = str(recommendation.get("selected_model") or "").upper()
	growth_stage = str(recommendation.get("growth_stage") or "").strip() or None
	feedback: list[str] = []

	if selected_model == "DDM" and defaults["dividend_per_share"] <= 0:
		feedback.append("DDM requires a positive dividend per share. Choose a model that does not rely on dividends if payouts are not meaningful.")

	if growth_stage == "H-Model" and selected_model != "DDM":
		feedback.append("The H-Model is only valid for DDM. Choose a valid growth stage for the selected model.")

	if financial_company and dividend_candidate and selected_model != "DDM":
		feedback.append("This looks like a financial dividend payer. Prefer DDM rather than FCFF, FCFE, or APV unless there is an unusually strong reason not to.")

	if financial_company and not dividend_candidate and book_anchor_usable and selected_model == "FCFF":
		feedback.append("This looks like a financial firm without a strong dividend anchor. Prefer RIM over FCFF unless you can justify why book value and ROE are not informative.")

	if tech_company and selected_model != "FCFF":
		feedback.append("This looks like a technology, platform, internet, or software business. Prefer FCFF over DDM or RIM unless there is a very unusual capital structure or payout profile.")

	if tech_company and high_growth_company and selected_model == "FCFF" and growth_stage == "Single-Stage (Stable)":
		feedback.append("A growth technology company should usually use a Two-Stage or Three-Stage FCFF model rather than a Single-Stage stable-growth model.")

	if selected_model == "APV" and not leverage_heavy:
		feedback.append("APV should only be used when leverage is a central part of the valuation story. Pick another model unless debt and tax shields are genuinely material.")

	return feedback


def _valuation_model_prompt(
	ticker: str,
	info: Mapping[str, Any],
	defaults: Mapping[str, float],
	analysis_focus: str | None,
) -> str:
	focus_line = analysis_focus.strip() if analysis_focus and analysis_focus.strip() else "No extra user focus provided."
	return dedent(
		f"""
		You are selecting the single best valuation model for the public equity ticker {ticker}.

		Allowed models:
		- FCFF
		- FCFE
		- DDM
		- APV
		- RIM

		Allowed growth stages when relevant:
		- Single-Stage (Stable)
		- Two-Stage
		- Three-Stage (Multi-stage decay)
		- H-Model (DDM only)

		Critical model-fit guidance:
		- Banks, insurers, asset managers, brokers, and other financial firms should usually use DDM when dividends are meaningful.
		- Financial firms without meaningful dividends should usually use RIM because book value and ROE are more informative than FCFF.
		- Technology, internet, software, semiconductor, and platform businesses should usually use FCFF.
		- Growth technology businesses should usually use Two-Stage or Three-Stage FCFF, not Single-Stage.
		- Use APV only when leverage and tax shields are central to the valuation.
		- Use FCFE only when direct equity cash flows are clearly more informative than enterprise-value framing.

		Few-shot examples:
		- JPMorgan with meaningful dividends: DDM
		- A non-dividend insurer with strong book value and ROE: RIM
		- Alphabet / Google: FCFF

		User focus:
		- {focus_line}

		Company snapshot:
		- Sector: {info.get('sector') or 'N/A'}
		- Industry: {info.get('industry') or 'N/A'}
		- Business summary: {str(info.get('longBusinessSummary') or info.get('shortName') or info.get('longName') or 'N/A')[:1200]}
		- Current price: {defaults['current_price']}
		- Market cap: {safe_number(info.get('marketCap'))}
		- Revenue growth: {safe_number(info.get('revenueGrowth'))}
		- Earnings growth: {safe_number(info.get('earningsGrowth'))}
		- Operating margin: {safe_number(info.get('operatingMargins'))}
		- Net margin: {safe_number(info.get('profitMargins'))}
		- Return on equity: {safe_number(info.get('returnOnEquity'))}
		- Dividend yield: {safe_number(info.get('dividendYield'))}
		- Dividend per share: {defaults['dividend_per_share']}
		- Payout ratio: {defaults['payout_ratio']}
		- Starting FCFF proxy: {defaults['starting_fcff']}
		- Starting FCFE proxy: {defaults['starting_fcfe']}
		- Book value per share: {defaults['book_value_per_share']}
		- Total debt: {defaults['total_debt']}
		- Cash: {defaults['cash']}

		Return valid JSON only in this exact shape:
		{{
		  "selected_model": "FCFF",
		  "growth_stage": "Two-Stage",
		  "model_reason": "why this is the best fit for the ticker"
		}}
		"""
	).strip()


def _valuation_parameter_prompt(
	ticker: str,
	info: Mapping[str, Any],
	defaults: Mapping[str, float],
	selected_model: str,
	growth_stage: str | None,
	analysis_focus: str | None,
) -> str:
	focus_line = analysis_focus.strip() if analysis_focus and analysis_focus.strip() else "No extra user focus provided."
	growth_stage_line = growth_stage or "None"
	return dedent(
		f"""
		You are selecting the best-fit editable valuation parameters for the public equity ticker {ticker}.

		The valuation model has already been selected:
		- Model: {selected_model}
		- Growth stage: {growth_stage_line}

		Rules:
		- Use the chosen model and growth stage. Do not change them.
		- Only recommend editable assumptions such as growth rates, discount rates, and forecast horizon.
		- Do not override factual company inputs like price, shares, FCFF, FCFE, debt, cash, dividends, book value, tax rate, payout ratio, or ROE.
		- Keep terminal growth below the relevant discount rate.
		- Use decimal rates, for example 0.10 means 10%.
		- Use integers for year counts.
		- Return valid JSON only.

		User focus:
		- {focus_line}

		Company snapshot:
		- Sector: {info.get('sector') or 'N/A'}
		- Industry: {info.get('industry') or 'N/A'}
		- Current price: {defaults['current_price']}
		- Revenue growth: {safe_number(info.get('revenueGrowth'))}
		- Earnings growth: {safe_number(info.get('earningsGrowth'))}
		- Operating margin: {safe_number(info.get('operatingMargins'))}
		- Net margin: {safe_number(info.get('profitMargins'))}
		- Return on equity: {defaults['return_on_equity']}
		- Dividend per share: {defaults['dividend_per_share']}
		- Starting FCFF proxy: {defaults['starting_fcff']}
		- Starting FCFE proxy: {defaults['starting_fcfe']}
		- Book value per share: {defaults['book_value_per_share']}
		- WACC anchor: {defaults['wacc']}
		- Cost of equity anchor: {defaults['cost_of_equity']}
		- Unlevered cost anchor: {defaults['unlevered_cost']}
		- High growth anchor: {defaults['high_growth']}
		- Stable growth anchor: {defaults['stable_growth']}
		- Projection years anchor: {defaults['projection_years']}
		- High-growth years anchor: {defaults['high_growth_years']}
		- Fade years anchor: {defaults['transition_years']}

		Return valid JSON only in this exact shape:
		{{
		  "parameter_reason": "overall explanation for the chosen parameter set",
		  "assumptions": {{
		    "wacc": null,
		    "cost_of_equity": null,
		    "required_return": null,
		    "unlevered_cost": null,
		    "high_growth": null,
		    "stable_growth": null,
		    "terminal_growth": null,
		    "short_term_growth": null,
		    "projection_years": null,
		    "high_growth_years": null,
		    "transition_years": null,
		    "half_life_years": null
		  }},
		  "assumption_reasons": [
		    {{"key": "wacc", "reason": "why this assumption is appropriate"}}
		  ]
		}}
		"""
	).strip()


def _default_llm_parameter_fallback(
	selected_model: str,
	growth_stage: str | None,
	defaults: Mapping[str, float],
) -> dict[str, Any]:
	assumptions: dict[str, float] = {}
	if selected_model == "FCFF":
		assumptions["wacc"] = defaults["wacc"]
		if growth_stage == "Single-Stage (Stable)":
			assumptions["stable_growth"] = defaults["stable_growth"]
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["high_growth_years"] = defaults["high_growth_years"]
			assumptions["transition_years"] = defaults["transition_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
		else:
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["projection_years"] = defaults["projection_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
	elif selected_model == "FCFE":
		assumptions["cost_of_equity"] = defaults["cost_of_equity"]
		if growth_stage == "Single-Stage (Stable)":
			assumptions["stable_growth"] = defaults["stable_growth"]
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["high_growth_years"] = defaults["high_growth_years"]
			assumptions["transition_years"] = defaults["transition_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
		else:
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["projection_years"] = defaults["projection_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
	elif selected_model == "DDM":
		assumptions["required_return"] = defaults["cost_of_equity"]
		if growth_stage == "H-Model":
			assumptions["short_term_growth"] = defaults["high_growth"]
			assumptions["stable_growth"] = defaults["stable_growth"]
			assumptions["half_life_years"] = defaults["projection_years"] / 2
		elif growth_stage == "Single-Stage (Stable)":
			assumptions["stable_growth"] = defaults["stable_growth"]
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["high_growth_years"] = defaults["high_growth_years"]
			assumptions["transition_years"] = defaults["transition_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
		else:
			assumptions["high_growth"] = defaults["high_growth"]
			assumptions["projection_years"] = defaults["projection_years"]
			assumptions["terminal_growth"] = defaults["stable_growth"]
	elif selected_model == "APV":
		assumptions["unlevered_cost"] = defaults["unlevered_cost"]
		assumptions["high_growth"] = defaults["high_growth"]
		assumptions["projection_years"] = defaults["projection_years"]
		assumptions["terminal_growth"] = defaults["stable_growth"]
	else:
		assumptions["cost_of_equity"] = defaults["cost_of_equity"]
		assumptions["projection_years"] = defaults["projection_years"]
		assumptions["terminal_growth"] = defaults["stable_growth"]

	return {
		"parameter_reason": "Fallback to model-consistent default anchors after the LLM did not return a fully usable parameter set.",
		"assumptions": assumptions,
		"assumption_reasons": [
			{"key": key, "reason": "Fallback to the default anchor generated from company fundamentals."}
			for key in assumptions
		],
	}


def _merge_recommended_assumptions(defaults: Mapping[str, float], raw_assumptions: Mapping[str, Any]) -> dict[str, float]:
	merged = dict(defaults)
	merged.setdefault("required_return", merged["cost_of_equity"])
	merged.setdefault("half_life_years", merged["projection_years"] / 2)
	for key, value in raw_assumptions.items():
		if value is None:
			continue
		if key in YAHOO_LOCKED_ASSUMPTIONS:
			continue
		if key in {"projection_years", "high_growth_years", "transition_years", "half_life_years"}:
			merged[key] = float(value)
			continue
		merged[key] = float(value)
	return merged


def _assumption_keys_for_choice(selected_model: str, growth_stage: str | None) -> list[str]:
	if selected_model == "FCFF":
		if growth_stage == "Single-Stage (Stable)":
			return ["starting_fcff", "shares_outstanding", "wacc", "stable_growth", "total_debt", "cash", "current_price"]
		if growth_stage == "Three-Stage (Multi-stage decay)":
			return ["starting_fcff", "shares_outstanding", "wacc", "high_growth", "high_growth_years", "transition_years", "terminal_growth", "total_debt", "cash", "current_price"]
		return ["starting_fcff", "shares_outstanding", "wacc", "high_growth", "projection_years", "terminal_growth", "total_debt", "cash", "current_price"]
	if selected_model == "FCFE":
		if growth_stage == "Single-Stage (Stable)":
			return ["starting_fcfe", "shares_outstanding", "cost_of_equity", "stable_growth", "current_price"]
		if growth_stage == "Three-Stage (Multi-stage decay)":
			return ["starting_fcfe", "shares_outstanding", "cost_of_equity", "high_growth", "high_growth_years", "transition_years", "terminal_growth", "current_price"]
		return ["starting_fcfe", "shares_outstanding", "cost_of_equity", "high_growth", "projection_years", "terminal_growth", "current_price"]
	if selected_model == "DDM":
		if growth_stage == "Single-Stage (Stable)":
			return ["dividend_per_share", "shares_outstanding", "required_return", "stable_growth", "current_price"]
		if growth_stage == "Three-Stage (Multi-stage decay)":
			return ["dividend_per_share", "shares_outstanding", "required_return", "high_growth", "high_growth_years", "transition_years", "terminal_growth", "current_price"]
		if growth_stage == "H-Model":
			return ["dividend_per_share", "shares_outstanding", "required_return", "short_term_growth", "stable_growth", "half_life_years", "current_price"]
		return ["dividend_per_share", "shares_outstanding", "required_return", "high_growth", "projection_years", "terminal_growth", "current_price"]
	if selected_model == "APV":
		return ["starting_fcff", "shares_outstanding", "high_growth", "projection_years", "unlevered_cost", "terminal_growth", "total_debt", "cash", "tax_rate", "cost_of_debt", "current_price"]
	return ["book_value_per_share", "shares_outstanding", "return_on_equity", "cost_of_equity", "payout_ratio", "projection_years", "terminal_growth", "current_price"]


def _calculate_recommended_value(
	info: Mapping[str, Any],
	recommendation: Mapping[str, Any],
	annual_cashflow=None,
	annual_balance_sheet=None,
	annual_income_stmt=None,
) -> dict[str, Any]:
	selected_model = str(recommendation.get("selected_model") or "").upper()
	if selected_model not in MODEL_NAME_MAP:
		raise ValueError("AI returned an unsupported valuation model.")

	defaults = default_valuation_inputs(
		info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	defaults["required_return"] = defaults["cost_of_equity"]
	defaults["half_life_years"] = defaults["projection_years"] / 2
	merged = _merge_recommended_assumptions(defaults, recommendation.get("assumptions") or {})
	growth_stage = recommendation.get("growth_stage")
	if selected_model in {"FCFF", "FCFE", "DDM"} and growth_stage not in {
		"Single-Stage (Stable)",
		"Two-Stage",
		"Three-Stage (Multi-stage decay)",
		"H-Model",
	}:
		growth_stage = "Two-Stage"

	if selected_model == "FCFF":
		if growth_stage == "Single-Stage (Stable)":
			result = calculate_fcff_single_stage(merged["starting_fcff"], merged["shares_outstanding"], merged["wacc"], merged["stable_growth"], merged["total_debt"], merged["cash"], merged["current_price"])
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			result = calculate_fcff_three_stage(merged["starting_fcff"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["high_growth_years"])), int(round(merged["transition_years"])), merged["wacc"], merged["terminal_growth"], merged["total_debt"], merged["cash"], merged["current_price"])
		else:
			result = calculate_fcff_two_stage(merged["starting_fcff"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["projection_years"])), merged["wacc"], merged["terminal_growth"], merged["total_debt"], merged["cash"], merged["current_price"])
	elif selected_model == "FCFE":
		if growth_stage == "Single-Stage (Stable)":
			result = calculate_fcfe_single_stage(merged["starting_fcfe"], merged["shares_outstanding"], merged["cost_of_equity"], merged["stable_growth"], merged["current_price"])
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			result = calculate_fcfe_three_stage(merged["starting_fcfe"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["high_growth_years"])), int(round(merged["transition_years"])), merged["cost_of_equity"], merged["terminal_growth"], merged["current_price"])
		else:
			result = calculate_fcfe_two_stage(merged["starting_fcfe"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["projection_years"])), merged["cost_of_equity"], merged["terminal_growth"], merged["current_price"])
	elif selected_model == "DDM":
		if growth_stage == "Single-Stage (Stable)":
			result = calculate_ddm_single_stage(merged["dividend_per_share"], merged["shares_outstanding"], merged["required_return"], merged["stable_growth"], merged["current_price"])
		elif growth_stage == "Three-Stage (Multi-stage decay)":
			result = calculate_ddm_three_stage(merged["dividend_per_share"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["high_growth_years"])), int(round(merged["transition_years"])), merged["required_return"], merged["terminal_growth"], merged["current_price"])
		elif growth_stage == "H-Model":
			result = calculate_ddm_h_model(merged["dividend_per_share"], merged["shares_outstanding"], merged["short_term_growth"], merged["stable_growth"], merged["half_life_years"], merged["required_return"], merged["current_price"])
		else:
			result = calculate_ddm_two_stage(merged["dividend_per_share"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["projection_years"])), merged["required_return"], merged["terminal_growth"], merged["current_price"])
	elif selected_model == "APV":
		growth_stage = None
		result = calculate_apv(merged["starting_fcff"], merged["shares_outstanding"], merged["high_growth"], int(round(merged["projection_years"])), merged["unlevered_cost"], merged["terminal_growth"], merged["total_debt"], merged["cash"], merged["tax_rate"], merged["cost_of_debt"], merged["current_price"])
	else:
		growth_stage = None
		result = calculate_rim(merged["book_value_per_share"], merged["shares_outstanding"], merged["return_on_equity"], merged["cost_of_equity"], merged["payout_ratio"], int(round(merged["projection_years"])), merged["terminal_growth"], merged["current_price"])

	reason_lookup = {
		item.get("key"): item.get("reason")
		for item in (recommendation.get("assumption_reasons") or [])
		if isinstance(item, dict) and item.get("key")
	}
	used_keys = _assumption_keys_for_choice(selected_model, growth_stage)
	used_assumptions = [
		{
			"key": key,
			"label": ASSUMPTION_LABELS.get(key, key.replace("_", " ").title()),
			"value": merged.get(key),
			"reason": reason_lookup.get(key, "AI selected this assumption as part of the recommended model setup."),
		}
		for key in used_keys
	]

	return {
		"selected_model": selected_model,
		"model_name": MODEL_NAME_MAP[selected_model],
		"growth_stage": growth_stage,
		"model_reason": str(recommendation.get("model_reason") or "").strip(),
		"parameter_reason": str(recommendation.get("parameter_reason") or "").strip(),
		"assumptions": used_assumptions,
		"fair_value_per_share": result.fair_value_per_share,
		"current_price": result.current_price,
		"margin_of_safety": result.margin_of_safety,
		"equity_value": result.equity_value,
		"present_value_of_cash_flows": result.present_value_of_cash_flows,
		"discounted_terminal_value": result.discounted_terminal_value,
		"enterprise_value": result.enterprise_value,
		"tax_shield_value": result.tax_shield_value,
	}


def recommend_valuation_model(
	target_ticker: str,
	stock_info: Mapping[str, Any] | Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	ticker = target_ticker.strip().upper()
	if not ticker:
		raise ValueError("A target ticker is required.")

	company_info = getattr(stock_info, "info", stock_info)
	annual_cashflow = getattr(stock_info, "annual_cashflow", None)
	annual_balance_sheet = getattr(stock_info, "annual_balance_sheet", None)
	annual_income_stmt = getattr(stock_info, "annual_income_stmt", None)
	defaults = default_valuation_inputs(
		company_info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	llm = _build_chat_model(model_name or os.getenv("AUTOGRAHAM_AGENT_MODEL", "gpt-4.1-mini"), temperature=0.1)
	model_prompt = _valuation_model_prompt(
		ticker,
		company_info,
		defaults,
		analysis_focus,
	)
	last_error: Exception | None = None
	last_model_recommendation: dict[str, Any] | None = None
	prompt = model_prompt
	for _ in range(3):
		response = llm.invoke(prompt)
		content = response.content if hasattr(response, "content") else str(response)
		if isinstance(content, list):
			content = "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
		try:
			recommendation = _extract_json_object(str(content))
			last_model_recommendation = recommendation
			feedback = _valuation_selection_feedback(
				company_info,
				defaults,
				recommendation,
				analysis_focus=analysis_focus,
			)
			if feedback:
				prompt = (
					model_prompt
					+ "\n\nYour previous recommendation did not fit the company/model guidance. Revise it and return JSON only.\n"
					+ "\n".join(f"- {issue}" for issue in feedback)
				)
				continue
			break
		except Exception as exc:
			last_error = exc
			prompt = (
				model_prompt
				+ "\n\nYour previous response could not be used. Fix the issue below and return valid JSON only.\n"
				+ f"- {exc}"
			)

	if not last_model_recommendation:
		if last_error is not None:
			raise last_error
		raise ValueError("The valuation model recommendation did not return a usable result.")

	selected_model = str(last_model_recommendation.get("selected_model") or "").upper()
	growth_stage = last_model_recommendation.get("growth_stage")
	if selected_model not in MODEL_NAME_MAP:
		raise ValueError("The valuation model recommendation did not return a supported model.")

	parameter_prompt = _valuation_parameter_prompt(
		ticker,
		company_info,
		defaults,
		selected_model,
		growth_stage,
		analysis_focus,
	)
	prompt = parameter_prompt
	for _ in range(3):
		response = llm.invoke(prompt)
		content = response.content if hasattr(response, "content") else str(response)
		if isinstance(content, list):
			content = "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
		try:
			parameter_payload = _extract_json_object(str(content))
			combined_recommendation = {
				"selected_model": selected_model,
				"growth_stage": growth_stage,
				"model_reason": str(last_model_recommendation.get("model_reason") or "").strip(),
				"parameter_reason": str(parameter_payload.get("parameter_reason") or "").strip(),
				"assumptions": parameter_payload.get("assumptions") or {},
				"assumption_reasons": parameter_payload.get("assumption_reasons") or [],
			}
			return _calculate_recommended_value(
				company_info,
				combined_recommendation,
				annual_cashflow=annual_cashflow,
				annual_balance_sheet=annual_balance_sheet,
				annual_income_stmt=annual_income_stmt,
			)
		except Exception as exc:
			last_error = exc
			prompt = (
				parameter_prompt
				+ "\n\nYour previous parameter recommendation could not be used. Fix the issue below and return JSON only.\n"
				+ f"- {exc}"
			)

	fallback_parameters = _default_llm_parameter_fallback(selected_model, growth_stage, defaults)
	fallback_recommendation = {
		"selected_model": selected_model,
		"growth_stage": growth_stage,
		"model_reason": str(last_model_recommendation.get("model_reason") or "").strip(),
		"parameter_reason": str(fallback_parameters.get("parameter_reason") or "").strip(),
		"assumptions": fallback_parameters.get("assumptions") or {},
		"assumption_reasons": fallback_parameters.get("assumption_reasons") or [],
	}
	return _calculate_recommended_value(
		company_info,
		fallback_recommendation,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
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


def run_ai_analysis(
	target_ticker: str,
	stock_info: Mapping[str, Any] | Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	memo_markdown = run_competitor_analysis(
		target_ticker,
		model_name=model_name,
		analysis_focus=analysis_focus,
	)
	result: dict[str, Any] = {"memo_markdown": memo_markdown}
	try:
		result["valuation_pick"] = recommend_valuation_model(
			target_ticker,
			stock_info,
			model_name=model_name,
			analysis_focus=analysis_focus,
		)
	except Exception as exc:
		result["valuation_pick_error"] = str(exc)
	return result
