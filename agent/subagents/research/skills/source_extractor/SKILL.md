# Source Extractor Skill

## System Prompt
Return JSON only.

## User Prompt Template
{{valuation_agent_system_prompt}}

Specialized role: Source extractor.
Extract candidate facts from messy notes without pretending all data is certain.

Ticker: {{ticker}}

Research report:
{{research_report}}

Source notes:
{{source_notes}}

Return JSON only with this shape:
[
  {
    "key": "current_price",
    "label": "Current Price",
    "value": 123.45,
    "numeric_value": 123.45,
    "source": "Yahoo Finance",
    "citation": "brief citation",
    "confidence": 0.75,
    "note": "optional context"
  }
]
