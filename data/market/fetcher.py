from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import yfinance as yf


INFO_FIELDS: dict[str, list[str]] = {
    "company_name": ["longName", "shortName", "displayName"],
    "sector": ["sector"],
    "industry": ["industry"],
    "exchange": ["exchange", "fullExchangeName"],
    "currency": ["currency", "financialCurrency"],
}

SNAPSHOT_FIELDS: dict[str, list[str]] = {
    "current_price": ["currentPrice", "regularMarketPrice", "lastPrice"],
    "market_cap": ["marketCap"],
    "enterprise_value": ["enterpriseValue"],
    "shares_outstanding": ["sharesOutstanding"],
    "beta": ["beta"],
    "pe_ratio": ["trailingPE", "forwardPE"],
    "pb_ratio": ["priceToBook"],
    "ps_ratio": ["priceToSalesTrailing12Months"],
    "dividend_yield": ["dividendYield"],
    "fifty_two_week_high": ["fiftyTwoWeekHigh", "yearHigh"],
    "fifty_two_week_low": ["fiftyTwoWeekLow", "yearLow"],
}

INCOME_ROW_MAP: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "gross_profit": ["Gross Profit"],
    "ebit": ["EBIT", "Ebit", "Normalized EBIT"],
    "operating_income": ["Operating Income", "Operating Income Or Loss"],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income Including Noncontrolling Interests",
    ],
    "depreciation_amortization": [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
        "Reconciled Depreciation",
        "Depreciation",
    ],
    "interest_expense": [
        "Interest Expense",
        "Interest Expense Non Operating",
        "Net Interest Income",
    ],
    "income_tax_expense": ["Tax Provision", "Income Tax Expense"],
}

CASHFLOW_ROW_MAP: dict[str, list[str]] = {
    "depreciation_amortization": [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
        "Depreciation",
    ],
    "dividends_paid": [
        "Cash Dividends Paid",
        "Common Stock Dividend Paid",
        "Dividends Paid",
    ],
    "capex": [
        "Capital Expenditure",
        "Capital Expenditure Reported",
        "Purchase Of PPE",
    ],
    "change_in_nwc": [
        "Change In Working Capital",
        "Change In Other Working Capital",
        "Changes In Working Capital",
    ],
    "operating_cash_flow": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Net Cash Provided By Operating Activities",
    ],
    "free_cash_flow": ["Free Cash Flow"],
}

BALANCE_SHEET_ROW_MAP: dict[str, list[str]] = {
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash",
    ],
    "total_debt": ["Total Debt"],
    "shareholders_equity": [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
    ],
    "shares_outstanding": [
        "Ordinary Shares Number",
        "Share Issued",
        "Common Stock Shares Outstanding",
    ],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
}


def _get_ticker_symbol(ticker: str) -> str:
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("ticker must be a non-empty string.")
    return symbol


def _get_ticker(ticker: str) -> yf.Ticker:
    return yf.Ticker(_get_ticker_symbol(ticker))


def _safe_get_info(ticker_obj: yf.Ticker) -> dict[str, Any]:
    try:
        info = ticker_obj.info
    except Exception:
        return {}
    return info if isinstance(info, dict) else {}


def _safe_get_fast_info(ticker_obj: yf.Ticker) -> dict[str, Any]:
    try:
        fast_info = ticker_obj.fast_info
    except Exception:
        return {}

    if hasattr(fast_info, "items"):
        try:
            return dict(fast_info.items())
        except Exception:
            pass

    if isinstance(fast_info, dict):
        return fast_info

    return {}


def _pick_first(source: dict[str, Any], candidates: list[str]) -> Any:
    for key in candidates:
        value = source.get(key)
        if value is not None and not pd.isna(value):
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date_like(value: Any) -> date | datetime | None:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date()
        return value

    if isinstance(value, date):
        return value

    if isinstance(value, pd.Timestamp):
        python_value = value.to_pydatetime()
        if python_value.time() == datetime.min.time():
            return python_value.date()
        return python_value

    return None


def _normalize_label(label: str) -> str:
    normalized = label.lower().replace("&", "and")
    return "".join(char for char in normalized if char.isalnum())


def _get_statement_frame(ticker_obj: yf.Ticker, attribute_names: list[str]) -> pd.DataFrame:
    for attribute_name in attribute_names:
        try:
            value = getattr(ticker_obj, attribute_name)
            frame = value() if callable(value) else value
        except Exception:
            continue

        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame

    return pd.DataFrame()


def _extract_statement_values(
    frame: pd.DataFrame,
    row_map: dict[str, list[str]],
) -> dict[date, dict[str, float | None]]:
    if frame.empty:
        return {}

    label_lookup = {_normalize_label(str(label)): label for label in frame.index}
    extracted: dict[date, dict[str, float | None]] = {}

    for normalized_key, candidates in row_map.items():
        matched_label = None
        for candidate in candidates:
            matched_label = label_lookup.get(_normalize_label(candidate))
            if matched_label is not None:
                break

        if matched_label is None:
            continue

        series = frame.loc[matched_label]
        for column, value in series.items():
            period_end = _to_date_like(column)
            if not isinstance(period_end, date):
                continue

            extracted.setdefault(period_end, {})[normalized_key] = _to_float(value)

    return extracted


