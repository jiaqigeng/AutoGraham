from __future__ import annotations

from typing import Any

from agent import AgentRunState, run_agent_graph


def run_ai_valuation(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	state = AgentRunState(
		ticker=target_ticker.strip().upper(),
		model_name=model_name,
		analysis_focus=analysis_focus,
		stock_data=stock_data,
	)
	final_state = run_agent_graph(state)
	return {
		"ticker": final_state.ticker,
		"company_name": final_state.company_name,
		"memo_markdown": final_state.research_report,
		"model_selection": dict(final_state.metadata.get("model_selection") or {}),
		"parameter_payload": final_state.parameter_payload,
		"valuation_pick": final_state.valuation_result,
		"fetched_facts": final_state.fetched_facts,
		"assumptions": final_state.assumptions,
		"explanation_markdown": final_state.explanation,
		"source_links": final_state.source_links,
		"confidence": final_state.confidence,
		"errors": final_state.errors,
	}
