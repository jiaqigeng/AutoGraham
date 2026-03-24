from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.tools.sec_tools import (
	build_sec_company_url,
	get_recent_filing_metadata,
	get_relevant_filing_section_notes,
	resolve_company_cik,
)


COMPANY_TICKERS_PAYLOAD = {
	"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}

SUBMISSIONS_PAYLOAD = {
	"filings": {
		"recent": {
			"form": ["8-K", "10-Q", "10-K"],
			"accessionNumber": ["0000000000-00-000001", "0000320193-26-000010", "0000320193-25-000100"],
			"primaryDocument": ["current.htm", "q10.htm", "k10.htm"],
			"filingDate": ["2026-03-01", "2026-02-01", "2025-11-01"],
			"primaryDocDescription": ["Current report", "Quarterly report", "Annual report"],
		}
	}
}

FILING_HTML = """
<html><body>
<h2>Item 1A. Risk Factors</h2>
<p>Demand could weaken in a recession and supply concentration could pressure results.</p>
<h2>Item 1B. Unresolved Staff Comments</h2>
<h2>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</h2>
<p>Management expects margin improvement next year and continued investment in capacity.</p>
<h2>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</h2>
</body></html>
"""

QUARTERLY_FILING_HTML = """
<html><body>
<h2>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</h2>
<p>Near-term demand trends remain favorable and guidance points to stronger revenue in the second half.</p>
<h2>Item 3. Quantitative and Qualitative Disclosures About Market Risk</h2>
</body></html>
"""


class SecToolsTests(unittest.TestCase):
	def test_build_sec_company_url(self) -> None:
		self.assertIn("CIK=AAPL", build_sec_company_url("aapl"))

	def test_resolve_company_cik_uses_sec_company_map(self) -> None:
		with patch("agent.tools.sec_tools._request_json", return_value=COMPANY_TICKERS_PAYLOAD):
			self.assertEqual(resolve_company_cik("AAPL"), "0000320193")

	def test_get_recent_filing_metadata_selects_latest_requested_forms(self) -> None:
		with patch("agent.tools.sec_tools.resolve_company_cik", return_value="0000320193"), patch(
			"agent.tools.sec_tools._request_json",
			return_value=SUBMISSIONS_PAYLOAD,
		):
			metadata = get_recent_filing_metadata("AAPL")

		self.assertEqual(len(metadata), 2)
		self.assertEqual(metadata[0]["form"], "10-Q")
		self.assertEqual(metadata[1]["form"], "10-K")
		self.assertIn("/320193/000032019326000010/q10.htm", metadata[0]["document_url"])

	def test_get_relevant_filing_section_notes_extracts_sections_not_in_yahoo(self) -> None:
		def fake_request_text(url: str) -> str:
			if url.endswith("q10.htm"):
				return QUARTERLY_FILING_HTML
			return FILING_HTML

		with patch(
			"agent.tools.sec_tools.get_recent_filing_metadata",
			return_value=[
				{"form": "10-Q", "document_url": "https://example.com/q10.htm", "filing_date": "2026-02-01"},
				{"form": "10-K", "document_url": "https://example.com/k10.htm", "filing_date": "2025-11-01"},
			],
		), patch("agent.tools.sec_tools._request_text", side_effect=fake_request_text):
			notes = get_relevant_filing_section_notes("AAPL", max_sections=3)

		self.assertEqual(len(notes), 3)
		self.assertEqual(notes[0]["form_type"], "10-Q")
		self.assertIn("Management Discussion and Analysis", notes[0]["title"])
		self.assertIn("guidance points to stronger revenue", notes[0]["snippet"])
		self.assertEqual(notes[1]["form_type"], "10-K")
		self.assertIn("Risk Factors", notes[1]["title"])
		self.assertIn("Demand could weaken", notes[1]["snippet"])


if __name__ == "__main__":
	unittest.main()
