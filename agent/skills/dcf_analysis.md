# Purpose
Guide the agent in estimating the `DCFAssumptions` object before the DCF model is run.

# What To Estimate
- `projection_years`: choose one explicit horizon supported by the context.
- `revenue_growth_rates`: estimate a year-by-year path from recent growth, scale, cyclicality, and maturity.
- `ebit_margins`: estimate a year-by-year operating margin path from historical margins, operating leverage, and business mix.
- `tax_rates`: estimate a year-by-year effective tax path from reported tax expense and profit mix when available.
- `da_as_pct_revenue`: estimate depreciation and amortization as a percent of revenue from historical capital intensity.
- `capex_as_pct_revenue`: estimate reinvestment needs from capex history, growth needs, and business-model intensity.
- `nwc_as_pct_revenue`: estimate working-capital drag or release from historical trends and operating model.
- `wacc`: estimate a company-appropriate discount rate using business quality, cyclicality, leverage, and equity risk.
- `exit_multiple`: estimate a terminal EBITDA multiple consistent with growth, durability, and maturity.

# What Good Looks Like
- Use the actual company context, not generic market defaults.
- Anchor assumptions to reported history first, then transition toward a realistic forward state.
- Keep assumptions internally consistent:
  faster growth usually requires reinvestment, weak businesses should not get premium terminal assumptions, and margin expansion needs support.
- Match every returned list to `projection_years`.

# What To Avoid
- Do not use canned default values just because a field is hard.
- Do not force growth, margins, or multiples into a normal range unless the evidence supports it.
- Do not mix output interpretation with assumption estimation.
- Do not invent evidence that is not present in the provided context.
- Do not return prose when the task expects structured assumptions only.

# Missing Data Guidance
- If the context is thin, still estimate the assumptions from the available evidence, but stay conservative and internally consistent.
- If a specific driver is weakly supported, infer it from adjacent evidence such as profitability, reinvestment history, leverage, and business maturity.
- If recent data is volatile, prefer a reasonable path over a single noisy period.
