from __future__ import annotations

import unittest

from valuation.common import margin_of_safety


class MarginOfSafetyTests(unittest.TestCase):
	def test_margin_of_safety_uses_current_price_denominator(self) -> None:
		self.assertAlmostEqual(margin_of_safety(120.0, 100.0), 20.0, places=6)

	def test_margin_of_safety_can_be_negative(self) -> None:
		self.assertAlmostEqual(margin_of_safety(80.0, 100.0), -20.0, places=6)

	def test_margin_of_safety_returns_none_for_invalid_prices(self) -> None:
		self.assertIsNone(margin_of_safety(0.0, 100.0))
		self.assertIsNone(margin_of_safety(100.0, 0.0))


if __name__ == "__main__":
	unittest.main()
