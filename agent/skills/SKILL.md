# Agent Skills Pack

This folder contains the markdown guidance files that shape the agent's writing and valuation behavior.

## How The App Uses These Files
- The application loads these files by filename from `agent/service.py`.
- Keep the existing filenames stable unless the loader is updated too.
- These files are prompt components, not user-facing documentation.

## Workflow
1. Build context from local market and financial data.
2. Produce the core analysis sections:
   `macro_industry_analysis`, `qualitative_analysis`, and `quantitative_analysis`.
3. Select the most appropriate valuation model.
4. Estimate model inputs where needed.
5. Interpret the computed valuation result in `valuation_analysis`.
6. Close with limitations and next-step guidance in `conclusion`.

## Current Files
- `macro_industry_analysis.md`: external drivers, industry structure, and implications.
- `qualitative_analysis.md`: business quality and risk framing under limited evidence.
- `quantitative_analysis.md`: operating, cash-flow, balance-sheet, and capital-allocation trends.
- `dcf_analysis.md`: estimation guidance for DCF assumptions.
- `ddm_analysis.md`: fit and interpretation guidance for dividend discount analysis.
- `rim_analysis.md`: fit and interpretation guidance for residual income analysis.
- `valuation_analysis.md`: interpretation guidance for whichever valuation result is available.
- `conclusion.md`: synthesis, limitations, and next steps.

## Writing Principles Across The Pack
- Use only the evidence provided by local tools and computed outputs.
- Prefer selective judgment over exhaustive description.
- Explain why the evidence matters to revenue, margins, risk, or valuation.
- Be explicit about missing data and confidence limits.
- Avoid investment-advice language or false precision.

## Editing Guidelines
- Keep instructions specific enough to steer model behavior.
- Avoid redundant wording that is already enforced elsewhere in `agent/service.py`.
- When the agent lacks transcripts, filings, or other primary sources, bias toward careful and provisional language.
