from __future__ import annotations

import html
import re


SECTION_TITLES = [
	"Business Strategy & Outlook",
	"Economic Moat",
	"Bull Case",
	"Bear Case",
	"Fair Value & Valuation",
	"Risk & Uncertainty",
	"Capital Allocation",
	"Conclusion",
]


def _format_inline(text: str) -> str:
	escaped = html.escape(text.strip())
	escaped = re.sub(r"`([^`]+)`", r'<code class="ai-report-inline-code">\1</code>', escaped)
	escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
	escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
	return escaped


def _is_table_block(lines: list[str]) -> bool:
	if len(lines) < 2:
		return False
	if not all("|" in line for line in lines[:2]):
		return False
	separator = lines[1].replace("|", "").replace(":", "").replace("-", "").strip()
	return separator == ""


def _render_table(lines: list[str]) -> str:
	rows: list[list[str]] = []
	for line in lines:
		stripped = line.strip().strip("|")
		if not stripped:
			continue
		rows.append([cell.strip() for cell in stripped.split("|")])
	if len(rows) < 2:
		return ""
	headers = rows[0]
	body_rows = rows[2:] if len(rows) > 2 else []
	head_html = "".join(f"<th>{_format_inline(cell)}</th>" for cell in headers)
	body_html = "".join("<tr>" + "".join(f"<td>{_format_inline(cell)}</td>" for cell in row) + "</tr>" for row in body_rows)
	return f'<div class="ai-report-table-wrap"><table class="ai-report-table"><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def _render_list(lines: list[str], ordered: bool) -> str:
	tag = "ol" if ordered else "ul"
	pattern = r"^\d+[.)]\s+" if ordered else r"^[-*]\s+"
	items = [f"<li>{_format_inline(re.sub(pattern, '', line.strip(), count=1))}</li>" for line in lines]
	return f'<{tag} class="ai-report-list">' + "".join(items) + f"</{tag}>"


def _render_paragraph(lines: list[str]) -> str:
	content = " ".join(line.strip() for line in lines if line.strip())
	return f'<p class="ai-report-paragraph">{_format_inline(content)}</p>' if content else ""


def _render_block(block: str) -> str:
	lines = [line.rstrip() for line in block.splitlines() if line.strip()]
	if not lines:
		return ""
	if _is_table_block(lines):
		return _render_table(lines)
	if all(re.match(r"^[-*]\s+", line.strip()) for line in lines):
		return _render_list(lines, ordered=False)
	if all(re.match(r"^\d+[.)]\s+", line.strip()) for line in lines):
		return _render_list(lines, ordered=True)
	return _render_paragraph(lines)


def _render_body(body: str) -> str:
	return "".join(_render_block(block) for block in re.split(r"\n\s*\n", body.strip()) if block.strip())


def _extract_peers(report_markdown: str) -> tuple[str, list[str]]:
	match = re.search(r"(?im)^\s*PEERS:\s*(.+?)\s*$", report_markdown)
	if not match:
		return report_markdown.strip(), []
	peers = [peer.strip() for peer in match.group(1).split(",") if peer.strip()]
	cleaned = re.sub(r"(?im)^\s*PEERS:\s*.+?\s*$", "", report_markdown).strip()
	return cleaned, peers


def _parse_sections(report_markdown: str) -> list[tuple[str, str]]:
	sections: list[tuple[str, str]] = []
	current_title: str | None = None
	current_lines: list[str] = []
	for raw_line in report_markdown.splitlines():
		line = raw_line.rstrip()
		matched_title = None
		remainder = ""
		for title in SECTION_TITLES:
			pattern = rf"^\s*(?:#+\s*)?(?:\d+[.)]\s*)?(?:\*\*)?{re.escape(title)}(?:\*\*)?(?::)?\s*(.*)$"
			match = re.match(pattern, line, flags=re.IGNORECASE)
			if match:
				matched_title = title
				remainder = match.group(1).strip()
				break
		if matched_title:
			if current_title is not None:
				sections.append((current_title, "\n".join(current_lines).strip()))
			current_title = matched_title
			current_lines = [remainder] if remainder else []
			continue
		if current_title is not None:
			current_lines.append(line)
	if current_title is not None:
		sections.append((current_title, "\n".join(current_lines).strip()))
	return sections


def _render_explanation_block(explanation_markdown: str | None) -> str:
	if not explanation_markdown:
		return ""
	return (
		'<article class="ai-report-section">'
		'<div class="ai-report-section-index">AI</div>'
		'<div class="ai-report-section-body">'
		'<h3 class="ai-report-section-title">Valuation Explanation</h3>'
		f'{_render_body(explanation_markdown)}'
		'</div>'
		'</article>'
	)


def render_ai_report(
	report_markdown: str,
	valuation_pick: dict[str, object] | None = None,
	explanation_markdown: str | None = None,
) -> str:
	cleaned_report, peers = _extract_peers(report_markdown)
	sections = _parse_sections(cleaned_report)
	peer_html = "".join(f'<span class="ai-report-chip">{html.escape(peer)}</span>' for peer in peers)
	peer_block = (
		'<div class="ai-report-peer-row">'
		'<div class="ai-report-peer-label">Peers Referenced</div>'
		f'<div class="ai-report-peer-chips">{peer_html}</div>'
		'</div>'
	) if peer_html else ""
	valuation_block = ""
	if valuation_pick:
		valuation_block = (
			'<article class="ai-report-section">'
			'<div class="ai-report-section-index">00</div>'
			'<div class="ai-report-section-body">'
			'<h3 class="ai-report-section-title">Structured Valuation Output</h3>'
			f"<p class='ai-report-paragraph'><strong>Model:</strong> {html.escape(str(valuation_pick.get('model_name') or valuation_pick.get('selected_model') or 'N/A'))}</p>"
			f"<p class='ai-report-paragraph'><strong>Growth Stage:</strong> {html.escape(str(valuation_pick.get('growth_stage') or 'N/A'))}</p>"
			f"<p class='ai-report-paragraph'><strong>Fair Value / Share:</strong> {html.escape(str(valuation_pick.get('fair_value_per_share') or 'N/A'))}</p>"
			f"<p class='ai-report-paragraph'><strong>Current Price:</strong> {html.escape(str(valuation_pick.get('current_price') or 'N/A'))}</p>"
			'</div>'
			'</article>'
		)
	section_html = "".join(
		'<article class="ai-report-section">'
		f'<div class="ai-report-section-index">{index:02d}</div>'
		'<div class="ai-report-section-body">'
		f'<h3 class="ai-report-section-title">{html.escape(title)}</h3>'
		f'{_render_body(body)}'
		'</div>'
		'</article>'
		for index, (title, body) in enumerate(sections, start=1)
	)
	fallback_html = _render_body(cleaned_report) if not sections else ""
	return (
		'<section class="ai-report-shell">'
		'<div class="ai-report-header">'
		'<div class="ai-report-kicker">AI Analyst Memo</div>'
		'<h2 class="ai-report-title">Investment Research Report</h2>'
		'<p class="ai-report-subtitle">Competitive framing, valuation context, and deterministic valuation output in one place.</p>'
		f'{peer_block}'
		'</div>'
		'<div class="ai-report-grid">'
		f'{valuation_block}'
		f'{_render_explanation_block(explanation_markdown)}'
		f'{section_html}'
		f'{fallback_html}'
		'</div>'
		'</section>'
	)
