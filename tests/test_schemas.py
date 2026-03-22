from __future__ import annotations

import unittest

from agent.schemas import DCFSchema, DDMSchema, ModelRecommendation, ParameterPayload, RIMSchema


class SchemaTests(unittest.TestCase):
	def test_model_recommendation_schema(self) -> None:
		model = ModelRecommendation(
			selected_model="DCF",
			selected_variant=None,
			preferred_calculation_model="FCFF",
			model_reason="Best fit",
		)
		self.assertEqual(model.selected_model, "DCF")

	def test_parameter_payload_schema(self) -> None:
		payload = ParameterPayload(
			selected_model="DCF",
			selected_variant=None,
			calculation_model="FCFF",
			parameter_reason="Okay",
			fetched_facts=[],
			assumptions={"wacc": 0.09},
			assumption_reasons=[],
		)
		self.assertEqual(payload.assumptions["wacc"], 0.09)

	def test_model_specific_schemas(self) -> None:
		self.assertEqual(DCFSchema(wacc=0.09).wacc, 0.09)
		self.assertEqual(DDMSchema(required_return=0.10).required_return, 0.10)
		self.assertEqual(RIMSchema(cost_of_equity=0.11).cost_of_equity, 0.11)


if __name__ == "__main__":
	unittest.main()
