from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_TO_MODULE = {
	"CashFlowHealthData": "agent.tools.finance_tools",
	"CompanyProfileData": "agent.tools.finance_tools",
	"IncomeStatementData": "agent.tools.finance_tools",
	"ValuationMetricsData": "agent.tools.finance_tools",
	"build_company_snapshot": "agent.tools.finance_tools",
	"build_source_links": "agent.tools.finance_tools",
	"calculate_recommended_value": "agent.tools.calculator_tools",
	"default_parameter_fallback": "agent.tools.calculator_tools",
	"format_cash_flow_health_text": "agent.tools.finance_tools",
	"format_company_profile_text": "agent.tools.finance_tools",
	"format_income_statement_text": "agent.tools.finance_tools",
	"format_valuation_metrics_text": "agent.tools.finance_tools",
	"get_cash_flow_health": "agent.tools.finance_tools",
	"get_cash_flow_health_data": "agent.tools.finance_tools",
	"get_company_profile_data": "agent.tools.finance_tools",
	"get_company_profile_text": "agent.tools.finance_tools",
	"get_filing_source_hints": "agent.tools.sec_tools",
	"get_relevant_filing_section_notes": "agent.tools.sec_tools",
	"get_relevant_filing_sections": "agent.tools.sec_tools",
	"get_income_statement": "agent.tools.finance_tools",
	"get_income_statement_data": "agent.tools.finance_tools",
	"get_valuation_metrics": "agent.tools.finance_tools",
	"get_valuation_metrics_data": "agent.tools.finance_tools",
	"resolve_stock_info": "agent.tools.finance_tools",
	"run_valuation_calculation": "agent.tools.calculator_tools",
	"search_company_market_context": "agent.tools.web_search",
	"search_company_market_context_payload": "agent.tools.web_search",
	"search_company_market_context_results": "agent.tools.web_search",
	"search_web": "agent.tools.web_search",
	"search_web_payload": "agent.tools.web_search",
	"search_web_results": "agent.tools.web_search",
	"search_parameter_research": "agent.tools.web_search",
	"search_parameter_research_payload": "agent.tools.web_search",
	"search_parameter_research_results": "agent.tools.web_search",
	"validate_parameter_payload": "agent.tools.validation_tools",
}


def __getattr__(name: str) -> Any:
	module_name = _EXPORT_TO_MODULE.get(name)
	if module_name is None:
		raise AttributeError(f"module 'agent.tools' has no attribute {name!r}")
	module = import_module(module_name)
	return getattr(module, name)


__all__ = list(_EXPORT_TO_MODULE)
