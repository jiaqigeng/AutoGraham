from __future__ import annotations

import html
import re
from typing import Any, Iterable, Mapping


PERCENT_KEYS = {
	"wacc",
	"cost_of_equity",
	"required_return",
	"growth_rate",
	"high_growth",
	"stable_growth",
	"terminal_growth",
	"short_term_growth",
	"return_on_equity",
	"payout_ratio",
	"tax_rate",
	"ebit_margin",
}
YEAR_KEYS = {"projection_years", "high_growth_years", "transition_years", "half_life_years"}
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


def _format_inline(text: str) -> str:
	escaped = html.escape(text.strip())
	escaped = re.sub(r"`([^`]+)`", r'<code class="ai-workflow-inline-code">\1</code>', escaped)
	escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
	escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
	escaped = re.sub(
		r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
		r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
		escaped,
	)
	return escaped


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
		return html.escape(str(value)) if value not in (None, "") else "N/A"
	if abs(number) >= 100:
		return f"{number:,.2f}"
	if number.is_integer():
		return f"{number:,.0f}"
	return f"{number:,.2f}"


def _format_percent_value(value: object) -> str:
	number = _coerce_float(value)
	if number is None:
		return html.escape(str(value)) if value not in (None, "") else "N/A"
	if abs(number) > 1:
		return f"{number:,.2f}%"
	return f"{number:.2%}"


def _format_metric_value(value: object, prefix: str = "") -> str:
	if value is None or value == "":
		return "N/A"
	if prefix == "$":
		return _format_currency(value)
	return _format_generic_number(value)


def _format_margin_of_safety(value: object) -> str:
	return _format_percent_value(value)


def _format_confidence(value: object) -> str:
	if value is None or value == "":
		return "Confidence not available"
	number = _coerce_float(value)
	if number is None:
		return f"Confidence {html.escape(str(value))}"
	return f"Confidence {number:.0%}"


def _label_from_key(key: str) -> str:
	return key.replace("_", " ").title()


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


def _first_sentence(text: str) -> str:
	cleaned = " ".join(text.split()).strip()
	if not cleaned:
		return ""
	match = re.match(r"^(.+?[.!?])(?:\s|$)", cleaned)
	return match.group(1) if match else cleaned


def _classify_assumption_origin(key: str, value: object, fetched_fact_keys: set[str]) -> str:
	if key in fetched_fact_keys or key in DIRECT_FACT_KEYS:
		return "direct"
	if isinstance(value, list):
		return "predicted"
	return "predicted"


def _build_assumption_reason(key: str, value: object, reason: str, origin: str) -> str:
	base_reason = (reason or "").strip()
	if origin == "direct":
		return _first_sentence(base_reason) or "Directly gathered from the latest available market or company-reported data."
	if isinstance(value, list):
		extra = "This is a forward-looking forecast path used to translate the operating view into explicit model-year assumptions."
	else:
		extra = "This is a forward-looking estimate rather than a directly reported figure, so it reflects the valuation model's base-case view."
	if not base_reason:
		return extra
	if extra.lower() in base_reason.lower():
		return base_reason
	return f"{base_reason} {extra}"


def _summarize_list_value(key: str, values: list[object]) -> str:
	if not values:
		return "No projected values"
	return f"{len(values)} projected values for the explicit forecast period"


def _flush_paragraph(paragraph_lines: list[str], blocks: list[str]) -> None:
	if not paragraph_lines:
		return
	content = " ".join(line.strip() for line in paragraph_lines if line.strip())
	if content:
		blocks.append(f'<p class="ai-workflow-paragraph">{_format_inline(content)}</p>')
	paragraph_lines.clear()


def _flush_list(items: list[str], blocks: list[str], ordered: bool) -> None:
	if not items:
		return
	tag = "ol" if ordered else "ul"
	item_html = "".join(f"<li>{_format_inline(item)}</li>" for item in items)
	blocks.append(f'<{tag} class="ai-workflow-list">{item_html}</{tag}>')
	items.clear()


