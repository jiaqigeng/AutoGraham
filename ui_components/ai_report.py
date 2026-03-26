from __future__ import annotations

from typing import Any, Iterable, Mapping

try:
	import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - allows pure helper tests without Streamlit installed
	st = None


PERCENT_KEYS = {
	"wacc",
	"cost_of_equity",
	"required_return",
	"growth_rate",
	"high_growth",
	"stable_growth",
	"terminal_growth",
	"return_on_equity",
	"payout_ratio",
	"tax_rate",
	"ebit_margin",
}
YEAR_KEYS = {"projection_years"}
COUNT_KEYS = {"shares_outstanding"}
CURRENCY_KEYS = {
	"revenue",
	"depreciation",
	"capex",
	"change_in_nwc",
	"net_borrowing",
	"total_debt",
	"cash",
	"book_value_per_share",
	"starting_fcff",
	"starting_fcfe",
	"current_fcff",
	"current_fcfe",
	"current_dividend_per_share",
	"dividend_per_share",
}
DIRECT_FACT_KEYS = {
	"current_price",
	"shares_outstanding",
	"total_debt",
	"cash",
	"book_value_per_share",
	"current_fcff",
	"current_fcfe",
	"current_dividend_per_share",
	"dividend_per_share",
}


def _coerce_float(value: object) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _escape_markdown_cell(value: object) -> str:
	text = str(value if value not in (None, "") else "N/A")
	return text.replace("|", r"\|").replace("\n", " ").strip()


def _format_currency(value: object) -> str:
	number = _coerce_float(value)
	if number is None:
		return "N/A"
	sign = "-" if number < 0 else ""
	abs_number = abs(number)
	if abs_number >= 1_000_000_000_000:
		return f"{sign}${abs_number / 1_000_000_000_000:,.2f}T"
	if abs_number >= 1_000_000_000:
		return f"{sign}${abs_number / 1_000_000_000:,.2f}B"
	if abs_number >= 1_000_000:
		return f"{sign}${abs_number / 1_000_000:,.2f}M"
	if abs_number >= 1_000:
		return f"{sign}${abs_number / 1_000:,.2f}K"
	return f"{sign}${abs_number:,.2f}"


def _format_count(value: object) -> str:
	number = _coerce_float(value)
	if number is None:
		return "N/A"
	abs_number = abs(number)
	sign = "-" if number < 0 else ""
	if abs_number >= 1_000_000_000_000:
		return f"{sign}{abs_number / 1_000_000_000_000:,.2f}T"
	if abs_number >= 1_000_000_000:
		return f"{sign}{abs_number / 1_000_000_000:,.2f}B"
	if abs_number >= 1_000_000:
		return f"{sign}{abs_number / 1_000_000:,.2f}M"
	if abs_number >= 1_000:
		return f"{sign}{abs_number / 1_000:,.2f}K"
	return f"{number:,.0f}"


def _format_generic_number(value: object) -> str:
	number = _coerce_float(value)
	if number is None:
		return str(value) if value not in (None, "") else "N/A"
	if abs(number) >= 100:
		return f"{number:,.2f}"
	if number.is_integer():
		return f"{number:,.0f}"
	return f"{number:,.2f}"


def _format_percent_value(value: object) -> str:
	number = _coerce_float(value)
	if number is None:
		return str(value) if value not in (None, "") else "N/A"
	if abs(number) > 1:
		return f"{number:,.2f}%"
	return f"{number:.2%}"


def _format_assumption_scalar(key: str, value: object) -> str:
	if key in YEAR_KEYS:
		number = _coerce_float(value)
		if number is None:
			return "N/A"
		rounded = int(round(number))
		suffix = "year" if rounded == 1 else "years"
		return f"{rounded} {suffix}"
	if key in PERCENT_KEYS:
		return _format_percent_value(value)
	if key in COUNT_KEYS:
		return _format_count(value)
	if key in CURRENCY_KEYS:
		return _format_currency(value)
	return _format_generic_number(value)


def _label_from_key(key: str) -> str:
	return key.replace("_", " ").title()