def _merge_statement_data(
    target: dict[date, dict[str, Any]],
    source: dict[date, dict[str, float | None]],
) -> None:
    for period_end, values in source.items():
        target.setdefault(period_end, {})
        target[period_end].update(values)


def _build_period_record(period_end: date, period_type: str, values: dict[str, Any]) -> dict[str, Any]:
    return {
        "period_end": period_end,
        "period_type": period_type,
        "fiscal_year": period_end.year,
        "fiscal_quarter": None if period_type == "annual" else ((period_end.month - 1) // 3) + 1,
        "revenue": values.get("revenue"),
        "gross_profit": values.get("gross_profit"),
        "ebit": values.get("ebit"),
        "operating_income": values.get("operating_income"),
        "net_income": values.get("net_income"),
        "depreciation_amortization": values.get("depreciation_amortization"),
        "interest_expense": values.get("interest_expense"),
        "income_tax_expense": values.get("income_tax_expense"),
        "dividends_paid": values.get("dividends_paid"),
        "capex": values.get("capex"),
        "change_in_nwc": values.get("change_in_nwc"),
        "operating_cash_flow": values.get("operating_cash_flow"),
        "free_cash_flow": values.get("free_cash_flow"),
        "cash": values.get("cash"),
        "total_debt": values.get("total_debt"),
        "shareholders_equity": values.get("shareholders_equity"),
        "shares_outstanding": values.get("shares_outstanding"),
        "current_assets": values.get("current_assets"),
        "current_liabilities": values.get("current_liabilities"),
    }


def fetch_company_info(ticker: str) -> dict[str, Any]:
    ticker_obj = _get_ticker(ticker)
    info = _safe_get_info(ticker_obj)
    fast_info = _safe_get_fast_info(ticker_obj)

    result: dict[str, Any] = {"ticker": _get_ticker_symbol(ticker)}
    for field_name, candidates in INFO_FIELDS.items():
        result[field_name] = _pick_first(info, candidates)
        if result[field_name] is None:
            result[field_name] = _pick_first(fast_info, candidates)

    return result


def fetch_market_snapshot(ticker: str) -> dict[str, Any]:
    ticker_obj = _get_ticker(ticker)
    info = _safe_get_info(ticker_obj)
    fast_info = _safe_get_fast_info(ticker_obj)

    result: dict[str, Any] = {}
    for field_name, candidates in SNAPSHOT_FIELDS.items():
        value = _pick_first(info, candidates)
        if value is None:
            value = _pick_first(fast_info, candidates)
        result[field_name] = _to_float(value)

    return result


def fetch_price_history(
    ticker: str,
    period: str = "5y",
    interval: str = "1d",
) -> list[dict[str, Any]]:
    ticker_obj = _get_ticker(ticker)

    try:
        history = ticker_obj.history(period=period, interval=interval, auto_adjust=False)
    except Exception:
        return []

    if history.empty:
        return []

    history = history.reset_index()
    date_column = "Date" if "Date" in history.columns else "Datetime"

    records: list[dict[str, Any]] = []
    for _, row in history.iterrows():
        records.append(
            {
                "date": _to_date_like(row.get(date_column)),
                "open": _to_float(row.get("Open")),
                "high": _to_float(row.get("High")),
                "low": _to_float(row.get("Low")),
                "close": _to_float(row.get("Close")),
                "volume": _to_float(row.get("Volume")),
            }
        )

    return records


def fetch_financial_periods(
    ticker: str,
    period_type: str = "annual",
) -> list[dict[str, Any]]:
    normalized_period_type = period_type.strip().lower()
    if normalized_period_type not in {"annual", "quarterly"}:
        raise ValueError("period_type must be either 'annual' or 'quarterly'.")

    ticker_obj = _get_ticker(ticker)

    if normalized_period_type == "annual":
        income_frame = _get_statement_frame(ticker_obj, ["income_stmt", "financials"])
        balance_frame = _get_statement_frame(ticker_obj, ["balance_sheet"])
        cashflow_frame = _get_statement_frame(ticker_obj, ["cashflow", "cash_flow"])
    else:
        income_frame = _get_statement_frame(
            ticker_obj,
            ["quarterly_income_stmt", "quarterly_financials"],
        )
        balance_frame = _get_statement_frame(ticker_obj, ["quarterly_balance_sheet"])
        cashflow_frame = _get_statement_frame(
            ticker_obj,
            ["quarterly_cashflow", "quarterly_cash_flow"],
        )

    period_values: dict[date, dict[str, Any]] = {}
    _merge_statement_data(period_values, _extract_statement_values(income_frame, INCOME_ROW_MAP))
    _merge_statement_data(
        period_values,
        _extract_statement_values(balance_frame, BALANCE_SHEET_ROW_MAP),
    )
    _merge_statement_data(
        period_values,
        _extract_statement_values(cashflow_frame, CASHFLOW_ROW_MAP),
    )

    records = [
        _build_period_record(period_end, normalized_period_type, values)
        for period_end, values in sorted(period_values.items(), reverse=True)
    ]
    return records
