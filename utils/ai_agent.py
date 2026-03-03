"""
utils/ai_agent.py
-----------------
AI-powered analysis helpers for AutoGraham.

Provides:
  - Economic Moat scoring via LLM
  - Earnings summary (Tailwinds / Headwinds)
  - Bull Case vs. Bear Case generation
"""

import os
import json
from openai import OpenAI


def _get_client() -> OpenAI:
    """Return an OpenAI client using the key from the environment."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    return OpenAI(api_key=api_key)


def _safe_json_parse(text: str, fallback: dict) -> dict:
    """Attempt to parse JSON from LLM output, returning fallback on failure."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) > 1:
            # Remove opening fence; remove closing fence if present
            text = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return fallback


def analyze_economic_moat(company_name: str, sector: str, description: str) -> dict:
    """
    Ask the LLM to score a company's economic moat across five dimensions.

    Returns a dict mapping dimension → score (1–5):
        {
            "Network Effect": 3,
            "Cost Advantage": 4,
            "Intangible Assets": 3,
            "Switching Costs": 4,
            "Efficient Scale": 2
        }
    Returns default scores of 1 on any error.
    """
    dimensions = [
        "Network Effect",
        "Cost Advantage",
        "Intangible Assets",
        "Switching Costs",
        "Efficient Scale",
    ]
    default = {d: 1 for d in dimensions}

    prompt = (
        f"You are a value-investing analyst trained in Benjamin Graham's principles.\n\n"
        f"Company: {company_name}\n"
        f"Sector: {sector}\n"
        f"Business description: {description}\n\n"
        f"Score the company's economic moat on each of the following dimensions "
        f"on a scale from 1 (none) to 5 (very strong):\n"
        f"{', '.join(dimensions)}\n\n"
        f"Return ONLY a valid JSON object with exactly these keys and integer values 1-5. "
        f"No extra text, no markdown."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        raw = response.choices[0].message.content or ""
        result = _safe_json_parse(raw, default)
        # Ensure all keys exist and values are ints 1-5
        for d in dimensions:
            val = result.get(d, 1)
            result[d] = max(1, min(5, int(val)))
        return result
    except Exception:
        return default


def analyze_earnings(company_name: str, sector: str, description: str) -> dict:
    """
    Ask the LLM for a structured earnings analysis.

    Returns a dict:
        {
            "tailwinds": ["...", "..."],
            "headwinds": ["...", "..."],
            "bull_case": "...",
            "bear_case": "..."
        }
    Returns placeholder strings on any error.
    """
    default = {
        "tailwinds": ["Data unavailable"],
        "headwinds": ["Data unavailable"],
        "bull_case": "Could not generate analysis. Please check your API key.",
        "bear_case": "Could not generate analysis. Please check your API key.",
    }

    prompt = (
        f"You are a senior equity research analyst.\n\n"
        f"Company: {company_name}\n"
        f"Sector: {sector}\n"
        f"Business description: {description}\n\n"
        f"Provide a structured analysis with four sections:\n"
        f"1. tailwinds: a list of 3 short bullet points about recent positive catalysts.\n"
        f"2. headwinds: a list of 3 short bullet points about recent risks or challenges.\n"
        f"3. bull_case: a 2-3 sentence bullish investment thesis.\n"
        f"4. bear_case: a 2-3 sentence devil's advocate bearish case.\n\n"
        f"Return ONLY a valid JSON object with keys 'tailwinds' (list), 'headwinds' (list), "
        f"'bull_case' (string), 'bear_case' (string). No extra text, no markdown."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )
        raw = response.choices[0].message.content or ""
        result = _safe_json_parse(raw, default)
        # Validate expected keys
        for key in ("tailwinds", "headwinds", "bull_case", "bear_case"):
            if key not in result:
                result[key] = default[key]
        return result
    except Exception:
        return default