def _first_sentence(text: str) -> str:
	cleaned = " ".join(text.split()).strip()
	if not cleaned:
		return ""
	for separator in (". ", "! ", "? "):
		if separator in cleaned:
			return f"{cleaned.split(separator, 1)[0]}{separator.strip()}"
	return cleaned


def _classify_assumption_origin(key: str, value: object, fetched_fact_keys: set[str]) -> str:
	if key in fetched_fact_keys or key in DIRECT_FACT_KEYS:
		return "direct"
	if isinstance(value, list):
		return "forecast"
	return "estimated"


def _build_assumption_reason(key: str, value: object, reason: str, origin: str) -> str:
	base_reason = _first_sentence(reason or "")
	if base_reason:
		return base_reason
	if origin == "direct":
		return "Directly gathered from current company or market data."
	if isinstance(value, list):
		return "Forecast path estimated by the workflow for the explicit projection period."
	return "Estimated by the workflow for the valuation case."


def _normalize_assumptions(
	valuation_pick: Mapping[str, Any] | None,
	parameter_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	fetched_fact_keys = {
		str(item.get("key") or "").strip()
		for item in ((parameter_payload or {}).get("fetched_facts") or [])
		if isinstance(item, Mapping) and str(item.get("key") or "").strip()
	}
	if valuation_pick:
		for item in valuation_pick.get("assumptions") or []:
			if not isinstance(item, Mapping):
				continue
			key = str(item.get("key") or "").strip()
			if not key:
				continue
			value = item.get("value")
			rows.append(
				{
					"key": key,
					"label": str(item.get("label") or _label_from_key(key)),
					"value": value,
					"reason": _build_assumption_reason(
						key,
						value,
						str(item.get("reason") or ""),
						_classify_assumption_origin(key, value, fetched_fact_keys),
					),
					"origin": _classify_assumption_origin(key, value, fetched_fact_keys),
				}
			)
	if rows:
		return rows

	reason_lookup = {
		str(item.get("key") or "").strip(): str(item.get("reason") or "").strip()
		for item in ((parameter_payload or {}).get("assumption_reasons") or [])
		if isinstance(item, Mapping)
	}
	for key, value in dict((parameter_payload or {}).get("assumptions") or {}).items():
		rows.append(
			{
				"key": str(key),
				"label": _label_from_key(str(key)),
				"value": value,
				"reason": _build_assumption_reason(
					str(key),
					value,
					reason_lookup.get(str(key), ""),
					_classify_assumption_origin(str(key), value, fetched_fact_keys),
				),
				"origin": _classify_assumption_origin(str(key), value, fetched_fact_keys),
			}
		)
	return rows


def _summarize_key_drivers(
	assumptions: list[dict[str, Any]],
	valuation_pick: Mapping[str, Any] | None,
) -> str:
	lookup = {row["key"]: row for row in assumptions}
	model_code = str((valuation_pick or {}).get("selected_model") or "").upper()
	drivers: list[str] = []

	if any(isinstance(row.get("value"), list) for row in assumptions):
		drivers.append("a year-by-year forecast")

	if model_code in {"FCFF", "FCFE"}:
		for key in ("wacc", "cost_of_equity", "growth_rate", "terminal_growth"):
			if key in lookup:
				drivers.append(f"{lookup[key]['label']} at {_format_assumption_scalar(key, lookup[key].get('value'))}")
	elif model_code == "DDM":
		for key in ("required_return", "high_growth", "stable_growth", "terminal_growth"):
			if key in lookup:
				drivers.append(f"{lookup[key]['label']} at {_format_assumption_scalar(key, lookup[key].get('value'))}")
	elif model_code == "RIM":
		for key in ("return_on_equity", "payout_ratio", "cost_of_equity", "terminal_growth"):
			if key in lookup:
				drivers.append(f"{lookup[key]['label']} at {_format_assumption_scalar(key, lookup[key].get('value'))}")

	return ", ".join(drivers[:3])


def _build_metric_summary(
	ticker: str | None,
	company_name: str | None,
	model_selection: Mapping[str, Any] | None,
	parameter_payload: Mapping[str, Any] | None,
	valuation_pick: Mapping[str, Any] | None,
	confidence: float | None,
) -> str:
	model_name = str(
		(valuation_pick or {}).get("model_name")
		or (model_selection or {}).get("preferred_calculation_model")
		or (model_selection or {}).get("selected_model")
		or "N/A"
	)
	lines: list[str] = []
	if company_name or ticker:
		lines.append(f"- **Company:** {_escape_markdown_cell(company_name or ticker or 'N/A')}")
	if ticker:
		lines.append(f"- **Ticker:** `{ticker.upper()}`")
	lines.append(f"- **Model:** {_escape_markdown_cell(model_name)}")
	if confidence is not None:
		lines.append(f"- **Confidence:** {_format_percent_value(confidence)}")

	notes: list[str] = []
	model_reason = str((model_selection or {}).get("model_reason") or "").strip()
	if model_reason:
		notes.append(model_reason)
	parameter_reason = str((parameter_payload or {}).get("parameter_reason") or "").strip()
	if parameter_reason:
		notes.append(parameter_reason)

	content = "\n".join(lines)
	if notes:
		content = f"{content}\n\n" + "\n\n".join(notes)
	return content


def _build_assumptions_markdown(assumptions: list[dict[str, Any]]) -> str:
	if not assumptions:
		return "No validated assumptions were available."

	rows = [
		"| Assumption | Value | Type | Reason |",
		"| --- | --- | --- | --- |",
	]
	forecast_sections: list[str] = []

	for row in assumptions:
		key = str(row.get("key") or "")
		label = _escape_markdown_cell(row.get("label") or key)
		value = row.get("value")
		origin = str(row.get("origin") or "estimated")
		origin_label = "Direct data" if origin == "direct" else "Forecast" if origin == "forecast" else "Estimated"
		if isinstance(value, list):
			value_summary = f"{len(value)} projected values"
			forecast_rows = [
				f"### {label}",
				"",
				"| Year | Value |",
				"| --- | --- |",
			]
			for index, item in enumerate(value, start=1):
				forecast_rows.append(f"| {index} | {_escape_markdown_cell(_format_assumption_scalar(key, item))} |")
			forecast_sections.append("\n".join(forecast_rows))
		else:
			value_summary = _format_assumption_scalar(key, value)

		rows.append(
			f"| {label} | {_escape_markdown_cell(value_summary)} | {origin_label} | {_escape_markdown_cell(row.get('reason') or 'N/A')} |"
		)

	content = "\n".join(rows)
	if forecast_sections:
		content = f"{content}\n\n## Forecast Paths\n\n" + "\n\n".join(forecast_sections)
	return content


def _build_schedule_markdown(schedule: object) -> str:
	if not isinstance(schedule, list) or not schedule:
		return ""
	row_items = [row for row in schedule if isinstance(row, Mapping)]
	if not row_items:
		return ""

	headers: list[str] = []
	for row in row_items:
		for key in row:
			key_text = str(key)
			if key_text not in headers:
				headers.append(key_text)

	lines = [
		"| " + " | ".join(_escape_markdown_cell(_label_from_key(header)) for header in headers) + " |",
		"| " + " | ".join("---" for _ in headers) + " |",
	]
	for row in row_items:
		cells = []
		for header in headers:
			value = row.get(header)
			formatted = _format_generic_number(value)
			if header in PERCENT_KEYS:
				formatted = _format_percent_value(value)
			elif any(token in header.lower() for token in ("value", "cash", "debt", "income", "flow", "price")):
				formatted = _format_currency(value)
			cells.append(_escape_markdown_cell(formatted))
		lines.append("| " + " | ".join(cells) + " |")
	return "\n".join(lines)


def _build_comparison_markdown(
	valuation_pick: Mapping[str, Any] | None,
	assumptions: list[dict[str, Any]],
) -> str:
	if not valuation_pick:
		return "Fair value comparison is unavailable."

	fair_value = _coerce_float(valuation_pick.get("fair_value_per_share"))
	current_price = _coerce_float(valuation_pick.get("current_price"))
	margin = _coerce_float(valuation_pick.get("margin_of_safety"))
	if fair_value is None or current_price is None or current_price <= 0:
		return "Fair value comparison is unavailable."
	if margin is None:
		margin = ((fair_value - current_price) / current_price) * 100

	if abs(margin) <= 5:
		stance = "roughly in line with estimated fair value"
	elif fair_value > current_price:
		stance = "below estimated fair value"
	else:
		stance = "above estimated fair value"

	driver_summary = _summarize_key_drivers(assumptions, valuation_pick)
	lines = [
		f"- **Estimated fair value:** {_format_currency(fair_value)}",
		f"- **Current price:** {_format_currency(current_price)}",
		f"- **Margin of safety:** {_format_percent_value(margin)}",
		f"- **Read-through:** The model suggests the shares trade {stance}.",
	]
	if driver_summary:
		lines.append(f"- **Key drivers:** {driver_summary}.")
	return "\n".join(lines)


def _build_sources_markdown(source_links: Iterable[str] | None) -> str:
	links = [link.strip() for link in (source_links or []) if isinstance(link, str) and link.strip()]
	if not links:
		return ""
	return "\n".join(f"- {link}" for link in dict.fromkeys(links))


def build_ai_report_sections(
	report_markdown: str,
	*,
	ticker: str | None = None,
	company_name: str | None = None,
	model_selection: Mapping[str, Any] | None = None,
	parameter_payload: Mapping[str, Any] | None = None,
	valuation_pick: Mapping[str, Any] | None = None,
	explanation_markdown: str | None = None,
	source_links: list[str] | None = None,
	confidence: float | None = None,
) -> dict[str, str]:
	final_text = (explanation_markdown or "").strip() or (report_markdown or "").strip()
	assumptions = _normalize_assumptions(valuation_pick, parameter_payload)
	return {
		"report_markdown": final_text or "No research report was generated.",
		"overview_markdown": _build_metric_summary(
			ticker,
			company_name,
			model_selection,
			parameter_payload,
			valuation_pick,
			confidence,
		),
		"assumptions_markdown": _build_assumptions_markdown(assumptions),
		"comparison_markdown": _build_comparison_markdown(valuation_pick, assumptions),
		"schedule_markdown": _build_schedule_markdown((valuation_pick or {}).get("schedule")),
		"sources_markdown": _build_sources_markdown(source_links),
	}


def render_ai_report(
	report_markdown: str,
	*,
	ticker: str | None = None,
	company_name: str | None = None,
	model_selection: Mapping[str, Any] | None = None,
	parameter_payload: Mapping[str, Any] | None = None,
	valuation_pick: Mapping[str, Any] | None = None,
	explanation_markdown: str | None = None,
	source_links: list[str] | None = None,
	confidence: float | None = None,
) -> None:
	if st is None:
		raise RuntimeError("Streamlit is required to render the AI report.")

	sections = build_ai_report_sections(
		report_markdown,
		ticker=ticker,
		company_name=company_name,
		model_selection=model_selection,
		parameter_payload=parameter_payload,
		valuation_pick=valuation_pick,
		explanation_markdown=explanation_markdown,
		source_links=source_links,
		confidence=confidence,
	)

	if valuation_pick:
		price_col, fair_value_col, margin_col = st.columns(3)
		with price_col:
			st.metric("Current Price", _format_currency(valuation_pick.get("current_price")))
		with fair_value_col:
			st.metric("Estimated Fair Value", _format_currency(valuation_pick.get("fair_value_per_share")))
		with margin_col:
			st.metric("Margin of Safety", _format_percent_value(valuation_pick.get("margin_of_safety")))

	if sections["overview_markdown"]:
		with st.expander("Valuation Overview", expanded=True):
			st.markdown(sections["overview_markdown"])

	st.subheader("Research Report")
	st.markdown(sections["report_markdown"])

	if valuation_pick:
		with st.expander("Assumptions", expanded=True):
			st.markdown(sections["assumptions_markdown"])
		with st.expander("Fair Value Context", expanded=True):
			st.markdown(sections["comparison_markdown"])
		if sections["schedule_markdown"]:
			with st.expander("Valuation Schedule", expanded=False):
				st.markdown(sections["schedule_markdown"])

	if sections["sources_markdown"]:
		with st.expander("Sources", expanded=False):
			st.markdown(sections["sources_markdown"])


__all__ = ["build_ai_report_sections", "render_ai_report"]
