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
		cells = [cell.strip() for cell in stripped.split("|")]
		rows.append(cells)

	if len(rows) < 2:
		return ""

	headers = rows[0]
	body_rows = rows[2:] if len(rows) > 2 else []
	head_html = "".join(f"<th>{_format_inline(cell)}</th>" for cell in headers)
	body_html = "".join(
		"<tr>" + "".join(f"<td>{_format_inline(cell)}</td>" for cell in row) + "</tr>"
		for row in body_rows
	)
	return (
		'<div class="ai-report-table-wrap">'
		'<table class="ai-report-table">'
		f"<thead><tr>{head_html}</tr></thead>"
		f"<tbody>{body_html}</tbody>"
		"</table>"
		"</div>"
	)


def _render_list(lines: list[str], ordered: bool) -> str:
	tag = "ol" if ordered else "ul"
	items: list[str] = []
	pattern = r"^\d+[.)]\s+" if ordered else r"^[-*]\s+"
	for line in lines:
		content = re.sub(pattern, "", line.strip(), count=1)
		items.append(f"<li>{_format_inline(content)}</li>")
	return f'<{tag} class="ai-report-list">' + "".join(items) + f"</{tag}>"


def _render_paragraph(lines: list[str]) -> str:
	content = " ".join(line.strip() for line in lines if line.strip())
	if not content:
		return ""
	return f'<p class="ai-report-paragraph">{_format_inline(content)}</p>'


def _render_block(block: str) -> str:
	lines = [line.rstrip() for line in block.splitlines() if line.strip()]
	if not lines:
		return ""
	if all(re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", line) for line in lines):
		return ""
	if _is_table_block(lines):
		return _render_table(lines)
	if all(re.match(r"^[-*]\s+", line.strip()) for line in lines):
		return _render_list(lines, ordered=False)
	if all(re.match(r"^\d+[.)]\s+", line.strip()) for line in lines):
		return _render_list(lines, ordered=True)
	return _render_paragraph(lines)


def _render_body(body: str) -> str:
	blocks = re.split(r"\n\s*\n", body.strip())
	return "".join(_render_block(block) for block in blocks if block.strip())


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

		if current_title is None:
			continue
		current_lines.append(line)

	if current_title is not None:
		sections.append((current_title, "\n".join(current_lines).strip()))

	return sections


def render_ai_report(report_markdown: str) -> str:
	cleaned_report, peers = _extract_peers(report_markdown)
	sections = _parse_sections(cleaned_report)

	if not sections:
		fallback_body = _render_body(cleaned_report)
		return (
			'<section class="ai-report-shell">'
			'<div class="ai-report-header">'
			'<div class="ai-report-kicker">AI Analyst Memo</div>'
			'<h2 class="ai-report-title">Investment Research Report</h2>'
			'</div>'
			f'<div class="ai-report-fallback">{fallback_body}</div>'
			'</section>'
		)

	peer_html = "".join(f'<span class="ai-report-chip">{html.escape(peer)}</span>' for peer in peers)
	section_html = ""
	for index, (title, body) in enumerate(sections, start=1):
		section_html += (
			'<article class="ai-report-section">'
			f'<div class="ai-report-section-index">0{index}</div>'
			'<div class="ai-report-section-body">'
			f'<h3 class="ai-report-section-title">{html.escape(title)}</h3>'
			f'{_render_body(body)}'
			'</div>'
			'</article>'
		)

	peer_block = ""
	if peer_html:
		peer_block = (
			'<div class="ai-report-peer-row">'
			'<div class="ai-report-peer-label">Peers Referenced</div>'
			f'<div class="ai-report-peer-chips">{peer_html}</div>'
			'</div>'
		)

	return (
		'<section class="ai-report-shell">'
		'<div class="ai-report-header">'
		'<div class="ai-report-kicker">AI Analyst Memo</div>'
		'<h2 class="ai-report-title">Investment Research Report</h2>'
		'<p class="ai-report-subtitle">'
		'Competitive framing, valuation context, and capital allocation analysis in a cleaner editorial format.'
		'</p>'
		f'{peer_block}'
		'</div>'
		f'<div class="ai-report-grid">{section_html}</div>'
		'</section>'
	)