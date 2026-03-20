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
		"memo_markdown": final_state.research_report,
		"valuation_pick": final_state.valuation_result,
		"fetched_facts": final_state.fetched_facts,
		"assumptions": final_state.assumptions,
		"explanation_markdown": final_state.explanation,
		"source_links": final_state.source_links,
		"confidence": final_state.confidence,
		"errors": final_state.errors,
	}