def _split_markdown_table_row(line: str) -> list[str]:
	stripped = line.strip().strip("|")
	return [cell.strip() for cell in stripped.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
	parts = _split_markdown_table_row(line)
	if not parts:
		return False
	return all(re.fullmatch(r":?-{3,}:?", part) for part in parts)


def _render_markdown_table(table_lines: list[str], *, condensed: bool = False) -> str:
	if len(table_lines) < 2:
		return "".join(f'<p class="ai-workflow-paragraph">{_format_inline(line)}</p>' for line in table_lines)
	headers = _split_markdown_table_row(table_lines[0])
	body_lines = table_lines[2:]
	parsed_rows: list[list[str]] = []
	for raw_line in body_lines:
		cells = _split_markdown_table_row(raw_line)
		if len(cells) < len(headers):
			cells.extend([""] * (len(headers) - len(cells)))
		parsed_rows.append(cells[: len(headers)])

	if condensed:
		return (
			'<p class="ai-dashboard-panel-copy ai-research-report-note">'
			"See Fair Value Estimation below for the detailed valuation breakdown."
			"</p>"
		)

	header_html = "".join(f"<th>{_format_inline(cell)}</th>" for cell in headers)
	row_html = []
	for cells in parsed_rows:
		row_html.append("".join(f"<td>{_format_inline(cell)}</td>" for cell in cells))
	rows = "".join(f"<tr>{cells}</tr>" for cells in row_html)
	return (
		'<div class="ai-dashboard-table-wrap">'
		'<table class="ai-dashboard-table ai-workflow-markdown-table">'
		f"<thead><tr>{header_html}</tr></thead>"
		f"<tbody>{rows}</tbody>"
		"</table>"
		"</div>"
	)


def _render_markdown_like(markdown_text: str, *, condensed_tables: bool = False) -> str:
	if not markdown_text or not markdown_text.strip():
		return '<p class="ai-workflow-empty">No workflow result was generated.</p>'

	blocks: list[str] = []
	paragraph_lines: list[str] = []
	list_items: list[str] = []
	list_is_ordered = False
	lines = markdown_text.splitlines()
	index = 0

	while index < len(lines):
		raw_line = lines[index]
		line = raw_line.rstrip()
		stripped = line.strip()

		if not stripped:
			_flush_paragraph(paragraph_lines, blocks)
			_flush_list(list_items, blocks, list_is_ordered)
			index += 1
			continue

		if (
			"|" in stripped
			and index + 1 < len(lines)
			and "|" in lines[index + 1]
			and _is_markdown_table_separator(lines[index + 1].strip())
		):
			_flush_paragraph(paragraph_lines, blocks)
			_flush_list(list_items, blocks, list_is_ordered)
			table_lines = [stripped, lines[index + 1].strip()]
			index += 2
			while index < len(lines):
				table_candidate = lines[index].strip()
				if not table_candidate or "|" not in table_candidate:
					break
				table_lines.append(table_candidate)
				index += 1
			blocks.append(_render_markdown_table(table_lines, condensed=condensed_tables))
			continue

		heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
		if heading_match:
			_flush_paragraph(paragraph_lines, blocks)
			_flush_list(list_items, blocks, list_is_ordered)
			level = min(len(heading_match.group(1)), 3)
			title = _format_inline(heading_match.group(2))
			blocks.append(f'<h{level} class="ai-workflow-heading ai-workflow-heading-{level}">{title}</h{level}>')
			index += 1
			continue

		unordered_match = re.match(r"^[-*]\s+(.*)$", stripped)
		ordered_match = re.match(r"^\d+[.)]\s+(.*)$", stripped)
		if unordered_match or ordered_match:
			current_is_ordered = bool(ordered_match)
			item = (ordered_match or unordered_match).group(1)
			if list_items and current_is_ordered != list_is_ordered:
				_flush_list(list_items, blocks, list_is_ordered)
			_flush_paragraph(paragraph_lines, blocks)
			list_is_ordered = current_is_ordered
			list_items.append(item)
			index += 1
			continue

		if list_items:
			_flush_list(list_items, blocks, list_is_ordered)
		paragraph_lines.append(stripped)
		index += 1

	_flush_paragraph(paragraph_lines, blocks)
	_flush_list(list_items, blocks, list_is_ordered)
	return "".join(blocks)


def _split_markdown_sections(markdown_text: str) -> list[tuple[str | None, str]]:
	if not markdown_text or not markdown_text.strip():
		return []

	sections: list[tuple[str | None, str]] = []
	current_title: str | None = None
	current_lines: list[str] = []

	def flush_section() -> None:
		body = "\n".join(current_lines).strip()
		if current_title is not None or body:
			sections.append((current_title, body))

	for raw_line in markdown_text.splitlines():
		stripped = raw_line.strip()
		heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
		if heading_match:
			flush_section()
			current_title = heading_match.group(2).strip()
			current_lines = []
			continue
		current_lines.append(raw_line)

	flush_section()
	if len(sections) > 1 and sections[0][0] and not sections[0][1].strip():
		sections = sections[1:]
	return sections


def _normalize_section_title(title: str | None) -> str:
	return re.sub(r"[^a-z]+", " ", (title or "").strip().lower()).strip()


def _render_argument_paragraph(label: str, body: str) -> str:
	content = " ".join(line.strip() for line in body.splitlines() if line.strip())
	if not content:
		content = "No details provided."
	return f'<p class="ai-dashboard-panel-copy"><strong>{html.escape(label)}.</strong> {_format_inline(content)}</p>'


def _split_table_tail(markdown_text: str) -> tuple[str, str]:
	lines = markdown_text.splitlines()
	for index in range(len(lines) - 1):
		if "|" not in lines[index]:
			continue
		if _is_markdown_table_separator(lines[index + 1].strip()):
			return "\n".join(lines[:index]).strip(), "\n".join(lines[index:]).strip()
	return markdown_text.strip(), ""


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
			rows.append(
				{
					"key": key,
					"label": str(item.get("label") or _label_from_key(key)),
					"value": item.get("value"),
					"reason": str(item.get("reason") or "").strip(),
					"origin": _classify_assumption_origin(key, item.get("value"), fetched_fact_keys),
				}
			)
	if rows:
		return rows

	assumptions = dict((parameter_payload or {}).get("assumptions") or {})
	reason_lookup = {
		str(item.get("key") or "").strip(): str(item.get("reason") or "").strip()
		for item in ((parameter_payload or {}).get("assumption_reasons") or [])
		if isinstance(item, Mapping)
	}
	for key, value in assumptions.items():
		rows.append(
			{
				"key": str(key),
				"label": _label_from_key(str(key)),
				"value": value,
				"reason": reason_lookup.get(str(key), "Estimated assumption used by the valuation workflow."),
				"origin": _classify_assumption_origin(str(key), value, fetched_fact_keys),
			}
		)
	return rows


def _render_projection_table(key: str, values: list[object]) -> str:
	headers = "".join(f"<th>Year {index}</th>" for index in range(1, len(values) + 1))
	cells = "".join(f"<td>{_format_assumption_scalar(key, item)}</td>" for item in values)
	return (
		'<div class="ai-dashboard-table-wrap">'
		'<table class="ai-dashboard-table">'
		f"<thead><tr>{headers}</tr></thead>"
		f"<tbody><tr>{cells}</tr></tbody>"
		"</table>"
		"</div>"
	)


def _render_assumption_cards(assumptions: list[dict[str, Any]]) -> str:
	if not assumptions:
		return '<p class="ai-dashboard-empty">No validated assumptions were available for display.</p>'

	cards: list[str] = []
	for row in assumptions:
		key = row["key"]
		label = html.escape(row["label"])
		value = row.get("value")
		origin = str(row.get("origin") or "predicted")
		reason = _format_inline(_build_assumption_reason(key, value, str(row.get("reason") or ""), origin))
		if isinstance(value, list):
			summary = _summarize_list_value(key, value)
			value_block = _render_projection_table(key, value)
		else:
			summary = _format_assumption_scalar(key, value)
			value_block = ""
		cards.append(
			'<article class="ai-dashboard-assumption-card">'
			f'<div class="ai-dashboard-assumption-head"><div class="ai-dashboard-assumption-label">{label}</div>'
			f'<div class="ai-dashboard-assumption-summary">{html.escape(summary)}</div></div>'
			f"{value_block}"
			f'<p class="ai-dashboard-assumption-reason">{reason}</p>'
			"</article>"
		)
	return "".join(cards)


def _summarize_key_drivers(
	assumptions: list[dict[str, Any]],
	valuation_pick: Mapping[str, Any] | None,
) -> str:
	lookup = {row["key"]: row for row in assumptions}
	model_code = str((valuation_pick or {}).get("selected_model") or "").upper()
	drivers: list[str] = []

	if any(isinstance(row.get("value"), list) for row in assumptions):
		drivers.append("a year-by-year operating forecast")

	if model_code in {"FCFF", "FCFE"}:
		discount_key = "wacc" if "wacc" in lookup else "cost_of_equity"
		if discount_key in lookup:
			drivers.append(f"{lookup[discount_key]['label']} at {_format_assumption_scalar(discount_key, lookup[discount_key].get('value'))}")
		if "growth_rate" in lookup:
			drivers.append(f"explicit growth at {_format_assumption_scalar('growth_rate', lookup['growth_rate'].get('value'))}")
		elif "high_growth" in lookup:
			drivers.append(f"initial growth at {_format_assumption_scalar('high_growth', lookup['high_growth'].get('value'))}")
		if "terminal_growth" in lookup:
			drivers.append(f"terminal growth at {_format_assumption_scalar('terminal_growth', lookup['terminal_growth'].get('value'))}")
	elif model_code == "DDM":
		if "required_return" in lookup:
			drivers.append(f"required return at {_format_assumption_scalar('required_return', lookup['required_return'].get('value'))}")
		for growth_key in ("stable_growth", "high_growth", "short_term_growth", "terminal_growth"):
			if growth_key in lookup:
				drivers.append(f"{lookup[growth_key]['label']} of {_format_assumption_scalar(growth_key, lookup[growth_key].get('value'))}")
				break
	elif model_code == "RIM":
		for key in ("return_on_equity", "payout_ratio", "cost_of_equity", "terminal_growth"):
			if key in lookup:
				drivers.append(f"{lookup[key]['label']} at {_format_assumption_scalar(key, lookup[key].get('value'))}")

	return ", ".join(drivers[:3])


def _comparison_reason_points(
	gap: float,
	margin: float,
	assumptions: list[dict[str, Any]],
	valuation_pick: Mapping[str, Any] | None,
) -> list[str]:
	lookup = {row["key"]: row for row in assumptions}
	model_code = str((valuation_pick or {}).get("selected_model") or "").upper()
	reasons: list[str] = []
	is_upside = gap > 0

	if any(isinstance(row.get("value"), list) for row in assumptions):
		reasons.append(
			"the explicit forecast assumes operating performance and cash generation that may turn out stronger than current market expectations"
			if is_upside
			else "the explicit forecast assumes more modest operating performance and cash generation than the market may currently be discounting"
		)

	if "wacc" in lookup:
		reasons.append(
			f"the valuation uses WACC of {_format_assumption_scalar('wacc', lookup['wacc'].get('value'))}, so small changes in discount rate can move present value materially"
		)
	elif "cost_of_equity" in lookup:
		reasons.append(
			f"the valuation uses cost of equity of {_format_assumption_scalar('cost_of_equity', lookup['cost_of_equity'].get('value'))}, which has a large impact on discounted value"
		)

	if "terminal_growth" in lookup:
		reasons.append(
			f"terminal growth of {_format_assumption_scalar('terminal_growth', lookup['terminal_growth'].get('value'))} drives a meaningful portion of long-run value"
		)

	if model_code in {"FCFF", "FCFE"}:
		reasons.append(
			"the difference may come from different views on margin durability, reinvestment needs, and how much cash flow the business can convert into distributable value"
		)
	elif model_code == "DDM":
		reasons.append(
			"the difference may come from different views on dividend growth durability, payout capacity, and the return investors require for owning the equity"
		)
	elif model_code == "RIM":
		reasons.append(
			"the difference may come from different views on sustainable ROE, book value growth, and how quickly excess returns fade toward a mature steady state"
		)

	if abs(margin) > 20:
		reasons.append(
			"the spread is wide enough that even modest changes to growth, discount rates, or terminal assumptions could narrow or widen the gap meaningfully"
		)

	return reasons[:5]


def _render_comparison_section(
	valuation_pick: Mapping[str, Any] | None,
	assumptions: list[dict[str, Any]],
) -> str:
	if not valuation_pick:
		return '<p class="ai-dashboard-empty">Fair value comparison is unavailable.</p>'

	fair_value = _coerce_float(valuation_pick.get("fair_value_per_share"))
	current_price = _coerce_float(valuation_pick.get("current_price"))
	margin = _coerce_float(valuation_pick.get("margin_of_safety"))
	if fair_value is None or current_price is None or current_price <= 0:
		return '<p class="ai-dashboard-empty">Fair value comparison is unavailable.</p>'

	if margin is None:
		margin = ((fair_value - current_price) / current_price) * 100
	gap = fair_value - current_price
	driver_summary = _summarize_key_drivers(assumptions, valuation_pick)
	reason_points = _comparison_reason_points(gap, margin, assumptions, valuation_pick)
	if abs(margin) <= 5:
		narrative = "Our estimated fair value is close to the current market price, so the model is broadly consistent with the market's expectations."
	elif gap > 0:
		narrative = "Our estimated fair value is above the current market price, so the model is assuming better long-term economics than the market is currently pricing."
	else:
		narrative = "Our estimated fair value is below the current market price, so the model is more conservative than the expectations embedded in the current quote."
	if driver_summary:
		narrative = f"{narrative} The main drivers here are {driver_summary}."
	reason_copy = ""
	if reason_points:
		reason_copy = "<p class=\"ai-dashboard-panel-copy\">Possible reasons include " + "; ".join(
			html.escape(point) for point in reason_points
		) + ".</p>"

	return (
		f'<p class="ai-dashboard-panel-copy">{html.escape(narrative)}</p>'
		f"{reason_copy}"
		f'<p class="ai-dashboard-footnote">Using the corrected formula, the implied margin of safety is <strong>{_format_margin_of_safety(margin)}</strong> versus the live price.</p>'
	)


def _render_model_section(
	ticker: str | None,
	company_name: str | None,
	model_selection: Mapping[str, Any] | None,
	parameter_payload: Mapping[str, Any] | None,
	valuation_pick: Mapping[str, Any] | None,
) -> str:
	company_label = html.escape(company_name or ticker or "this company")
	model_name = html.escape(
		str(
			(valuation_pick or {}).get("model_name")
			or (model_selection or {}).get("preferred_calculation_model")
			or (model_selection or {}).get("selected_model")
			or "N/A"
		)
	)
	model_reason = str((model_selection or {}).get("model_reason") or "").strip()
	parameter_reason = str((parameter_payload or {}).get("parameter_reason") or "").strip()
	if not model_reason:
		model_reason = (
			f"The workflow selected {html.unescape(model_name)} because it was the best match for the cash-flow profile and capital structure observed for {html.unescape(company_label)}."
		)
	return (
		f'<p class="ai-dashboard-panel-copy">{company_label} was valued using <strong>{model_name}</strong>. {html.escape(model_reason)}</p>'
		f'<div class="ai-dashboard-detail-row"><span>Model</span><span class="ai-dashboard-detail-value ai-dashboard-detail-value-strong">{model_name}</span></div>'
		f'<div class="ai-dashboard-detail-row"><span>Parameter Framing</span><span class="ai-dashboard-detail-value ai-dashboard-detail-value-half">{html.escape(parameter_reason or "Validated assumptions were passed into the deterministic valuation engine.")}</span></div>'
	)


def _render_metric_cards(valuation_pick: Mapping[str, Any] | None) -> str:
	if not valuation_pick:
		return ""
	margin = _coerce_float(valuation_pick.get("margin_of_safety"))
	margin_tone = "is-positive" if (margin or 0) > 0 else "is-negative" if (margin or 0) < 0 else "is-neutral"
	cards = [
		("Current Price", _format_metric_value(valuation_pick.get("current_price"), prefix="$"), ""),
		("Estimated Fair Value", _format_metric_value(valuation_pick.get("fair_value_per_share"), prefix="$"), ""),
		("Margin of Safety", _format_margin_of_safety(valuation_pick.get("margin_of_safety")), margin_tone),
	]
	card_html = "".join(
		f'<div class="ai-dashboard-metric-card {tone}"><div class="ai-dashboard-metric-label">{label}</div><div class="ai-dashboard-metric-value">{value}</div></div>'
		for label, value, tone in cards
	)
	return f'<div class="ai-dashboard-metrics">{card_html}</div>'


def _render_badges(valuation_pick: Mapping[str, Any] | None, confidence: float | None) -> str:
	badges: list[str] = []
	if valuation_pick:
		model_name = valuation_pick.get("model_name") or valuation_pick.get("selected_model")
		if model_name:
			badges.append(f'<span class="ai-dashboard-badge">{html.escape(str(model_name))}</span>')
		growth_stage = valuation_pick.get("growth_stage")
		if growth_stage:
			badges.append(f'<span class="ai-dashboard-badge">{html.escape(str(growth_stage))}</span>')
	if confidence is not None:
		badges.append(f'<span class="ai-dashboard-badge">{html.escape(_format_confidence(confidence))}</span>')
	return f'<div class="ai-dashboard-badges">{"".join(badges)}</div>' if badges else ""


def _render_report_header(
	ticker: str | None,
	company_name: str | None,
	valuation_pick: Mapping[str, Any] | None,
	confidence: float | None,
) -> str:
	company_label = html.escape(company_name or ticker or "AI Analyst")
	ticker_label = html.escape((ticker or "").upper())
	context_bits = [f'<span class="ai-dashboard-context-chip">Ticker {ticker_label}</span>'] if ticker_label else []
	if valuation_pick and valuation_pick.get("model_name"):
		context_bits.append(
			f'<span class="ai-dashboard-context-chip">Model {html.escape(str(valuation_pick.get("model_name")))}</span>'
		)
	context_line = f'<div class="ai-dashboard-header-meta">{"".join(context_bits)}</div>' if context_bits else ""
	return (
		'<header class="ai-dashboard-header">'
		'<div class="ai-dashboard-header-kicker">AI Analyst Report</div>'
		f'<h2 class="ai-dashboard-header-title">{company_label}</h2>'
		'<p class="ai-dashboard-header-subtitle">A unified research memo, valuation summary, and parameter breakdown with a consistent visual hierarchy for headings, subheadings, and body content.</p>'
		f"{context_line}"
		f"{_render_badges(valuation_pick, confidence)}"
		"</header>"
	)


def _render_sources(source_links: Iterable[str] | None) -> str:
	links = [link.strip() for link in (source_links or []) if isinstance(link, str) and link.strip()]
	if not links:
		return ""
	items = "".join(
		f'<li><a href="{html.escape(link)}" target="_blank" rel="noopener noreferrer">{html.escape(link)}</a></li>'
		for link in dict.fromkeys(links)
	)
	return (
		'<div class="ai-workflow-sources">'
		'<div class="ai-workflow-sources-label">Sources</div>'
		f'<ul class="ai-workflow-source-list">{items}</ul>'
		"</div>"
	)


def _render_research_report(
	explanation_markdown: str | None,
	report_markdown: str,
	source_links: Iterable[str] | None = None,
) -> str:
	final_text = (explanation_markdown or "").strip() or (report_markdown or "").strip()
	if not final_text:
		return '<p class="ai-dashboard-empty">No research report was generated.</p>'
	sections = _split_markdown_sections(final_text)
	if not sections:
		sections = [(None, final_text)]
	section_cards: list[str] = []
	index = 0
	while index < len(sections):
		title, body = sections[index]
		title_key = _normalize_section_title(title)
		next_title, next_body = sections[index + 1] if index + 1 < len(sections) else (None, "")
		next_title_key = _normalize_section_title(next_title)
		third_title, third_body = sections[index + 2] if index + 2 < len(sections) else (None, "")
		third_title_key = _normalize_section_title(third_title)

		if title_key in {"sources", "source", "financial health"}:
			index += 1
			continue

		if (
			title_key == "bulls say bears say"
			and not body.strip()
			and next_title_key in {"bulls say", "bull case"}
			and third_title_key in {"bears say", "bear case"}
		):
			bull_body, bull_tail = _split_table_tail(next_body)
			bear_body, bear_tail = _split_table_tail(third_body)
			table_tail = bear_tail or bull_tail
			section_cards.append(
				'<section class="ai-dashboard-panel ai-dashboard-panel-inner ai-research-report ai-research-section-card">'
				f'<div class="ai-dashboard-panel-title">{html.escape(title or "Bulls Say / Bears Say")}</div>'
				f'{_render_argument_paragraph("Bulls Say", bull_body)}'
				f'{_render_argument_paragraph("Bears Say", bear_body)}'
				f'{_render_markdown_like(table_tail, condensed_tables=True) if table_tail else ""}'
				"</section>"
			)
			index += 3
			continue

		if (
			title_key in {"bulls say", "bull case"}
			and next_title_key in {"bears say", "bear case"}
		):
			bull_body, bull_tail = _split_table_tail(body)
			bear_body, bear_tail = _split_table_tail(next_body)
			table_tail = bear_tail or bull_tail
			section_cards.append(
				'<section class="ai-dashboard-panel ai-dashboard-panel-inner ai-research-report ai-research-section-card">'
				'<div class="ai-dashboard-panel-title">Bulls Say / Bears Say</div>'
				f'{_render_argument_paragraph("Bulls Say", bull_body)}'
				f'{_render_argument_paragraph("Bears Say", bear_body)}'
				f'{_render_markdown_like(table_tail, condensed_tables=True) if table_tail else ""}'
				"</section>"
			)
			index += 2
			continue
		section_title = html.escape(title or "Overview")
		section_body = _render_markdown_like(body, condensed_tables=True) if body else '<p class="ai-dashboard-empty">No details provided.</p>'
		section_cards.append(
			'<section class="ai-dashboard-panel ai-dashboard-panel-inner ai-research-report ai-research-section-card">'
			f'<div class="ai-dashboard-panel-title">{section_title}</div>'
			f"{section_body}"
			"</section>"
		)
		index += 1
	return (
		'<div class="ai-dashboard-estimation-stack ai-research-report-stack">'
		f'{"".join(section_cards)}'
		"</div>"
	)


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
) -> str:
	assumptions = _normalize_assumptions(valuation_pick, parameter_payload)
	if not valuation_pick:
		final_text = (explanation_markdown or "").strip() or (report_markdown or "").strip()
		return (
			'<section class="ai-workflow-shell">'
			'<div class="ai-workflow-header">'
			'<div class="ai-workflow-kicker">AI Workflow Result</div>'
			'<h2 class="ai-workflow-title">Final Analyst Output</h2>'
			'<p class="ai-workflow-subtitle">The workflow completed, but the structured valuation payload was unavailable. Showing the narrative output instead.</p>'
			"</div>"
			'<div class="ai-workflow-body">'
			f"{_render_markdown_like(final_text)}"
			"</div>"
			"</section>"
		)

	return (
		'<section class="ai-dashboard-shell">'
		f"{_render_metric_cards(valuation_pick)}"
		'<details class="ai-dashboard-panel ai-dashboard-panel-major ai-dashboard-collapsible" open>'
		'<summary class="ai-dashboard-collapsible-summary">Investment Research Report</summary>'
		f"{_render_research_report(explanation_markdown, report_markdown, source_links)}"
		"</details>"
		'<details class="ai-dashboard-panel ai-dashboard-panel-major ai-dashboard-collapsible" open>'
		'<summary class="ai-dashboard-collapsible-summary">Fair Value Estimation</summary>'
		'<div class="ai-dashboard-estimation-stack">'
		'<section class="ai-dashboard-panel ai-dashboard-panel-inner">'
		'<div class="ai-dashboard-panel-title">1. Why This Model</div>'
		f"{_render_model_section(ticker, company_name, model_selection, parameter_payload, valuation_pick)}"
		"</section>"
		'<section class="ai-dashboard-panel ai-dashboard-panel-inner">'
		'<div class="ai-dashboard-panel-title">2. Parameter Breakdown</div>'
		'<p class="ai-dashboard-panel-copy">Each validated input is shown individually. For year-by-year projections, the values are laid out in a single-row forecast table first, followed by the reason the workflow used that input.</p>'
		f"{_render_assumption_cards(assumptions)}"
		"</section>"
		'<section class="ai-dashboard-panel ai-dashboard-panel-inner">'
		'<div class="ai-dashboard-panel-title">3. Fair Value Vs Current Price</div>'
		f"{_render_comparison_section(valuation_pick, assumptions)}"
		"</section>"
		"</div>"
		"</details>"
		"</section>"
	)
